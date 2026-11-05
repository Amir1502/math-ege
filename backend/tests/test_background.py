import asyncio
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from app.background import DeadlineWorker
from app.operations.health import OperationHealth


def test_reconciliation_failure_is_redacted_and_later_recovers(caplog):
    calls = []

    def reconcile_deadlines(*, limit):
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("sensitive request payload")
        return 1

    async def scenario():
        health = OperationHealth()
        worker = DeadlineWorker(SimpleNamespace(reconcile_deadlines=reconcile_deadlines), health)
        await worker.reconcile()
        failed = health.snapshot()["jobs"]["deadline_reconcile"]
        assert failed["status"] == "failed" and failed["backoff_seconds"] == 5
        await worker.reconcile()
        recovered = health.snapshot()["jobs"]["deadline_reconcile"]
        assert recovered["status"] == "ok"
        assert recovered["successes"] == recovered["failures"] == 1
        assert recovered["backoff_seconds"] == 0

    asyncio.run(scenario())
    assert calls == [100, 100]
    assert "RuntimeError" in caplog.text
    assert "sensitive request payload" not in caplog.text


def test_periodic_worker_drains_an_inflight_thread_before_stopping():
    entered, release, finished = Event(), Event(), Event()

    def reconcile_deadlines(*, limit):
        entered.set()
        assert release.wait(5)
        finished.set()
        return 0

    async def scenario():
        worker = DeadlineWorker(
            SimpleNamespace(reconcile_deadlines=reconcile_deadlines), OperationHealth(),
            interval_seconds=0.001,
        )
        task = asyncio.create_task(worker.run())
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            worker.stop()
            assert not task.done()
            release.set()
            await asyncio.wait_for(task, 5)
            assert finished.is_set()
        finally:
            release.set()
            worker.stop()
            await task

    asyncio.run(scenario())


def test_application_mounts_assessments_and_freezes_without_an_assessment_request(
    client_factory, clock,
):
    from app.assessments.models import AssessmentRecord

    client = client_factory()
    health = client.app.state.operation_health.snapshot()["jobs"]["deadline_reconcile"]
    assert health["status"] == "ok" and health["successes"] >= 1
    client.post("/api/v1/guest", json={})
    device = str(uuid4())
    prepared = client.post("/api/v1/assessments", json={
        "mode": "exam", "duration_minutes": 15, "device_id": device,
    }, headers={"Idempotency-Key": str(uuid4())})
    assert prepared.status_code == 200, prepared.text
    assessment_id = prepared.json()["id"]
    active = client.post(f"/api/v1/assessments/{assessment_id}/activate", json={
        "device_id": device, "writer_generation": 1,
    }, headers={"Idempotency-Key": str(uuid4())})
    assert active.status_code == 200, active.text
    clock[0] += timedelta(minutes=16)
    client.portal.call(client.app.state.deadline_worker.reconcile)
    with client.app.state.database.transaction() as db:
        record = db.get(AssessmentRecord, assessment_id)
        assert record.status == "awaiting_snapshot"
        assert record.server_result is not None
        assert record.released_at is None
    diagnostics = client.get("/api/v1/operations/health")
    assert diagnostics.status_code == 503
    assert diagnostics.json()["error"]["code"] == "accounts_disabled"
