"""Exact final-only grading. Invalid drafts are not mathematical attempts."""

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid5

from app.assessments.models import AssessmentRecord
from app.assessments.schemas import AssessmentResult, ResultRow
from app.checker import AnswerFormatError, check_answer, parse_answer
from app.operations.health import OperationHealth


def content_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def complete_snapshot(
    record: AssessmentRecord, answers: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """A finish is a full snapshot: omitted task IDs are empty, not stale drafts."""
    return {
        task["id"]: dict(answers.get(task["id"], {"answer": "", "active_seconds": 0}))
        for task in record.tasks_snapshot
    }


def build_result(
    record: AssessmentRecord, answers: dict[str, Any], *, at: datetime,
    source: Literal["server", "local"], reason: Literal["finished", "deadline", "connection_lost"],
    prior_numeric: set[str], assisted_tasks: set[str], operation_health: OperationHealth,
) -> AssessmentResult:
    slots = {slot["number"]: slot["id"] for slot in record.profile_snapshot["slots"]}
    rows = []
    for task in record.tasks_snapshot:
        task_id = task["id"]
        draft = answers[task_id]
        raw = draft["answer"]
        skipped = not raw.strip()
        normalized = None
        correct = False
        format_message = None
        if not skipped:
            try:
                try:
                    checked = check_answer(raw, task["answer"], "exam")
                except Exception:
                    operation_health.record_event("answer_check", success=False)
                    raise
                operation_health.record_event("answer_check", success=True)
                normalized, correct = checked.normalized_answer, checked.correct
            except AnswerFormatError as exc:
                format_message = str(exc)
        assisted = task_id in assisted_tasks
        rows.append(ResultRow(
            id=str(uuid5(UUID(record.id), f"{source}:{task_id}")),
            task_id=task_id, task_revision=task["revision"], slot=task["slot"],
            slot_id=slots[task["slot"]], family_id=task["family_id"], skill_ids=task["skill_ids"],
            raw=raw, normalized=normalized,
            expected=parse_answer(task["answer"], "exam").normalized_answer,
            correct=correct, skipped=skipped, format_error=format_message is not None,
            format_message=format_message,
            independent=(
                source == "server" and normalized is not None and not assisted
                and task_id not in prior_numeric
            ),
            assisted=assisted, first_attempt=source == "server",
            active_seconds=draft["active_seconds"], solution=task["solution"],
            first_draft=record.first_drafts.get(task_id),
            first_answer=record.answer_context.get(task_id, {}).get("first_answer"),
            label=("Пропущено" if skipped else "Ошибка формата" if format_message else
                   "Верно" if correct else "Неверно"),
        ))
    label = "Учебная диагностика" if record.mode == "diagnostic" else "Пробник первой части"
    if source == "local":
        label = "Локальный учебный результат при нарушении соединения"
    return AssessmentResult(
        source=source, reason=reason, label=label,
        score=sum(row.correct for row in rows), total=13,
        answered=sum(row.normalized is not None for row in rows),
        skipped=sum(row.skipped for row in rows),
        format_errors=sum(row.format_error for row in rows),
        independent_total=sum(row.independent for row in rows),
        independent_correct=sum(row.independent and row.correct for row in rows),
        assisted_total=sum(row.assisted for row in rows),
        active_seconds=sum(row.active_seconds for row in rows),
        elapsed_seconds=max(0, int((at - record.started_at).total_seconds())),
        snapshot_at=at.isoformat(),
        snapshot_hash=content_hash({
            "profile": record.profile_snapshot, "tasks": record.tasks_snapshot, "answers": answers,
        }),
        connection_lost=source == "local" or reason == "connection_lost",
        checker_revision="fraction-v1-exam",
        rows=rows,
        weak_skill_ids=sorted({
            skill for row in rows if not row.correct for skill in row.skill_ids
        }),
        recommendation=(
            "Карта диагностики предварительная: "
            "проверьте сомнительные навыки на 3–5 новых задачах. "
            "Одна верная задача не означает освоение."
            if record.mode == "diagnostic" else
            "Разберите ошибки, пропуски и формат ответа; закрепите навыки на других экземплярах. "
            "Учебный результат не является прогнозом экзаменационной оценки."
        ),
    )
