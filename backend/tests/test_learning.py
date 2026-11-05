"""Learning behavior at the approved pure-policy and public HTTP seams."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from tests.helpers import answer, expected, finish, key, start

EPOCH = datetime(2026, 11, 5, 12, tzinfo=UTC)


def evidence(identifier, *, at=EPOCH, task_id=None, **changes):
    from app.learning.policy import Evidence

    values = {
        "id": identifier, "task_id": task_id or identifier, "task_revision": "1",
        "skill_ids": ("fractions",), "family_id": "fraction-addition", "slot_id": "algebra",
        "at": at, "correct": True, "independent": True, "assisted": False,
        "skipped": False, "active_seconds": 60, "source": "practice",
    }
    return Evidence(**(values | changes))


def test_review_advances_only_at_due_time_on_a_new_independent_instance():
    from app.learning.policy import replay

    wrong = evidence("first", correct=False)
    initial = replay([wrong]).reviews[0]
    assert initial.interval_days == 1
    assert initial.due_at == EPOCH + timedelta(days=1)

    early = evidence("early", at=initial.due_at - timedelta(microseconds=1))
    unchanged = replay([wrong, early]).reviews[0]
    assert unchanged == initial

    due = evidence("due", at=initial.due_at)
    advanced = replay([due, early, wrong, wrong]).reviews[0]
    assert advanced.interval_days == 3
    assert advanced.due_at == EPOCH + timedelta(days=4)

    repeated = evidence("repeated", task_id="due", at=advanced.due_at)
    result = replay([wrong, early, due, repeated])
    assert result.reviews[0] == advanced
    assert result.evidence[-1].independent is False


@pytest.mark.parametrize("flags", [
    {"correct": False},
    {"correct": True, "assisted": True, "independent": False},
    {"correct": False, "skipped": True, "independent": False},
])
def test_error_help_or_skip_resets_one_review_even_before_due(flags):
    from app.learning.policy import replay

    events = [evidence("wrong", correct=False), evidence("day-1", at=EPOCH + timedelta(days=1))]
    reset_at = EPOCH + timedelta(days=2)
    events.append(evidence("reset", at=reset_at, **flags))
    result = replay(events)
    assert len(result.reviews) == 1
    assert result.reviews[0].interval_days == 1
    assert result.reviews[0].due_at == EPOCH + timedelta(days=3)


def test_review_closes_after_30_day_success_and_a_new_error_reopens_it():
    from app.learning.policy import replay

    events = [evidence("wrong", correct=False)]
    for elapsed, next_interval in [(1, 3), (4, 7), (11, 14), (25, 30), (55, 30)]:
        events.append(evidence(f"day-{elapsed}", at=EPOCH + timedelta(days=elapsed)))
        review = replay(events).reviews[0]
        assert review.interval_days == next_interval
    assert review.due_at is None
    events.append(evidence("new-error", correct=False, at=EPOCH + timedelta(days=60)))
    reopened = replay(events).reviews[0]
    assert reopened.interval_days == 1
    assert reopened.due_at == EPOCH + timedelta(days=61)


def mastered_evidence():
    return [
        evidence("a-wrong", correct=False),
        evidence("b-review-1", at=EPOCH + timedelta(days=1)),
        evidence("c-review-3", at=EPOCH + timedelta(days=4)),
        *[
            evidence(
                f"practice-{index:02}", at=EPOCH + timedelta(days=4, minutes=index + 1),
                family_id="percent-growth" if index % 2 else "fraction-division",
                skill_ids=("percent",) if index % 2 else ("fractions",),
            )
            for index in range(17)
        ],
    ]


def test_mastery_requires_all_thresholds_and_is_demoted_by_a_failed_delayed_review():
    from app.learning.policy import replay, slot_progress

    events = mastered_evidence()
    progress = slot_progress(replay(events), "algebra", ("fractions", "percent"))
    assert (progress.status, progress.attempts, progress.correct) == ("Освоено", 20, 19)
    assert progress.covered_skills == 2

    events.append(evidence(
        "failed-retention", at=EPOCH + timedelta(days=11), assisted=True, independent=False,
    ))
    assert slot_progress(replay(events), "algebra", ("fractions", "percent")).status == "Закрепляю"
    events.append(evidence("repeat-1", at=EPOCH + timedelta(days=12)))
    assert slot_progress(replay(events), "algebra", ("fractions", "percent")).status == "Закрепляю"
    events.append(evidence("repeat-3", at=EPOCH + timedelta(days=15)))
    assert slot_progress(replay(events), "algebra", ("fractions", "percent")).status == "Освоено"


def test_delayed_recheck_can_confirm_mastery_without_a_prior_error():
    from app.learning.policy import replay, slot_progress

    families = ("fraction-addition", "fraction-division", "percent-growth")
    required = ("fractions", "percent")
    events = [evidence(
        f"perfect-{index:02}", at=EPOCH + timedelta(minutes=index),
        family_id=families[index % 3],
        skill_ids=("percent",) if index % 3 == 2 else ("fractions",),
    ) for index in range(19)]
    due = evidence("delayed", at=EPOCH + timedelta(days=3, minutes=18))
    early = replace(due, at=due.at - timedelta(microseconds=1))
    assert slot_progress(replay([*events, early]), "algebra", required).status == "Закрепляю"
    projection = replay([*events, due])
    assert projection.reviews == ()
    assert slot_progress(projection, "algebra", required).status == "Освоено"
    failed = evidence("failed-recheck", at=due.at + timedelta(days=3), correct=False)
    assert slot_progress(replay([*events, due, failed]), "algebra", required).status == "Закрепляю"


@pytest.mark.parametrize("missing", ["attempts", "recent", "families", "days", "skill", "delay"])
def test_mastery_is_withheld_if_any_required_evidence_is_missing(missing):
    from app.learning.policy import replay, slot_progress

    events = mastered_evidence()
    if missing == "attempts":
        events = events[:-1]
    elif missing == "recent":
        events = [*events[:-3], *(replace(item, correct=False) for item in events[-3:])]
    elif missing == "families":
        events = [replace(item, family_id="fraction-addition") for item in events]
    elif missing == "days":
        events = [replace(item, at=EPOCH + timedelta(minutes=i)) for i, item in enumerate(events)]
    elif missing == "skill":
        events = [replace(item, skill_ids=("fractions",)) for item in events]
    elif missing == "delay":
        events = [replace(item, at=EPOCH + timedelta(days=2, minutes=i)) if i >= 2 else item
                  for i, item in enumerate(events)]
    assert slot_progress(replay(events), "algebra", ("fractions", "percent")).status != "Освоено"


@pytest.mark.parametrize(("correct", "status"), [
    ([], "Нет данных"), ([True], "Изучаю"), ([True, True], "Изучаю"),
    ([True, True, True], "Закрепляю"), ([True, False, True, False, False], "Изучаю"),
])
def test_sparse_history_uses_counts_and_conservative_statuses(correct, status):
    from app.learning.policy import replay, slot_progress

    events = [evidence(str(i), correct=value) for i, value in enumerate(correct)]
    progress = slot_progress(replay(events), "algebra", ("fractions",))
    assert progress.status == status
    assert progress.attempts == len(correct)


def test_equal_clock_correction_and_help_cannot_erase_the_original_independent_answer():
    from app.learning.policy import replay, slot_progress

    original = evidence("z-original", task_id="same-instance", correct=False)
    correction = evidence("a-correction", task_id="same-instance", independent=False, assisted=True)
    result = replay([correction, original])
    progress = slot_progress(result, "algebra", ("fractions",))
    assert (progress.attempts, progress.correct) == (1, 0)
    assert original.independent is True
    assert correction.independent is False


def test_editorial_exclusion_replays_reviews_without_rewriting_or_requalifying_an_instance():
    from app.learning.policy import replay, slot_progress

    wrong = evidence("wrong", correct=False)
    same_instance = evidence(
        "other-origin", task_id="wrong", task_revision="2", at=EPOCH + timedelta(1),
    )
    exclusions = {("wrong", "1"): "В исходном условии пропущено ограничение."}
    result = replay([wrong, same_instance], exclusions=exclusions)
    assert result.reviews == ()
    assert slot_progress(result, "algebra", ("fractions",)).attempts == 0
    assert wrong.independent is True
    assert same_instance.independent is True
    assert result.excluded_ids == ("wrong",)


@pytest.fixture
def learning_factory(client_factory):
    def make(**overrides):
        from app.learning.api import router
        from app.learning.service import LearningExtrasService

        client = client_factory(**overrides)
        if not any(getattr(route, "path", None) == "/api/v1/learning/dashboard"
                   for route in client.app.routes):
            client.app.include_router(router)
        client.app.state.learning = LearningExtrasService(client.app.state.service)
        client.app.state.database.create_schema_for_tests()
        return client

    return make


@pytest.fixture
def account_learning_factory(learning_factory):
    from app.accounts.config import AccountSettings
    from app.accounts.service import AccountService

    class Mailbox:
        def __init__(self):
            self.links = []

        def send_login_link(self, email, link, expires_at):
            self.links.append(link)

    def make(**overrides):
        client = learning_factory(environment="test", **overrides)
        mailbox = Mailbox()
        client.app.state.accounts = AccountService(
            client.app.state.service,
            AccountSettings(
                enabled=True, policy_approved=True, policy_version="learning-test",
                policy_url="https://example.org/privacy", public_origin="http://testserver",
            ),
            mail_sender=mailbox,
        )
        return client, mailbox

    return make


def learning_login(client, mailbox):
    response = client.post("/api/v1/auth/request-link", json={
        "email": "learning@example.org", "policy_version": "learning-test", "accept_policy": True,
    })
    assert response.status_code == 202, response.text
    token = parse_qs(urlsplit(mailbox.links[-1]).fragment)["token"][0]
    response = client.post("/api/v1/auth/complete", json={"token": token})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def assessment_learning_factory(learning_factory):
    def make(**overrides):
        from app.assessments.api import router
        from app.assessments.service import AssessmentService

        client = learning_factory(**overrides)
        if not hasattr(client.app.state, "assessments"):
            client.app.state.assessments = AssessmentService(client.app.state.service)
            client.app.include_router(router)
        return client

    return make


def test_dashboard_projects_owned_history_and_keeps_original_errors_and_summaries(
    learning_factory, content, clock,
):
    client = learning_factory()
    assert client.get("/api/v1/learning/dashboard").status_code == 401
    assert client.post("/api/v1/guest", json={}).status_code == 200
    session = start(client).json()
    first, second, third = session["tasks"][:3]
    wrong = answer(client, session, first, "987654321", seconds=12).json()
    correction = answer(client, session, first, expected(content, first), seconds=20).json()
    skipped = answer(client, session, second, "", skipped=True, seconds=14).json()
    correct = answer(client, session, third, expected(content, third), seconds=60).json()
    frozen = finish(client, session).json()

    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["algorithm_version"] == "learning-v1"
    assert (data["independent_total"], data["independent_correct"]) == (2, 1)
    assert (data["assisted_total"], data["corrections_total"], data["skipped_total"]) == (1, 1, 1)
    slot = next(item for item in data["slots"] if item["number"] == 1)
    assert slot["slot_id"] == content.profile.slots[0].id
    assert (slot["attempts"], slot["correct"], slot["status"]) == (2, 1, "Изучаю")
    assert len(data["slots"]) == 13
    journal = {item["id"]: item for item in data["journal"]}
    assert set(journal) == {wrong["id"], skipped["id"]}
    assert journal[wrong["id"]]["attempt"] == wrong
    assert journal[wrong["id"]]["cause"] is None
    assert data["favourites"] == data["assessment_history"] == []
    assert all(item["due_at"] == (clock[0] + timedelta(days=1)).isoformat()
               for item in data["reviews"])
    assert data["reviews"]
    for item in data["journal"]:
        assert not {"answer", "hints", "solution", "source"} & item["task"].keys()
    assert client.get("/api/v1/learning/dashboard").json() == data
    assert client.get(f"/api/v1/sessions/{session['id']}").json() == frozen
    assert {item["id"] for item in frozen["attempts"]} == {
        wrong["id"], correction["id"], skipped["id"], correct["id"],
    }

    outsider = learning_factory(database_url=client.app.state.settings.database_url)
    assert outsider.post("/api/v1/guest", json={}).status_code == 200
    foreign = outsider.get("/api/v1/learning/dashboard").json()
    assert foreign["journal"] == foreign["reviews"] == []
    assert foreign["independent_total"] == 0


def selection_bank(content, *, weak=12, review=12, new=12):
    from app.content import ContentBundle
    from app.learning.policy import replay

    base = next(task for task in content.tasks if task.slot == 1)
    skill = base.skill_ids[0]
    slot_id = content.profile.slots[0].id
    tasks = [base.model_copy(update={
        "id": f"{group}-{index:02}", "family_id": f"{group}-family", "slot_id": slot_id,
        "skill_ids": [skill], "difficulty": 1,
    }) for group, count in [("weak", weak), ("review", review), ("new", new)]
        for index in range(count)]
    tasks = [task.model_copy(update={
        "statement": (
            f"Катеты прямоугольного треугольника равны {2 * index} см и 3 см. "
            "Найдите его площадь в квадратных сантиметрах."
        ),
        "formula": None, "answer": str(3 * index),
        "hints": [
            "Катеты перпендикулярны.", "Площадь равна половине произведения катетов.",
            f"Вычислите {2 * index} · 3 / 2.",
        ],
        "solution": [f"S = {2 * index} · 3 / 2 = {3 * index} см²."],
    }) for index, task in enumerate(tasks, start=1)]
    projection = replay([
        evidence("review-error", at=EPOCH - timedelta(days=2), correct=False,
                 skill_ids=(skill,), family_id="review-family", slot_id=slot_id),
        evidence("weak-error", at=EPOCH - timedelta(hours=1), correct=False,
                 skill_ids=(skill,), family_id="weak-family", slot_id=slot_id),
    ])
    return ContentBundle(content.profile, content.lessons, tuple(tasks)), projection


def selection_request(length=10, **changes):
    return SimpleNamespace(**({
        "slots": [1], "length": length, "mode": "practice", "skill_ids": [], "family_ids": [],
        "difficulty": None, "selection": "mixed", "repeat_task_id": None,
    } | changes))


@pytest.mark.parametrize(("length", "counts"), [(5, (3, 1, 1)), (10, (5, 3, 2)), (20, (10, 6, 4))])
def test_mixed_selection_has_exact_nonoverlapping_proportions_and_is_reproducible(
    content, length, counts,
):
    from app.learning.selection import mixed_candidates

    bundle, projection = selection_bank(content)
    request = selection_request(length)
    selected = mixed_candidates(bundle, request, projection, {}, EPOCH, "salt")
    assert len(selected.tasks) == length
    assert len({task.id for task in selected.tasks}) == length
    assert tuple(sum(task.family_id == f"{group}-family" for task in selected.tasks)
                 for group in ("weak", "review", "new")) == counts
    assert mixed_candidates(bundle, request, projection, {}, EPOCH, "salt") == selected
    reversed_bundle = replace(bundle, tasks=tuple(reversed(bundle.tasks)))
    assert mixed_candidates(reversed_bundle, request, projection, {}, EPOCH, "salt") == selected
    assert selected.notice is None


def test_mixed_shortages_fall_back_to_weak_then_new_without_hidden_repeats(content):
    from app.learning.selection import mixed_candidates

    bundle, projection = selection_bank(content, review=1)
    selected = mixed_candidates(bundle, selection_request(), projection, {}, EPOCH, "salt")
    assert (sum(task.id.startswith("weak") for task in selected.tasks),
            sum(task.id.startswith("review") for task in selected.tasks),
            sum(task.id.startswith("new") for task in selected.tasks)) == (7, 1, 2)
    assert selected.notice
    scarce, projection = selection_bank(content, weak=0, review=1, new=4)
    selected = mixed_candidates(scarce, selection_request(), projection, {}, EPOCH, "salt")
    assert len(selected.tasks) == 5
    assert len({task.id for task in selected.tasks}) == 5
    assert "5" in selected.notice and "10" in selected.notice


def test_mixed_selection_respects_30_day_boundary_filters_and_explicit_repeat(content):
    from app.learning.selection import mixed_candidates

    bundle, projection = selection_bank(content)
    seen = {task.id: EPOCH - timedelta(days=30) + timedelta(microseconds=1)
            for task in bundle.tasks}
    request = selection_request(family_ids=["new-family"], difficulty=1)
    assert mixed_candidates(bundle, request, projection, seen, EPOCH, "salt").tasks == ()
    seen["new-00"] = EPOCH - timedelta(days=30)
    chosen = mixed_candidates(bundle, request, projection, seen, EPOCH, "salt")
    assert [task.id for task in chosen.tasks] == ["new-00"]
    explicit = selection_request(repeat_task_id="weak-00", family_ids=["weak-family"])
    repeated = mixed_candidates(bundle, explicit, projection, seen, EPOCH, "salt")
    assert [task.id for task in repeated.tasks] == ["weak-00"]
    assert not mixed_candidates(bundle, selection_request(skill_ids=["unrelated"]), projection,
                                {}, EPOCH, "salt").tasks
    assert not mixed_candidates(
        bundle, selection_request(difficulty=3), projection, {}, EPOCH, "salt",
    ).tasks


def test_plan_estimates_use_methodist_times_then_personal_median_not_the_mean(content):
    from app.learning.planning import estimate_seconds, plan_length
    from app.learning.policy import replay

    tasks = [item.model_copy(update={"estimated_seconds": 120}) for item in content.tasks[:5]]
    events = [evidence(str(i), active_seconds=seconds)
              for i, seconds in enumerate([10, 20, 30, 40])]
    assert estimate_seconds(tasks, replay(events)) == 600
    assert plan_length(10, tasks, replay(events)) == 5
    events.append(evidence("outlier", active_seconds=999))
    projection = replay(events)
    assert estimate_seconds(tasks, projection) == 150
    assert plan_length(10, tasks, projection) == 20
    events.extend([
        evidence("correction", task_id="outlier", active_seconds=86400, independent=False),
        evidence("help", independent=False, assisted=True, active_seconds=86400),
        evidence("skip", independent=False, skipped=True, active_seconds=86400),
        evidence("zero", active_seconds=0),
    ])
    assert estimate_seconds(tasks, replay(events)) == 150


def annotate(client, session, task, *, headers=None, **changes):
    return client.post("/api/v1/learning/annotations", headers=headers or key(), json={
        "session_id": session["id"], "task_id": task["id"], **changes,
    })


def test_annotation_lifecycle_preserves_omitted_values_and_exact_request_replay(
    learning_factory, content,
):
    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    headers = key()
    first = annotate(client, session, task, headers=headers, favourite=True)
    assert first.status_code == 200, first.text
    assert first.json()["manual"] is False
    saved = annotate(client, session, task, manual=True, cause="calculation")
    assert saved.status_code == 200
    assert saved.json()["favourite"] is True
    data = client.get("/api/v1/learning/dashboard").json()
    assert data["favourites"][0]["task"]["id"] == task["id"]
    assert data["journal"][0]["attempt"] is None
    assert data["journal"][0]["cause"] == "calculation"
    assert data["journal"][0]["manual"] is True
    assert data["independent_total"] == 0
    assert data["reviews"] == []
    cleared = annotate(client, session, task, cause=None, favourite=False)
    assert cleared.json()["cause"] is None
    assert cleared.json()["manual"] is True
    assert annotate(client, session, task, headers=headers, favourite=True).content == first.content
    assert annotate(client, session, task, headers=headers,
                    favourite=True, manual=False).status_code == 409
    assert client.get("/api/v1/learning/dashboard").json()["favourites"] == []

    wrong = answer(client, session, task, "987654321").json()
    answer(client, session, task, expected(content, task))
    assert annotate(client, session, task, manual=False, cause="theory").status_code == 200
    journal = client.get("/api/v1/learning/dashboard").json()["journal"]
    assert len(journal) == 1
    assert journal[0]["attempt"] == wrong
    assert journal[0]["cause"] == "theory"
    assert journal[0]["manual"] is False


def test_not_understood_creates_one_durable_review_and_clearing_a_note_keeps_evidence(
    learning_factory, clock,
):
    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    first = annotate(client, session, task, not_understood=True)
    assert first.status_code == 200, first.text
    data = client.get("/api/v1/learning/dashboard").json()
    reviews = data["reviews"]
    assert reviews and all(item["due_at"] == (clock[0] + timedelta(days=1)).isoformat()
                           for item in reviews)
    assert data["journal"][0]["not_understood"] is True
    assert data["journal"][0]["attempt"] is None
    clock[0] += timedelta(hours=2)
    assert annotate(client, session, task, not_understood=True).status_code == 200
    assert client.get("/api/v1/learning/dashboard").json()["reviews"] == reviews
    assert annotate(client, session, task, not_understood=False).status_code == 200
    data = client.get("/api/v1/learning/dashboard").json()
    assert data["journal"] == []
    assert data["reviews"] == reviews
    assert data["independent_total"] == data["skipped_total"] == 0
    restarted = learning_factory(database_url=client.app.state.settings.database_url)
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == data


def test_not_understood_note_does_not_disqualify_the_first_unassisted_answer(
    learning_factory, content, clock,
):
    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    assert annotate(client, session, task, not_understood=True).status_code == 200
    reviews = client.get("/api/v1/learning/dashboard").json()["reviews"]
    clock[0] += timedelta(minutes=1)
    attempt = answer(client, session, task, expected(content, task)).json()
    assert attempt["independent"] is True
    assert attempt["assisted"] is False
    data = client.get("/api/v1/learning/dashboard").json()
    assert (data["independent_total"], data["independent_correct"]) == (1, 1)
    assert data["reviews"] == reviews
    assert data["journal"][0]["attempt"] == attempt


def test_annotations_reject_foreign_tasks_bad_types_missing_keys_and_unsafe_origins(
    learning_factory,
):
    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    outsider = learning_factory(database_url=client.app.state.settings.database_url)
    assert annotate(outsider, session, task, manual=True).status_code == 401
    outsider.post("/api/v1/guest", json={})
    assert annotate(outsider, session, task, manual=True).status_code == 404
    assert annotate(client, session, {"id": "foreign-task"}, favourite=True).status_code == 404
    for body in ({"favourite": None}, {"manual": 1}, {"cause": "guessed"}, {}, {"owner_id": "x"}):
        assert annotate(client, session, task, **body).status_code == 422
    assert client.post("/api/v1/learning/annotations", json={
        "session_id": session["id"], "task_id": task["id"], "favourite": True,
    }).status_code == 422
    assert annotate(client, session, task, manual=True,
                    headers={**key(), "Origin": "https://foreign.example"}).status_code == 403


def test_http_plan_uses_personal_median_and_does_not_issue_or_repeat_tasks(
    learning_factory, content_dir, content,
):
    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    for task in tasks:
        task["estimated_seconds"] = 90
    path.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    client = learning_factory()
    assert client.get("/api/v1/learning/plan?minutes=10").status_code == 401
    client.post("/api/v1/guest", json={})
    initial = client.get("/api/v1/learning/plan?minutes=10")
    assert initial.status_code == 200, initial.text
    assert initial.json()["length"] == 5
    assert initial.json()["estimated_seconds"] == 450
    assert initial.json()["selection"] == "mixed"
    assert client.get("/api/v1/export").json()["sessions"] == []
    session = start(client).json()
    for task, seconds in zip(session["tasks"], [10, 20, 30, 40, 999], strict=True):
        response = answer(client, session, task, expected(content, task), seconds=seconds)
        assert response.status_code == 200, response.text
    planned = client.get("/api/v1/learning/plan?minutes=10").json()
    assert planned["length"] == 20
    assert planned["estimated_seconds"] == 600
    assert planned["slots"] == list(range(1, 14))
    assert client.get("/api/v1/learning/plan?minutes=10").json() == planned
    assert len(client.get("/api/v1/export").json()["sessions"]) == 1
    assert client.get("/api/v1/learning/plan?minutes=15").status_code == 422


def test_export_and_dashboard_pages_are_bounded_safe_and_durable(learning_factory):
    client = learning_factory()
    assert client.get("/api/v1/learning/export").status_code == 401
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    for task in session["tasks"]:
        assert annotate(client, session, task, manual=True, favourite=True).status_code == 200
    first = client.get("/api/v1/learning/export?limit=2")
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["algorithm_version"] == "learning-v1"
    assert len(data["annotations"]) == 2
    assert data["pagination"] == {
        "offset": 0, "limit": 2, "totals": {"annotations": 5, "reviews": 0},
    }
    second = client.get("/api/v1/learning/export?limit=2&offset=2").json()
    assert {item["id"] for item in data["annotations"]}.isdisjoint(
        {item["id"] for item in second["annotations"]},
    )
    dashboard = client.get("/api/v1/learning/dashboard?limit=2").json()
    assert len(dashboard["journal"]) == len(dashboard["favourites"]) == 2
    assert dashboard["pagination"]["totals"]["journal"] == 5
    for forbidden in ("token_digest", "guest_id", "owner_id", "secret", "answer", "solution"):
        assert forbidden not in first.text
    assert client.get("/api/v1/learning/export?limit=101").status_code == 422
    assert client.get("/api/v1/learning/dashboard?offset=-1").status_code == 422
    restarted = learning_factory(database_url=client.app.state.settings.database_url)
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/v1/learning/export?limit=2").json() == data


def test_legacy_frozen_profile_ids_survive_current_slot_renumbering(
    learning_factory, content_dir, content,
):
    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    wrong = answer(client, session, task, "987654321").json()
    frozen = finish(client, session).json()
    stable = content.profile.slots[0].id
    for filename in ("profile.json", "tasks.json", "lessons.json"):
        path = content_dir / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data["slots"] if filename == "profile.json" else data
        field = "number" if filename == "profile.json" else "slot"
        for item in records:
            item[field] = {1: 2, 2: 1}.get(item[field], item[field])
        if filename == "profile.json":
            data["revision"] = "renumbered-2"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    slots = {item["number"]: item for item in data["slots"]}
    assert (slots[2]["slot_id"], slots[2]["attempts"]) == (stable, 1)
    assert slots[1]["attempts"] == 0
    assert all(item["slot"] == 2 and item["slot_id"] == stable for item in data["reviews"])
    original = data["journal"][0]
    assert original["task"]["slot"] == 1
    assert original["task"]["slot_id"] == stable
    assert original["profile_id"] == content.profile.id
    assert original["profile_revision"] == content.profile.revision
    assert original["attempt"] == wrong
    assert client.get(f"/api/v1/sessions/{session['id']}").json() == frozen


def test_editorial_exclusion_has_a_visible_reason_and_leaves_frozen_results_intact(
    learning_factory, clock,
):
    from app.editor.models import CorrectionExclusion

    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    answer(client, session, task, "987654321")
    frozen = finish(client, session).json()
    assert client.get("/api/v1/learning/dashboard").json()["independent_total"] == 1
    correction_id = str(uuid4())
    # External editorial storage is a fixture; the learning observation is HTTP.
    with client.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=correction_id, task_id=task["id"], task_revision=task["revision"],
            reason="В условии пропущено ограничение.", actor_id="test-methodist",
            created_at=clock[0],
        ))
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["independent_total"] == 0
    assert data["excluded_total"] == 1
    assert data["reviews"] == []
    assert data["notice"] and "исключены" in data["notice"]
    assert data["notifications"][0]["id"] == correction_id
    assert "В условии пропущено ограничение." in data["notifications"][0]["message"]
    assert len(data["journal"]) == 1
    assert client.get(f"/api/v1/sessions/{session['id']}").json() == frozen
    assert client.get("/api/v1/learning/export").json()["reviews"] == []


def test_algorithm_version_is_durable_and_recalculation_is_explained(learning_factory):
    from app.learning.policy import LearningPolicy
    from app.learning.service import LearningExtrasService

    client = learning_factory()
    client.post("/api/v1/guest", json={})
    assert client.get("/api/v1/learning/dashboard").json()["algorithm_version"] == "learning-v1"
    changed = replace(LearningPolicy(), version="learning-v2", mastery_attempts=25)
    client.app.state.learning = LearningExtrasService(client.app.state.service, policy=changed)
    data = client.get("/api/v1/learning/dashboard").json()
    assert data["algorithm_version"] == "learning-v2"
    assert "learning-v1" in data["notice"] and "learning-v2" in data["notice"]
    restarted = learning_factory(database_url=client.app.state.settings.database_url)
    restarted.cookies.update(client.cookies)
    restarted.app.state.learning = LearningExtrasService(
        restarted.app.state.service, policy=changed,
    )
    assert restarted.get("/api/v1/learning/dashboard").json() == data
    restarted.app.state.learning = LearningExtrasService(
        restarted.app.state.service, policy=replace(changed, mastery_attempts=30),
    )
    response = restarted.get("/api/v1/learning/dashboard")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "policy_version_conflict"


def test_first_account_projection_explains_a_policy_upgrade_from_claimed_guest_history(
    account_learning_factory,
):
    from app.learning.policy import LearningPolicy
    from app.learning.service import LearningExtrasService

    client, mailbox = account_learning_factory()
    client.post("/api/v1/guest", json={})
    assert client.get("/api/v1/learning/dashboard").json()["algorithm_version"] == "learning-v1"
    learning_login(client, mailbox)
    upgraded = replace(LearningPolicy(), version="learning-v2", mastery_attempts=25)
    client.app.state.learning = LearningExtrasService(client.app.state.service, policy=upgraded)
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    notice = response.json()["notice"]
    assert notice and "learning-v1" in notice and "learning-v2" in notice
    assert client.get("/api/v1/learning/dashboard").json()["notice"] == notice


def test_merged_origins_deduplicate_achievement_and_preserve_source_history_and_replay(
    account_learning_factory, content, clock,
):
    one, mail_one = account_learning_factory()
    first_owner = one.post("/api/v1/guest", json={}).json()["id"]
    old_token = one.cookies.get("math_ege_guest")
    first = start(one).json()
    task = first["tasks"][0]
    wrong = answer(one, first, task, "987654321").json()
    correction = answer(one, first, task, expected(content, task)).json()
    headers = key()
    annotation = annotate(one, first, task, headers=headers, favourite=True, cause="calculation")
    assert annotation.status_code == 200
    frozen_first = finish(one, first).json()
    assert one.get("/api/v1/learning/dashboard").json()["independent_total"] == 1

    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    second_owner = two.post("/api/v1/guest", json={}).json()["id"]
    second = start(two).json()
    second_task = next(item for item in second["tasks"] if item["id"] == task["id"])
    clock[0] += timedelta(minutes=10)
    duplicate = answer(two, second, second_task, expected(content, task)).json()
    assert duplicate["independent"] is True
    frozen_second = finish(two, second).json()
    assert two.get("/api/v1/learning/dashboard").json()["independent_correct"] == 1
    original_reviews = one.get("/api/v1/learning/dashboard").json()["reviews"]

    account = learning_login(one, mail_one)
    assert learning_login(two, mail_two)["id"] == account["id"]
    assert {first_owner, second_owner} <= set(one.get("/api/v1/account").json()["owner_ids"])
    response = one.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    merged = response.json()
    assert (merged["independent_total"], merged["independent_correct"]) == (1, 0)
    assert merged["reviews"] == original_reviews
    assert [entry["id"] for entry in merged["journal"]] == [wrong["id"]]
    assert merged["journal"][0]["attempt"] == wrong
    assert len(merged["favourites"]) == 1
    assert two.get("/api/v1/learning/dashboard").json() == merged
    assert annotate(two, first, task, headers=headers, favourite=True,
                    cause="calculation").content == annotation.content
    assert annotate(two, first, task, headers=headers, favourite=False).status_code == 409

    for route in ("/api/v1/export", "/api/v1/account/export"):
        sessions = {item["id"]: item for item in one.get(route).json()["sessions"]}
        assert sessions == {first["id"]: frozen_first, second["id"]: frozen_second}
        identifiers = {attempt["id"] for session in sessions.values()
                       for attempt in session["attempts"]}
        assert identifiers == {
            wrong["id"], correction["id"], duplicate["id"],
        }
        assert sessions[second["id"]]["attempts"][0]["independent"] is True
    restarted, _ = account_learning_factory(**shared)
    restarted.cookies.update(one.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == merged
    assert restarted.get("/api/v1/learning/export").json() == (
        one.get("/api/v1/learning/export").json()
    )
    outsider, _ = account_learning_factory(**shared)
    outsider.cookies.set("math_ege_guest", old_token)
    assert outsider.get("/api/v1/learning/dashboard").status_code == 401
    outsider.cookies.clear()
    outsider.post("/api/v1/guest", json={})
    assert outsider.get("/api/v1/learning/dashboard").json()["independent_total"] == 0
    assert outsider.get("/api/v1/learning/export").json()["annotations"] == []
    assert annotate(outsider, first, task, favourite=True).status_code == 404


def test_assessment_learning_uses_only_released_server_rows_and_survives_restart(
    assessment_learning_factory, content, clock,
):
    from tests.test_assessments import activate, correct_answers, finalize, prepare, save, view

    client = assessment_learning_factory()
    client.post("/api/v1/guest", json={})
    device = str(uuid4())
    prepared = prepare(client, device=device, duration_minutes=15)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    task, wrong, invalid = assessment["tasks"][:3]

    def assert_hidden():
        response = client.get("/api/v1/learning/dashboard")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["independent_total"] == data["skipped_total"] == 0
        assert data["assessment_history"] == data["journal"] == data["reviews"] == []
        assert data["notifications"] == data["favourites"] == []
        exported = client.get("/api/v1/learning/export").json()
        assert exported["reviews"] == exported["annotations"] == []
        assert annotate(client, assessment, task, favourite=True).status_code == 404

    assert_hidden()
    active = activate(client, assessment, device)
    assert active.status_code == 200, active.text
    server_answers = {
        task["id"]: {"answer": expected(content, task), "active_seconds": 17},
        wrong["id"]: {"answer": "987654321", "active_seconds": 13},
        invalid["id"]: {"answer": "2,", "active_seconds": 4},
    }
    assert save(client, assessment, device, server_answers).status_code == 200
    assert_hidden()
    clock[0] += timedelta(minutes=15)
    pending = view(client, assessment, device).json()
    assert pending["status"] == "awaiting_snapshot"
    assert pending["server_result"] is pending["local_result"] is None
    assert_hidden()

    local_answers = correct_answers(content, assessment)
    headers = key()
    finished = finalize(client, assessment, device, local_answers, lost=True, headers=headers)
    assert finished.status_code == 200, finished.text
    server, local = (finished.json()[name] for name in ("server_result", "local_result"))
    assert (server["score"], local["score"]) == (1, 13)
    response = client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["independent_total"], data["independent_correct"], data["skipped_total"]) == (
        2, 1, 10,
    )
    assert data["assisted_total"] == data["corrections_total"] == 0
    assert len(data["assessment_history"]) == 1
    summary = data["assessment_history"][0]
    assert (summary["id"], summary["score"], summary["format_errors"]) == (assessment["id"], 1, 1)
    assert summary["snapshot_at"] == active.json()["deadline_at"]
    journal = {entry["id"]: entry for entry in data["journal"]}
    assert set(journal) == {row["id"] for row in server["rows"] if not row["correct"]}
    assert set(journal).isdisjoint(row["id"] for row in local["rows"])
    for row in server["rows"]:
        if row["correct"]:
            continue
        entry = journal[row["id"]]
        assert entry["attempt"]["raw_answer"] == row["raw"]
        assert entry["attempt"]["normalized_answer"] == row["normalized"]
        assert entry["attempt"]["created_at"] == server["snapshot_at"]
        assert entry["profile_revision"] == assessment["profile_revision"]
        assert not {"answer", "hints", "solution", "source"} & entry["task"].keys()
    assert all(item["interval_days"] == 1 for item in data["reviews"])
    assert finalize(client, assessment, device, local_answers,
                    lost=True, headers=headers).content == finished.content
    assert client.get("/api/v1/learning/dashboard").json() == data
    assert annotate(client, assessment, invalid, favourite=True, cause="format").status_code == 200
    data = client.get("/api/v1/learning/dashboard").json()
    assert data["favourites"][0]["task"]["id"] == invalid["id"]
    invalid_entry = next(item for item in data["journal"] if item["task"]["id"] == invalid["id"])
    assert invalid_entry["cause"] == "format"

    shared = {"database_url": client.app.state.settings.database_url}
    restarted = assessment_learning_factory(**shared)
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == data
    assert restarted.get("/api/v1/learning/export").json() == (
        client.get("/api/v1/learning/export").json()
    )
    assert view(restarted, assessment).json()["server_result"] == server
    assert view(restarted, assessment).json()["local_result"] == local
    outsider = assessment_learning_factory(**shared)
    outsider.post("/api/v1/guest", json={})
    assert outsider.get("/api/v1/learning/dashboard").json()["assessment_history"] == []
    assert outsider.get("/api/v1/learning/export").json()["reviews"] == []
    assert annotate(outsider, assessment, task, favourite=True).status_code == 404


@pytest.mark.parametrize("level", [1, None])
def test_help_hook_resets_immediately_once_and_reuses_the_callers_transaction(
    learning_factory, content, clock, level,
):
    from app.accounts.principals import resolve_guest
    from app.learning.evidence import record_help
    from app.models import LearningSessionRecord

    client = learning_factory()
    client.post("/api/v1/guest", json={})
    session = start(client).json()
    task = session["tasks"][0]
    token = client.cookies.get("math_ege_guest")
    bundle = client.app.state.service.content()

    def signal():
        with client.app.state.database.transaction(write=True) as db:
            guest = resolve_guest(db, token, clock[0], write=True)
            record = db.get(LearningSessionRecord, session["id"])
            record_help(db, guest, record, task["id"], clock[0], level=level)
            return client.app.state.learning.dashboard_for(db, guest, bundle, now=clock[0])

    # The coordinator hook is a public in-transaction seam. Rollback proves the
    # signal does not commit independently of the core mutation that calls it.
    with (
        pytest.raises(RuntimeError, match="caller rollback"),
        client.app.state.database.transaction(write=True) as db,
    ):
        guest = resolve_guest(db, token, clock[0], write=True)
        record_help(db, guest, db.get(LearningSessionRecord, session["id"]),
                    task["id"], clock[0], level=level)
        raise RuntimeError("caller rollback")
    assert client.get("/api/v1/learning/dashboard").json()["reviews"] == []

    route = "solution" if level is None else "hints"
    body = {"task_id": task["id"]} | ({"level": level} if level is not None else {})
    assert client.post(f"/api/v1/sessions/{session['id']}/{route}", json=body).status_code == 200
    in_transaction = signal().model_dump()
    data = client.get("/api/v1/learning/dashboard").json()
    assert data == in_transaction
    assert data["independent_total"] == data["assisted_total"] == 0
    assert len(data["reviews"]) == len(task["skill_ids"])
    due = (clock[0] + timedelta(days=1)).isoformat()
    assert all(item["due_at"] == due and item["interval_days"] == 1 for item in data["reviews"])
    clock[0] += timedelta(hours=2)
    assert signal().model_dump()["reviews"] == data["reviews"]
    assisted = answer(client, session, task, expected(content, task)).json()
    assert assisted["assisted"] is True and assisted["independent"] is False
    after = client.get("/api/v1/learning/dashboard").json()
    assert after["independent_total"] == 0
    assert after["assisted_total"] == 1
    assert all(item["due_at"] == (clock[0] + timedelta(days=1)).isoformat()
               for item in after["reviews"])
    restarted = learning_factory(database_url=client.app.state.settings.database_url)
    restarted.cookies.update(client.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == after


def test_mixed_selection_hook_uses_merged_http_history_and_editorial_exclusions(
    account_learning_factory, content, content_dir, clock,
):
    from app.accounts.principals import resolve_guest
    from app.editor.models import CorrectionExclusion
    from app.instances import instance_key
    from app.learning.selection import select_tasks, selection_details
    from app.schemas import CreateSessionRequest

    bank, _ = selection_bank(content)
    assert len({instance_key(task) for task in bank.tasks}) == len(bank.tasks)
    path = content_dir / "tasks.json"
    path.write_text(json.dumps([
        *json.loads(path.read_text(encoding="utf-8")),
        *(task.model_dump(mode="json") for task in bank.tasks),
    ], ensure_ascii=False), encoding="utf-8")
    one, mail_one = account_learning_factory()
    one.post("/api/v1/guest", json={})

    def practise(client, family):
        response = client.post("/api/v1/sessions", headers=key(), json={
            "mode": "practice", "slots": [1], "length": 5, "family_ids": [family],
        })
        assert response.status_code == 200, response.text
        session = response.json()
        assert answer(client, session, session["tasks"][0], "987654321").status_code == 200
        assert finish(client, session).status_code == 200
        return {task["id"] for task in session["tasks"]}

    seen = practise(one, "review-family")
    clock[0] += timedelta(days=2)
    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    two.post("/api/v1/guest", json={})
    seen |= practise(two, "weak-family")
    learning_login(one, mail_one)
    learning_login(two, mail_two)
    request = CreateSessionRequest(
        slots=[1], length=10, mode="practice", selection="mixed", difficulty=1,
        family_ids=["weak-family", "review-family", "new-family"],
        skill_ids=[bank.tasks[0].skill_ids[0]],
    )

    def select(client):
        with client.app.state.database.transaction(write=True) as db:
            guest = resolve_guest(db, client.cookies.get("math_ege_guest"), clock[0], write=True)
            result = selection_details(db, guest, bank, request, clock[0], "stable-salt")
            assert select_tasks(db, guest, bank, request, clock[0], "stable-salt") == list(
                result.tasks,
            )
            return result

    history = one.get("/api/v1/export").json()["sessions"]
    chosen = select(one)
    assert chosen.quotas == chosen.counts == (5, 3, 2)
    assert len({task.id for task in chosen.tasks}) == 10
    assert {task.id for task in chosen.tasks}.isdisjoint(seen)
    assert tuple(sum(task.family_id == family for task in chosen.tasks)
                 for family in ("weak-family", "review-family", "new-family")) == (5, 3, 2)
    assert select(two) == chosen
    assert select(one) == chosen
    assert one.get("/api/v1/export").json()["sessions"] == history

    removed = chosen.tasks[0]
    with one.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id=removed.id, task_revision=removed.revision,
            reason="Проверка исключения из нового подбора.", actor_id="test-methodist",
            created_at=clock[0],
        ))
    revised = select(two)
    assert removed.id not in {task.id for task in revised.tasks}
    assert revised.counts == (5, 3, 2)
    outsider, _ = account_learning_factory(**shared)
    outsider.post("/api/v1/guest", json={})
    assert select(outsider).counts == (0, 0, 10)


def test_learning_migration_preserves_populated_history_and_matches_models(
    assessment_learning_factory, content, content_dir, clock, tmp_path,
):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from fastapi.testclient import TestClient
    from sqlalchemy import MetaData, inspect, select

    from app.config import Settings
    from app.database import Database
    from app.learning.api import router
    from app.learning.service import LearningExtrasService
    from app.main import create_app
    from app.models import Base
    from tests.conftest import MUTATION_HEADERS, TEST_ORIGIN
    from tests.test_assessments import activate, correct_answers, finalize, prepare

    source = assessment_learning_factory()
    source.post("/api/v1/guest", json={})
    practice = start(source).json()
    task = practice["tasks"][0]
    answer(source, practice, task, "987654321", seconds=23)
    frozen = finish(source, practice).json()
    device = str(uuid4())
    assessment = prepare(source, device=device, mode="diagnostic").json()
    assert activate(source, assessment, device).status_code == 200
    completed = finalize(source, assessment, device, correct_answers(content, assessment))
    assert completed.status_code == 200, completed.text
    expected_dashboard = source.get("/api/v1/learning/dashboard").json()

    backend = Path(__file__).resolve().parents[1]
    migration = Config(str(backend / "alembic.ini"))
    migration.set_main_option("script_location", str(backend / "migrations"))
    url = f"sqlite:///{(tmp_path / 'learning-migration.sqlite3').as_posix()}"
    migration.set_main_option("sqlalchemy.url", url)
    command.upgrade(migration, "0003_assessments")
    settings = Settings(
        database_url=url, content_dir=content_dir, allow_demo_content=True,
        allowed_origins=(TEST_ORIGIN,),
    )
    database = Database(settings)
    try:
        legacy = MetaData()
        legacy.reflect(bind=database.engine, only=[
            name for name in inspect(database.engine).get_table_names() if name != "alembic_version"
        ])

        def snapshot(engine):
            with engine.connect() as connection:
                return {
                    table.name: [dict(row) for row in connection.execute(
                        select(table).order_by(*table.primary_key),
                    ).mappings()]
                    for table in legacy.sorted_tables
                }

        # Copy genuine HTTP-created history using only predecessor columns.
        before = snapshot(source.app.state.database.engine)
        assert all(before[name]
                   for name in ("guests", "learning_sessions", "attempts", "assessments"))
        with database.engine.begin() as connection:
            for table in legacy.sorted_tables:
                if before[table.name]:
                    connection.execute(table.insert(), before[table.name])
        assert snapshot(database.engine) == before
        command.upgrade(migration, "0004_learning")
        assert snapshot(database.engine) == before

        names = {"learning_evidence", "learning_policy_states", "learning_annotations"}
        metadata = MetaData(naming_convention=Base.metadata.naming_convention)
        for name in names | {"guests"}:
            Base.metadata.tables[name].to_metadata(metadata)
        with database.engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={
                "include_object": lambda obj, name, kind, reflected, compared: (
                    name in names if kind == "table" else True
                ),
            })
            assert compare_metadata(context, metadata) == []
            for name in names:
                actual_checks = {item["sqltext"]
                                 for item in inspect(connection).get_check_constraints(name)}
                model_checks = {str(item.sqltext) for item in metadata.tables[name].constraints
                                if hasattr(item, "sqltext")}
                assert actual_checks == model_checks
        with pytest.raises(RuntimeError, match="must not be deleted"):
            command.downgrade(migration, "0003_assessments")
        assert snapshot(database.engine) == before
        command.upgrade(migration, "head")
        assert snapshot(database.engine) == before
    finally:
        database.dispose()

    app = create_app(settings, clock=lambda: clock[0])
    app.state.learning = LearningExtrasService(app.state.service)
    if not any(getattr(route, "path", None) == "/api/v1/learning/dashboard"
               for route in app.routes):
        app.include_router(router)
    # No create_schema_for_tests: every table used here must come from Alembic.
    with TestClient(app, base_url=TEST_ORIGIN, headers=MUTATION_HEADERS) as migrated:
        migrated.cookies.update(source.cookies)
        response = migrated.get("/api/v1/learning/dashboard")
        assert response.status_code == 200, response.text
        assert response.json() == expected_dashboard
        assert annotate(migrated, practice, task, favourite=True).status_code == 200
        exported = migrated.get("/api/v1/learning/export").json()
        assert exported["annotations"][0]["task_id"] == task["id"]
        original = migrated.get(f"/api/v1/sessions/{practice['id']}").json()
        for name in (
            "id", "profile_id", "tasks", "attempts", "summary", "created_at", "completed_at",
        ):
            assert original[name] == frozen[name]
