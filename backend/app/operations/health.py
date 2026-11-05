"""Process-local diagnostics with a fixed label set and no exception/payload storage."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from app.operations.common import OperationError, utc

JOB_NAMES = ("deadline_reconcile", "backup", "restore_validation", "deletion_plan")
EVENT_NAMES = ("answer_check", "generator", "attempt_save", "draft_save")


@dataclass(slots=True)
class _Job:
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    backoff_seconds: int = 0


class OperationHealth:
    def __init__(
        self, *, now: datetime | None = None, monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._started_at = utc(now if now is not None else datetime.now(UTC))
        self._monotonic = monotonic
        self._started_tick = monotonic()
        self._lock = Lock()
        self._jobs = {name: _Job() for name in JOB_NAMES}
        self._events = {name: {"successes": 0, "failures": 0} for name in EVENT_NAMES}

    def record_job(self, name: str, success: bool, now: datetime) -> None:
        if name not in JOB_NAMES or type(success) is not bool:
            raise OperationError("invalid_job_observation")
        now = utc(now)
        with self._lock:
            job = self._jobs[name]
            if now < self._started_at or (job.last_attempt_at and now < job.last_attempt_at):
                raise OperationError("out_of_order_job_observation")
            job.last_attempt_at = now
            if success:
                job.successes += 1
                job.last_success_at = now
                job.consecutive_failures = job.backoff_seconds = 0
            else:
                job.failures += 1
                job.consecutive_failures += 1
                job.last_failure_at = now
                job.backoff_seconds = min(300, 5 * 2 ** min(6, job.consecutive_failures - 1))

    def record_event(self, name: str, success: bool) -> None:
        if name not in EVENT_NAMES or type(success) is not bool:
            raise OperationError("invalid_event_observation")
        with self._lock:
            self._events[name]["successes" if success else "failures"] += 1

    def retry_delay(self, name: str, now: datetime) -> float:
        if name not in JOB_NAMES:
            raise OperationError("unknown_operational_job")
        now = utc(now)
        with self._lock:
            job = self._jobs[name]
            if job.last_attempt_at is None or not job.backoff_seconds:
                return 0.0
            due = job.last_attempt_at + timedelta(seconds=job.backoff_seconds)
            return max(0.0, (due - now).total_seconds())

    def snapshot(self) -> dict[str, Any]:
        elapsed = self._monotonic() - self._started_tick
        if not math.isfinite(elapsed):
            raise OperationError("invalid_monotonic_clock")
        with self._lock:
            jobs = {}
            for name, job in self._jobs.items():
                next_retry = (
                    job.last_attempt_at + timedelta(seconds=job.backoff_seconds)
                    if job.last_attempt_at and job.backoff_seconds else None
                )
                jobs[name] = {
                    "status": "not_run" if job.last_attempt_at is None else (
                        "failed" if job.consecutive_failures else "ok"
                    ),
                    "successes": job.successes,
                    "failures": job.failures,
                    "consecutive_failures": job.consecutive_failures,
                    "last_attempt_at": _date(job.last_attempt_at),
                    "last_success_at": _date(job.last_success_at),
                    "last_failure_at": _date(job.last_failure_at),
                    "backoff_seconds": job.backoff_seconds,
                    "next_retry_at": _date(next_retry),
                }
            return {
                "version": "1", "scope": "process", "started_at": _date(self._started_at),
                "uptime_seconds": round(max(0.0, elapsed), 3), "jobs": jobs,
                "events": {name: dict(counts) for name, counts in self._events.items()},
            }

    @staticmethod
    def public_snapshot(*, database_ok: bool) -> dict[str, str]:
        if type(database_ok) is not bool:
            raise OperationError("invalid_health_observation")
        return {"status": "ok" if database_ok else "unavailable"}


def _date(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
