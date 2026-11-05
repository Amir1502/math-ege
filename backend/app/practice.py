import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.models import AssessmentRecord
from app.content import ContentBundle, Task
from app.editor.repository import exclusions
from app.errors import ApiError
from app.generators import RUNTIME_FAMILIES
from app.instances import Snapshot, instance_key, mark_instances, recent_exposure
from app.issuance import generate_candidates, historical_repeat_candidate
from app.models import Guest, LearningSessionRecord
from app.schemas import CreateSessionRequest

if TYPE_CHECKING:
    from app.services import LearningService


def _matches_filters(task: Task, request: CreateSessionRequest) -> bool:
    return (
        task.slot in request.slots
        and (not request.family_ids or task.family_id in request.family_ids)
        and (not request.skill_ids or bool(set(task.skill_ids) & set(request.skill_ids)))
        and (request.difficulty is None or task.difficulty == request.difficulty)
    )


def _owned_repeat_snapshot(db: Session, owners: list[str], task_id: str) -> Snapshot | None:
    for model in (LearningSessionRecord, AssessmentRecord):
        query = select(model).where(model.guest_id.in_(owners)).order_by(
            model.created_at.desc(), model.id.desc(),
        )
        if model is AssessmentRecord:
            query = query.where(
                model.status == "completed", model.released_at.is_not(None),
                model.server_result.is_not(None),
            )
        for record in db.scalars(query):
            if model is AssessmentRecord and (
                not isinstance(record.server_result, dict)
                or record.server_result.get("source") != "server"
            ):
                continue
            for snapshot in record.tasks_snapshot:
                if snapshot.get("id") == task_id:
                    return snapshot
    return None


def select_tasks(
    learning: "LearningService", db: Session, guest: Guest, request: CreateSessionRequest,
    key: str | None, bundle: ContentBundle, *, exclude: frozenset[str] = frozenset(),
    exclude_tasks: tuple[Snapshot, ...] = (),
) -> tuple[list[Task], str | None]:
    slots = {slot.number: slot for slot in bundle.profile.slots}
    if not set(request.slots) <= slots.keys():
        raise ApiError(422, "invalid_slots", "Позиция отсутствует в текущем профиле.")
    skills = {skill.id for number in request.slots for skill in slots[number].skills}
    families = {task.family_id for task in bundle.tasks if task.slot in request.slots}
    families.update(family.id for family in RUNTIME_FAMILIES if family.slot in request.slots)
    if not set(request.skill_ids) <= skills or not set(request.family_ids) <= families:
        raise ApiError(
            422, "invalid_filters", "Подтема или семейство не входят в выбранные позиции."
        )
    available = bundle.available_tasks(allow_demo_content=learning.settings.allow_demo_content)
    excluded = exclusions(db)
    candidates = [
        task for task in available if _matches_filters(task, request)
        and task.id not in exclude
        and (task.id, task.revision) not in excluded
    ]
    owners = learning.owner_ids(db, guest)
    now = learning.clock()
    if request.repeat_task_id:
        selected = [task for task in candidates if task.id == request.repeat_task_id]
        snapshot = _owned_repeat_snapshot(db, owners, request.repeat_task_id)
        if snapshot is not None and not selected and request.repeat_task_id not in exclude:
            try:
                historical = Task.model_validate(snapshot)
            except ValueError:
                historical = None
            if historical is not None and _matches_filters(historical, request) and (
                historical.id, historical.revision,
            ) not in excluded:
                repeated = historical_repeat_candidate(learning, db, historical, bundle, now=now)
                if repeated is not None:
                    selected = [repeated]
        if snapshot is None or not selected:
            raise ApiError(404, "task_unavailable", "Задача для явного повтора недоступна.")
        return selected, "Явный повтор знакомого экземпляра, а не новое независимое достижение."
    exposure = recent_exposure(
        db, owners, bundle.tasks, now, exclude=exclude, exclude_tasks=exclude_tasks,
    )
    signatures = set(exposure.keys)
    eligible = []
    for task in candidates:
        signature = instance_key(task)
        if task.id in exposure.ids or signature in signatures:
            continue
        eligible.append(task)
        signatures.add(signature)

    def choose(pool: list[Task]) -> tuple[list[Task], str | None]:
        if request.selection == "mixed":
            from app.learning.selection import selection_details

            choice = selection_details(
                db, guest, ContentBundle(bundle.profile, bundle.lessons, tuple(pool)),
                request, now, key or "", policy=learning.extras.policy,
            )
            return list(choice.tasks), choice.notice
        selected = _balanced(pool, request, guest.id, key)
        notice = None if len(selected) == request.length else (
            f"В банке доступно {len(selected)} из {request.length} задач. "
            "Выданные за 30 дней экземпляры исключены; скрытых повторов нет."
        )
        return selected, notice

    selected, notice = choose(eligible)
    if len(selected) < request.length:
        generated, generation_notice = generate_candidates(
            learning, db, guest, request, key, bundle, limit=request.length - len(selected),
            exclude=exclude, exclude_tasks=(*exclude_tasks, *eligible), now=now,
        )
        if generated:
            selected, notice = choose([*eligible, *generated])
        if len(selected) < request.length and generation_notice:
            notice = f"{notice} {generation_notice}" if notice else generation_notice
    if not selected:
        if not available and not learning.settings.allow_demo_content:
            raise ApiError(
                503, "demo_content_disabled",
                "Нет опубликованного проверенного банка. Демонстрационные материалы выключены.",
            )
        raise ApiError(
            409, "bank_exhausted",
            "Нет новых подходящих экземпляров: выданные за 30 дней исключены. "
            "Измените фильтры или выберите явный повтор из истории.",
        )
    return selected, notice


def _balanced(
    candidates: list[Task], request: CreateSessionRequest, owner_id: str, key: str | None,
) -> list[Task]:
    groups = {slot: [task for task in candidates if task.slot == slot] for slot in request.slots}
    for group in groups.values():
        group.sort(key=lambda task: hashlib.sha256(f"{owner_id}:{key}:{task.id}".encode()).digest())
    selected = []
    while len(selected) < request.length and any(groups.values()):
        for slot in request.slots:
            if groups[slot] and len(selected) < request.length:
                selected.append(groups[slot].pop())
    return selected


def mark_seen(learning: "LearningService", db: Session, owner_id: str, tasks: list[Task]) -> None:
    mark_instances(db, owner_id, tasks, learning.clock())
