"""Editorial lifecycle, optimistic revisions, atomic import and publication."""

import copy
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.authorization import authorize_staff
from app.content import ContentError, Task, public_task
from app.editor.evidence import TemplateEvidence
from app.editor.models import (
    CorrectionExclusion,
    EditorAudit,
    EditorCatalog,
    EditorPublication,
    EditorRevision,
)
from app.editor.repository import base_payloads, combined_content, lock_catalog
from app.editor.schemas import (
    AuditEvent,
    BaseImport,
    BaseItem,
    BaseList,
    BatchResult,
    ChangeRequest,
    CreateRevision,
    EditorActor,
    EditorMeta,
    EditRevision,
    ImportBatch,
    Kind,
    Preview,
    PublicationRef,
    PublishBatch,
    ReviewRequest,
    RevisionList,
    RevisionSummary,
    RevisionView,
    SampleReview,
    Status,
    TemplateSample,
    Withdrawal,
    WithdrawRequest,
)
from app.editor.validation import (
    data_only,
    digest,
    editable_payload,
    generate_sample,
    registered_families,
    validate_generation,
    validate_payload,
    validation_error,
)
from app.errors import ApiError, not_found
from app.services import LearningService, StoredResponse


class EditorService:
    def __init__(self, learning_service: LearningService) -> None:
        self.learning = learning_service
        self.evidence = TemplateEvidence(learning_service)

    @staticmethod
    def _staff(actor: EditorActor, *, publish: bool = False) -> None:
        if actor.role not in {"methodist", "admin"} or (publish and actor.role != "admin"):
            raise ApiError(403, "editor_forbidden", "Для публикации нужен администратор с MFA.")

    def _write(
        self,
        token: str | None,
        actor: EditorActor,
        key: str | None,
        operation: str,
        body: BaseModel,
        action: Callable[[Session, EditorCatalog], BaseModel],
        *,
        publish=False,
    ) -> StoredResponse:
        self._staff(actor, publish=publish)
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            def authorize() -> None:
                current = authorize_staff(
                    db, token, self.learning.clock(), publish=publish, write=True,
                    clock=self.learning.clock,
                )
                if (
                    guest.id != actor.owner_id
                    or current.id != actor.id
                    or current.root_guest_id != actor.owner_id
                    or current.role != actor.role
                ):
                    raise ApiError(
                        403, "editor_identity_changed", "Сеанс изменился. Войдите заново.",
                    )

            authorize()

            def atomic() -> BaseModel:
                try:
                    # _idempotent catches ApiError and commits its response. ALL editorial
                    # writes must be inside this savepoint, including audit/pointer writes.
                    with db.begin_nested():
                        catalog = lock_catalog(db)
                        authorize()
                        result = action(db, catalog)
                        db.flush()
                        return result
                except IntegrityError as exc:
                    raise ApiError(
                        409, "editor_conflict", "Запись уже изменена. Обновите редактор."
                    ) from exc

            return self.learning._idempotent(
                db,
                guest,
                key,
                f"EDITOR {actor.id} {operation}",
                body,
                atomic,
            )

    @staticmethod
    def _get(db: Session, identifier: str, expected: int | None = None) -> EditorRevision:
        record = db.get(EditorRevision, identifier)
        if record is None:
            raise not_found()
        if expected is not None and expected != record.revision:
            raise ApiError(
                409,
                "revision_conflict",
                "Редакция изменилась. Сохраните ввод и загрузите её заново.",
                "expected_revision",
            )
        return record

    @staticmethod
    def _author(record: EditorRevision, actor: EditorActor) -> None:
        if record.author_id != actor.id:
            raise ApiError(
                403, "author_required", "Изменять черновик может его автор. Создайте свою редакцию."
            )

    @staticmethod
    def _state(record: EditorRevision, *allowed: str) -> None:
        if record.status not in allowed:
            raise ApiError(409, "invalid_transition", "Действие недоступно в текущем состоянии.")

    @staticmethod
    def _independent(record: EditorRevision, actor: EditorActor) -> None:
        if record.author_id == actor.id:
            raise ApiError(
                403, "independent_review_required", "Нужен другой авторизованный методист."
            )

    def _audit(
        self,
        db: Session,
        record: EditorRevision | None,
        actor: EditorActor,
        action: str,
        note: str,
        previous: str | None = None,
        *,
        kind: str | None = None,
        content_id: str | None = None,
    ) -> None:
        if len(note.strip()) < 5:
            raise ApiError(422, "note_required", "Опишите причину минимум пятью символами.", "note")
        data_only(note)
        db.add(
            EditorAudit(
                id=str(uuid4()),
                revision_id=record.id if record else None,
                kind=record.kind if record else kind,
                content_id=record.content_id if record else content_id,
                actor_id=actor.id,
                actor_role=actor.role,
                action=action,
                from_status=previous,
                to_status=record.status if record else "archived",
                note=note.strip(),
                created_at=self.learning.clock(),
            )
        )

    def _event(
        self,
        db: Session,
        record: EditorRevision,
        actor: EditorActor,
        action: str,
        note: str,
        *,
        status: str | None = None,
    ) -> None:
        previous = record.status
        record.status = status or record.status
        record.revision += 1
        record.updated_at = self.learning.clock()
        self._audit(db, record, actor, action, note, previous)

    @staticmethod
    def _capabilities(record: EditorRevision, actor: EditorActor) -> list[str]:
        actions = ["fork"]
        if record.status == "draft" and record.author_id == actor.id:
            actions.extend(["edit", "submit", "archive"])
        if record.status in {"review", "ready"} and (
            actor.id in {record.author_id, record.reviewer_id} or record.status == "review"
        ):
            actions.append("return_to_draft")
        if record.status == "review" and record.author_id != actor.id:
            actions.append("approve")
            if record.kind == "template":
                actions.append("review_sample")
        if record.kind == "template" and record.status in {"draft", "review"}:
            actions.append("run_checks")
        if actor.role == "admin":
            if record.status == "ready":
                actions.append("publish")
            if record.status == "published":
                actions.append("withdraw" if record.kind == "task" else "archive")
        return actions

    def _summary(self, record: EditorRevision, actor: EditorActor) -> RevisionSummary:
        return RevisionSummary(
            id=record.id,
            kind=record.kind,
            content_id=record.content_id,
            content_revision=record.payload.get("revision", f"ed-{record.id}"),
            version=record.version,
            revision=record.revision,
            status=record.status,
            title=record.title,
            author_id=record.author_id,
            reviewer_id=record.reviewer_id,
            change_note=record.change_note,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            capabilities=self._capabilities(record, actor),
        )

    def _view(self, db: Session, record: EditorRevision, actor: EditorActor) -> RevisionView:
        db.flush()
        audit = db.scalars(
            select(EditorAudit)
            .where(EditorAudit.revision_id == record.id)
            .order_by(EditorAudit.created_at, EditorAudit.id)
        )
        return RevisionView(
            **self._summary(record, actor).model_dump(),
            payload=editable_payload(record.kind, record.payload),
            review_note=record.review_note,
            published_at=record.published_at.isoformat() if record.published_at else None,
            audit=[
                AuditEvent(
                    id=event.id,
                    actor_id=event.actor_id,
                    actor_role=event.actor_role,
                    action=event.action,
                    from_status=event.from_status,
                    to_status=event.to_status,
                    note=event.note,
                    created_at=event.created_at.isoformat(),
                )
                for event in audit
            ],
            evidence=self.evidence.summary(db, record) if record.kind == "template" else None,
        )

    def meta(self, actor: EditorActor) -> EditorMeta:
        self._staff(actor)
        with self.learning.database.transaction() as db:
            profile = combined_content(db, self.learning.settings).profile
        return EditorMeta(
            actor=actor,
            profile=profile,
            kinds=["task", "lesson", "profile", "template"],
            statuses=["draft", "review", "ready", "published", "archived"],
            max_import_items=10,
            max_request_bytes=self.learning.settings.max_request_bytes,
            templates=[
                {
                    "id": family.id,
                    "title": family.title,
                    "slot": family.slot,
                    "skill_ids": list(family.skill_ids),
                }
                for family in registered_families().values()
            ],
        )

    def list_revisions(
        self,
        actor: EditorActor,
        *,
        kind: Kind | None = None,
        status: Status | None = None,
        q: str = "",
        content_id: str | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> RevisionList:
        self._staff(actor)
        statement = select(EditorRevision)
        if kind:
            statement = statement.where(EditorRevision.kind == kind)
        if status:
            statement = statement.where(EditorRevision.status == status)
        if content_id:
            statement = statement.where(EditorRevision.content_id == content_id)
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            statement = statement.where(
                EditorRevision.title.ilike(f"%{escaped}%", escape="\\")
                | EditorRevision.content_id.ilike(f"%{escaped}%", escape="\\"),
            )
        with self.learning.database.transaction() as db:
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            records = db.scalars(
                statement.order_by(
                    EditorRevision.updated_at.desc(),
                    EditorRevision.content_id,
                    EditorRevision.version.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
            return RevisionList(
                items=[self._summary(record, actor) for record in records],
                total=total,
                limit=limit,
                offset=offset,
            )

    def get(self, actor: EditorActor, identifier: str) -> RevisionView:
        self._staff(actor)
        with self.learning.database.transaction() as db:
            return self._view(db, self._get(db, identifier), actor)

    def _new(
        self,
        db: Session,
        actor: EditorActor,
        body: CreateRevision,
        identifier: str,
        payload: dict[str, Any],
        *,
        parent_id: str | None = None,
        base_snapshot: dict[str, Any] | None = None,
    ) -> EditorRevision:
        version = (
            db.scalar(
                select(func.max(EditorRevision.version)).where(
                    EditorRevision.kind == body.kind,
                    EditorRevision.content_id == payload["id"],
                )
            )
            or 0
        )
        record = EditorRevision(
            id=identifier,
            kind=body.kind,
            content_id=payload["id"],
            version=version + 1,
            revision=1,
            status="draft",
            title=payload["title"],
            payload=payload,
            payload_hash=digest(payload),
            parent_id=parent_id,
            base_snapshot=base_snapshot,
            author_id=actor.id,
            reviewer_id=None,
            change_note=body.change_note,
            review_note=None,
            reviewed_formula=False,
            reviewed_constraints=False,
            created_at=self.learning.clock(),
            updated_at=self.learning.clock(),
            reviewed_at=None,
            published_at=None,
        )
        db.add(record)
        db.flush()
        self._audit(db, record, actor, "create", body.change_note)
        return record

    @staticmethod
    def _unused(db: Session, kind: str, content_id: str) -> None:
        if db.scalar(
            select(EditorRevision.id)
            .where(
                EditorRevision.kind == kind,
                EditorRevision.content_id == content_id,
            )
            .limit(1)
        ):
            raise ApiError(
                409, "content_exists", "Материал уже есть. Создайте новую редакцию из него."
            )

    def create(self, token, actor: EditorActor, body: CreateRevision, key) -> StoredResponse:
        def action(db, catalog):
            identifier = str(uuid4())
            payload = validate_payload(
                body.kind, body.payload, author_id=actor.id, revision_id=identifier
            )
            self._unused(db, body.kind, payload["id"])
            if payload["id"] in base_payloads(self.learning.settings)[body.kind]:
                raise ApiError(
                    409, "base_exists", "Откройте исходный материал и создайте его редакцию."
                )
            return self._view(db, self._new(db, actor, body, identifier, payload), actor)

        return self._write(token, actor, key, "create", body, action)

    def import_batch(self, token, actor: EditorActor, body: ImportBatch, key) -> StoredResponse:
        def action(db, catalog):
            prepared = []
            errors = []
            identities = set()
            base = base_payloads(self.learning.settings)
            for row, values in enumerate(body.items, 1):
                try:
                    request = CreateRevision.model_validate(values)
                    identifier = str(uuid4())
                    payload = validate_payload(
                        request.kind,
                        request.payload,
                        author_id=actor.id,
                        revision_id=identifier,
                    )
                    identity = (request.kind, payload["id"])
                    if identity in identities:
                        raise ApiError(422, "duplicate_item", "Повтор id в пакете.")
                    identities.add(identity)
                    self._unused(db, *identity)
                    if payload["id"] in base[request.kind]:
                        raise ApiError(
                            422, "base_exists", "Исходный материал импортируется через /base."
                        )
                    prepared.append((request, identifier, payload))
                except ValidationError as exc:
                    errors.append(f"Строка {row}: {validation_error(exc).message}")
                except ApiError as exc:
                    errors.append(f"Строка {row}: {exc.message}")
            if errors:
                raise ApiError(422, "invalid_import", "\n".join(errors), "items")
            records = [
                self._new(db, actor, request, identifier, payload)
                for request, identifier, payload in prepared
            ]
            return BatchResult(items=[self._view(db, record, actor) for record in records])

        return self._write(token, actor, key, "import", body, action)

    def edit(
        self, token, actor: EditorActor, identifier: str, body: EditRevision, key
    ) -> StoredResponse:
        def action(db, catalog):
            record = self._get(db, identifier, body.expected_revision)
            self._author(record, actor)
            self._state(record, "draft")
            if record.published_at is not None:
                raise ApiError(409, "immutable_revision", "Опубликованный снимок неизменяем.")
            payload = validate_payload(
                record.kind, body.payload, author_id=actor.id, revision_id=record.id
            )
            if payload["id"] != record.content_id:
                raise ApiError(422, "immutable_id", "Стабильный id нельзя менять.", "id")
            record.payload, record.payload_hash = payload, digest(payload)
            record.title, record.change_note = payload["title"], body.change_note
            self._event(db, record, actor, "edit", body.change_note)
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"edit {identifier}", body, action)

    def fork(
        self, token, actor: EditorActor, identifier: str, body: ChangeRequest, key
    ) -> StoredResponse:
        def action(db, catalog):
            parent = self._get(db, identifier, body.expected_revision)
            new_id = str(uuid4())
            request = CreateRevision(
                kind=parent.kind,
                payload=editable_payload(parent.kind, parent.payload),
                change_note=body.note,
            )
            payload = validate_payload(
                parent.kind, request.payload, author_id=actor.id, revision_id=new_id
            )
            record = self._new(db, actor, request, new_id, payload, parent_id=parent.id)
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"fork {identifier}", body, action)

    def transition(
        self,
        token,
        actor: EditorActor,
        identifier: str,
        action_name: str,
        body: ReviewRequest,
        key,
    ) -> StoredResponse:
        def action(db, catalog):
            record = self._get(db, identifier, body.expected_revision)
            if action_name == "submit":
                self._author(record, actor)
                self._state(record, "draft")
                self._event(db, record, actor, "submit", body.note, status="review")
            elif action_name == "return_to_draft":
                self._state(record, "review", "ready")
                if record.status == "ready" and actor.id not in {
                    record.author_id,
                    record.reviewer_id,
                }:
                    raise ApiError(
                        403, "reviewer_required", "Вернуть редакцию может автор или её рецензент."
                    )
                payload = validate_payload(
                    record.kind,
                    editable_payload(record.kind, record.payload),
                    author_id=record.author_id,
                    revision_id=record.id,
                )
                record.payload, record.payload_hash = payload, digest(payload)
                record.reviewer_id = record.reviewed_at = record.review_note = None
                record.reviewed_formula = record.reviewed_constraints = False
                self._event(db, record, actor, "return_to_draft", body.note, status="draft")
            elif action_name == "approve":
                self._state(record, "review")
                self._independent(record, actor)
                if record.kind == "template":
                    if not body.reviewed_formula or not body.reviewed_constraints:
                        raise ApiError(
                            422,
                            "formula_review_required",
                            "Подтвердите проверку формул и ограничений.",
                        )
                    self.evidence.gate(db, record, actor.id)
                payload = copy.deepcopy(record.payload)
                if record.kind == "task":
                    payload["review_status"] = "reviewed"
                    payload["source"]["reviewed_by"] = actor.id
                elif record.kind == "lesson":
                    payload.update(review_status="reviewed", reviewed_by=actor.id)
                record.payload, record.payload_hash = payload, digest(payload)
                record.reviewer_id, record.reviewed_at = actor.id, self.learning.clock()
                record.review_note = body.note
                record.reviewed_formula, record.reviewed_constraints = (
                    body.reviewed_formula,
                    body.reviewed_constraints,
                )
                self._event(db, record, actor, "approve", body.note, status="ready")
            else:
                raise not_found()
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"{action_name} {identifier}", body, action)

    def _publish(
        self,
        db: Session,
        catalog: EditorCatalog,
        actor: EditorActor,
        references: list[PublicationRef],
        note: str,
    ) -> list[EditorRevision]:
        records = [self._get(db, item.id, item.expected_revision) for item in references]
        identities = [(record.kind, record.content_id) for record in records]
        if len(set(identities)) != len(identities):
            raise ApiError(
                422, "duplicate_publication", "Можно публиковать одну редакцию каждого материала."
            )
        for record in records:
            self._state(record, "ready")
            if (
                record.reviewer_id is None
                or record.reviewer_id == record.author_id
                or record.reviewed_at is None
            ):
                raise ApiError(
                    403, "independent_review_required", "Отсутствует независимая проверка."
                )
            pointer = db.get(EditorPublication, (record.kind, record.content_id))
            previous = (
                db.get(EditorRevision, pointer.revision_id)
                if pointer and pointer.revision_id
                else None
            )
            if previous is not None and previous.version >= record.version:
                raise ApiError(409, "newer_publication", "Уже опубликована более новая редакция.")
        try:
            bundle = combined_content(db, self.learning.settings, records)
        except ContentError as exc:
            raise ApiError(422, "invalid_publication", f"Пакет не опубликован: {exc}") from exc
        for record in records:
            if record.kind == "task":
                validate_generation(Task.model_validate(record.payload), bundle.profile)
            elif record.kind == "template":
                if not record.reviewed_formula or not record.reviewed_constraints:
                    raise ApiError(
                        422, "formula_review_required", "Нет проверки формул и ограничений."
                    )
                self.evidence.gate(db, record, record.reviewer_id, bundle.profile)
        # Validate template mappings across the complete package, including those
        # left published while a profile is changed.
        replacing = set(identities)
        active_templates = db.scalars(
            select(EditorRevision)
            .join(
                EditorPublication,
                EditorPublication.revision_id == EditorRevision.id,
            )
            .where(EditorPublication.kind == "template", EditorPublication.withdrawn.is_(False))
        )
        for template in active_templates:
            if (template.kind, template.content_id) not in replacing:
                if any(record.kind == "profile" for record in records):
                    self.evidence.gate(db, template, template.reviewer_id, bundle.profile)
                else:
                    generate_sample(template.payload, 0, bundle.profile)
        for record in records:
            pointer = db.get(EditorPublication, (record.kind, record.content_id))
            if pointer is None:
                pointer = EditorPublication(
                    kind=record.kind,
                    content_id=record.content_id,
                    revision_id=record.id,
                    withdrawn=False,
                    reason=None,
                    updated_at=self.learning.clock(),
                )
                db.add(pointer)
            elif pointer.revision_id:
                old = self._get(db, pointer.revision_id)
                if old.status == "published":
                    self._event(db, old, actor, "supersede", note, status="archived")
            pointer.revision_id, pointer.withdrawn, pointer.reason = record.id, False, None
            pointer.updated_at = self.learning.clock()
            if record.kind == "profile":
                catalog.profile_revision_id = record.id
            record.published_at = self.learning.clock()
            self._event(db, record, actor, "publish", note, status="published")
        catalog.revision += 1
        return records

    def publish(
        self, token, actor: EditorActor, identifier: str, body: ChangeRequest, key
    ) -> StoredResponse:
        def action(db, catalog):
            records = self._publish(
                db,
                catalog,
                actor,
                [
                    PublicationRef(
                        id=identifier,
                        expected_revision=body.expected_revision,
                    )
                ],
                body.note,
            )
            return self._view(db, records[0], actor)

        return self._write(token, actor, key, f"publish {identifier}", body, action, publish=True)

    def publish_batch(self, token, actor: EditorActor, body: PublishBatch, key) -> StoredResponse:
        def action(db, catalog):
            records = self._publish(db, catalog, actor, body.items, body.note)
            return BatchResult(items=[self._view(db, record, actor) for record in records])

        return self._write(token, actor, key, "publish batch", body, action, publish=True)

    def withdraw(
        self, token, actor: EditorActor, content_id: str, body: WithdrawRequest, key
    ) -> StoredResponse:
        def action(db, catalog):
            bundle = combined_content(db, self.learning.settings)
            task = next((task for task in bundle.tasks if task.id == content_id), None)
            if task is None:
                raise not_found()
            if task.revision != body.task_revision:
                raise ApiError(
                    409, "revision_conflict", "Снимается другая редакция. Обновите материал."
                )
            pointer = db.get(EditorPublication, ("task", content_id))
            record = self._get(db, pointer.revision_id) if pointer and pointer.revision_id else None
            if pointer is None:
                pointer = EditorPublication(
                    kind="task",
                    content_id=content_id,
                    revision_id=None,
                    withdrawn=True,
                    reason=body.reason,
                    updated_at=self.learning.clock(),
                )
                db.add(pointer)
            pointer.withdrawn, pointer.reason, pointer.updated_at = (
                True,
                body.reason,
                self.learning.clock(),
            )
            if record:
                self._event(db, record, actor, "withdraw", body.reason, status="archived")
            else:
                self._audit(
                    db,
                    None,
                    actor,
                    "withdraw",
                    body.reason,
                    "published",
                    kind="task",
                    content_id=content_id,
                )
            exclusion = CorrectionExclusion(
                id=str(uuid4()),
                task_id=content_id,
                task_revision=body.task_revision,
                reason=body.reason,
                actor_id=actor.id,
                created_at=self.learning.clock(),
            )
            db.add(exclusion)
            catalog.revision += 1
            return Withdrawal(
                task_id=content_id,
                task_revision=body.task_revision,
                reason=body.reason,
                created_at=exclusion.created_at.isoformat(),
            )

        return self._write(token, actor, key, f"withdraw {content_id}", body, action, publish=True)

    def archive(
        self, token, actor: EditorActor, identifier: str, body: ChangeRequest, key
    ) -> StoredResponse:
        def action(db, catalog):
            record = self._get(db, identifier, body.expected_revision)
            self._state(record, "draft", "review", "ready", "published")
            if record.status == "published":
                self._staff(actor, publish=True)
                if record.kind == "task":
                    raise ApiError(
                        422, "withdraw_required", "Для задачи используйте снятие с причиной."
                    )
                if catalog.profile_revision_id == record.id:
                    raise ApiError(
                        409, "active_profile", "Сначала опубликуйте замену текущему профилю."
                    )
                pointer = db.get(EditorPublication, (record.kind, record.content_id))
                pointer.withdrawn, pointer.reason = True, body.note
                pointer.updated_at = self.learning.clock()
                db.flush()
                try:
                    combined_content(db, self.learning.settings)
                except ContentError as exc:
                    raise ApiError(
                        422, "referenced_content", f"Материал ещё используется: {exc}"
                    ) from exc
                catalog.revision += 1
            else:
                self._author(record, actor)
            self._event(db, record, actor, "archive", body.note, status="archived")
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"archive {identifier}", body, action)

    def base_list(self, actor: EditorActor, kind: Kind, q: str = "", offset: int = 0) -> BaseList:
        self._staff(actor)
        values = [
            value
            for value in base_payloads(self.learning.settings)[kind].values()
            if q.casefold() in (value["title"] + " " + value["id"]).casefold()
        ]
        return BaseList(
            items=[
                BaseItem(
                    kind=kind,
                    content_id=value["id"],
                    title=value["title"],
                    content_revision=value["revision"],
                )
                for value in values[offset : offset + 30]
            ],
            total=len(values),
        )

    def import_base(
        self, token, actor: EditorActor, kind: Kind, content_id: str, body: BaseImport, key
    ) -> StoredResponse:
        def action(db, catalog):
            self._unused(db, kind, content_id)
            base = base_payloads(self.learning.settings)
            original = base[kind].get(content_id)
            if original is None:
                raise not_found()
            editable = editable_payload(kind, original)
            if (
                kind in {"task", "lesson"}
                and editable.get("kind") != "foundation"
                and not editable.get("slot_id")
            ):
                profile = next(iter(base["profile"].values()))
                editable["slot_id"] = next(
                    slot["id"] for slot in profile["slots"] if slot["number"] == editable["slot"]
                )
            identifier = str(uuid4())
            payload = validate_payload(kind, editable, author_id=actor.id, revision_id=identifier)
            request = CreateRevision(kind=kind, payload=editable, change_note=body.change_note)
            record = self._new(
                db, actor, request, identifier, payload, base_snapshot=copy.deepcopy(original)
            )
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"base {kind} {content_id}", body, action)

    def export(self, actor: EditorActor, identifiers: list[str]) -> ImportBatch:
        self._staff(actor)
        with self.learning.database.transaction() as db:
            records = [self._get(db, identifier) for identifier in identifiers]
            return ImportBatch(
                version="1",
                items=[
                    {
                        "kind": record.kind,
                        "payload": editable_payload(record.kind, record.payload),
                        "change_note": record.change_note,
                    }
                    for record in records
                ],
            )

    def preview(self, actor: EditorActor, body: CreateRevision) -> Preview:
        self._staff(actor)
        payload = validate_payload(
            body.kind, body.payload, author_id=actor.id, revision_id=str(uuid4())
        )
        return Preview(
            kind=body.kind,
            task=public_task(payload) if body.kind == "task" else None,
            payload=editable_payload(body.kind, payload),
            message=(
                "Структура JSON и безопасные команды проверены. "
                "Математическую корректность подтверждает рецензент."
            ),
        )

    def sample(self, actor: EditorActor, identifier: str, seed: int) -> TemplateSample:
        self._staff(actor)
        with self.learning.database.transaction() as db:
            record = self._get(db, identifier)
            if record.kind != "template":
                raise not_found()
            return self.evidence.sample(db, record, seed)

    def run_checks(
        self, token, actor: EditorActor, identifier: str, body: ChangeRequest, key
    ) -> StoredResponse:
        def action(db, catalog):
            record = self._get(db, identifier, body.expected_revision)
            self._state(record, "draft", "review")
            if record.kind != "template":
                raise not_found()
            result = self.evidence.run(db, record, actor)
            self._event(db, record, actor, "run_checks", body.note)
            return result

        return self._write(token, actor, key, f"checks {identifier}", body, action)

    def review_sample(
        self, token, actor: EditorActor, identifier: str, body: SampleReview, key
    ) -> StoredResponse:
        def action(db, catalog):
            record = self._get(db, identifier, body.expected_revision)
            self._state(record, "review")
            self._independent(record, actor)
            if record.kind != "template":
                raise not_found()
            self.evidence.review(db, record, actor, body)
            self._event(db, record, actor, "review_sample", body.note)
            return self._view(db, record, actor)

        return self._write(token, actor, key, f"review sample {identifier}", body, action)
