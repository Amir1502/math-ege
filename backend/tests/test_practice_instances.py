import json
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.accounts.models import AccessSession
from app.assessments.models import AssessmentRecord
from app.eligibility import prior_numeric_ids
from app.models import AttemptRecord, Guest, LearningSessionRecord, SeenTask
from tests.helpers import answer, start
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory
from tests.test_assessments import activate, prepare, save
from tests.test_assessments import single_slot_bank as single_slot_bank


def alias_bank(content_dir, original):
    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    alias = {**original.model_dump(mode="json"), "id": "owned-visible-alias"}
    path.write_text(json.dumps([
        alias if task["id"] == original.id else task for task in tasks
    ], ensure_ascii=False), encoding="utf-8")
    return alias


def one_session(client):
    response = start(client)
    assert response.status_code == 200, response.text
    assert len(response.json()["tasks"]) == 1
    return response.json()


@pytest.mark.parametrize("exposure", ["hint", "solution", "numeric", "skip"])
def test_alias_assistance_survives_claims_without_rewriting_original_attempts_or_origins(
    account_factory, account_config, content_dir, single_slot_bank, exposure,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first_owner = first.post("/api/v1/guest", json={}).json()["id"]
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    old_session = one_session(first)
    old_task = old_session["tasks"][0]
    if exposure in {"hint", "solution"}:
        route, body = (
            ("hints", {"task_id": old_task["id"], "level": 1})
            if exposure == "hint" else ("solution", {"task_id": old_task["id"]})
        )
        helped = first.post(f"/api/v1/sessions/{old_session['id']}/{route}", json=body)
        assert helped.status_code == 200
    else:
        assert answer(
            first, old_session, old_task, original.answer if exposure == "numeric" else "",
            skipped=exposure == "skip",
        ).status_code == 200
    frozen = first.get(f"/api/v1/sessions/{old_session['id']}").json()
    alias = alias_bank(content_dir, original)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    second_owner = second.post("/api/v1/guest", json={}).json()["id"]
    new_session = one_session(second)
    assert new_session["tasks"][0]["id"] == alias["id"]
    account = login(first, mailbox)
    assert login(second, mailbox)["id"] == account["id"]

    submitted = answer(second, new_session, new_session["tasks"][0], original.answer)

    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["correct"] and submitted.json()["first_attempt"]
    assert submitted.json()["assisted"] and not submitted.json()["independent"]
    assert second.get(f"/api/v1/sessions/{old_session['id']}").json() == frozen
    with first.app.state.database.transaction() as db:
        assert db.get(LearningSessionRecord, old_session["id"]).guest_id == first_owner
        assert db.get(LearningSessionRecord, new_session["id"]).guest_id == second_owner
        new_attempt = db.get(AttemptRecord, submitted.json()["id"])
        assert new_attempt.guest_id == second_owner and new_attempt.task_id == alias["id"]
        original_attempts = list(db.scalars(select(AttemptRecord).where(
            AttemptRecord.session_id == old_session["id"],
        )))
        assert [item.id for item in original_attempts] == [
            item["id"] for item in frozen["attempts"]
        ]
        if exposure == "numeric":
            assert original_attempts[0].independent and not original_attempts[0].assisted
        exposures = list(db.scalars(select(SeenTask)))
        assert {(row.guest_id, row.task_id) for row in exposures} == {
            (first_owner, original.id), (second_owner, alias["id"]),
        }


def test_foreign_alias_history_does_not_reserve_or_assist_another_owner(
    client_factory, content_dir, single_slot_bank,
):
    first = client_factory()
    foreign_owner = first.post("/api/v1/guest", json={}).json()["id"]
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    old_session = one_session(first)
    assert first.post(f"/api/v1/sessions/{old_session['id']}/hints", json={
        "task_id": original.id, "level": 1,
    }).status_code == 200
    old_attempt = answer(first, old_session, old_session["tasks"][0], original.answer).json()
    frozen = first.get(f"/api/v1/sessions/{old_session['id']}").json()
    alias_bank(content_dir, original)
    second = client_factory(database_url=first.app.state.settings.database_url)
    owner = second.post("/api/v1/guest", json={}).json()["id"]
    new_session = one_session(second)

    submitted = answer(second, new_session, new_session["tasks"][0], original.answer)

    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["independent"] and not submitted.json()["assisted"]
    assert first.get(f"/api/v1/sessions/{old_session['id']}").json() == frozen
    assert second.get(f"/api/v1/sessions/{old_session['id']}").status_code == 404
    with first.app.state.database.transaction() as db:
        assert prior_numeric_ids(db, [owner]) == {new_session["tasks"][0]["id"]}
        saved = db.get(AttemptRecord, old_attempt["id"])
        assert saved.guest_id == foreign_owner and saved.assisted and not saved.independent


def test_pending_server_answer_reserves_a_claimed_practice_alias_without_releasing_it(
    account_factory, account_config, content_dir, single_slot_bank, clock,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    original_owner = first.post("/api/v1/guest", json={}).json()["id"]
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    device = str(uuid4())
    prepared = prepare(first, device=device, duration_minutes=15)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    assert activate(first, assessment, device).status_code == 200
    assert save(first, assessment, device, {
        original.id: {"answer": original.answer, "active_seconds": 12},
    }).status_code == 200
    alias_bank(content_dir, original)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    practice_owner = second.post("/api/v1/guest", json={}).json()["id"]
    practice = one_session(second)
    clock[0] += timedelta(minutes=16)
    first.app.state.assessments.reconcile_deadlines()
    with first.app.state.database.transaction() as db:
        pending = deepcopy(db.get(AssessmentRecord, assessment["id"]).server_result)
        assert pending["rows"][0]["normalized"] is not None
        assert not db.scalars(select(SeenTask).where(
            SeenTask.guest_id == original_owner, SeenTask.task_id == original.id,
        )).one().reference_seen
    account = login(first, mailbox)
    assert login(second, mailbox)["id"] == account["id"]
    exported = second.get("/api/v1/export").json()
    assert exported["assessments"][0]["server_result"] is None
    assert exported["assessments"][0]["local_result"] is None
    assert second.get("/api/v1/progress").json()["independent_total"] == 0

    submitted = answer(second, practice, practice["tasks"][0], original.answer)

    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["first_attempt"] and not submitted.json()["assisted"]
    assert not submitted.json()["independent"]
    with first.app.state.database.transaction() as db:
        record = db.get(AssessmentRecord, assessment["id"])
        assert record.guest_id == original_owner and record.server_result == pending
        assert record.local_result is None and record.released_at is None
        assert db.get(AttemptRecord, submitted.json()["id"]).guest_id == practice_owner
    exported = second.get("/api/v1/export").json()
    assert exported["assessments"][0]["status"] == "awaiting_snapshot"
    assert exported["assessments"][0]["server_result"] is None


@pytest.mark.parametrize("kind", ["guest", "account"])
def test_progress_rechecks_expiry_after_the_coherent_catalog_read(
    account_factory, account_config, clock, monkeypatch, kind,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    client.post("/api/v1/guest", json={})
    identity = (
        login(client, mailbox) if kind == "account" else client.get("/api/v1/identity").json()
    )
    database = client.app.state.database
    with database.transaction(write=True) as db:
        if kind == "account":
            access = db.scalars(select(AccessSession).where(
                AccessSession.account_id == identity["id"],
            )).one()
            access.expires_at = clock[0] + timedelta(seconds=1)
        else:
            db.get(Guest, identity["id"]).expires_at = clock[0] + timedelta(seconds=1)
    service = client.app.state.service
    original_content = service.content

    def delayed_content(db=None):
        bundle = original_content(db)
        clock[0] += timedelta(seconds=2)
        return bundle

    monkeypatch.setattr(service, "content", delayed_content)

    response = client.get("/api/v1/progress")

    assert response.status_code == 401, response.text
    with database.transaction() as db:
        assert not list(db.scalars(select(AttemptRecord)))
        assert not list(db.scalars(select(LearningSessionRecord)))


@pytest.mark.parametrize("kind", ["guest", "account"])
def test_successful_progress_reauthorization_does_not_mutate_access_timestamps(
    account_factory, account_config, clock, kind,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    guest = client.post("/api/v1/guest", json={}).json()
    account = login(client, mailbox) if kind == "account" else None
    owner = account["root_guest_id"] if account else guest["id"]
    database = client.app.state.database
    with database.transaction() as db:
        root_timestamp = db.get(Guest, owner).last_seen_at
        access_timestamps = {row.id: row.last_seen_at for row in db.scalars(select(AccessSession))}
    clock[0] += timedelta(seconds=1)

    response = client.get("/api/v1/progress")

    assert response.status_code == 200, response.text
    with database.transaction() as db:
        assert db.get(Guest, owner).last_seen_at == root_timestamp
        assert {row.id: row.last_seen_at for row in db.scalars(select(AccessSession))} == (
            access_timestamps
        )
