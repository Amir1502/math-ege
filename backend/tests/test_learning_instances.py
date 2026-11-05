"""Runtime alias integration at policy, HTTP and immutable-ledger seams."""

import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text

from app.accounts.models import AccessSession
from app.content import ContentBundle
from app.editor.models import CorrectionExclusion
from app.instances import instance_key
from app.learning.evidence import load_history
from app.learning.models import EvidenceRecord, LearningState
from app.learning.policy import replay
from app.learning.selection import mixed_candidates, selection_details
from app.models import Guest, LearningSessionRecord, SeenTask
from tests.helpers import answer, finish, start
from tests.test_assessments import activate, finalize, prepare
from tests.test_assessments import single_slot_bank as single_slot_bank
from tests.test_learning import (
    EPOCH,
    annotate,
    evidence,
    learning_login,
    selection_bank,
    selection_request,
)
from tests.test_learning import account_learning_factory as account_learning_factory
from tests.test_learning import learning_factory as learning_factory


def install_alias(content_dir, original):
    """Change the isolated current bank; previously issued snapshots stay frozen."""
    alias = original.model_copy(update={"id": "learning-visible-alias", "revision": "alias-2"})
    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps([
        alias.model_dump(mode="json") if item["id"] == original.id else item for item in tasks
    ], ensure_ascii=False), encoding="utf-8")
    return alias


@pytest.mark.parametrize("source", ["practice", "assessment"])
def test_linked_origins_deduplicate_visible_aliases_and_keep_source_results(
    account_learning_factory, single_slot_bank, content_dir, clock, source,
):
    one, mail_one = account_learning_factory()
    owner_one = one.post("/api/v1/guest", json={}).json()["id"]
    first = start(one).json()
    task = first["tasks"][0]
    original = next(item for item in single_slot_bank.tasks if item.id == task["id"])
    wrong = answer(one, first, task, "987654321")
    assert wrong.status_code == 200, wrong.text
    frozen = finish(one, first).json()
    assert one.get("/api/v1/learning/dashboard").json()["independent_total"] == 1

    alias = install_alias(content_dir, original)
    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    owner_two = two.post("/api/v1/guest", json={}).json()["id"]
    clock[0] += timedelta(seconds=1)
    if source == "practice":
        second = start(two).json()
        alias_task = next(item for item in second["tasks"] if item["id"] == alias.id)
        response = answer(two, second, alias_task, alias.answer)
        assert response.status_code == 200, response.text
        original_result = finish(two, second).json()
        original_attempt = response.json()
    else:
        device = str(uuid4())
        prepared = prepare(two, mode="diagnostic", device=device)
        assert prepared.status_code == 200, prepared.text
        second = prepared.json()
        assert activate(two, second, device).status_code == 200
        assert two.get("/api/v1/learning/dashboard").json()["independent_total"] == 0
        completed = finalize(two, second, device, {
            alias.id: {"answer": alias.answer, "active_seconds": 12},
        })
        assert completed.status_code == 200, completed.text
        original_result = completed.json()["server_result"]
        original_attempt = next(
            row for row in original_result["rows"] if row["task_id"] == alias.id
        )
    assert original_attempt["independent"] is original_attempt["first_attempt"] is True
    assert original_attempt["task_id"] != wrong.json()["task_id"]
    assert two.get("/api/v1/learning/dashboard").json()["independent_total"] == 1

    account = learning_login(one, mail_one)
    assert learning_login(two, mail_two)["id"] == account["id"]
    assert {owner_one, owner_two} <= set(one.get("/api/v1/account").json()["owner_ids"])
    response = one.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    merged = response.json()
    assert (
        merged["independent_total"], merged["independent_correct"], merged["corrections_total"],
    ) == (1, 0, 1)
    assert merged["skipped_total"] == (12 if source == "assessment" else 0)
    assert one.get(f"/api/v1/sessions/{first['id']}").json() == frozen
    if source == "practice":
        assert two.get(f"/api/v1/sessions/{second['id']}").json() == original_result
    else:
        saved = two.get(f"/api/v1/assessments/{second['id']}").json()
        assert saved["server_result"] == original_result
    assert two.get("/api/v1/learning/dashboard").json() == merged
    restarted, _ = account_learning_factory(**shared)
    restarted.cookies.update(one.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == merged

    with one.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id=original.id, task_revision=original.revision,
            reason="Ошибка прежней редакции.", actor_id="alias-fixture", created_at=clock[0],
        ))
    excluded = one.get("/api/v1/learning/dashboard").json()
    assert (
        excluded["independent_total"], excluded["corrections_total"], excluded["excluded_total"],
    ) == (0, 1, 1)
    assert any(item["attempt"] == wrong.json() for item in excluded["journal"])
    assert one.get(f"/api/v1/sessions/{first['id']}").json() == frozen


@pytest.mark.parametrize("signal", ["help", "not_understood"])
def test_alias_of_help_or_difficulty_anchor_cannot_satisfy_other_instance_review(
    account_learning_factory, single_slot_bank, content_dir, clock, signal,
):
    one, mail_one = account_learning_factory()
    assert one.post("/api/v1/guest", json={}).status_code == 200
    first = start(one).json()
    task = first["tasks"][0]
    original = next(item for item in single_slot_bank.tasks if item.id == task["id"])
    if signal == "help":
        response = one.post(f"/api/v1/sessions/{first['id']}/hints", json={
            "task_id": task["id"], "level": 1,
        })
    else:
        response = annotate(one, first, task, not_understood=True)
    assert response.status_code == 200, response.text
    initial = one.get("/api/v1/learning/dashboard").json()
    assert initial["reviews"]

    alias = install_alias(content_dir, original)
    two, mail_two = account_learning_factory(database_url=one.app.state.settings.database_url)
    assert two.post("/api/v1/guest", json={}).status_code == 200
    second = start(two).json()
    alias_task = next(item for item in second["tasks"] if item["id"] == alias.id)
    clock[0] += timedelta(days=3)
    answered = answer(two, second, alias_task, alias.answer)
    assert answered.status_code == 200, answered.text
    assert answered.json()["independent"] is True
    account = learning_login(one, mail_one)
    assert learning_login(two, mail_two)["id"] == account["id"]

    response = one.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    merged = response.json()
    assert {item["due_at"] for item in merged["reviews"]} == {
        (EPOCH + timedelta(days=1)).isoformat(),
    }
    assert {item["interval_days"] for item in merged["reviews"]} == {1}
    assert merged["independent_total"] == (1 if signal == "not_understood" else 0)
    assert merged["corrections_total"] == 0
    exported = one.get("/api/v1/learning/export")
    assert exported.status_code == 200, exported.text
    assert {item["anchor_task_id"] for item in exported.json()["reviews"]} == {original.id}
    assert "instance_id" not in response.text and "instance_id" not in exported.text
    assert one.get("/api/v1/learning/dashboard").json() == merged


def test_retention_needs_another_condition_but_keeps_the_original_anchor_task_id():
    signal = evidence(
        "difficulty", task_id="original-a", instance_id="condition-a", correct=False,
        independent=False, source="not_understood",
    )
    alias = evidence(
        "alias-answer", task_id="original-b", instance_id="condition-a",
        at=EPOCH + timedelta(days=3),
    )
    after_alias = replay([signal, alias])
    assert after_alias.evidence[-1].independent is True
    assert after_alias.retention == ()
    assert after_alias.reviews[0].anchor_task_id == "original-a"
    assert after_alias.reviews[0].due_at == EPOCH + timedelta(days=1)

    different = evidence(
        "different-answer", task_id="original-c", instance_id="condition-b",
        at=EPOCH + timedelta(days=6),
    )
    confirmed = replay([signal, alias, different])
    assert confirmed.retention[-1].success is True
    assert confirmed.retention[-1].at == different.at
    assert confirmed.reviews[0].anchor_task_id == "original-c"
    assert confirmed.reviews[0].due_at == EPOCH + timedelta(days=9)


def test_other_condition_under_a_reused_task_id_can_advance_an_independent_review():
    first = evidence(
        "first", task_id="catalog-id", instance_id="condition-a", correct=False,
    )
    changed = evidence(
        "changed", task_id="catalog-id", task_revision="2", instance_id="condition-b",
        at=EPOCH + timedelta(days=3),
    )
    projection = replay([first, changed])
    assert all(item.independent for item in projection.evidence)
    assert projection.reviews[0].interval_days == 3
    assert projection.reviews[0].anchor_task_id == "catalog-id"
    assert projection.retention[-1].success is True


def ledger_rows(client):
    """Raw SQLite JSON and original row metadata are the immutability contract."""
    with client.app.state.database.transaction() as db:
        return tuple(db.execute(text(
            "SELECT event_id, owner_id, session_id, source, payload, created_at, recorded_at "
            "FROM learning_evidence ORDER BY event_id"
        )).tuples())


@pytest.fixture
def legacy_history(request, learning_factory, single_slot_bank):
    source = getattr(request, "param", "practice")
    client = learning_factory()
    owner = client.post("/api/v1/guest", json={}).json()["id"]
    if source == "assessment":
        device = str(uuid4())
        prepared = prepare(client, mode="diagnostic", device=device)
        assert prepared.status_code == 200, prepared.text
        session = prepared.json()
        task = session["tasks"][0]
        assert activate(client, session, device).status_code == 200
        result = finalize(client, session, device, {
            task["id"]: {"answer": "987654321", "active_seconds": 0},
        })
        assert result.status_code == 200, result.text
        route = f"/api/v1/assessments/{session['id']}"
    else:
        session = start(client).json()
        task = session["tasks"][0]
        if source == "help":
            result = client.post(f"/api/v1/sessions/{session['id']}/hints", json={
                "task_id": task["id"], "level": 1,
            })
        elif source == "not_understood":
            result = annotate(client, session, task, not_understood=True)
        else:
            result = answer(client, session, task, "987654321")
        assert result.status_code == 200, result.text
        route = f"/api/v1/sessions/{session['id']}"
    dashboard = client.get("/api/v1/learning/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    exported = client.get("/api/v1/learning/export").json()
    original = client.get(route).json()
    # Seed the old serialized format in this new isolated fixture database.
    with client.app.state.database.transaction(write=True) as db:
        records = list(db.scalars(select(EvidenceRecord)))
        assert records
        for record in records:
            record.payload = {name: value for name, value in record.payload.items()
                              if name != "instance_id"}
    return SimpleNamespace(
        client=client, owner=owner, task=task, route=route, original=original,
        dashboard=dashboard.json(), exported=exported,
        snapshot=next(item for item in single_slot_bank.tasks if item.id == task["id"]),
    )


@pytest.mark.parametrize(
    "legacy_history", ["practice", "assessment", "help", "not_understood"], indirect=True,
)
def test_legacy_identity_comes_from_frozen_snapshot_without_rewriting_ledger(
    legacy_history, learning_factory, content_dir,
):
    old = legacy_history
    before = ledger_rows(old.client)
    assert all("instance_id" not in json.loads(row.payload) for row in before)
    path = content_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    for item in tasks:
        if item["id"] == old.task["id"]:
            item["statement"] = "A different condition in the current bank, not the frozen history."
            assert instance_key(item) != instance_key(old.snapshot)
    path.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")

    response = old.client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    assert response.json() == old.dashboard
    assert old.client.get("/api/v1/learning/export").json() == old.exported
    with old.client.app.state.database.transaction() as db:
        history = load_history(db, [old.owner])
    relevant = [event for event in history.events if event.task_id == old.task["id"]]
    assert relevant and {event.instance_id for event in relevant} == {instance_key(old.snapshot)}
    assert old.client.get(old.route).json() == old.original
    assert ledger_rows(old.client) == before
    restarted = learning_factory(database_url=old.client.app.state.settings.database_url)
    restarted.cookies.update(old.client.cookies)
    assert restarted.get("/api/v1/learning/dashboard").json() == old.dashboard
    assert restarted.get("/api/v1/learning/export").json() == old.exported
    assert ledger_rows(restarted) == before


@pytest.mark.parametrize(("field", "value"), [
    ("id", "changed-event"), ("task_id", "changed-task"), ("task_revision", "changed-revision"),
    ("skill_ids", ["changed-skill"]), ("family_id", "changed-family"), ("slot_id", "changed-slot"),
    ("at", (EPOCH + timedelta(seconds=1)).isoformat()), ("correct", True), ("independent", False),
    ("assisted", True), ("skipped", True), ("active_seconds", 1), ("source", "assessment"),
    ("unexpected", "extra-field"), ("missing_correct", None),
])
def test_legacy_identity_compatibility_rejects_every_other_payload_change(
    legacy_history, field, value,
):
    old = legacy_history
    with old.client.app.state.database.transaction(write=True) as db:
        record = db.scalar(select(EvidenceRecord))
        changed = dict(record.payload)
        if field == "missing_correct":
            changed.pop("correct")
        else:
            changed[field] = value
        record.payload = changed
    before = ledger_rows(old.client)
    response = old.client.get("/api/v1/learning/dashboard")
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "evidence_conflict"
    assert ledger_rows(old.client) == before
    assert old.client.get(old.route).json() == old.original


@pytest.mark.parametrize(
    "legacy_history", ["practice", "assessment", "help", "not_understood"], indirect=True,
)
@pytest.mark.parametrize("identity", [None, "0" * 64], ids=["explicit-null", "different-key"])
def test_existing_instance_identity_is_not_normalized_away(legacy_history, identity):
    old = legacy_history
    with old.client.app.state.database.transaction(write=True) as db:
        for record in db.scalars(select(EvidenceRecord)):
            record.payload = {**record.payload, "instance_id": identity}
    before = ledger_rows(old.client)
    response = old.client.get("/api/v1/learning/dashboard")
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "evidence_conflict"
    assert ledger_rows(old.client) == before
    assert old.client.get(old.route).json() == old.original


def test_instance_aware_mixed_pool_deduplicates_conditions_before_filling_quotas(content):
    bank, projection = selection_bank(content, weak=3, review=1, new=1)
    originals = tuple(task.model_copy(update={
        "statement": f"Вычислите {index + 1} + {index + 2}.",
    }) for index, task in enumerate(bank.tasks))
    aliases = tuple(task.model_copy(update={
        "id": f"runtime-alias-{task.id}", "revision": "2",
    }) for task in originals)
    combined = replace(bank, tasks=(*originals, *aliases))
    request = selection_request(length=10)
    selected = mixed_candidates(
        combined, request, projection, {}, EPOCH, "combined-pool", instance_aware=True,
    )
    assert len(selected.tasks) == len({instance_key(task) for task in selected.tasks}) == 5
    assert selected.counts == (3, 1, 1)
    assert selected.quotas == (5, 3, 2)
    assert "5 из 10" in selected.notice
    assert {instance_key(task) for task in selected.tasks} == {
        instance_key(task) for task in originals
    }
    assert mixed_candidates(
        replace(combined, tasks=tuple(reversed(combined.tasks))), request,
        projection, {}, EPOCH, "combined-pool", instance_aware=True,
    ) == selected


@pytest.mark.parametrize("explicit", [False, True], ids=["inferred", "explicit"])
@pytest.mark.parametrize("excluded", [False, True])
def test_due_selection_remembers_alias_conditions_including_excluded_evidence(
    content, excluded, explicit,
):
    original = next(task for task in content.tasks if task.slot == 1)
    skill = original.skill_ids[0]
    common = {"skill_ids": (skill,), "family_id": original.family_id,
              "slot_id": content.profile.slots[0].id}
    old = evidence(
        "original", task_id=original.id, task_revision=original.revision,
        instance_id=instance_key(original), at=EPOCH - timedelta(days=32), **common,
    )
    signal = evidence(
        "review", task_id="another-condition",
        instance_id=None if excluded else "another-condition-key",
        at=EPOCH - timedelta(days=31), correct=False, **common,
    )
    projection = replay(
        [old, signal], exclusions={(old.task_id, old.task_revision): "Ошибка."} if excluded else {},
    )
    alias = original.model_copy(update={"id": "alias-of-original", "revision": "2"})
    bank = ContentBundle(content.profile, content.lessons, (alias,))
    options = {"instance_aware": True} if explicit else {}
    selected = mixed_candidates(
        bank, selection_request(length=5), projection, {}, EPOCH, "due-alias",
        **options,
    )
    assert selected.tasks == (alias,)
    assert selected.counts == (1, 0, 0)
    assert original.id in projection.encountered_task_ids
    assert instance_key(original) in projection.encountered_instance_ids
    assert old.id in projection.excluded_ids if excluded else old.id not in projection.excluded_ids

    different = original.model_copy(update={
        "revision": "3", "statement": "Вычислите 107 + 119.",
    })
    fresh = mixed_candidates(
        replace(bank, tasks=(different,)), selection_request(length=5), projection,
        {}, EPOCH, "due-alias", **options,
    )
    assert fresh.tasks == (different,)
    assert fresh.counts == (0, 1, 0)
    duplicates = mixed_candidates(
        replace(bank, tasks=(alias, alias.model_copy(update={"id": "third-visible-alias"}))),
        selection_request(length=5), projection, {}, EPOCH, "due-alias", **options,
    )
    assert len(duplicates.tasks) == 1 and duplicates.counts == (1, 0, 0)


def test_instance_aware_seen_keys_obey_exact_boundary_and_explicit_actual_id_repeat(content):
    original = content.tasks[0]
    alias = original.model_copy(update={"id": "explicit-alias"})
    bank = ContentBundle(content.profile, content.lessons, (alias,))
    request = selection_request(length=5, slots=[original.slot])
    cutoff = EPOCH - timedelta(days=30)
    seen = {instance_key(original): cutoff + timedelta(microseconds=1)}
    assert mixed_candidates(
        bank, request, replay([]), seen, EPOCH, "boundary", instance_aware=True,
    ).tasks == ()
    repeated = mixed_candidates(
        bank, selection_request(length=5, slots=[original.slot], repeat_task_id=alias.id),
        replay([]), seen, EPOCH, "boundary", instance_aware=True,
    )
    assert repeated.tasks == (alias,)
    seen[instance_key(original)] = cutoff
    assert mixed_candidates(
        bank, request, replay([]), seen, EPOCH, "boundary", instance_aware=True,
    ).tasks == (alias,)


def test_selection_details_filters_linked_origin_aliases_and_only_fills_legacy_exposure_keys(
    account_learning_factory, single_slot_bank, clock,
):
    one, mail_one = account_learning_factory()
    owner = one.post("/api/v1/guest", json={}).json()["id"]
    first = start(one).json()
    task = first["tasks"][0]
    assert one.post(f"/api/v1/sessions/{first['id']}/hints", json={
        "task_id": task["id"], "level": 1,
    }).status_code == 200
    original = next(item for item in single_slot_bank.tasks if item.id == task["id"])
    alias = original.model_copy(update={"id": "new-alias-id", "revision": "2"})
    fresh = original.model_copy(update={
        "id": "new-condition-id", "statement": "Вычислите 123 + 321.",
    })
    pool = ContentBundle(single_slot_bank.profile, single_slot_bank.lessons, (
        alias, fresh, fresh.model_copy(update={"id": "generated-alias-of-new-condition"}),
    ))
    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    assert two.post("/api/v1/guest", json={}).status_code == 200
    learning_login(one, mail_one)
    learning_login(two, mail_two)
    frozen = one.get(f"/api/v1/sessions/{first['id']}").json()
    columns = [column for column in SeenTask.__table__.columns if column.name != "instance_key"]
    with one.app.state.database.transaction(write=True) as db:
        record = db.scalars(select(SeenTask).where(SeenTask.guest_id == owner)).one()
        record.instance_key = None
        before = tuple(db.execute(select(*columns)).tuples())

    def choose(client):
        service = client.app.state.service
        with service._guest_transaction(client.cookies.get("math_ege_guest"), write=True) as (
            db, guest,
        ):
            return selection_details(
                db, guest, pool, selection_request(length=5), clock[0], "owner-scoped-pool",
            )

    chosen = choose(two)
    assert {instance_key(item) for item in chosen.tasks} == {instance_key(fresh)}
    assert len(chosen.tasks) == 1
    assert choose(one) == chosen
    with one.app.state.database.transaction() as db:
        assert tuple(db.execute(select(*columns)).tuples()) == before
        record = db.scalars(select(SeenTask).where(SeenTask.guest_id == owner)).one()
        assert record.instance_key == instance_key(original)
        assert record.guest_id == owner and record.task_id == original.id
    assert one.get(f"/api/v1/sessions/{first['id']}").json() == frozen
    outsider, _ = account_learning_factory(**shared)
    assert outsider.post("/api/v1/guest", json={}).status_code == 200
    foreign = choose(outsider)
    assert len(foreign.tasks) == 2
    assert {instance_key(item) for item in foreign.tasks} == {
        instance_key(original), instance_key(fresh),
    }


def test_mixed_quotas_and_editorial_exclusions_use_distinct_conditions_after_owner_merge(
    account_learning_factory, content, content_dir, clock,
):
    bank, _ = selection_bank(content)
    bank = replace(bank, tasks=tuple(task.model_copy(update={
        "statement": f"Вычислите {index + 10} + 2.", "formula": None,
        "answer": str(index + 12),
    }) for index, task in enumerate(bank.tasks)))
    path = content_dir / "tasks.json"
    path.write_text(json.dumps([
        *json.loads(path.read_text(encoding="utf-8")),
        *(task.model_dump(mode="json") for task in bank.tasks),
    ], ensure_ascii=False), encoding="utf-8")
    one, mail_one = account_learning_factory()
    assert one.post("/api/v1/guest", json={}).status_code == 200

    def practise(client, family):
        response = client.post("/api/v1/sessions", headers={"Idempotency-Key": str(uuid4())}, json={
            "mode": "practice", "slots": [1], "length": 5, "family_ids": [family],
        })
        assert response.status_code == 200, response.text
        session = response.json()
        assert len(session["tasks"]) == 5
        assert answer(client, session, session["tasks"][0], "987654321").status_code == 200
        completed = finish(client, session)
        assert completed.status_code == 200, completed.text
        return completed.json()

    first = practise(one, "review-family")
    clock[0] += timedelta(days=2)
    shared = {"database_url": one.app.state.settings.database_url}
    two, mail_two = account_learning_factory(**shared)
    assert two.post("/api/v1/guest", json={}).status_code == 200
    second = practise(two, "weak-family")
    learning_login(one, mail_one)
    learning_login(two, mail_two)
    exposed = {instance_key(task) for task in (*first["tasks"], *second["tasks"])}

    def choose(client):
        service = client.app.state.service
        with service._guest_transaction(client.cookies.get("math_ege_guest"), write=True) as (
            db, guest,
        ):
            return selection_details(
                db, guest, bank, selection_request(), clock[0], "merged-quotas",
            )

    selected = choose(one)
    assert selected.quotas == selected.counts == (5, 3, 2)
    keys = {instance_key(task) for task in selected.tasks}
    assert len(keys) == 10 and keys.isdisjoint(exposed)
    assert choose(two) == selected
    removed = selected.tasks[0]
    with one.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id=removed.id, task_revision=removed.revision,
            reason="Исключение из подбора.", actor_id="learning-instance-fixture",
            created_at=clock[0],
        ))
    updated = choose(two)
    assert updated.counts == (5, 3, 2)
    assert removed.id not in {task.id for task in updated.tasks}
    assert one.get(f"/api/v1/sessions/{first['id']}").json() == first
    assert two.get(f"/api/v1/sessions/{second['id']}").json() == second
    outsider, _ = account_learning_factory(**shared)
    assert outsider.post("/api/v1/guest", json={}).status_code == 200
    assert choose(outsider).counts == (0, 0, 10)


def test_plan_excludes_recent_visible_aliases_without_issuing_or_rewriting_history(
    learning_factory, single_slot_bank, content_dir,
):
    client = learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    first = start(client, slots=list(range(1, 14)), length=20)
    assert first.status_code == 200, first.text
    original = single_slot_bank.tasks[0]
    assert original.id in {task["id"] for task in first.json()["tasks"]}
    install_alias(content_dir, original)
    with client.app.state.database.transaction(write=True) as db:
        for record in db.scalars(select(SeenTask)):
            record.instance_key = None
        sessions_before = tuple(db.execute(text(
            "SELECT id, guest_id, tasks_snapshot, profile_snapshot "
            "FROM learning_sessions ORDER BY id"
        )).tuples())
        seen_before = tuple(db.execute(select(SeenTask.id, SeenTask.last_seen_at)).tuples())
    response = client.get("/api/v1/learning/plan?minutes=10")
    assert response.status_code == 200, response.text
    assert response.json()["estimated_seconds"] == 0
    assert "Доступно 0 из" in response.json()["notice"]
    assert client.get("/api/v1/learning/plan?minutes=10").json() == response.json()
    with client.app.state.database.transaction() as db:
        assert tuple(db.execute(text(
            "SELECT id, guest_id, tasks_snapshot, profile_snapshot "
            "FROM learning_sessions ORDER BY id"
        )).tuples()) == sessions_before
        assert tuple(db.execute(select(SeenTask.id, SeenTask.last_seen_at)).tuples()) == seen_before
        assert all(record.instance_key is not None for record in db.scalars(select(SeenTask)))
    outsider = learning_factory(database_url=client.app.state.settings.database_url)
    assert outsider.post("/api/v1/guest", json={}).status_code == 200
    assert outsider.get("/api/v1/learning/plan?minutes=10").json()["estimated_seconds"] > 0


@pytest.mark.parametrize("route", ["dashboard", "plan?minutes=10"])
@pytest.mark.parametrize("principal", ["guest", "account"])
@pytest.mark.parametrize("expires", [False, True], ids=["valid", "expires-at-catalog"])
def test_learning_catalog_read_uses_one_owned_transaction_and_post_read_authorization(
    account_learning_factory, clock, route, principal, expires,
):
    client, mailbox = account_learning_factory()
    assert client.post("/api/v1/guest", json={}).status_code == 200
    session = start(client).json()
    assert answer(client, session, session["tasks"][0], "987654321").status_code == 200
    if principal == "account":
        learning_login(client, mailbox)
    database = client.app.state.database
    if expires:
        with database.transaction(write=True) as db:
            model = AccessSession if principal == "account" else Guest
            db.scalars(select(model)).one().expires_at = clock[0] + timedelta(seconds=1)
    before = ledger_rows(client)
    transactions, queries = [], []

    def begin(connection):
        transactions.append(connection.get_execution_options().get("write"))

    def after_query(connection, cursor, statement, parameters, context, executemany):
        if "FROM guests" in statement:
            queries.append("owner")
        elif "FROM editor_catalog" in statement:
            queries.append("catalog")
            clock[0] += timedelta(seconds=2)

    event.listen(database.engine, "begin", begin)
    event.listen(database.engine, "after_cursor_execute", after_query)
    try:
        response = client.get(f"/api/v1/learning/{route}")
    finally:
        event.remove(database.engine, "after_cursor_execute", after_query)
        event.remove(database.engine, "begin", begin)
    assert response.status_code == (401 if expires else 200), response.text
    assert transactions == [True]
    assert queries.count("catalog") == 1
    catalog = queries.index("catalog")
    assert "owner" in queries[:catalog] and "owner" in queries[catalog + 1:]
    if expires:
        assert response.json()["error"]["code"] == "guest_required"
        assert ledger_rows(client) == before
        with database.transaction() as db:
            assert list(db.scalars(select(LearningState))) == []
    else:
        with database.transaction() as db:
            assert db.scalars(select(LearningState)).one().updated_at == clock[0]
            assert db.scalars(select(LearningSessionRecord)).one().id == session["id"]
