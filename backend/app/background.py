import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from app.operations.health import OperationHealth
from app.services import utc_now

if TYPE_CHECKING:
    from app.assessments.service import AssessmentService

logger = logging.getLogger(__name__)


class DeadlineWorker:
    def __init__(
        self, assessments: "AssessmentService", health: OperationHealth, *,
        interval_seconds: float = 5, clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("The reconciliation interval must be positive")
        self.assessments = assessments
        self.health = health
        self.clock = clock
        self.interval = interval_seconds
        self.stopped = asyncio.Event()

    async def reconcile(self) -> None:
        success = False
        try:
            await asyncio.to_thread(self.assessments.reconcile_deadlines, limit=100)
            success = True
        except Exception as exc:
            logger.error("Deadline reconciliation failed (%s)", type(exc).__name__)
        self.health.record_job("deadline_reconcile", success, self.clock())

    async def run(self) -> None:
        while not self.stopped.is_set():
            delay = max(self.interval, self.health.retry_delay("deadline_reconcile", self.clock()))
            try:
                await asyncio.wait_for(self.stopped.wait(), delay)
            except TimeoutError:
                await self.reconcile()

    def stop(self) -> None:
        self.stopped.set()
