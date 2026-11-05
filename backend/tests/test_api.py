import json
from datetime import timedelta
from uuid import uuid4

import pytest

from tests.helpers import answer, draft, expected, finish, key, start


def test_guest_can_start_private_answer_free_session(guest_client):
    response = start(guest_client)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert len(data["tasks"]) == 5
    assert data["attempts"] == []
    assert data["summary"]["independent_total"] == 0
    for task in data["tasks"]:
        assert not ({"answer", "expected_answer", "hints", "solution", "source"} & task.keys())
    resumed = guest_client.get(f"/api/v1/sessions/{data['id']}")
    assert resumed.status_code == 200
    assert resumed.json() == data


def test_profile_and_lessons_are_data_driven(client, content):
    profile = client.get("/api/v1/profile")
    assert profile.status_code == 200
    data = profile.json()
    assert data["id"] == content.profile.id
    assert data["revision"] == content.profile.revision
    assert data["status"] == "draft"
    assert data["demo_mode"] is True
    assert data["bank_size"] == len(content.tasks)
    assert [slot["number"] for slot in data["slots"]] == list(range(1, 14))
    assert [slot["available_tasks"] for slot in data["slots"]] == [5] * 13
    lesson = client.get("/api/v1/lessons/6")
    assert lesson.status_code == 200
    assert lesson.json() == next(item.model_dump() for item in content.lessons if item.slot == 6)
    assert not client.cookies


def test_disabled_demo_content_is_not_issued(client_factory):
    client = client_factory(allow_demo_content=False)
    profile = client.get("/api/v1/profile").json()
    assert profile["bank_size"] == 0
    assert profile["demo_mode"] is False
    assert all(slot["available_tasks"] == 0 for slot in profile["slots"])
    client.post("/api/v1/guest", json={})
    assert start(client).status_code == 503
    assert client.get("/api/v1/lessons/1").status_code == 503


def test_guest_cookie_is_opaque_httponly_strict_and_reused(client):
    first = client.post("/api/v1/guest", json={})
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Domain=" not in cookie
    assert set(first.json()) == {"id"}
    token = client.cookies.get("math_ege_guest")
    second = client.post("/api/v1/guest", json={})
    assert second.json() == first.json()
    assert client.cookies.get("math_ege_guest") == token
    assert token not in first.text


def test_session_create_replay_is_byte_identical_even_after_session_changes(guest_client, content):
    headers = key()
    first = start(guest_client, headers=headers)
    session = first.json()
    task = session["tasks"][0]
    assert answer(guest_client, session, task, expected(content, task)).status_code == 200
    replay = start(guest_client, headers=headers)
    assert replay.content == first.content
    assert replay.status_code == first.status_code
    assert len(guest_client.get("/api/v1/export").json()["sessions"]) == 1
    changed = start(guest_client, slots=[2], headers=headers)
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_conflict"


def test_idempotency_uuid_is_scoped_to_guest_not_server(client_factory):
    one = client_factory()
    two = client_factory(database_url=one.app.state.settings.database_url)
    for client in (one, two):
        assert client.post("/api/v1/guest", json={}).status_code == 200
    headers = key()
    first = start(one, headers=headers)
    second = start(two, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] != second.json()["id"]


def test_idempotency_uuid_cannot_be_reused_for_another_operation(guest_client):
    headers = key()
    session = start(guest_client, headers=headers).json()
    response = finish(guest_client, session, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


def test_first_wrong_answer_survives_correction_and_retry(guest_client, content):
    session = start(guest_client).json()
    task = session["tasks"][0]
    correct = expected(content, task)
    wrong = "987654321987654321"
    assert correct != wrong
    headers = key()
    first = answer(guest_client, session, task, wrong, seconds=7, headers=headers)
    assert first.status_code == 200
    original = first.json()
    assert original["correct"] is False
    assert original["first_attempt"] is True
    assert original["independent"] is True
    second = answer(guest_client, session, task, correct, seconds=12)
    assert second.status_code == 200
    assert second.json()["correct"] is True
    assert second.json()["first_attempt"] is False
    assert second.json()["independent"] is False
    replay = answer(guest_client, session, task, wrong, seconds=7, headers=headers)
    assert replay.content == first.content
    changed = answer(guest_client, session, task, correct, seconds=7, headers=headers)
    assert changed.status_code == 409
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["attempts"] == [original, second.json()]
    assert saved["summary"]["independent_total"] == 1
    assert saved["summary"]["independent_correct"] == 0
    assert saved["summary"]["corrections"] == 1
    assert saved["summary"]["active_seconds"] == 12
    progress = guest_client.get("/api/v1/progress").json()
    assert progress["independent_total"] == 1
    assert progress["independent_correct"] == 0
    assert progress["mistakes"][0]["attempt"] == original


@pytest.mark.parametrize("help_kind", ["hints", "solution"])
def test_server_remembers_assistance_before_first_answer(guest_client, content, help_kind):
    session = start(guest_client).json()
    task = session["tasks"][0]
    body = {"task_id": task["id"]}
    if help_kind == "hints":
        body["level"] = 2
    help_response = guest_client.post(f"/api/v1/sessions/{session['id']}/{help_kind}", json=body)
    assert help_response.status_code == 200
    assert guest_client.post(
        f"/api/v1/sessions/{session['id']}/{help_kind}", json=body
    ).json() == help_response.json()
    resumed = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert resumed["draft_revision"] == 0
    saved_help = resumed["help"][task["id"]]
    if help_kind == "hints":
        assert saved_help["hints"] == [help_response.json()]
        assert saved_help["solution"] is None
    else:
        assert saved_help["solution"] == help_response.json()
    result = answer(guest_client, session, task, expected(content, task)).json()
    assert result["assisted"] is True
    assert result["first_attempt"] is True
    assert result["independent"] is False
    assert result["correct"] is True
    assert guest_client.get("/api/v1/progress").json()["assisted_total"] == 1


def test_help_after_first_answer_does_not_rewrite_it(guest_client, content):
    session = start(guest_client).json()
    task = session["tasks"][0]
    first = answer(guest_client, session, task, expected(content, task)).json()
    assert first["independent"] is True
    assert first["assisted"] is False
    assert guest_client.post(
        f"/api/v1/sessions/{session['id']}/solution", json={"task_id": task["id"]}
    ).status_code == 200
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["attempts"] == [first]
    assert saved["summary"]["assisted"] == 0


@pytest.mark.parametrize("invalid", ["", "1/0", "NaN", "Infinity", "2 кг", "2+3", "+1", "1 000"])
def test_format_errors_create_no_mathematical_attempt_or_time(guest_client, content, invalid):
    session = start(guest_client).json()
    task = session["tasks"][0]
    headers = key()
    response = answer(guest_client, session, task, invalid, seconds=37, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "answer"
    assert (
        answer(guest_client, session, task, invalid, seconds=37, headers=headers).content
        == response.content
    )
    state = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert state["attempts"] == []
    assert state["summary"]["active_seconds"] == 0
    assert (
        answer(guest_client, session, task, expected(content, task), headers=headers).status_code
        == 409
    )
    valid = answer(guest_client, session, task, expected(content, task))
    assert valid.status_code == 200
    assert valid.json()["independent"] is True


def test_training_accepts_exact_fraction(guest_client, content):
    from fractions import Fraction

    session = start(guest_client).json()
    task = session["tasks"][0]
    value = Fraction(expected(content, task).replace(",", "."))
    fraction = f"{value.numerator * 2}/{value.denominator * 2}"
    response = answer(guest_client, session, task, fraction)
    assert response.status_code == 200
    assert response.json()["correct"] is True
    assert "/" not in response.json()["normalized_answer"]


def test_skip_is_separate_and_later_answer_is_not_independent(guest_client, content):
    session = start(guest_client).json()
    task = session["tasks"][0]
    response = answer(guest_client, session, task, "", seconds=10, skipped=True)
    skipped = response.json()
    assert response.status_code == 200
    assert skipped["skipped"] is True
    assert skipped["normalized_answer"] is None
    assert skipped["independent"] is False
    assert skipped["correct"] is False
    progress = guest_client.get("/api/v1/progress").json()
    assert progress["independent_total"] == 0
    assert progress["skipped_total"] == 1
    assert progress["mistakes"][0]["attempt"] == skipped
    correction = answer(guest_client, session, task, expected(content, task), seconds=20)
    assert correction.json()["independent"] is False
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["summary"]["skipped"] == 1
    assert saved["summary"]["corrections"] == 1
    assert saved["summary"]["active_seconds"] == 20


@pytest.mark.parametrize("value", ["0", " ", "NaN"])
def test_skip_rejects_nonempty_answer(guest_client, value):
    session = start(guest_client).json()
    response = answer(guest_client, session, session["tasks"][0], value, skipped=True)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "answer"


def test_draft_resume_and_conflict_preserve_saved_text_and_time(guest_client):
    session = start(guest_client).json()
    task = session["tasks"][2]
    saved = draft(guest_client, session, task, "−12,", seconds=12)
    assert saved.status_code == 200
    assert saved.json() == {"draft_revision": 1}
    conflict = draft(guest_client, session, task, "999", seconds=88, revision=0)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "draft_conflict"
    resumed = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert resumed["current_index"] == 2
    assert resumed["drafts"][task["id"]] == {"answer": "−12,", "active_seconds": 12}
    assert resumed["summary"]["active_seconds"] == 12
    assert resumed["attempts"] == []
    assert guest_client.get("/api/v1/progress").json()["active_session_id"] == session["id"]


def test_active_seconds_are_per_task_cumulative_and_monotonic(guest_client, content):
    session = start(guest_client).json()
    first, second = session["tasks"][:2]
    assert draft(guest_client, session, first, "1", seconds=20).status_code == 200
    assert draft(guest_client, session, first, "2", seconds=8, revision=1).status_code == 200
    headers = key()
    initial = answer(
        guest_client, session, first, expected(content, first), seconds=10, headers=headers
    )
    assert initial.json()["active_seconds"] == 20
    assert (
        answer(guest_client, session, first, expected(content, first), seconds=10, headers=headers)
        .content == initial.content
    )
    assert draft(guest_client, session, second, "", seconds=15, revision=2).status_code == 200
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["summary"]["active_seconds"] == 35
    assert saved["draft_revision"] == 3


def test_attempt_advances_current_task_without_changing_draft_revision(guest_client, content):
    session = start(guest_client).json()
    first = session["tasks"][0]
    assert answer(guest_client, session, first, expected(content, first)).status_code == 200
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["current_index"] == 1
    assert saved["draft_revision"] == 0


def test_finish_is_immutable_and_never_checks_drafts(guest_client, content, clock):
    session = start(guest_client).json()
    task = session["tasks"][0]
    assert draft(guest_client, session, task, expected(content, task), seconds=9).status_code == 200
    headers = key()
    first = finish(guest_client, session, headers=headers)
    data = first.json()
    assert first.status_code == 200
    assert data["status"] == "completed"
    assert data["attempts"] == []
    assert data["summary"]["independent_total"] == 0
    assert data["summary"]["answered"] == 0
    assert data["summary"]["skipped"] == 0
    assert data["summary"]["active_seconds"] == 9
    clock[0] += timedelta(hours=2)
    assert finish(guest_client, session, headers=headers).content == first.content
    assert finish(guest_client, session).content == first.content
    assert draft(guest_client, session, task, "123", revision=1).status_code == 409
    assert answer(guest_client, session, task, expected(content, task)).status_code == 409
    assert guest_client.post(
        f"/api/v1/sessions/{session['id']}/hints", json={"task_id": task["id"], "level": 1}
    ).status_code == 409
    assert guest_client.post(
        f"/api/v1/sessions/{session['id']}/solution", json={"task_id": task["id"]}
    ).status_code == 409
    assert guest_client.get(f"/api/v1/sessions/{session['id']}").json() == data
    assert guest_client.get("/api/v1/progress").json()["active_session_id"] is None


def test_retry_of_old_attempt_after_finish_returns_original_result(guest_client, content):
    session = start(guest_client).json()
    task = session["tasks"][0]
    headers = key()
    first = answer(guest_client, session, task, expected(content, task), headers=headers)
    assert finish(guest_client, session).status_code == 200
    replay = answer(guest_client, session, task, expected(content, task), headers=headers)
    assert replay.content == first.content


def test_shortage_and_30_day_exclusion_are_explicit(guest_client, clock):
    partial = start(guest_client, length=10)
    assert partial.status_code == 200
    session = partial.json()
    assert len(session["tasks"]) == 5
    assert session["requested_length"] == 10
    assert "30" in session["notice"]
    assert "5" in session["notice"]
    assert "10" in session["notice"]
    assert start(guest_client).json()["error"]["code"] == "bank_exhausted"
    clock[0] += timedelta(days=30) - timedelta(seconds=1)
    assert start(guest_client).status_code == 409
    clock[0] += timedelta(seconds=1)
    new_session = start(guest_client)
    assert new_session.status_code == 200
    assert {task["id"] for task in new_session.json()["tasks"]} == {
        task["id"] for task in session["tasks"]
    }


def test_multi_slot_selection_balances_positions_without_repeats(guest_client):
    data = start(guest_client, slots=[1, 6, 13], length=10).json()
    assert len(data["tasks"]) == 10
    assert len({task["id"] for task in data["tasks"]}) == 10
    counts = [sum(task["slot"] == slot for task in data["tasks"]) for slot in (1, 6, 13)]
    assert counts == [4, 3, 3]
    another = start(guest_client, slots=[1, 6, 13], length=10).json()
    assert len(another["tasks"]) == 5
    assert {task["id"] for task in data["tasks"]}.isdisjoint(
        {task["id"] for task in another["tasks"]}
    )


def test_reissued_instance_is_never_a_new_independent_achievement(guest_client, content, clock):
    first = start(guest_client).json()
    task = first["tasks"][0]
    original = answer(guest_client, first, task, expected(content, task)).json()
    assert original["independent"] is True
    clock[0] += timedelta(days=30)
    second = start(guest_client).json()
    repeated = next(item for item in second["tasks"] if item["id"] == task["id"])
    response = answer(guest_client, second, repeated, expected(content, repeated)).json()
    assert response["independent"] is False
    assert guest_client.get("/api/v1/progress").json()["independent_total"] == 1


def test_unanswered_help_stays_disqualifying_across_later_sessions(guest_client, content, clock):
    first = start(guest_client).json()
    task = first["tasks"][0]
    guest_client.post(
        f"/api/v1/sessions/{first['id']}/hints", json={"task_id": task["id"], "level": 1}
    )
    clock[0] += timedelta(days=30)
    second = start(guest_client).json()
    response = answer(guest_client, second, task, expected(content, task)).json()
    assert response["independent"] is False
    assert response["assisted"] is True


def test_three_correct_answers_can_be_consolidating_but_never_mastered(guest_client, content):
    session = start(guest_client).json()
    for task in session["tasks"][:3]:
        assert answer(guest_client, session, task, expected(content, task)).status_code == 200
    data = guest_client.get("/api/v1/progress").json()
    assert data["independent_total"] == 3
    assert data["slots"][0]["status"] == "Закрепляю"
    assert all(slot["status"] != "Освоено" for slot in data["slots"])
    assert all(slot["status"] == "Нет данных" for slot in data["slots"][1:])


def test_issued_snapshot_and_profile_revision_survive_content_edits(
    guest_client, content, content_dir
):
    from sqlalchemy import select

    from app.models import LearningSessionRecord

    session = start(guest_client).json()
    task = session["tasks"][0]
    old_expected = expected(content, task)
    tasks = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    source = next(item for item in tasks if item["id"] == task["id"])
    source["answer"] = "987654321987654321"
    source["revision"] = "changed-test-revision"
    source["statement"] = "Изменённое условие."
    (content_dir / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    profile = json.loads((content_dir / "profile.json").read_text(encoding="utf-8"))
    profile["revision"] = "changed-profile-revision"
    (content_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False), encoding="utf-8"
    )
    assert guest_client.get("/api/v1/profile").json()["revision"] == "changed-profile-revision"
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["tasks"] == session["tasks"]
    result = answer(guest_client, session, task, old_expected)
    assert result.json()["correct"] is True
    with guest_client.app.state.database.transaction() as db:
        stored = db.scalar(
            select(LearningSessionRecord).where(LearningSessionRecord.id == session["id"])
        )
        assert stored.profile_revision == content.profile.revision
        assert stored.profile_snapshot["revision"] == content.profile.revision


def test_export_uses_allowlist_and_never_exports_guest_secrets(guest_client, content):
    from hashlib import sha256

    session = start(guest_client).json()
    task = session["tasks"][0]
    assert answer(guest_client, session, task, expected(content, task)).status_code == 200
    exported = guest_client.get("/api/v1/export")
    value = exported.json()
    assert exported.status_code == 200
    assert set(value) == {"version", "exported_at", "profile_id", "sessions"}
    assert value["version"] == "1"
    assert len(value["sessions"]) == 1
    raw_token = guest_client.cookies.get("math_ege_guest")
    assert raw_token not in exported.text
    assert sha256(raw_token.encode()).hexdigest() not in exported.text
    for secret in (
        "guest_id", "token_digest", "request_hash", "request_key",
        "profile_snapshot", "tasks_snapshot"
    ):
        assert f'"{secret}"' not in exported.text
    assert "no-store" in exported.headers["cache-control"]


def test_missing_object_and_unknown_lesson_use_same_error_shape(guest_client):
    responses = [
        guest_client.get(f"/api/v1/sessions/{uuid4()}"), guest_client.get("/api/v1/lessons/999")
    ]
    for response in responses:
        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "not_found", "message": "Объект не найден.", "field": None}
        }
