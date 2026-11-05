import asyncio
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.background import DeadlineWorker
from app.models import AttemptRecord
from app.operations.health import OperationHealth
from tests.helpers import answer, draft, expected, key, start


def test_application_diagnostics_use_the_injected_learning_clock(client, clock):
    health = client.app.state.operation_health.snapshot()
    assert health["started_at"] == clock[0].isoformat()
    assert health["jobs"]["deadline_reconcile"]["last_success_at"] == clock[0].isoformat()
    assert client.app.state.service.operation_health is client.app.state.operation_health
    clock[0] += timedelta(minutes=1)
    client.portal.call(client.app.state.deadline_worker.reconcile)
    assert client.app.state.operation_health.snapshot()["jobs"]["deadline_reconcile"][
        "last_success_at"
    ] == clock[0].isoformat()


def test_deadline_failure_and_recovery_use_the_supplied_clock(clock):
    calls = []

    def reconcile_deadlines(*, limit):
        calls.append(limit)
        if len(calls) == 1:
            raise RuntimeError("discarded payload")

    async def scenario():
        health = OperationHealth(now=clock[0])
        worker = DeadlineWorker(
            SimpleNamespace(reconcile_deadlines=reconcile_deadlines), health,
            clock=lambda: clock[0],
        )
        await worker.reconcile()
        assert health.retry_delay("deadline_reconcile", clock[0]) == 5
        clock[0] += timedelta(seconds=5)
        await worker.reconcile()
        job = health.snapshot()["jobs"]["deadline_reconcile"]
        assert job["last_success_at"] == clock[0].isoformat()
        assert job["successes"] == job["failures"] == 1

    asyncio.run(scenario())


def test_checker_and_committed_save_counters_do_not_count_idempotent_replays(
    guest_client, content,
):
    session = start(guest_client).json()
    task = session["tasks"][0]
    health = guest_client.app.state.operation_health
    assert draft(guest_client, session, task, "12").status_code == 200
    assert health.snapshot()["events"]["draft_save"] == {"successes": 1, "failures": 0}
    headers = key()
    first = answer(guest_client, session, task, expected(content, task), headers=headers)
    assert first.status_code == 200
    assert answer(
        guest_client, session, task, expected(content, task), headers=headers,
    ).content == first.content
    counters = health.snapshot()["events"]
    assert counters["answer_check"] == {"successes": 1, "failures": 0}
    assert counters["attempt_save"] == {"successes": 1, "failures": 0}


def test_invalid_format_and_skips_are_not_attempted_checker_or_save_successes(guest_client):
    session = start(guest_client).json()
    task = session["tasks"][0]
    headers = key()
    rejected = answer(guest_client, session, task, "NaN", headers=headers)
    assert rejected.status_code == 422
    assert answer(guest_client, session, task, "NaN", headers=headers).content == rejected.content
    counters = guest_client.app.state.operation_health.snapshot()["events"]
    assert counters["answer_check"] == {"successes": 0, "failures": 1}
    assert counters["attempt_save"] == {"successes": 0, "failures": 0}
    assert answer(guest_client, session, task, "", skipped=True).status_code == 200
    counters = guest_client.app.state.operation_health.snapshot()["events"]
    assert counters["answer_check"] == {"successes": 0, "failures": 1}
    assert counters["attempt_save"] == {"successes": 1, "failures": 0}


@pytest.mark.parametrize("operation", ["attempt", "draft"])
def test_a_failed_commit_is_a_save_failure_not_a_success(
    guest_client, content, monkeypatch, operation,
):
    session = start(guest_client).json()
    task = session["tasks"][0]
    database = guest_client.app.state.database
    original = database.transaction

    @contextmanager
    def failing_commit(*, write=False):
        with original(write=write) as db:
            yield db
            if write:
                raise OperationalError("synthetic commit failure", None, None)

    with monkeypatch.context() as patch:
        patch.setattr(database, "transaction", failing_commit)
        response = (
            answer(guest_client, session, task, expected(content, task))
            if operation == "attempt" else draft(guest_client, session, task, "12")
        )
    assert response.status_code == 503
    counters = guest_client.app.state.operation_health.snapshot()["events"]
    assert counters[f"{operation}_save"] == {"successes": 0, "failures": 1}
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["draft_revision"] == 0 and saved["drafts"] == {}
    with database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(AttemptRecord)) == 0
