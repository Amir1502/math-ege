from uuid import uuid4


def key():
    return {"Idempotency-Key": str(uuid4())}


def start(client, *, slots=None, length=5, headers=None):
    return client.post(
        "/api/v1/sessions",
        json={"slots": slots or [1], "length": length, "mode": "practice"},
        headers=headers or key(),
    )


def answer(client, session, task, value, *, seconds=0, skipped=False, headers=None):
    return client.post(
        f"/api/v1/sessions/{session['id']}/attempts",
        json={
            "task_id": task["id"], "answer": value, "active_seconds": seconds, "skipped": skipped
        },
        headers=headers or key(),
    )


def draft(client, session, task, value, *, seconds=0, revision=0):
    return client.put(
        f"/api/v1/sessions/{session['id']}/draft",
        json={"task_id": task["id"], "answer": value, "active_seconds": seconds,
              "expected_revision": revision},
    )


def finish(client, session, *, headers=None):
    return client.post(
        f"/api/v1/sessions/{session['id']}/finish", json={}, headers=headers or key()
    )


def expected(content, task):
    return next(item.answer for item in content.tasks if item.id == task["id"])
