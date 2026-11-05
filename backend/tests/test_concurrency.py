from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests.helpers import answer, draft, expected, finish, key, start


def twins(client_factory):
    first = client_factory()
    first.post("/api/v1/guest", json={})
    second = client_factory(database_url=first.app.state.settings.database_url)
    second.cookies.set("math_ege_guest", first.cookies.get("math_ege_guest"))
    return first, second


def race(*actions):
    barrier = Barrier(len(actions))

    def run(action):
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


def test_concurrent_create_replays_one_session_across_separate_app_engines(client_factory):
    one, two = twins(client_factory)
    headers = key()
    responses = race(*(
        lambda client=client: start(client, headers=headers) for client in (one, two) * 3
    ))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == responses[0].content for response in responses)
    assert len(one.get("/api/v1/export").json()["sessions"]) == 1


def test_concurrent_different_creates_cannot_reissue_an_instance(client_factory):
    one, two = twins(client_factory)
    responses = race(lambda: start(one), lambda: start(two))
    assert sorted(response.status_code for response in responses) == [200, 409]
    refused = next(response for response in responses if response.status_code == 409)
    assert refused.json()["error"]["code"] == "bank_exhausted"


def test_concurrent_same_attempt_key_does_not_double_count(client_factory, content):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    headers = key()
    responses = race(*(
        lambda client=client: answer(
            client, session, task, expected(content, task), seconds=13, headers=headers
        )
        for client in (one, two) * 3
    ))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == responses[0].content for response in responses)
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    assert len(saved["attempts"]) == 1
    assert saved["summary"]["independent_total"] == 1
    assert saved["summary"]["active_seconds"] == 13


def test_concurrent_same_key_changed_body_has_only_one_winner(client_factory):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    headers = key()
    responses = race(
        lambda: answer(one, session, task, "10", headers=headers),
        lambda: answer(two, session, task, "20", headers=headers),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    assert len(saved["attempts"]) == 1


def test_concurrent_different_attempt_keys_keep_only_one_first_answer(client_factory, content):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    responses = race(
        lambda: answer(one, session, task, expected(content, task), seconds=5),
        lambda: answer(two, session, task, expected(content, task), seconds=12),
    )
    assert all(response.status_code == 200 for response in responses)
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    assert len(saved["attempts"]) == 2
    assert saved["summary"]["independent_total"] == 1
    assert saved["summary"]["corrections"] == 1
    assert saved["summary"]["active_seconds"] == 12


def test_concurrent_drafts_cannot_overwrite_same_revision(client_factory):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    responses = race(
        lambda: draft(one, session, task, "10", seconds=10),
        lambda: draft(two, session, task, "20", seconds=20),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    winner = 0 if responses[0].status_code == 200 else 1
    assert saved["drafts"][task["id"]] == {
        "answer": "10" if winner == 0 else "20", "active_seconds": 10 if winner == 0 else 20
    }
    assert saved["draft_revision"] == 1


def test_concurrent_finish_returns_same_frozen_summary(client_factory, content):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    answer(one, session, task, expected(content, task), seconds=11)
    headers = key()
    responses = race(
        lambda: finish(one, session, headers=headers),
        lambda: finish(two, session, headers=headers),
        lambda: finish(one, session), lambda: finish(two, session),
    )
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == responses[0].content for response in responses)
    assert responses[0].json()["summary"]["active_seconds"] == 11


def test_finish_racing_attempt_never_changes_a_frozen_result(client_factory, content):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    results = race(
        lambda: answer(one, session, task, expected(content, task)), lambda: finish(two, session)
    )
    assert results[0].status_code in (200, 409)
    assert results[1].status_code == 200
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved == results[1].json()
    assert saved["summary"]["answered"] == (1 if results[0].status_code == 200 else 0)


def test_help_racing_answer_cannot_retroactively_change_first_attempt(client_factory, content):
    one, two = twins(client_factory)
    session = start(one).json()
    task = session["tasks"][0]
    results = race(
        lambda: answer(one, session, task, expected(content, task)),
        lambda: two.post(
            f"/api/v1/sessions/{session['id']}/hints", json={"task_id": task["id"], "level": 1}
        ),
    )
    assert all(response.status_code == 200 for response in results)
    attempt = results[0].json()
    saved = one.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["attempts"] == [attempt]
    assert saved["summary"]["independent_total"] == (0 if attempt["assisted"] else 1)
