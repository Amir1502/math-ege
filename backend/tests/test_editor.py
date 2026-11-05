"""Editorial API regressions use isolated databases and real staff/MFA authorization."""

import copy
import json
import secrets
from dataclasses import replace
from datetime import timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from sqlalchemy import MetaData, func, inspect, select

from app import generators
from app.accounts.config import AccountSettings
from app.accounts.models import AccessSession, Account, TotpCredential
from app.accounts.service import AccountService
from app.accounts.tokens import token_digest
from app.assessments.models import AssessmentRecord
from app.config import Settings
from app.database import Database
from app.editor.models import (
    EditorAudit,
    EditorCatalog,
    EditorPublication,
    EditorRevision,
    TemplateCheckRun,
)
from app.editor.repository import exclusions, notices, published_content
from app.editor.schemas import EditorActor
from app.editor.validation import editable_payload
from app.errors import ApiError
from app.generators.base import Family, make_task
from app.models import Base, Guest, LearningSessionRecord


class StaffContext:
    """Trusted account/session/MFA records in a newly created test database only."""

    def __init__(self, client, now, cipher):
        self.client = client
        self.actors = {}
        self.credentials = {}
        self.sessions = {}
        for name, role in (("author", "methodist"), ("reviewer", "methodist"), ("admin", "admin")):
            credential = secrets.token_urlsafe(32)
            root_id, account_id, session_id = (str(uuid4()) for _ in range(3))
            with client.app.state.database.transaction(write=True) as db:
                db.add(
                    Guest(
                        id=root_id,
                        token_digest=token_digest(credential),
                        created_at=now,
                        last_seen_at=now,
                        expires_at=now + timedelta(days=30),
                    )
                )
                db.flush()
                db.add(
                    Account(
                        id=account_id,
                        email=f"{name}@editor.test",
                        root_guest_id=root_id,
                        role=role,
                        created_at=now,
                        email_verified_at=now,
                        consented_at=now,
                        policy_version="isolated-fixture",
                        daily_minutes=20,
                    )
                )
                db.flush()
                db.add(
                    AccessSession(
                        id=session_id,
                        account_id=account_id,
                        token_digest=token_digest(credential),
                        created_at=now,
                        expires_at=now + timedelta(days=30),
                        last_seen_at=now,
                        revoked_at=None,
                        mfa_verified_at=now,
                    )
                )
                db.flush()
                db.add(
                    TotpCredential(
                        account_id=account_id,
                        secret_ciphertext=cipher.encrypt(secrets.token_bytes(20)).decode(),
                        enrollment_session_id=session_id,
                        enrollment_expires_at=now + timedelta(minutes=15),
                        confirmed_at=now,
                        last_timecode=-1,
                        attempts=[],
                    )
                )
            self.actors[name] = EditorActor(id=account_id, role=role, owner_id=root_id)
            self.credentials[name] = credential
            self.sessions[name] = session_id
        self.use("author")

    def use(self, name):
        self.current = self.actors[name]
        self.client.cookies.clear()
        self.client.cookies.set(self.client.app.state.settings.cookie_name, self.credentials[name])

    def __getitem__(self, index):
        assert index == 0
        return self.current


class UnusedTestMail:
    def send_login_link(self, email, link, expires_at):
        raise AssertionError("The editorial fixture must not send mail")


@pytest.fixture
def editor(client_factory, clock):
    client = client_factory(environment="test", max_request_bytes=131_072)
    app = client.app
    key = Fernet.generate_key()
    app.state.accounts = AccountService(
        app.state.service,
        AccountSettings(
            enabled=True,
            policy_approved=True,
            policy_version="isolated-fixture",
            policy_url="http://testserver/policy",
            public_origin="http://testserver",
            mfa_encryption_key=key.decode(),
        ),
        UnusedTestMail(),
    )
    identity = StaffContext(client, clock[0], Fernet(key))
    yield client, identity


def post(client, path, body, key=None):
    return client.post(
        f"/api/v1/editor{path}",
        json=body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


def task_payload(content, *, identity="editor-task"):
    payload = content.tasks[0].model_dump(mode="json")
    payload["id"] = identity
    payload["slot_id"] = next(
        slot.id for slot in content.profile.slots if slot.number == payload["slot"]
    )
    for key in ("revision", "review_status"):
        payload.pop(key)
    payload["source"] = {"origin": "Original isolated fixture", "rights": "Test use"}
    return payload


def create(client, content, *, identity="editor-task"):
    response = post(
        client,
        "/revisions",
        {
            "kind": "task",
            "payload": task_payload(content, identity=identity),
            "change_note": "Уточнено условие для проверки.",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def act(client, revision, action, **values):
    return post(
        client,
        f"/revisions/{revision['id']}/{action}",
        {
            "expected_revision": revision["revision"],
            "note": "Проверено на отдельном примере.",
            **values,
        },
    )


def reviewer(identity):
    identity.use("reviewer")


def administrator(identity):
    identity.use("admin")


def reviewed(client, identity, content, *, task_id="editor-task"):
    revision = create(client, content, identity=task_id)
    revision = act(client, revision, "submit").json()
    reviewer(identity)
    response = act(client, revision, "approve")
    assert response.status_code == 200, response.text
    return response.json()


def test_author_review_and_publication_gates(editor, content):
    client, identity = editor
    revision = create(client, content)
    assert revision["author_id"] == identity[0].id
    assert revision["reviewer_id"] is None
    revision = act(client, revision, "submit").json()
    assert act(client, revision, "approve").status_code == 403
    reviewer(identity)
    revision = act(client, revision, "approve").json()
    assert revision["reviewer_id"] == identity[0].id
    assert act(client, revision, "publish").status_code == 403
    administrator(identity)
    response = act(client, revision, "publish")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    bundle = published_content(client.app.state.database, client.app.state.settings)
    task = next(item for item in bundle.tasks if item.id == "editor-task")
    assert task.review_status == "reviewed"
    assert task.source.author != task.source.reviewed_by


def test_revision_conflict_and_exact_idempotent_replay(editor, content):
    client, _ = editor
    body = {"kind": "task", "payload": task_payload(content), "change_note": "Создание задачи."}
    key = str(uuid4())
    first = post(client, "/revisions", body, key)
    again = post(client, "/revisions", body, key)
    assert first.status_code == 200, first.text
    assert first.content == again.content
    assert (
        post(client, "/revisions", {**body, "change_note": "Другой текст."}, key).status_code == 409
    )
    revision = first.json()
    assert act(client, revision, "submit").status_code == 200
    assert act(client, revision, "submit").status_code == 409
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorRevision)) == 1
        assert db.scalar(select(func.count()).select_from(EditorAudit)) == 2


def test_editor_actor_binding_rejects_stale_tabs_before_reads_or_replays(editor, content):
    client, identity = editor
    author_id = identity[0].id
    headers = {"X-Editor-Actor": author_id, "Idempotency-Key": str(uuid4())}
    body = {
        "kind": "task",
        "payload": task_payload(content),
        "change_note": "Привязка к сотруднику.",
    }
    created = client.post("/api/v1/editor/revisions", json=body, headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["author_id"] == author_id
    assert (
        client.get("/api/v1/editor/meta", headers={"X-Editor-Actor": author_id}).status_code == 200
    )

    reviewer(identity)
    stale = client.post("/api/v1/editor/revisions", json=body, headers=headers)
    assert stale.status_code == 403
    assert stale.json()["error"]["code"] == "editor_identity_changed"
    assert (
        client.get("/api/v1/editor/meta", headers={"X-Editor-Actor": author_id}).status_code == 403
    )
    assert (
        client.get("/api/v1/editor/meta", headers={"X-Editor-Actor": identity[0].id}).status_code
        == 200
    )
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorRevision)) == 1
        assert db.scalar(select(func.count()).select_from(EditorAudit)) == 1

    client.cookies.clear()
    assert (
        client.get("/api/v1/editor/meta", headers={"X-Editor-Actor": author_id}).status_code == 401
    )


def test_editor_actor_binding_also_gates_publishers_without_granting_authority(editor, content):
    client, identity = editor
    record = reviewed(client, identity, content)
    body = {"expected_revision": record["revision"], "note": "Публикация после проверки."}
    path = f"/api/v1/editor/revisions/{record['id']}/publish"
    forged = client.post(
        path,
        json=body,
        headers={
            "Idempotency-Key": str(uuid4()),
            "X-Editor-Actor": identity.actors["admin"].id,
        },
    )
    assert forged.status_code == 403
    administrator(identity)
    stale = client.post(
        path,
        json=body,
        headers={
            "Idempotency-Key": str(uuid4()),
            "X-Editor-Actor": identity.actors["reviewer"].id,
        },
    )
    assert stale.status_code == 403
    assert stale.json()["error"]["code"] == "editor_identity_changed"
    with client.app.state.database.transaction() as db:
        assert db.get(EditorRevision, record["id"]).status == "ready"
        assert db.scalar(select(func.count()).select_from(EditorPublication)) == 0


def test_import_validates_every_row_before_writing(editor, content):
    client, _ = editor
    good = {"kind": "task", "payload": task_payload(content), "change_note": "Импорт задачи."}
    bad = copy.deepcopy(good)
    bad["payload"]["answer"] = "1/3"
    bad["payload"]["id"] = "invalid-task"
    response = post(client, "/import", {"version": "1", "items": [good, bad]})
    assert response.status_code == 422, response.text
    assert "2" in response.json()["error"]["message"]
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorRevision)) == 0
        assert db.scalar(select(func.count()).select_from(EditorAudit)) == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"code": "print('unsafe')"}),
        lambda value: value.update({"formula": r"\href{javascript:alert(1)}{x}"}),
        lambda value: value.update({"statement": "<svg onload='x'></svg>"}),
        lambda value: value["source"].update({"reviewed_by": "pretend-reviewer"}),
        lambda value: value["source"].update({"author": "pretend-author"}),
        lambda value: value.update({"review_status": "reviewed"}),
    ],
)
def test_unsafe_or_managed_payload_is_rejected(editor, content, mutate):
    client, _ = editor
    payload = task_payload(content)
    mutate(payload)
    response = post(
        client,
        "/revisions",
        {
            "kind": "task",
            "payload": payload,
            "change_note": "Проверка неверного ввода.",
        },
    )
    assert response.status_code == 422, response.text


def test_withdrawal_tombstones_base_and_preserves_attempts(editor, content):
    client, identity = editor
    owner_id = identity[0].owner_id
    session = client.post(
        "/api/v1/sessions",
        json={
            "slots": [1],
            "length": 5,
            "mode": "practice",
        },
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    task = session["tasks"][0]
    attempt = client.post(
        f"/api/v1/sessions/{session['id']}/attempts",
        json={
            "task_id": task["id"],
            "answer": "0",
            "active_seconds": 10,
            "skipped": False,
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert attempt.status_code == 200, attempt.text
    before = client.get(f"/api/v1/sessions/{session['id']}").content
    administrator(identity)
    response = post(
        client,
        f"/tasks/{task['id']}/withdraw",
        {
            "task_revision": task["revision"],
            "reason": "Неоднозначное условие; исключено из освоения.",
        },
    )
    assert response.status_code == 200, response.text
    bundle = published_content(client.app.state.database, client.app.state.settings)
    assert task["id"] not in {item.id for item in bundle.tasks}
    identity.use("author")
    assert client.get(f"/api/v1/sessions/{session['id']}").content == before
    with client.app.state.database.transaction() as db:
        assert (task["id"], task["revision"]) in exclusions(db)
        messages = notices(db, [owner_id])
        assert messages[0]["attempt_ids"] == [attempt.json()["id"]]
        assert messages[0]["historical_scores_unchanged"] is True
        assert notices(db, [str(uuid4())]) == []
        assert "expected_answer" not in json.dumps(messages)


@pytest.mark.parametrize(
    "failure", ["no_cookie", "student", "no_mfa", "old_mfa", "unconfirmed", "revoked"]
)
def test_actual_staff_authorization_gates_reads_and_writes(editor, content, clock, failure):
    client, identity = editor
    with client.app.state.database.transaction(write=True) as db:
        account = db.get(Account, identity[0].id)
        access = db.get(AccessSession, identity.sessions["author"])
        if failure == "student":
            account.role = "student"
        elif failure == "no_mfa":
            access.mfa_verified_at = None
        elif failure == "old_mfa":
            access.mfa_verified_at = clock[0] - timedelta(minutes=15)
        elif failure == "unconfirmed":
            db.get(TotpCredential, account.id).confirmed_at = None
        elif failure == "revoked":
            access.revoked_at = clock[0]
    if failure == "no_cookie":
        client.cookies.clear()
    assert client.get("/api/v1/editor/meta").status_code in {401, 403}
    assert client.get("/api/v1/editor/revisions").status_code in {401, 403}
    response = post(
        client,
        "/revisions",
        {
            "kind": "task",
            "payload": task_payload(content),
            "change_note": "Запрещённое изменение.",
        },
    )
    assert response.status_code in {401, 403}
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorRevision)) == 0


def test_late_import_failure_rolls_back_the_savepoint_but_replays_the_error(
    editor, content, monkeypatch
):
    client, _ = editor
    service = client.app.state.editor
    audit = service._audit
    calls = []

    def fail_after_one_write(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ApiError(422, "test_late_failure", "Проверка атомарности после первой записи.")
        return audit(*args, **kwargs)

    monkeypatch.setattr(service, "_audit", fail_after_one_write)
    body = {
        "version": "1",
        "items": [
            {
                "kind": "task",
                "payload": task_payload(content, identity=f"import-{index}"),
                "change_note": "Пакет для атомарной проверки.",
            }
            for index in range(2)
        ],
    }
    key = str(uuid4())
    first = post(client, "/import", body, key)
    again = post(client, "/import", body, key)
    assert first.status_code == 422
    assert again.content == first.content
    assert len(calls) == 2
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorRevision)) == 0
        assert db.scalar(select(func.count()).select_from(EditorAudit)) == 0


def test_import_reports_multiple_bad_rows_and_enforces_cap(editor, content):
    client, _ = editor
    body = {"kind": "task", "payload": task_payload(content), "change_note": "Пакетная проверка."}
    response = post(client, "/import", {"version": "1", "items": [body, "wrong", {"code": "no"}]})
    assert response.status_code == 422
    assert "Строка 2" in response.json()["error"]["message"]
    assert "Строка 3" in response.json()["error"]["message"]
    assert post(client, "/import", {"version": "1", "items": [body] * 11}).status_code == 422


def test_published_payload_is_immutable_and_a_fork_requires_a_new_review(editor, content):
    client, identity = editor
    record = reviewed(client, identity, content)
    administrator(identity)
    record = act(client, record, "publish").json()
    with client.app.state.database.transaction() as db:
        frozen = copy.deepcopy(db.get(EditorRevision, record["id"]).payload)
    changed = copy.deepcopy(record["payload"])
    changed["answer"] = "999"
    response = client.put(
        f"/api/v1/editor/revisions/{record['id']}",
        json={
            "expected_revision": record["revision"],
            "payload": changed,
            "change_note": "Попытка изменить опубликованный эталон.",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code in {403, 409}
    fork = act(client, record, "fork").json()
    assert fork["version"] == 2 and fork["status"] == "draft"
    assert fork["content_id"] == record["content_id"]
    assert fork["content_revision"] != record["content_revision"]
    assert fork["reviewer_id"] is None
    assert act(client, fork, "publish").status_code == 409
    with client.app.state.database.transaction() as db:
        assert db.get(EditorRevision, record["id"]).payload == frozen


def test_invalid_combined_package_never_becomes_public(editor, content):
    client, identity = editor
    payload = task_payload(content)
    payload["skill_ids"] = ["unknown-skill"]
    record = post(
        client,
        "/revisions",
        {"kind": "task", "payload": payload, "change_note": "Проверка ссылок на навыки."},
    ).json()
    record = act(client, record, "submit").json()
    reviewer(identity)
    record = act(client, record, "approve").json()
    administrator(identity)
    response = act(client, record, "publish")
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/editor/revisions/{record['id']}").json()["status"] == "ready"
    bundle = published_content(client.app.state.database, client.app.state.settings)
    assert payload["id"] not in {item.id for item in bundle.tasks}


def test_base_import_and_profile_renumbering_need_explicit_mappings(editor, content):
    client, identity = editor
    record = post(
        client,
        f"/base/profile/{content.profile.id}",
        {
            "change_note": "Переход к уточнённой нумерации.",
        },
    ).json()
    payload = record["payload"]
    payload["slots"][0]["number"], payload["slots"][1]["number"] = 2, 1
    response = client.put(
        f"/api/v1/editor/revisions/{record['id']}",
        json={
            "expected_revision": record["revision"],
            "payload": payload,
            "change_note": "Перенумерованы две стабильные позиции.",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    record = act(client, response.json(), "submit").json()
    reviewer(identity)
    record = act(client, record, "approve").json()
    administrator(identity)
    assert act(client, record, "publish").status_code == 422
    with client.app.state.database.transaction() as db:
        assert db.get(EditorRevision, record["id"]).base_snapshot == content.profile.model_dump(
            mode="json"
        )
    assert (
        published_content(client.app.state.database, client.app.state.settings).profile
        == content.profile
    )


def test_assessment_correction_notice_waits_for_release_and_never_changes_score(
    editor, content, clock
):
    client, identity = editor
    task = content.tasks[0]
    owner_id = identity[0].owner_id
    assessment_id = str(uuid4())
    frozen = {"score": 7, "total": 13, "items": []}
    with client.app.state.database.transaction(write=True) as db:
        db.add(
            AssessmentRecord(
                id=assessment_id,
                guest_id=owner_id,
                profile_id=content.profile.id,
                profile_revision=content.profile.revision,
                profile_snapshot=content.profile.model_dump(mode="json"),
                tasks_snapshot=[task.model_dump(mode="json")],
                mode="exam",
                status="awaiting_snapshot",
                created_at=clock[0] - timedelta(hours=1),
                started_at=clock[0] - timedelta(hours=1),
                deadline_at=clock[0],
                released_at=None,
                duration_minutes=60,
                writer_device_id=str(uuid4()),
                writer_generation=1,
                draft_revision=0,
                current_index=0,
                drafts={},
                first_drafts={},
                answer_context={},
                server_result=copy.deepcopy(frozen),
                local_result=None,
                finish_hash=None,
            )
        )
    administrator(identity)
    response = post(
        client,
        f"/tasks/{task.id}/withdraw",
        {
            "task_revision": task.revision,
            "reason": "Исправление эталона после проверки условия.",
        },
    )
    assert response.status_code == 200, response.text
    with client.app.state.database.transaction(write=True) as db:
        assert notices(db, [owner_id]) == []
        assessment = db.get(AssessmentRecord, assessment_id)
        assert assessment.server_result == frozen
        assessment.status = "completed"
        assessment.released_at = clock[0]
        assessment.finish_hash = "a" * 64
    with client.app.state.database.transaction() as db:
        messages = notices(db, [owner_id])
        assert messages[0]["assessment_ids"] == [assessment_id]
        assert messages[0]["historical_scores_unchanged"] is True
        assert db.get(AssessmentRecord, assessment_id).server_result == frozen


def edit_payload(client, record, payload):
    response = client.put(
        f"/api/v1/editor/revisions/{record['id']}",
        json={
            "expected_revision": record["revision"],
            "payload": payload,
            "change_note": "Уточнена явная привязка материала.",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_atomic_profile_remapping_preserves_stable_skills_and_old_snapshots(editor, content):
    client, identity = editor
    session = client.post(
        "/api/v1/sessions",
        json={
            "slots": [1],
            "length": 5,
            "mode": "practice",
        },
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    before = client.get(f"/api/v1/sessions/{session['id']}").content
    records = []
    changes = [
        ("profile", content.profile),
        *[("lesson", lesson) for lesson in content.lessons if lesson.slot in {1, 2}],
        *[("task", task) for task in content.tasks if task.slot in {1, 2}],
    ]
    for kind, item in changes:
        response = post(
            client, f"/base/{kind}/{item.id}", {"change_note": "Явная перенумерация профиля."}
        )
        assert response.status_code == 200, response.text
        record = response.json()
        payload = record["payload"]
        if kind == "profile":
            for slot in payload["slots"]:
                if slot["number"] in {1, 2}:
                    slot["number"] = 3 - slot["number"]
        else:
            payload["slot"] = 3 - payload["slot"]
            # A fixed generator version cannot pretend to support a new binding.
            if kind == "task":
                payload["generation"] = None
        records.append(act(client, edit_payload(client, record, payload), "submit").json())
    reviewer(identity)
    records = [act(client, record, "approve").json() for record in records]
    administrator(identity)
    body = {
        "items": [
            {"id": record["id"], "expected_revision": record["revision"]} for record in records
        ],
        "note": "Профиль и все связи публикуются атомарно.",
    }
    incomplete = post(client, "/publish", {**body, "items": body["items"][:-1]})
    assert incomplete.status_code == 422, incomplete.text
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(EditorPublication)) == 0
    published = post(client, "/publish", body)
    assert published.status_code == 200, published.text
    bundle = published_content(client.app.state.database, client.app.state.settings)
    for original in content.tasks:
        current = next(task for task in bundle.tasks if task.id == original.id)
        assert current.skill_ids == original.skill_ids
        if original.slot in {1, 2}:
            assert current.slot == 3 - original.slot
            assert current.slot_id == next(
                slot.id for slot in content.profile.slots if slot.number == original.slot
            )
    for original in content.lessons:
        if original.slot in {1, 2}:
            current = next(lesson for lesson in bundle.lessons if lesson.id == original.id)
            assert current.slot == 3 - original.slot
            assert current.revision != original.revision
    identity.use("author")
    assert client.get(f"/api/v1/sessions/{session['id']}").content == before
    with client.app.state.database.transaction() as db:
        old = db.get(LearningSessionRecord, session["id"])
        assert old.profile_snapshot["revision"] == content.profile.revision


def test_foundation_lesson_uses_explicit_related_stable_slots(editor, content):
    client, identity = editor
    payload = editable_payload("lesson", content.lessons[0].model_dump(mode="json"))
    payload.update(
        id="editor-foundation",
        kind="foundation",
        slot=0,
        slot_id=None,
        related_slot_ids=[content.profile.slots[0].id],
        family_ids=[],
        practice_task_ids=[],
    )
    response = post(
        client,
        "/revisions",
        {
            "kind": "lesson",
            "payload": payload,
            "change_note": "Базовый урок перед экзаменационной темой.",
        },
    )
    assert response.status_code == 200, response.text
    record = act(client, response.json(), "submit").json()
    reviewer(identity)
    record = act(client, record, "approve").json()
    administrator(identity)
    response = act(client, record, "publish")
    assert response.status_code == 200, response.text
    bundle = published_content(client.app.state.database, client.app.state.settings)
    lesson = next(lesson for lesson in bundle.lessons if lesson.id == payload["id"])
    assert lesson.slot_id is None and lesson.related_slot_ids == [content.profile.slots[0].id]


@pytest.fixture
def registered_template(monkeypatch, content):
    """A small exact, deterministic server generator; not imported editorial code."""
    position = next(slot for slot in content.profile.slots if slot.number == 1)
    identifier = "editor-test-family"
    changes = {"offset": 0}

    def generate(seed, profile):
        value = seed % 17 + 1 + changes["offset"]
        return make_task(
            profile,
            1,
            identifier,
            seed,
            title="Вычисление для протокола",
            statement=f"Найдите сумму {value} и 2.",
            answer=value + 2,
            skills=[position.skills[0].id],
            hints=["Сложите числа.", "Прибавьте два.", "Проверьте сумму."],
            solution=[f"{value} + 2 = {value + 2}."],
        )

    family = Family(
        identifier, 1, "Проверяемое семейство", (position.skills[0].id,), generate, True
    )
    monkeypatch.setattr(generators, "FAMILIES", {identifier: family}, raising=False)
    payload = {
        "id": "editor-template",
        "title": "Проверяемый шаблон",
        "generator_id": identifier,
        "generator_version": "1",
        "profile_id": content.profile.id,
        "slot_id": position.id,
        "family_id": identifier,
        "skill_ids": list(family.skill_ids),
        "formula_notes": "Сумма целых чисел, эталон вычисляется точно.",
        "constraints": ["Seed принадлежит диапазону uint32; ответ целый."],
    }
    return payload, family, changes


def template_in_review(client, payload):
    response = post(
        client,
        "/revisions",
        {"kind": "template", "payload": payload, "change_note": "Шаблон для предметной проверки."},
    )
    assert response.status_code == 200, response.text
    response = act(client, response.json(), "submit")
    assert response.status_code == 200, response.text
    return response.json()


def human_sample(client, record, seed, *, approved=True):
    response = client.get(f"/api/v1/editor/revisions/{record['id']}/sample", params={"seed": seed})
    assert response.status_code == 200, response.text
    sample = response.json()
    return act(
        client, record, "samples", seed=seed, output_hash=sample["output_hash"], approved=approved
    )


def test_template_needs_recorded_seed_evidence_human_review_and_unchanged_generator(
    editor, registered_template
):
    client, identity = editor
    payload, _, changes = registered_template
    record = template_in_review(client, payload)
    reviewer(identity)
    reviewed_flags = {"reviewed_formula": True, "reviewed_constraints": True}
    response = act(client, record, "approve", **reviewed_flags)
    assert response.json()["error"]["code"] == "template_evidence_required"
    response = act(client, record, "checks")
    assert response.status_code == 200 and response.json()["passed"], response.text
    assert response.json()["seed_count"] == 1000
    record = client.get(f"/api/v1/editor/revisions/{record['id']}").json()
    assert (
        act(client, record, "approve", **reviewed_flags).json()["error"]["code"]
        == "human_review_required"
    )
    identity.use("author")
    assert human_sample(client, record, 0).status_code == 403
    reviewer(identity)
    assert (
        act(client, record, "samples", seed=0, output_hash="0" * 64, approved=True).status_code
        == 409
    )
    for seed in range(10):
        response = human_sample(client, record, seed)
        assert response.status_code == 200, response.text
        record = response.json()
    assert human_sample(client, record, 0).status_code == 409
    assert act(client, record, "approve").json()["error"]["code"] == "formula_review_required"
    response = act(client, record, "approve", **reviewed_flags)
    assert response.status_code == 200, response.text
    record = response.json()
    administrator(identity)
    changes["offset"] = 1
    response = act(client, record, "publish")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "template_evidence_stale"
    changes["offset"] = 0
    response = act(client, record, "publish")
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["reviewed_seeds"] == list(range(10))
    with client.app.state.database.transaction() as db:
        run = db.scalar(select(TemplateCheckRun))
        assert set(run.output_hashes) == {str(seed) for seed in (*range(998), 2**32 - 2, 2**32 - 1)}
        assert run.actor_id == identity.actors["reviewer"].id
    # A new profile revision must not silently leave active templates with stale evidence.
    identity.use("author")
    profile = client.get("/api/v1/editor/meta").json()["profile"]
    profile_record = post(
        client,
        f"/base/profile/{profile['id']}",
        {
            "change_note": "Новая редакция профиля для проверки привязки.",
        },
    ).json()
    profile_record = act(client, profile_record, "submit").json()
    reviewer(identity)
    profile_record = act(client, profile_record, "approve").json()
    administrator(identity)
    response = act(client, profile_record, "publish")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "template_evidence_required"


def test_template_rejection_and_payload_edits_invalidate_evidence(editor, registered_template):
    client, identity = editor
    payload, _, _ = registered_template
    record = template_in_review(client, payload)
    assert act(client, record, "checks").json()["passed"]
    record = client.get(f"/api/v1/editor/revisions/{record['id']}").json()
    reviewer(identity)
    record = human_sample(client, record, 2**32 - 1, approved=False).json()
    response = act(client, record, "approve", reviewed_formula=True, reviewed_constraints=True)
    assert response.json()["error"]["code"] == "template_rejected"
    identity.use("author")
    record = act(client, record, "return_to_draft").json()
    payload["constraints"] = ["Исправлены ограничения; требуется новая полная проверка."]
    record = edit_payload(client, record, payload)
    assert record["evidence"]["automated_passed"] is False
    assert record["evidence"]["reviewed_seeds"] == []
    assert record["evidence"]["rejected_seeds"] == []


def test_unregistered_generator_and_wrong_version_fail_closed(
    editor, registered_template, monkeypatch
):
    client, _ = editor
    payload, family, _ = registered_template
    monkeypatch.setattr(generators, "FAMILIES", {})
    response = post(
        client,
        "/revisions",
        {
            "kind": "template",
            "payload": payload,
            "change_note": "Проверка отсутствующего генератора.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unregistered_generator"
    monkeypatch.setattr(generators, "FAMILIES", {family.id: family})
    record = template_in_review(client, {**payload, "generator_version": "not-registered"})
    assert (
        client.get(
            f"/api/v1/editor/revisions/{record['id']}/sample", params={"seed": 0}
        ).status_code
        == 422
    )
    response = act(client, record, "checks")
    assert response.status_code == 200, response.text
    assert response.json()["passed"] is False and response.json()["seed_count"] == 0


def test_generated_task_cannot_claim_a_false_seed_or_snapshot(editor, content, registered_template):
    client, identity = editor
    _, family, _ = registered_template
    payload = editable_payload("task", family.generate(4, content.profile))
    payload["answer"] = "999"
    response = post(
        client,
        "/revisions",
        {"kind": "task", "payload": payload, "change_note": "Изменённый результат генерации."},
    )
    assert response.status_code == 200, response.text
    record = act(client, response.json(), "submit").json()
    reviewer(identity)
    record = act(client, record, "approve").json()
    administrator(identity)
    response = act(client, record, "publish")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "generation_mismatch"


def test_withdrawal_affects_next_issuance_through_the_mounted_service(editor, content):
    client, identity = editor
    task = content.tasks[0]
    administrator(identity)
    assert (
        post(
            client,
            f"/tasks/{task.id}/withdraw",
            {
                "task_revision": task.revision,
                "reason": "Ошибка условия; новые выдачи остановлены.",
            },
        ).status_code
        == 200
    )
    identity.use("author")
    response = client.post(
        "/api/v1/sessions",
        json={
            "slots": [task.slot],
            "length": 5,
            "mode": "practice",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert task.id not in {item["id"] for item in response.json()["tasks"]}


def test_publication_adapter_honors_reviewed_only_issuance(editor, content):
    client, identity = editor
    record = reviewed(client, identity, content)
    administrator(identity)
    assert act(client, record, "publish").status_code == 200
    settings = replace(client.app.state.settings, allow_demo_content=False)
    bundle = published_content(client.app.state.database, settings)
    assert "editor-task" in {task.id for task in bundle.tasks}
    assert all(task.review_status == "reviewed" for task in bundle.tasks)


def test_editor_migration_preserves_populated_predecessor_and_matches_models(tmp_path, clock):
    url = f"sqlite:///{(tmp_path / 'editor-migration.sqlite3').as_posix()}"
    database = Database(Settings(database_url=url))
    migration = import_module("migrations.versions.0005_editor")
    assert migration.down_revision == "0004_learning"
    # Verify this migration's actual operations independently of other workers'
    # unfinished migration files. Full chain verification belongs to integration.
    Base.metadata.create_all(
        database.engine,
        tables=[
            table for table in Base.metadata.sorted_tables if not table.name.startswith("editor_")
        ],
    )
    identifier = str(uuid4())
    try:
        with database.transaction(write=True) as db:
            db.add(
                Guest(
                    id=identifier,
                    token_digest="b" * 64,
                    created_at=clock[0],
                    last_seen_at=clock[0],
                    expires_at=clock[0] + timedelta(days=30),
                )
            )
        with (
            database.engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            migration.upgrade()
        with database.transaction() as db:
            assert db.get(Guest, identifier).token_digest == "b" * 64
            assert db.get(EditorCatalog, 1).revision == 0
        metadata = MetaData(naming_convention=Base.metadata.naming_convention)
        for table in Base.metadata.tables.values():
            if table.name.startswith("editor_"):
                table.to_metadata(metadata)
        with database.engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_object": lambda obj, name, type_, reflected, compared: (
                        name.startswith("editor_") if type_ == "table" else True
                    ),
                },
            )
            assert compare_metadata(context, metadata) == []
            for table in metadata.tables.values():
                actual = {
                    check["sqltext"]
                    for check in inspect(connection).get_check_constraints(table.name)
                }
                expected = {
                    str(check.sqltext) for check in table.constraints if hasattr(check, "sqltext")
                }
                assert actual == expected
        with pytest.raises(RuntimeError, match="must not be deleted"):
            migration.downgrade()
        with database.transaction() as db:
            assert db.get(Guest, identifier) is not None
            assert db.get(EditorCatalog, 1) is not None
    finally:
        database.dispose()
