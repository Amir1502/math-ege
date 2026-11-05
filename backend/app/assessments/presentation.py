"""The only assessment view: closed results never reach public serialization."""

from datetime import datetime

from app.assessments.models import AssessmentRecord
from app.assessments.schemas import AssessmentView
from app.content import public_task


def assessment_view(
    record: AssessmentRecord, now: datetime, device_id: str | None
) -> AssessmentView:
    released = record.status == "completed" and record.released_at is not None
    notices = {
        "prepared": "Условия подготовлены. Начните после сохранения всех 13 задач на устройстве.",
        "active": "Правильность, эталоны и решения будут доступны после завершения.",
        "awaiting_snapshot": (
            "Время истекло. Серверный снимок сохранён; ожидается итоговый снимок с устройства. "
            "Эталоны и решения пока закрыты."
        ),
        "completed": (
            "Учебный результат 0–13. Он не переводится в полный тестовый балл ЕГЭ."
        ),
    }
    notice = notices[record.status]
    if released and record.local_result is not None:
        notice = (
            "Серверный и локальный учебный результаты сохранены отдельно. "
            "Локальный снимок получен при нарушении соединения или после дедлайна. "
            "В освоении учитывается только серверный результат."
        )
    return AssessmentView(
        id=record.id,
        mode=record.mode,
        status=record.status,
        profile_id=record.profile_id,
        profile_revision=record.profile_revision,
        profile=record.profile_snapshot,
        created_at=record.created_at.isoformat(),
        server_now=now.isoformat(),
        started_at=record.started_at.isoformat() if record.started_at else None,
        deadline_at=record.deadline_at.isoformat() if record.deadline_at else None,
        released_at=record.released_at.isoformat() if record.released_at else None,
        duration_minutes=record.duration_minutes,
        writer_generation=record.writer_generation,
        can_write=device_id == record.writer_device_id and record.status != "completed",
        draft_revision=record.draft_revision,
        current_index=record.current_index,
        tasks=[public_task(task).model_copy(update={"hint_count": 0})
               for task in record.tasks_snapshot],
        drafts=record.drafts,
        server_result=record.server_result if released else None,
        local_result=record.local_result if released else None,
        result_notice=notice,
    )
