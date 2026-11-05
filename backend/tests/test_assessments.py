"""Assessment regressions through HTTP, durable restarts and the public clock seam."""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from tests.helpers import answer as practice_answer
from tests.helpers import expected, key, start
from tests.test_concurrency import race


@pytest.fixture
def assessment_factory(client_factory):
    def make(**overrides):
        from app.assessments.api import router
        from app.assessments.service import AssessmentService

        client = client_factory(**overrides)
        app = client.app
        if not hasattr(app.state, "assessments"):
            # Public ownership contract supplied by the coordinator. The original
            # core has only guests; keep the standalone HTTP fixture runnable.
            if not hasattr(app.state.service, "owner_ids"):
                from app.accounts.principals import owner_ids

                app.state.service.owner_ids = owner_ids
            app.state.assessments = AssessmentService(app.state.service)
            app.include_router(router)
            app.state.database.create_schema_for_tests()
        return client

    return make


@pytest.fixture
def assessment_client(assessment_factory):
    client = assessment_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    return client


@pytest.fixture
def single_slot_bank(content_dir):
    from app.content import load_content

    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    selected = {}
    for task in tasks:
        selected.setdefault(task["slot"], task)
    path.write_text(json.dumps(list(selected.values())), encoding="utf-8")
    return load_content(content_dir)


@pytest.fixture
def account_assessment_factory(assessment_factory):
    """Bind the agreed principal contract using real account functions and HTTP.

    Shared core integration is coordinator-owned. This test harness supplies
    that contract to the assessment service, including the real root row lock.
    """
    from app.accounts.api import router
    from app.accounts.config import AccountSettings
    from app.accounts.principals import owner_ids, resolve_guest
    from app.accounts.service import AccountService
    from app.assessments.service import AssessmentService
    from app.services import LearningService

    class PrincipalContract(LearningService):
        @staticmethod
        def owner_ids(db, guest):
            return owner_ids(db, guest)

        @contextmanager
        def _guest_transaction(self, token, *, write=False):
            with self.database.transaction(write=write) as db:
                yield db, resolve_guest(db, token, self.clock(), write=write)

    class Mailbox:
        def __init__(self):
            self.links = []

        def send_login_link(self, email, link, expires_at):
            self.links.append(link)

    def make(**overrides):
        client = assessment_factory(environment="test", **overrides)
        original = client.app.state.service
        principal = PrincipalContract(original.database, original.settings, original.clock)
        client.app.state.assessments = AssessmentService(principal)
        mailbox = Mailbox()
        if not hasattr(client.app.state, "accounts"):
            client.app.include_router(router)
        client.app.state.accounts = AccountService(
            principal,
            AccountSettings(
                enabled=True, policy_approved=True, policy_version="assessment-test",
                policy_url="https://example.org/privacy", public_origin="http://testserver",
            ),
            mail_sender=mailbox,
        )
        client.app.state.database.create_schema_for_tests()
        return client, mailbox

    return make


def sign_in(client, mailbox):
    requested = client.post("/api/v1/auth/request-link", json={
        "email": "assessment@example.org", "policy_version": "assessment-test",
        "accept_policy": True,
    })
    assert requested.status_code == 202, requested.text
    token = parse_qs(urlsplit(mailbox.links[-1]).fragment)["token"][0]
    response = client.post("/api/v1/auth/complete", json={"token": token})
    assert response.status_code == 200, response.text
    return response.json()


def prepare(client, *, mode="exam", device=None, headers=None, **values):
    return client.post(
        "/api/v1/assessments",
        json={"mode": mode, "device_id": device or str(uuid4()), **values},
        headers=headers or key(),
    )


def activate(client, assessment, device, *, headers=None, generation=None):
    return client.post(
        f"/api/v1/assessments/{assessment['id']}/activate",
        json={"device_id": device, "writer_generation": generation or
              assessment["writer_generation"]},
        headers=headers or key(),
    )


def view(client, assessment, device=None):
    return client.get(
        f"/api/v1/assessments/{assessment['id']}",
        headers={"X-Assessment-Device": device} if device else {},
    )


def save(client, assessment, device, answers, *, revision=0, index=0, generation=None):
    return client.put(
        f"/api/v1/assessments/{assessment['id']}/draft",
        json={
            "device_id": device,
            "writer_generation": generation or assessment["writer_generation"],
            "expected_revision": revision, "current_index": index, "answers": answers,
        },
    )


def takeover(client, assessment, device, *, headers=None):
    return client.post(
        f"/api/v1/assessments/{assessment['id']}/takeover",
        json={"device_id": device, "writer_generation": assessment["writer_generation"]},
        headers=headers or key(),
    )


def finalize(client, assessment, device, answers, *, lost=False, headers=None):
    return client.post(
        f"/api/v1/assessments/{assessment['id']}/finish",
        json={"device_id": device, "writer_generation": assessment["writer_generation"],
              "answers": answers, "connection_lost": lost},
        headers=headers or key(),
    )


def correct_answers(content, assessment):
    return {task["id"]: {"answer": expected(content, task), "active_seconds": 10}
            for task in assessment["tasks"]}


def released_rows(client, guest_id, assessment):
    from app.assessments.evidence import released_evidence

    with client.app.state.database.transaction() as db:
        return [row for row in released_evidence(db, [guest_id])
                if row["assessment_id"] == assessment["id"]]


def twins(assessment_factory):
    first = assessment_factory()
    first.post("/api/v1/guest", json={})
    second = assessment_factory(database_url=first.app.state.settings.database_url)
    second.cookies.update(first.cookies)
    return first, second


def test_prepare_freezes_thirteen_public_slots_without_starting_a_timer(assessment_client):
    device = str(uuid4())
    response = prepare(assessment_client, device=device)
    assert response.status_code == 200, response.text
    prepared = response.json()
    assert prepared["status"] == "prepared"
    assert prepared["started_at"] is None
    assert prepared["deadline_at"] is None
    assert prepared["duration_minutes"] == 65
    assert prepared["draft_revision"] == 0
    assert prepared["writer_generation"] == 1
    assert prepared["can_write"] is True
    assert len(prepared["tasks"]) == 13
    assert {task["slot"] for task in prepared["tasks"]} == set(range(1, 14))
    assert len({task["id"] for task in prepared["tasks"]}) == 13
    assert prepared["server_result"] is None
    assert prepared["local_result"] is None
    for task in prepared["tasks"]:
        assert not {"answer", "hints", "solution", "source"} & task.keys()
        assert task["hint_count"] == 0


def test_only_explicit_activation_starts_an_immutable_server_deadline(assessment_client, clock):
    device = str(uuid4())
    prepared = prepare(assessment_client, device=device, duration_minutes=15).json()
    clock[0] += timedelta(days=1)
    pending = view(assessment_client, prepared, device)
    assert pending.status_code == 200
    assert pending.json()["started_at"] is None
    assert pending.json()["deadline_at"] is None
    assert activate(assessment_client, prepared, str(uuid4())).status_code == 409
    active = activate(assessment_client, prepared, device)
    assert active.status_code == 200, active.text
    active = active.json()
    assert active["status"] == "active"
    assert datetime.fromisoformat(active["started_at"]) == clock[0]
    deadline = clock[0] + timedelta(minutes=15)
    assert datetime.fromisoformat(active["deadline_at"]) == deadline
    clock[0] += timedelta(minutes=2)
    repeated = activate(assessment_client, prepared, device).json()
    assert repeated["started_at"] == active["started_at"]
    assert repeated["deadline_at"] == active["deadline_at"]
    assert view(assessment_client, active, device).json()["can_write"] is True
    assert view(assessment_client, active).json()["can_write"] is False
    assert view(assessment_client, active, str(uuid4())).json()["can_write"] is False


def test_drafts_accept_intermediate_strings_but_never_silently_overwrite(assessment_client):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    task_id = assessment["tasks"][0]["id"]
    first = {task_id: {"answer": "−", "active_seconds": 12}}
    assert save(assessment_client, assessment, device, first).status_code == 409
    assert activate(assessment_client, assessment, device).status_code == 200
    saved = save(assessment_client, assessment, device, first, index=3)
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft_revision"] == 1
    assert saved.json()["drafts"] == first
    assert saved.json()["current_index"] == 3
    replacement = {task_id: {"answer": "0002,", "active_seconds": 8}}
    stale = save(assessment_client, assessment, device, replacement)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "assessment_draft_conflict"
    assert view(assessment_client, assessment).json()["drafts"] == first
    accepted = save(assessment_client, assessment, device, replacement, revision=1, index=12)
    assert accepted.status_code == 200
    state = view(assessment_client, assessment, device).json()
    assert state["drafts"][task_id] == {"answer": "0002,", "active_seconds": 12}
    assert state["draft_revision"] == 2
    assert state["current_index"] == 12
    assert state["server_result"] is None
    assert state["local_result"] is None


def test_takeover_is_explicit_idempotent_and_invalidates_the_old_writer(assessment_factory):
    one = assessment_factory()
    one.post("/api/v1/guest", json={})
    two = assessment_factory(database_url=one.app.state.settings.database_url)
    two.cookies.update(one.cookies)
    device_one, device_two = str(uuid4()), str(uuid4())
    assessment = prepare(one, device=device_one).json()
    activate(one, assessment, device_one)
    task_id = assessment["tasks"][0]["id"]
    answers = {task_id: {"answer": "14", "active_seconds": 2}}
    assert save(one, assessment, device_one, answers).status_code == 200
    assert view(two, assessment, device_two).json()["can_write"] is False
    assert save(two, assessment, device_two, answers, revision=1).status_code == 409
    headers = key()
    adopted = takeover(two, assessment, device_two, headers=headers)
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["writer_generation"] == 2
    assert adopted.json()["drafts"] == answers
    assert takeover(two, assessment, device_two, headers=headers).content == adopted.content
    assert takeover(one, assessment, device_one, headers=headers).status_code == 409
    assert takeover(one, assessment, device_one).status_code == 409
    assert view(one, assessment, device_one).json()["can_write"] is False
    assert save(one, assessment, device_one, answers, revision=1).status_code == 409
    assert save(two, adopted.json(), device_two, {}, revision=1).status_code == 200


def test_finish_grades_last_values_in_exam_format_and_freezes_one_result(
    assessment_client, content, clock
):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device, mode="diagnostic").json()
    activate(assessment_client, assessment, device)
    one, two, three = [task["id"] for task in assessment["tasks"][:3]]
    assert save(assessment_client, assessment, device, {
        one: {"answer": "99999", "active_seconds": 1}
    }).status_code == 200
    answers = correct_answers(content, assessment)
    normalized = answers[one]["answer"]
    answers[one]["answer"] = " 000" + normalized.replace(",", ".") + " "
    answers[two]["answer"] = "1/2"
    answers[three]["answer"] = ""
    headers = key()
    completed = finalize(assessment_client, assessment, device, answers, headers=headers)
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert completed.json()["status"] == "completed"
    assert completed.json()["can_write"] is False
    assert completed.json()["local_result"] is None
    assert result["score"] == 11
    assert result["total"] == 13
    assert result["answered"] == 11
    assert result["skipped"] == 1
    assert result["format_errors"] == 1
    assert result["independent_total"] == 11
    assert result["rows"][0]["normalized"] == normalized
    assert result["rows"][0]["correct"] is True
    assert result["rows"][0]["first_draft"]["answer"] == "99999"
    invalid = result["rows"][1]
    assert invalid["format_error"] is True
    assert invalid["normalized"] is None
    assert invalid["independent"] is False
    assert invalid["label"] == "Ошибка формата"
    assert result["rows"][2]["skipped"] is True
    assert result["rows"][2]["format_error"] is False
    assert all(row["expected"] and row["solution"] for row in result["rows"])
    clock[0] += timedelta(hours=1)
    assert finalize(assessment_client, assessment, device, answers, headers=headers).content == (
        completed.content
    )
    replay = finalize(assessment_client, assessment, device, answers)
    assert replay.json()["server_result"] == result
    answers[one]["answer"] = "0"
    conflict = finalize(assessment_client, assessment, device, answers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "assessment_snapshot_conflict"
    changed_replay = finalize(assessment_client, assessment, device, answers, headers=headers)
    assert changed_replay.status_code == 409
    assert save(assessment_client, assessment, device, {}, revision=1).status_code == 409
    assert view(assessment_client, assessment).json()["server_result"] == result


def test_deadline_worker_survives_restart_and_keeps_local_and_server_results_separate(
    assessment_factory, content, clock
):
    from app.assessments.models import AssessmentRecord

    original = assessment_factory()
    original.post("/api/v1/guest", json={})
    device = str(uuid4())
    assessment = prepare(original, device=device, duration_minutes=15).json()
    active = activate(original, assessment, device).json()
    one, two = [task["id"] for task in assessment["tasks"][:2]]
    server_answers = {
        one: {"answer": expected(content, assessment["tasks"][0]), "active_seconds": 17},
        two: {"answer": "2,", "active_seconds": 4},
    }
    assert save(original, assessment, device, server_answers).status_code == 200
    clock[0] += timedelta(minutes=14, seconds=59)
    assert original.app.state.assessments.reconcile_deadlines() == 0
    clock[0] += timedelta(hours=2)
    restarted = assessment_factory(database_url=original.app.state.settings.database_url)
    restarted.cookies.update(original.cookies)
    # Read persisted state before any HTTP request or explicit reconciliation:
    # the real lifespan worker must already have frozen the expired exam.
    with restarted.app.state.database.transaction() as db:
        persisted = db.get(AssessmentRecord, assessment["id"])
        assert persisted is not None
        assert persisted.status == "awaiting_snapshot"
        assert persisted.released_at is None
        assert persisted.local_result is None
        assert persisted.drafts == server_answers
        startup_server = persisted.server_result
        assert startup_server is not None
        assert startup_server["reason"] == "deadline"
        assert startup_server["snapshot_at"] == active["deadline_at"]
        assert startup_server["score"] == 1
    assert restarted.app.state.assessments.reconcile_deadlines() == 0
    pending = view(restarted, assessment, device).json()
    assert pending["status"] == "awaiting_snapshot"
    assert pending["server_result"] is None
    assert pending["local_result"] is None
    assert pending["drafts"] == server_answers
    assert "ожидается" in pending["result_notice"]
    finished = finalize(
        restarted, assessment, device, correct_answers(content, assessment), lost=True
    )
    assert finished.status_code == 200, finished.text
    finished = finished.json()
    server, local = finished["server_result"], finished["local_result"]
    assert server == startup_server
    assert server["score"] == 1
    assert server["snapshot_at"] == active["deadline_at"]
    assert server["elapsed_seconds"] == 900
    assert server["reason"] == "deadline"
    assert server["rows"][1]["raw"] == "2,"
    assert server["rows"][1]["format_error"] is True
    assert server["rows"][1]["normalized"] is None
    assert local["score"] == 13
    assert local["connection_lost"] is True
    assert local["independent_total"] == 0
    assert finished["drafts"] == server_answers
    assert restarted.app.state.assessments.reconcile_deadlines() == 0
    assert view(original, assessment).json()["server_result"] == server


def test_learning_adapter_releases_only_canonical_rows_after_final_snapshot_acceptance(
    assessment_factory, content, clock
):
    from app.assessments.evidence import released_evidence

    client = assessment_factory()
    guest_id = client.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    assessment = prepare(client, device=device, duration_minutes=15).json()
    activate(client, assessment, device)
    answers = correct_answers(content, assessment)
    one = assessment["tasks"][0]["id"]
    save(client, assessment, device, {one: answers[one]})

    def evidence(owners):
        with client.app.state.database.transaction() as db:
            return released_evidence(db, owners)

    assert evidence([guest_id]) == []
    clock[0] += timedelta(minutes=15)
    client.app.state.assessments.reconcile_deadlines()
    assert evidence([guest_id]) == []
    finished = finalize(client, assessment, device, answers, lost=True).json()
    rows = evidence([guest_id, guest_id])
    assert len(rows) == 13
    assert len({row["id"] for row in rows}) == 13
    assert sum(row["correct"] for row in rows) == 1
    assert sum(row["independent"] for row in rows) == 1
    assert {row["result_source"] for row in rows} == {"server"}
    assert {row["assessment_id"] for row in rows} == {assessment["id"]}
    assert rows[0]["at"] == datetime.fromisoformat(finished["server_result"]["snapshot_at"])
    assert rows[0]["profile_revision"] == assessment["profile_revision"]
    assert rows[0]["task_snapshot"]["revision"] == assessment["tasks"][0]["revision"]
    assert evidence([str(uuid4())]) == []
    assert evidence([guest_id]) == rows
    assert client.get("/api/v1/export").json()["sessions"] == []


def test_missing_slot_rejects_the_whole_assessment_and_replays_the_bank_error(
    assessment_client, content_dir
):
    task_file = content_dir / "tasks.json"
    original = task_file.read_text(encoding="utf-8")
    tasks = json.loads(original)
    task_file.write_text(
        json.dumps([task for task in tasks if task["slot"] != 13]), encoding="utf-8"
    )
    device, headers = str(uuid4()), key()
    refused = prepare(assessment_client, device=device, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "assessment_bank_incomplete"
    task_file.write_text(original, encoding="utf-8")
    assert prepare(assessment_client, device=device, headers=headers).content == refused.content
    assert len(prepare(assessment_client, device=device).json()["tasks"]) == 13


def test_profile_itself_must_have_exactly_thirteen_slots(assessment_client, content_dir):
    for filename, list_key in (
        ("profile.json", "slots"), ("tasks.json", None), ("lessons.json", None)
    ):
        path = content_dir / filename
        value = json.loads(path.read_text(encoding="utf-8"))
        if list_key:
            value[list_key] = [slot for slot in value[list_key] if slot["number"] != 13]
        else:
            value = [item for item in value if item["slot"] != 13]
        path.write_text(json.dumps(value), encoding="utf-8")
    response = prepare(assessment_client)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "assessment_profile_invalid"


@pytest.mark.parametrize("duration", [14, 181, "65", True, 65.5])
def test_prepare_rejects_invalid_duration_types_and_bounds(assessment_client, duration):
    assert prepare(assessment_client, duration_minutes=duration).status_code == 422


def test_frozen_profile_tasks_and_reference_survive_content_updates(
    assessment_client, content_dir, content
):
    device, headers = str(uuid4()), key()
    prepared = prepare(assessment_client, device=device, headers=headers)
    assessment = prepared.json()
    tasks_file, profile_file = content_dir / "tasks.json", content_dir / "profile.json"
    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    for task in tasks:
        task.update(answer="999999", revision="new-test-revision", statement="Изменённое условие.")
    profile["revision"] = "new-test-profile"
    tasks_file.write_text(json.dumps(tasks), encoding="utf-8")
    profile_file.write_text(json.dumps(profile), encoding="utf-8")
    assert prepare(assessment_client, device=device, headers=headers).content == prepared.content
    changed_body = prepare(assessment_client, device=device, mode="diagnostic", headers=headers)
    assert changed_body.status_code == 409
    current = view(assessment_client, assessment).json()
    assert current["profile"] == assessment["profile"]
    assert current["tasks"] == assessment["tasks"]
    activate(assessment_client, assessment, device)
    result = finalize(assessment_client, assessment, device, correct_answers(content, assessment))
    assert result.status_code == 200
    assert result.json()["server_result"]["score"] == 13
    assert result.json()["tasks"] == assessment["tasks"]


def test_diagnostic_can_pause_and_resume_without_a_deadline(assessment_client, content, clock):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device, mode="diagnostic").json()
    active = activate(assessment_client, assessment, device).json()
    assert active["deadline_at"] is None
    clock[0] += timedelta(days=7)
    assert assessment_client.app.state.assessments.reconcile_deadlines() == 0
    restored = view(assessment_client, assessment, device).json()
    assert restored["status"] == "active"
    assert restored["started_at"] == active["started_at"]
    assert restored["server_result"] is None
    saved = save(assessment_client, assessment, device, correct_answers(content, assessment))
    assert saved.status_code == 200
    finished = finalize(assessment_client, assessment, device, correct_answers(content, assessment))
    assert finished.status_code == 200
    assert finished.json()["server_result"]["score"] == 13
    assert finished.json()["server_result"]["active_seconds"] == 130


@pytest.mark.parametrize("trigger", ["get", "draft", "writer_conflict", "replay", "key_conflict"])
def test_deadline_is_committed_even_when_the_triggering_request_is_rejected_or_replayed(
    assessment_client, clock, trigger
):
    device, headers = str(uuid4()), key()
    assessment = prepare(assessment_client, device=device, duration_minutes=15).json()
    activated = activate(assessment_client, assessment, device, headers=headers)
    clock[0] += timedelta(minutes=15)
    if trigger == "get":
        response = view(assessment_client, assessment, device)
        assert response.status_code == 200
        assert response.json()["status"] == "awaiting_snapshot"
    elif trigger == "draft":
        assert save(assessment_client, assessment, device, {}).status_code == 409
    elif trigger == "writer_conflict":
        assert finalize(assessment_client, assessment, str(uuid4()), {}).status_code == 409
    elif trigger == "replay":
        replay = activate(assessment_client, assessment, device, headers=headers)
        assert replay.content == activated.content
    else:
        conflict = finalize(assessment_client, assessment, device, {}, headers=headers)
        assert conflict.status_code == 409
    # A fresh worker would report one if the rejected request rolled back its freeze.
    assert assessment_client.app.state.assessments.reconcile_deadlines() == 0
    pending = view(assessment_client, assessment).json()
    assert pending["status"] == "awaiting_snapshot"
    assert pending["server_result"] is None
    assert pending["local_result"] is None


def test_no_help_results_or_practice_escape_routes_before_release(assessment_client, clock):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device, duration_minutes=15).json()
    activate(assessment_client, assessment, device)
    task_id = assessment["tasks"][0]["id"]
    for pending in (False, True):
        if pending:
            clock[0] += timedelta(minutes=15)
        current = view(assessment_client, assessment, device)
        assert current.json()["server_result"] is None
        assert current.json()["local_result"] is None
        for field in ("expected", "solution", "hints", "source"):
            assert f'"{field}":' not in current.text
        assert assessment_client.get(f"/api/v1/sessions/{assessment['id']}").status_code == 404
        for prefix in ("assessments", "sessions"):
            for suffix, body in (
                ("hints", {"task_id": task_id, "level": 1}),
                ("solution", {"task_id": task_id}),
                ("attempts", {"task_id": task_id, "answer": "0", "active_seconds": 0,
                              "skipped": False}),
            ):
                response = assessment_client.post(
                    f"/api/v1/{prefix}/{assessment['id']}/{suffix}", json=body, headers=key()
                )
                assert response.status_code == 404
        exported = assessment_client.get("/api/v1/export").json()
        assert exported["sessions"] == []
        progress = assessment_client.get("/api/v1/progress").json()
        assert progress["independent_total"] == 0
        assert progress["mistakes"] == []


def test_foreign_owner_cannot_read_mutate_or_release_an_assessment(assessment_factory):
    owner, stranger = assessment_factory(), None
    owner.post("/api/v1/guest", json={})
    stranger = assessment_factory(database_url=owner.app.state.settings.database_url)
    device = str(uuid4())
    assessment = prepare(owner, device=device).json()
    assert view(stranger, assessment, device).status_code == 401
    stranger.post("/api/v1/guest", json={})
    assert view(stranger, assessment, device).status_code == 404
    assert activate(stranger, assessment, device).status_code == 404
    assert save(stranger, assessment, device, {}).status_code == 404
    assert takeover(stranger, assessment, device).status_code == 404
    assert finalize(stranger, assessment, device, {}).status_code == 404
    assert view(owner, assessment, device).json()["status"] == "prepared"


@pytest.mark.parametrize("raw,normalized,format_error,skipped", [
    ("−0", "0", False, False),
    ("0002.50", "2,5", False, False),
    ("1/2", None, True, False),
    ("1e3", None, True, False),
    ("2+2", None, True, False),
    ("2,", None, True, False),
    ("   ", None, False, True),
    ("0", "0", False, False),
])
def test_final_input_is_either_exact_numeric_skip_or_explicit_format_error(
    assessment_client, raw, normalized, format_error, skipped
):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    activate(assessment_client, assessment, device)
    task_id = assessment["tasks"][0]["id"]
    answers = {task_id: {"answer": raw, "active_seconds": 3}}
    assert save(assessment_client, assessment, device, answers).status_code == 200
    response = finalize(assessment_client, assessment, device, answers)
    assert response.status_code == 200
    row = response.json()["server_result"]["rows"][0]
    assert row["raw"] == raw
    assert row["normalized"] == normalized
    assert row["format_error"] is format_error
    assert row["skipped"] is skipped
    assert row["independent"] is (normalized is not None)


@pytest.mark.parametrize("field,value", [
    ("answer", "x" * 65), ("answer", 12), ("active_seconds", -1),
    ("active_seconds", 86401), ("active_seconds", True), ("active_seconds", "5"),
])
def test_invalid_draft_shape_is_atomic(assessment_client, field, value):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    activate(assessment_client, assessment, device)
    task_id = assessment["tasks"][0]["id"]
    answers = {task_id: {"answer": "1", "active_seconds": 0, field: value}}
    assert save(assessment_client, assessment, device, answers).status_code == 422
    assert finalize(assessment_client, assessment, device, answers).status_code == 422
    state = view(assessment_client, assessment).json()
    assert state["draft_revision"] == 0
    assert state["drafts"] == {}
    assert state["status"] == "active"


def test_draft_maps_are_bounded_to_known_tasks_and_valid_positions(assessment_client):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    activate(assessment_client, assessment, device)
    unknown = {"foreign-task": {"answer": "5", "active_seconds": 0}}
    assert save(assessment_client, assessment, device, unknown).status_code == 422
    assert finalize(assessment_client, assessment, device, unknown).status_code == 422
    too_many = {f"foreign-{index}": {"answer": "", "active_seconds": 0} for index in range(14)}
    assert save(assessment_client, assessment, device, too_many).status_code == 422
    assert save(assessment_client, assessment, device, {}, index=13).status_code == 422
    assert save(assessment_client, assessment, device, {}, index=-1).status_code == 422
    assert view(assessment_client, assessment).json()["draft_revision"] == 0


def test_first_numeric_answer_is_preserved_separately_from_blank_and_final_drafts(
    assessment_client, content, clock
):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device, mode="diagnostic").json()
    activate(assessment_client, assessment, device)
    task = assessment["tasks"][0]
    first_value = expected(content, task)
    for revision, raw in enumerate(("", "−", first_value, "999999")):
        clock[0] += timedelta(seconds=1)
        assert save(assessment_client, assessment, device, {
            task["id"]: {"answer": raw, "active_seconds": revision + 1}
        }, revision=revision).status_code == 200
    finished = finalize(assessment_client, assessment, device, {
        task["id"]: {"answer": "999999", "active_seconds": 4}
    }).json()
    row = finished["server_result"]["rows"][0]
    assert row["first_draft"]["answer"] == ""
    assert row["first_answer"]["answer"] == first_value
    assert row["first_answer"]["active_seconds"] == 3
    assert row["raw"] == "999999"
    assert row["correct"] is False
    assert row["independent"] is True


@pytest.mark.parametrize("kind", ["hint", "solution", "attempt"])
def test_prior_practice_and_reference_exposure_prevent_independent_credit(
    assessment_client, single_slot_bank, kind
):
    practice = start(assessment_client, slots=[1]).json()
    task = practice["tasks"][0]
    if kind == "attempt":
        response = practice_answer(
            assessment_client, practice, task, expected(single_slot_bank, task)
        )
    else:
        suffix = "hints" if kind == "hint" else "solution"
        body = {"task_id": task["id"], **({"level": 1} if kind == "hint" else {})}
        response = assessment_client.post(f"/api/v1/sessions/{practice['id']}/{suffix}", json=body)
    assert response.status_code == 200
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    assert assessment["tasks"][0]["id"] == task["id"]
    activate(assessment_client, assessment, device)
    result = finalize(
        assessment_client, assessment, device, correct_answers(single_slot_bank, assessment)
    ).json()["server_result"]
    assert result["score"] == 13
    assert result["independent_total"] == 12
    assert result["rows"][0]["assisted"] is True
    assert result["rows"][0]["independent"] is False


@pytest.mark.parametrize("mode", ["diagnostic", "exam"])
def test_reference_after_first_numeric_draft_prevents_final_independent_credit(
    assessment_factory, single_slot_bank, clock, mode
):
    client = assessment_factory()
    guest_id = client.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    assessment = prepare(client, device=device, mode=mode).json()
    reference = prepare(client, device=device, mode="diagnostic").json()
    task = assessment["tasks"][0]
    assert reference["tasks"][0]["id"] == task["id"]
    assert activate(client, assessment, device).status_code == 200
    clock[0] += timedelta(seconds=1)
    first = {"answer": "999999", "active_seconds": 3}
    first_answer = {**first, "recorded_at": clock[0].isoformat()}
    assert save(client, assessment, device, {task["id"]: first}).status_code == 200

    clock[0] += timedelta(seconds=1)
    assert activate(client, reference, device).status_code == 200
    exposed = finalize(client, reference, device, {})
    assert exposed.status_code == 200, exposed.text
    reference_result = exposed.json()["server_result"]
    assert reference_result["answered"] == 0
    assert reference_result["rows"][0]["expected"] == expected(single_slot_bank, task)
    assert reference_result["rows"][0]["solution"]
    assert released_rows(client, guest_id, assessment) == []

    clock[0] += timedelta(seconds=1)
    completed = finalize(client, assessment, device, {
        task["id"]: {"answer": expected(single_slot_bank, task), "active_seconds": 10},
    })
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert result["score"] == 1
    row = result["rows"][0]
    assert row["correct"] is True
    assert row["first_draft"] == first_answer
    assert row["first_answer"] == first_answer
    assert row["assisted"] is True
    assert row["independent"] is False
    assert result["independent_total"] == 0
    evidence = released_rows(client, guest_id, assessment)
    assert len(evidence) == 13
    assert evidence[0]["id"] == row["id"]
    assert evidence[0]["correct"] is True
    assert evidence[0]["assisted"] is True
    assert evidence[0]["first_answer"] == first_answer
    assert not any(item["independent"] for item in evidence)


@pytest.mark.parametrize("kind", ["hint", "solution"])
@pytest.mark.parametrize("lost", [False, True])
def test_practice_help_after_first_numeric_draft_prevents_final_independent_credit(
    assessment_factory, single_slot_bank, clock, kind, lost
):
    client = assessment_factory()
    guest_id = client.post("/api/v1/guest", json={}).json()["id"]
    practice = start(client, slots=[1]).json()
    task = practice["tasks"][0]
    device = str(uuid4())
    assessment = prepare(client, device=device).json()
    assert assessment["tasks"][0]["id"] == task["id"]
    assert activate(client, assessment, device).status_code == 200
    clock[0] += timedelta(seconds=1)
    first = {"answer": "999999", "active_seconds": 3}
    first_answer = {**first, "recorded_at": clock[0].isoformat()}
    assert save(client, assessment, device, {task["id"]: first}).status_code == 200
    clock[0] += timedelta(seconds=1)
    answers = correct_answers(single_slot_bank, assessment)
    assert save(client, assessment, device, answers, revision=1).status_code == 200

    clock[0] += timedelta(seconds=1)
    suffix = "hints" if kind == "hint" else "solution"
    body = {"task_id": task["id"], **({"level": 1} if kind == "hint" else {})}
    assert client.post(f"/api/v1/sessions/{practice['id']}/{suffix}", json=body).status_code == 200
    assert released_rows(client, guest_id, assessment) == []
    clock[0] += timedelta(seconds=1)
    completed = finalize(client, assessment, device, answers, lost=lost)
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert result["score"] == 13
    assert result["independent_total"] == 12
    row = result["rows"][0]
    assert row["correct"] is True
    assert row["assisted"] is True
    assert row["independent"] is False
    assert row["first_draft"] == first_answer
    assert row["first_answer"] == first_answer
    if lost:
        assert completed.json()["local_result"]["independent_total"] == 0
    evidence = released_rows(client, guest_id, assessment)
    assert len(evidence) == 13
    assert sum(item["independent"] for item in evidence) == 12
    assert evidence[0]["id"] == row["id"]
    assert evidence[0]["correct"] is True
    assert evidence[0]["assisted"] is True
    assert evidence[0]["independent"] is False
    assert evidence[0]["first_answer"] == first_answer


@pytest.mark.parametrize("reference_before_freeze", [True, False])
def test_deadline_eligibility_is_frozen_separately_from_first_input_and_late_exposure(
    assessment_factory, single_slot_bank, clock, reference_before_freeze
):
    from app.assessments.models import AssessmentRecord

    client = assessment_factory()
    guest_id = client.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    assessment = prepare(client, device=device, duration_minutes=15).json()
    reference = prepare(client, device=device, mode="diagnostic").json()
    task = assessment["tasks"][0]
    assert reference["tasks"][0]["id"] == task["id"]
    active = activate(client, assessment, device).json()
    clock[0] += timedelta(seconds=1)
    first = {"answer": "999999", "active_seconds": 3}
    first_answer = {**first, "recorded_at": clock[0].isoformat()}
    assert save(client, assessment, device, {task["id"]: first}).status_code == 200
    clock[0] += timedelta(seconds=1)
    server_answers = {
        task["id"]: {"answer": expected(single_slot_bank, task), "active_seconds": 10},
    }
    assert save(client, assessment, device, server_answers, revision=1).status_code == 200
    if reference_before_freeze:
        clock[0] += timedelta(seconds=1)
        assert activate(client, reference, device).status_code == 200
        assert finalize(client, reference, device, {}).status_code == 200

    clock[0] = datetime.fromisoformat(active["deadline_at"])
    client.app.state.assessments.reconcile_deadlines()
    with client.app.state.database.transaction() as db:
        persisted = db.get(AssessmentRecord, assessment["id"])
        assert persisted is not None
        assert persisted.status == "awaiting_snapshot"
        assert persisted.released_at is None
        assert persisted.local_result is None
        frozen = persisted.server_result
        assert frozen is not None
        assert frozen["reason"] == "deadline"
        assert frozen["snapshot_at"] == active["deadline_at"]
        assert frozen["score"] == 1
        row = frozen["rows"][0]
        assert row["first_answer"] == first_answer
        assert row["assisted"] is reference_before_freeze
        assert row["independent"] is not reference_before_freeze
    pending = view(client, assessment, device).json()
    assert pending["server_result"] is None
    assert pending["local_result"] is None
    assert pending["drafts"] == server_answers
    assert released_rows(client, guest_id, assessment) == []

    clock[0] += timedelta(seconds=1)
    if not reference_before_freeze:
        assert activate(client, reference, device).status_code == 200
        assert finalize(client, reference, device, {}).status_code == 200
    clock[0] += timedelta(seconds=1)
    completed = finalize(
        client, assessment, device, correct_answers(single_slot_bank, assessment), lost=True
    )
    assert completed.status_code == 200, completed.text
    finished = completed.json()
    assert finished["server_result"] == frozen
    assert finished["drafts"] == server_answers
    local = finished["local_result"]
    assert local["score"] == 13
    assert local["independent_total"] == 0
    assert local["snapshot_at"] != frozen["snapshot_at"]
    assert local["rows"][0]["assisted"] is True
    assert local["rows"][0]["first_answer"] == first_answer
    evidence = released_rows(client, guest_id, assessment)
    assert len(evidence) == 13
    assert sum(item["correct"] for item in evidence) == 1
    assert sum(item["independent"] for item in evidence) == int(not reference_before_freeze)
    assert evidence[0]["id"] == row["id"]
    assert evidence[0]["id"] != local["rows"][0]["id"]
    assert evidence[0]["assisted"] is reference_before_freeze
    assert evidence[0]["independent"] is not reference_before_freeze
    assert evidence[0]["first_answer"] == first_answer
    assert view(client, assessment).json()["server_result"] == frozen


def test_multiple_frozen_assessments_reserve_one_independent_instance(
    assessment_client, single_slot_bank, clock
):
    device = str(uuid4())
    first = prepare(assessment_client, device=device, duration_minutes=15).json()
    second = prepare(assessment_client, device=device, duration_minutes=15).json()
    assert [task["id"] for task in first["tasks"]] == [task["id"] for task in second["tasks"]]
    for assessment in (first, second):
        activate(assessment_client, assessment, device)
        save(assessment_client, assessment, device, correct_answers(single_slot_bank, assessment))
    clock[0] += timedelta(minutes=15)
    assert assessment_client.app.state.assessments.reconcile_deadlines() == 2
    results = [finalize(
        assessment_client, assessment, device, correct_answers(single_slot_bank, assessment),
        lost=True,
    ).json() for assessment in (second, first)]
    assert sum(item["server_result"]["independent_total"] for item in results) == 13
    assert all(item["local_result"]["independent_total"] == 0 for item in results)
    third = prepare(assessment_client, device=device).json()
    activate(assessment_client, third, device)
    final = finalize(
        assessment_client, third, device, correct_answers(single_slot_bank, third)
    ).json()
    assert final["server_result"]["score"] == 13
    assert final["server_result"]["independent_total"] == 0


def test_assessment_selection_prefers_unseen_instances(assessment_client):
    one = prepare(assessment_client).json()
    two = prepare(assessment_client).json()
    assert not {task["id"] for task in one["tasks"]} & {task["id"] for task in two["tasks"]}


def test_concurrent_prepare_replays_the_same_assessment_across_engines(assessment_factory):
    one, two = twins(assessment_factory)
    device, headers = str(uuid4()), key()
    responses = race(*[
        lambda client=client: prepare(client, device=device, headers=headers)
        for client in (one, two) * 3
    ])
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == responses[0].content for response in responses)


def test_concurrent_drafts_have_one_revision_winner(assessment_factory):
    one, two = twins(assessment_factory)
    device = str(uuid4())
    assessment = prepare(one, device=device).json()
    activate(one, assessment, device)
    task_id = assessment["tasks"][0]["id"]
    responses = race(
        lambda: save(one, assessment, device, {task_id: {"answer": "10", "active_seconds": 5}}),
        lambda: save(two, assessment, device, {task_id: {"answer": "20", "active_seconds": 6}}),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = view(one, assessment, device).json()
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert saved["draft_revision"] == 1
    assert saved["drafts"] == winner["drafts"]


def test_competing_takeovers_have_one_generation_winner(assessment_factory):
    one, two = twins(assessment_factory)
    first, second, third = str(uuid4()), str(uuid4()), str(uuid4())
    assessment = prepare(one, device=first).json()
    responses = race(
        lambda: takeover(one, assessment, second), lambda: takeover(two, assessment, third)
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert view(one, assessment, first).json()["can_write"] is False
    assert view(one, assessment, first).json()["writer_generation"] == 2
    assert sum(view(one, assessment, device).json()["can_write"] for device in (second, third)) == 1


def test_concurrent_repeated_finish_returns_one_canonical_result(assessment_factory, content):
    one, two = twins(assessment_factory)
    device, headers = str(uuid4()), key()
    assessment = prepare(one, device=device).json()
    activate(one, assessment, device)
    answers = correct_answers(content, assessment)
    responses = race(*[
        lambda client=client: finalize(client, assessment, device, answers, headers=headers)
        for client in (one, two) * 3
    ])
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == responses[0].content for response in responses)
    frozen = responses[0].json()["server_result"]
    assert frozen["score"] == 13
    assert view(one, assessment).json()["server_result"] == frozen


@pytest.mark.parametrize("same_key", [False, True])
def test_competing_final_snapshots_cannot_change_the_winner(
    assessment_factory, content, same_key
):
    one, two = twins(assessment_factory)
    device, headers = str(uuid4()), key()
    assessment = prepare(one, device=device).json()
    activate(one, assessment, device)
    answers = correct_answers(content, assessment)
    responses = race(
        lambda: finalize(one, assessment, device, answers, headers=headers),
        lambda: finalize(two, assessment, device, {}, headers=headers if same_key else key()),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    result = next(
        response.json()["server_result"] for response in responses if response.status_code == 200
    )
    assert result["score"] == (13 if responses[0].status_code == 200 else 0)
    assert view(two, assessment).json()["server_result"] == result


def test_deadline_workers_racing_finish_and_draft_keep_the_exact_server_snapshot(
    assessment_factory, content, clock
):
    one, two = twins(assessment_factory)
    device = str(uuid4())
    assessment = prepare(one, device=device, duration_minutes=15).json()
    active = activate(one, assessment, device).json()
    answers = correct_answers(content, assessment)
    first = assessment["tasks"][0]["id"]
    save(one, assessment, device, {first: answers[first]})
    clock[0] += timedelta(minutes=15)
    responses = race(
        lambda: one.app.state.assessments.reconcile_deadlines(),
        lambda: two.app.state.assessments.reconcile_deadlines(),
        lambda: finalize(two, assessment, device, answers, lost=True),
        lambda: save(one, assessment, device, answers, revision=1),
    )
    assert sum(responses[:2]) <= 1
    assert responses[2].status_code == 200
    assert responses[3].status_code == 409
    result = responses[2].json()
    assert result["server_result"]["score"] == 1
    assert result["server_result"]["snapshot_at"] == active["deadline_at"]
    assert result["local_result"]["score"] == 13
    assert one.app.state.assessments.reconcile_deadlines() == 0
    assert view(one, assessment).json()["server_result"] == result["server_result"]


def test_finish_requires_activation_and_failed_request_replay_stays_failed(assessment_client):
    device, headers = str(uuid4()), key()
    assessment = prepare(assessment_client, device=device).json()
    rejected = finalize(assessment_client, assessment, device, {}, headers=headers)
    assert rejected.status_code == 409
    assert view(assessment_client, assessment).json()["server_result"] is None
    activate(assessment_client, assessment, device)
    replay = finalize(assessment_client, assessment, device, {}, headers=headers)
    assert replay.content == rejected.content
    assert finalize(assessment_client, assessment, device, {}).status_code == 200


def test_offline_finish_received_early_preserves_the_last_online_drafts(assessment_client, content):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    activate(assessment_client, assessment, device)
    answers = correct_answers(content, assessment)
    finished = finalize(assessment_client, assessment, device, answers, lost=True).json()
    assert finished["server_result"]["score"] == 0
    assert finished["local_result"]["score"] == 13
    assert finished["local_result"]["independent_total"] == 0
    replay = finalize(assessment_client, assessment, device, answers, lost=True).json()
    assert replay["local_result"] == finished["local_result"]
    assert finalize(assessment_client, assessment, device, answers, lost=False).status_code == 409


def test_finish_hash_ignores_map_order_and_treats_omitted_tasks_as_blank(
    assessment_client, content
):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device).json()
    activate(assessment_client, assessment, device)
    first = assessment["tasks"][0]
    initial = {first["id"]: {"answer": expected(content, first), "active_seconds": 1}}
    frozen = finalize(assessment_client, assessment, device, initial).json()["server_result"]
    equivalent = {task["id"]: initial.get(task["id"], {"answer": "", "active_seconds": 0})
                  for task in reversed(assessment["tasks"])}
    replay = finalize(assessment_client, assessment, device, equivalent)
    assert replay.status_code == 200
    assert replay.json()["server_result"] == frozen


def test_additive_migration_preserves_populated_practice_history_and_disables_downgrade(
    tmp_path, content_dir, content, clock, client_factory
):
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import JSON, MetaData, Table, select

    from app.assessments.api import router
    from app.assessments.service import AssessmentService
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import MUTATION_HEADERS, TEST_ORIGIN

    source = client_factory()
    assert source.post("/api/v1/guest", json={}).status_code == 200
    started = start(source)
    assert started.status_code == 200, started.text
    practice = started.json()
    answered = practice_answer(
        source, practice, practice["tasks"][0], expected(content, practice["tasks"][0])
    )
    assert answered.status_code == 200, answered.text
    assert source.post(
        f"/api/v1/sessions/{practice['id']}/finish", json={}, headers=key()
    ).status_code == 200
    device = str(uuid4())
    prepared = prepare(source, device=device)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()

    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{(tmp_path / 'migration-verification.sqlite3').as_posix()}"
    versions = tmp_path / "versions"
    versions.mkdir()
    for name in ("0001_learning_core.py", "0002_accounts.py", "0003_assessments.py"):
        (versions / name).write_bytes((backend / "migrations" / "versions" / name).read_bytes())
    migration = Config(str(backend / "alembic.ini"))
    migration.set_main_option("script_location", str(backend / "migrations"))
    migration.set_main_option("version_locations", str(versions))
    migration.set_main_option("sqlalchemy.url", url)
    command.upgrade(migration, "0002_accounts")
    settings = Settings(
        database_url=url, content_dir=content_dir, allow_demo_content=True,
        allowed_origins=(TEST_ORIGIN,),
    )
    app = create_app(settings, clock=lambda: clock[0])
    if not hasattr(app.state, "assessments"):
        app.state.assessments = AssessmentService(app.state.service)
        app.include_router(router)
    # Intentionally no lifespan: this database is still on the predecessor
    # schema, before this new subsystem and its periodic worker can exist.
    client = TestClient(app, base_url=TEST_ORIGIN, headers=MUTATION_HEADERS)
    client.cookies.update(source.cookies)
    try:
        # Current practice ORM columns can belong to later migrations. Copy
        # real HTTP-created history using the predecessor's reflected schema.
        engine = app.state.database.engine
        legacy = MetaData()
        legacy.reflect(bind=engine, only=(
            "guests", "learning_sessions", "attempts", "seen_tasks", "idempotency_records",
        ))

        def snapshot(database_engine):
            with database_engine.connect() as connection:
                return {
                    table.name: {
                        row["id"]: dict(row)
                        for row in connection.execute(select(table)).mappings()
                    }
                    for table in legacy.sorted_tables
                }

        before = snapshot(source.app.state.database.engine)
        assert all(before.values())
        with engine.begin() as connection:
            for table in legacy.sorted_tables:
                connection.execute(table.insert(), list(before[table.name].values()))
        assert snapshot(engine) == before
        command.upgrade(migration, "0003_assessments")
        assert snapshot(engine) == before
        assessments = Table("assessments", MetaData(), autoload_with=engine)
        # Reflection cannot recover JSON's Python-None binding policy.
        for name in ("server_result", "local_result"):
            assessments.c[name].type = JSON(none_as_null=True)
        with source.app.state.database.engine.connect() as connection:
            prepared_record = dict(connection.execute(select(assessments).where(
                assessments.c.id == assessment["id"],
            )).mappings().one())
        with engine.begin() as connection:
            connection.execute(assessments.insert(), prepared_record)
        with pytest.raises(RuntimeError, match="disabled"):
            command.downgrade(migration, "0002_accounts")
        assert snapshot(engine) == before
        current_migration = Config(str(backend / "alembic.ini"))
        current_migration.set_main_option("script_location", str(backend / "migrations"))
        current_migration.set_main_option("sqlalchemy.url", url)
        command.upgrade(current_migration, "head")
        assert snapshot(engine) == before
        with engine.connect() as connection:
            assert dict(connection.execute(select(assessments)).mappings().one()) == prepared_record
        restored = view(client, assessment, device)
        assert restored.status_code == 200, restored.text
        assert restored.json() == view(source, assessment, device).json()
        assert restored.json()["tasks"] == prepared.json()["tasks"]
        assert activate(client, assessment, device).status_code == 200
        finished = finalize(client, assessment, device, correct_answers(content, assessment))
        assert finished.status_code == 200, finished.text
        assert finished.json()["server_result"]["score"] == 13
        after = snapshot(engine)
        for name in ("learning_sessions", "attempts"):
            assert after[name] == before[name]
        assert {
            identifier: after["idempotency_records"][identifier]
            for identifier in before["idempotency_records"]
        } == before["idempotency_records"]
        with pytest.raises(RuntimeError, match="disabled"):
            command.downgrade(current_migration, "0002_accounts")
        assert snapshot(engine) == after
        assert view(client, assessment).json()["server_result"] == finished.json()["server_result"]
    finally:
        client.close()
        app.state.database.dispose()


def test_claimed_origins_share_writer_scope_seen_flags_and_the_deadline_root(
    account_assessment_factory, single_slot_bank, clock
):
    one, mail_one = account_assessment_factory()
    one.post("/api/v1/guest", json={})
    two, mail_two = account_assessment_factory(database_url=one.app.state.settings.database_url)
    two.post("/api/v1/guest", json={})
    prior = start(two, slots=[1]).json()
    assert two.post(f"/api/v1/sessions/{prior['id']}/solution", json={
        "task_id": prior["tasks"][0]["id"],
    }).status_code == 200
    device_one, device_two = str(uuid4()), str(uuid4())
    assessment = prepare(one, device=device_one, duration_minutes=15).json()
    activate(one, assessment, device_one)
    account = sign_in(one, mail_one)
    assert sign_in(two, mail_two)["id"] == account["id"]
    assert view(two, assessment, device_two).status_code == 200
    assert view(two, assessment, device_two).json()["can_write"] is False
    adopted = takeover(two, assessment, device_two).json()
    assert adopted["writer_generation"] == 2
    assert view(one, assessment, device_one).json()["can_write"] is False
    answers = correct_answers(single_slot_bank, assessment)
    assert save(two, adopted, device_two, answers).status_code == 200
    clock[0] += timedelta(minutes=15)
    assert one.app.state.assessments.reconcile_deadlines() == 1
    result = finalize(two, adopted, device_two, answers, lost=True).json()["server_result"]
    assert result["score"] == 13
    assert result["rows"][0]["assisted"] is True
    assert result["rows"][0]["independent"] is False
    assert result["independent_total"] == 12


def test_a_claim_between_first_draft_and_finish_retains_earlier_origin_exposure(
    account_assessment_factory, single_slot_bank
):
    one, mail_one = account_assessment_factory()
    one.post("/api/v1/guest", json={})
    two, mail_two = account_assessment_factory(database_url=one.app.state.settings.database_url)
    two.post("/api/v1/guest", json={})
    prior = start(two, slots=[1]).json()
    assert two.post(f"/api/v1/sessions/{prior['id']}/hints", json={
        "task_id": prior["tasks"][0]["id"], "level": 1,
    }).status_code == 200
    device = str(uuid4())
    assessment = prepare(one, device=device).json()
    activate(one, assessment, device)
    answers = correct_answers(single_slot_bank, assessment)
    assert save(one, assessment, device, answers).status_code == 200
    sign_in(one, mail_one)
    sign_in(two, mail_two)
    result = finalize(one, assessment, device, answers).json()["server_result"]
    assert result["rows"][0]["assisted"] is True
    assert result["rows"][0]["independent"] is False
    assert result["independent_total"] == 12


@pytest.mark.parametrize("microseconds_before", range(7))
def test_clock_crossing_during_finish_cannot_stamp_a_late_snapshot_as_online(
    assessment_client, content, microseconds_before
):
    device = str(uuid4())
    assessment = prepare(assessment_client, device=device, duration_minutes=15).json()
    active = activate(assessment_client, assessment, device).json()
    deadline = datetime.fromisoformat(active["deadline_at"])
    instant = deadline - timedelta(microseconds=microseconds_before)

    def advancing_clock():
        nonlocal instant
        observed = instant
        instant += timedelta(microseconds=1)
        return observed

    assessment_client.app.state.service.clock = advancing_clock
    response = finalize(
        assessment_client, assessment, device, correct_answers(content, assessment)
    )
    assert response.status_code == 200
    result = response.json()["server_result"]
    frozen_at = datetime.fromisoformat(result["snapshot_at"])
    assert frozen_at <= deadline
    if result["reason"] == "finished":
        assert frozen_at < deadline
        assert result["score"] == 13
    else:
        assert result["reason"] == "deadline"
        assert result["score"] == 0
        assert response.json()["local_result"]["score"] == 13
