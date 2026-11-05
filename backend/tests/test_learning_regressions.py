"""Regression proof for retention, canonical repeats and claimed policy history."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest

from app.learning.policy import LearningPolicy, replay, slot_progress
from app.learning.service import LearningExtrasService
from tests.helpers import answer, expected, finish, key, start
from tests.test_assessments import activate, finalize, prepare
from tests.test_assessments import single_slot_bank as single_slot_bank
from tests.test_learning import EPOCH, evidence, learning_login, mastered_evidence
from tests.test_learning import account_learning_factory as account_learning_factory
from tests.test_learning import assessment_learning_factory as assessment_learning_factory
from tests.test_learning import learning_factory as learning_factory


@pytest.mark.parametrize("flags", [
    {"correct": False},
    {"correct": True, "assisted": True, "independent": False},
], ids=["wrong", "helped"])
@pytest.mark.parametrize(("gap", "status"), [
    (timedelta(days=3) - timedelta(microseconds=1), "Освоено"),
    (timedelta(days=3), "Закрепляю"),
    (timedelta(days=4), "Закрепляю"),
], ids=["before-required-gap", "exact-required-gap", "day-eight"])
def test_failed_retention_demotes_at_required_gap_before_scheduled_due(flags, gap, status):
    events = mastered_evidence()
    required = ("fractions", "percent")
    before = replay(events)
    assert slot_progress(before, "algebra", required).status == "Освоено"
    assert before.reviews[0].due_at == EPOCH + timedelta(days=11)

    check_at = EPOCH + timedelta(days=4) + gap
    assert check_at < before.reviews[0].due_at
    failed = evidence("failed-check", at=check_at, **flags)
    after = replay([*events, failed])
    assert after.reviews[0].interval_days == 1
    assert after.reviews[0].due_at == check_at + timedelta(days=1)
    assert slot_progress(after, "algebra", required).status == status


def test_early_success_after_required_gap_does_not_advance_review_or_retention():
    events = mastered_evidence()
    before = replay(events)
    early = evidence("early-success", at=EPOCH + timedelta(days=8))
    after = replay([*events, early])
    assert after.reviews == before.reviews
    assert after.retention == before.retention
    assert slot_progress(after, "algebra", ("fractions", "percent")).status == "Освоено"


def test_cross_session_numeric_repeat_is_counted_and_source_flags_stay_frozen(
    learning_factory, content, clock,
):
    client = learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    session = start(client).json()
    task = session["tasks"][0]
    original = answer(client, session, task, expected(content, task))
    assert original.status_code == 200, original.text
    frozen = finish(client, session).json()

    clock[0] += timedelta(seconds=1)
    repeated = client.post("/api/v1/sessions", headers=key(), json={
        "slots": [task["slot"]], "length": 5, "mode": "practice", "repeat_task_id": task["id"],
    })
    assert repeated.status_code == 200, repeated.text
    headers = key()
    corrected = answer(client, repeated.json(), task, expected(content, task), headers=headers)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["first_attempt"] is True
    assert corrected.json()["independent"] is False
    repeated_frozen = finish(client, repeated.json()).json()

    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["independent_total"], data["independent_correct"], data["assisted_total"],
        data["corrections_total"], data["skipped_total"],
    ) == (1, 1, 1, 1, 0)
    assert answer(client, repeated.json(), task, expected(content, task),
                  headers=headers).content == corrected.content
    assert client.get("/api/v1/learning/dashboard").json() == data
    assert client.get(f"/api/v1/sessions/{session['id']}").json() == frozen
    assert client.get(f"/api/v1/sessions/{repeated.json()['id']}").json() == repeated_frozen
    assert frozen["attempts"] == [original.json()]
    assert repeated_frozen["attempts"] == [corrected.json()]


def test_merged_origins_count_numeric_repeat_once_without_rewriting_source_flags(
    account_learning_factory, content, clock,
):
    one, mail_one = account_learning_factory()
    assert one.post("/api/v1/guest", json={}).status_code == 200
    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    assert two.post("/api/v1/guest", json={}).status_code == 200
    first, second = start(one).json(), start(two).json()
    common = {task["id"] for task in first["tasks"]} & {task["id"] for task in second["tasks"]}
    assert common
    task_id = sorted(common)[0]
    task = next(task for task in first["tasks"] if task["id"] == task_id)
    second_task = next(task for task in second["tasks"] if task["id"] == task_id)
    original = answer(one, first, task, "987654321")
    assert original.status_code == 200, original.text
    clock[0] += timedelta(seconds=1)
    duplicate = answer(two, second, second_task, expected(content, second_task))
    assert duplicate.status_code == 200, duplicate.text
    assert original.json()["independent"] is duplicate.json()["independent"] is True
    frozen_first, frozen_second = finish(one, first).json(), finish(two, second).json()
    for client in (one, two):
        before = client.get("/api/v1/learning/dashboard").json()
        assert (before["independent_total"], before["corrections_total"]) == (1, 0)

    account = learning_login(one, mail_one)
    assert learning_login(two, mail_two)["id"] == account["id"]
    response = one.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["independent_total"], data["independent_correct"], data["assisted_total"],
        data["corrections_total"], data["skipped_total"],
    ) == (1, 0, 0, 1, 0)
    assert two.get("/api/v1/learning/dashboard").json() == data
    assert one.get(f"/api/v1/sessions/{first['id']}").json() == frozen_first
    assert two.get(f"/api/v1/sessions/{second['id']}").json() == frozen_second
    assert frozen_first["attempts"] == [original.json()]
    assert frozen_second["attempts"] == [duplicate.json()]
    restarted, _ = account_learning_factory(**shared)
    restarted.cookies.update(one.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == data


@pytest.mark.parametrize("prelude", ["hint", "skip"])
def test_first_assisted_numeric_answer_is_not_a_repeat_and_skips_stay_separate(
    learning_factory, content, prelude,
):
    client = learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    session = start(client).json()
    task = session["tasks"][0]
    if prelude == "hint":
        response = client.post(f"/api/v1/sessions/{session['id']}/hints", json={
            "task_id": task["id"], "level": 1,
        })
    else:
        response = answer(client, session, task, "", skipped=True)
    assert response.status_code == 200, response.text
    before = client.get("/api/v1/learning/dashboard").json()
    assert before["corrections_total"] == before["independent_total"] == 0

    first_numeric = answer(client, session, task, expected(content, task))
    assert first_numeric.status_code == 200, first_numeric.text
    assert first_numeric.json()["assisted"] is True
    assert first_numeric.json()["independent"] is False
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["independent_total"], data["assisted_total"], data["corrections_total"],
    ) == (0, 1, 0)
    assert data["skipped_total"] == (1 if prelude == "skip" else 0)

    repeated = answer(client, session, task, expected(content, task))
    assert repeated.status_code == 200, repeated.text
    after = client.get("/api/v1/learning/dashboard").json()
    assert (after["assisted_total"], after["corrections_total"]) == (2, 1)
    assert after["skipped_total"] == data["skipped_total"]


def test_assessment_format_error_does_not_consume_first_numeric_answer(
    assessment_learning_factory, single_slot_bank, clock,
):
    client = assessment_learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    practice = start(client).json()
    task = practice["tasks"][0]
    device = str(uuid4())
    prepared = prepare(client, mode="diagnostic", device=device)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    assert task["id"] in {item["id"] for item in assessment["tasks"]}
    assert activate(client, assessment, device).status_code == 200
    finished = finalize(client, assessment, device, {
        task["id"]: {"answer": "2,", "active_seconds": 1},
    })
    assert finished.status_code == 200, finished.text
    server = finished.json()["server_result"]
    assert server["format_errors"] == 1
    before = client.get("/api/v1/learning/dashboard").json()
    assert (before["independent_total"], before["corrections_total"], before["skipped_total"]) == (
        0, 0, 12,
    )

    clock[0] += timedelta(seconds=1)
    numeric = answer(client, practice, task, expected(single_slot_bank, task))
    assert numeric.status_code == 200, numeric.text
    assert numeric.json()["assisted"] is True
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    assert response.json()["corrections_total"] == 0
    clock[0] += timedelta(seconds=1)
    assert answer(client, practice, task, expected(single_slot_bank, task)).status_code == 200
    after = client.get("/api/v1/learning/dashboard").json()
    assert (after["corrections_total"], after["skipped_total"]) == (1, 12)
    assert client.get(f"/api/v1/assessments/{assessment['id']}").json()["server_result"] == server


def test_excluded_earlier_numeric_revision_still_makes_later_numeric_answer_a_repeat(
    learning_factory, content, content_dir, clock,
):
    from app.editor.models import CorrectionExclusion

    client = learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    first = start(client).json()
    task = first["tasks"][0]
    assert answer(client, first, task, expected(content, task)).status_code == 200
    frozen = finish(client, first).json()
    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    for item in tasks:
        if item["id"] == task["id"]:
            item["revision"] = "repeat-regression-2"
    path.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    clock[0] += timedelta(seconds=1)
    repeated = client.post("/api/v1/sessions", headers=key(), json={
        "slots": [task["slot"]], "length": 5, "mode": "practice", "repeat_task_id": task["id"],
    })
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["tasks"][0]["revision"] == "repeat-regression-2"
    assert answer(client, repeated.json(), task, expected(content, task)).status_code == 200
    # The editorial subsystem supplies an external fixture; observe learning through HTTP.
    with client.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id=task["id"], task_revision=task["revision"],
            reason="Ошибка в прежней редакции.", actor_id="regression-fixture", created_at=clock[0],
        ))
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (
        data["independent_total"], data["corrections_total"], data["excluded_total"],
    ) == (0, 1, 1)
    assert client.get(f"/api/v1/sessions/{first['id']}").json() == frozen


@pytest.mark.parametrize("existing_notice", [False, True], ids=["no-notice", "prior-notice"])
def test_current_root_explains_newly_claimed_old_policy_and_keeps_notice_after_restart(
    account_learning_factory, existing_notice,
):
    old_guest, old_mail = account_learning_factory()
    assert old_guest.post("/api/v1/guest", json={}).status_code == 200
    session = start(old_guest).json()
    task = session["tasks"][0]
    assert answer(old_guest, session, task, "987654321").status_code == 200
    frozen = finish(old_guest, session).json()
    assert old_guest.get("/api/v1/learning/dashboard").json()["algorithm_version"] == "learning-v1"

    shared = {"database_url": old_guest.app.state.settings.database_url}
    account_client, account_mail = account_learning_factory(**shared)
    assert account_client.post("/api/v1/guest", json={}).status_code == 200
    account = learning_login(account_client, account_mail)
    if existing_notice:
        account_client.app.state.learning = LearningExtrasService(
            account_client.app.state.service,
            policy=LearningPolicy(version="learning-v0", mastery_attempts=21),
        )
        assert account_client.get("/api/v1/learning/dashboard").json()["notice"] is None
    current = LearningPolicy(version="learning-v2", mastery_attempts=25)
    account_client.app.state.learning = LearningExtrasService(
        account_client.app.state.service, policy=current,
    )
    before = account_client.get("/api/v1/learning/dashboard").json()
    assert before["algorithm_version"] == "learning-v2"
    assert before["independent_total"] == 0
    if existing_notice:
        assert "learning-v0" in before["notice"] and "learning-v2" in before["notice"]
        assert "learning-v1" not in before["notice"]
    else:
        assert before["notice"] is None

    old_guest.app.state.learning = LearningExtrasService(
        old_guest.app.state.service, policy=current,
    )
    assert learning_login(old_guest, old_mail)["id"] == account["id"]
    response = old_guest.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    after = response.json()
    notice = after["notice"]
    assert notice and "learning-v1" in notice and "learning-v2" in notice
    if existing_notice:
        assert before["notice"] in notice
    assert after["independent_total"] == 1
    assert old_guest.get("/api/v1/learning/dashboard").json() == after
    assert account_client.get("/api/v1/learning/dashboard").json() == after
    assert old_guest.get(f"/api/v1/sessions/{session['id']}").json() == frozen

    restarted, _ = account_learning_factory(**shared)
    restarted.cookies.update(old_guest.cookies)
    restarted.app.state.learning = LearningExtrasService(
        restarted.app.state.service, policy=current,
    )
    assert restarted.get("/api/v1/learning/dashboard").json() == after
    assert restarted.get("/api/v1/learning/dashboard").json()["notice"] == notice


def test_current_root_rejects_newly_claimed_same_version_with_different_thresholds(
    account_learning_factory,
):
    old_guest, old_mail = account_learning_factory()
    assert old_guest.post("/api/v1/guest", json={}).status_code == 200
    old_guest.app.state.learning = LearningExtrasService(
        old_guest.app.state.service, policy=LearningPolicy(version="learning-v2"),
    )
    assert old_guest.get("/api/v1/learning/dashboard").status_code == 200

    account_client, account_mail = account_learning_factory(
        database_url=old_guest.app.state.settings.database_url,
    )
    assert account_client.post("/api/v1/guest", json={}).status_code == 200
    account = learning_login(account_client, account_mail)
    current = LearningPolicy(version="learning-v2", mastery_attempts=25)
    account_client.app.state.learning = LearningExtrasService(
        account_client.app.state.service, policy=current,
    )
    assert account_client.get("/api/v1/learning/dashboard").status_code == 200
    assert learning_login(old_guest, old_mail)["id"] == account["id"]
    response = account_client.get("/api/v1/learning/dashboard")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "policy_version_conflict"


def test_policy_upgrade_notice_is_stable_when_root_and_claimed_origin_had_different_versions(
    account_learning_factory,
):
    origin, origin_mail = account_learning_factory()
    assert origin.post("/api/v1/guest", json={}).status_code == 200
    assert origin.get("/api/v1/learning/dashboard").json()["algorithm_version"] == "learning-v1"
    account_client, account_mail = account_learning_factory(
        database_url=origin.app.state.settings.database_url,
    )
    assert account_client.post("/api/v1/guest", json={}).status_code == 200
    account = learning_login(account_client, account_mail)
    account_client.app.state.learning = LearningExtrasService(
        account_client.app.state.service, policy=LearningPolicy(version="learning-v0"),
    )
    assert account_client.get("/api/v1/learning/dashboard").json()["notice"] is None
    assert learning_login(origin, origin_mail)["id"] == account["id"]

    account_client.app.state.learning = LearningExtrasService(
        account_client.app.state.service,
        policy=LearningPolicy(version="learning-v2", mastery_attempts=25),
    )
    response = account_client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    first = response.json()
    assert all(
        version in first["notice"] for version in ("learning-v0", "learning-v1", "learning-v2")
    )
    assert account_client.get("/api/v1/learning/dashboard").json() == first
