from uuid import uuid4


def test_identity_is_read_only_and_does_not_create_a_guest(client):
    assert client.get("/api/v1/identity").status_code == 401
    created = client.post("/api/v1/guest", json={}).json()
    identity = client.get("/api/v1/identity").json()
    assert identity == {"id": created["id"], "kind": "guest", "owner_ids": [created["id"]]}


def test_stale_client_identity_cannot_write_under_a_different_cookie(guest_client):
    headers = {"Idempotency-Key": str(uuid4()), "X-Learning-Owner": str(uuid4())}
    response = guest_client.post(
        "/api/v1/sessions", json={"slots": [1], "length": 5, "mode": "practice"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_changed"
    assert guest_client.get("/api/v1/export").json()["sessions"] == []


def test_matching_identity_can_read_and_write(guest_client):
    owner = guest_client.get("/api/v1/identity").json()["id"]
    response = guest_client.post(
        "/api/v1/sessions", json={"slots": [1], "length": 5, "mode": "practice"},
        headers={"Idempotency-Key": str(uuid4()), "X-Learning-Owner": owner},
    )
    assert response.status_code == 200
    assert guest_client.get(
        f"/api/v1/sessions/{response.json()['id']}", headers={"X-Learning-Owner": owner},
    ).status_code == 200
