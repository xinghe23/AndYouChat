from __future__ import annotations

from tests.conftest import auth


def _send_request(client, token, to_id, message="hello"):
    return client.post(
        "/api/v1/friends/requests",
        json={"to_user_id": to_id, "message": message},
        headers=auth(token),
    )


def test_search_users(client, alice, bob):
    resp = client.get(
        "/api/v1/users/search", params={"q": "bo"}, headers=auth(alice["access_token"])
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["username"] == "bob"
    assert items[0]["is_friend"] is False
    assert items[0]["request_pending"] is False


def test_search_excludes_self(client, alice):
    resp = client.get(
        "/api/v1/users/search", params={"q": "alice"}, headers=auth(alice["access_token"])
    )
    assert resp.json() == []


def test_request_and_accept_flow(client, alice, bob):
    resp = _send_request(client, alice["access_token"], bob["user"]["id"])
    assert resp.status_code == 200
    request_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    inbox = client.get("/api/v1/friends/requests", headers=auth(bob["access_token"]))
    assert inbox.status_code == 200
    assert [r["id"] for r in inbox.json()] == [request_id]

    resp = client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": True},
        headers=auth(bob["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    for who, other in ((alice, bob), (bob, alice)):
        friends = client.get("/api/v1/friends", headers=auth(who["access_token"])).json()
        assert [f["username"] for f in friends] == [other["user"]["username"]]

    assert client.get("/api/v1/friends/requests", headers=auth(bob["access_token"])).json() == []


def test_reject_flow(client, alice, bob):
    request_id = _send_request(client, alice["access_token"], bob["user"]["id"]).json()["id"]
    resp = client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": False},
        headers=auth(bob["access_token"]),
    )
    assert resp.json()["status"] == "rejected"
    assert client.get("/api/v1/friends", headers=auth(alice["access_token"])).json() == []


def test_cannot_add_self(client, alice):
    resp = _send_request(client, alice["access_token"], alice["user"]["id"])
    assert resp.status_code == 400


def test_add_unknown_user(client, alice):
    resp = _send_request(client, alice["access_token"], 999999999)
    assert resp.status_code == 404


def test_duplicate_request_is_idempotent(client, alice, bob):
    first = _send_request(client, alice["access_token"], bob["user"]["id"]).json()
    second = _send_request(client, alice["access_token"], bob["user"]["id"]).json()
    assert first["id"] == second["id"]


def test_reverse_request_auto_accepts(client, alice, bob):
    _send_request(client, alice["access_token"], bob["user"]["id"])
    resp = _send_request(client, bob["access_token"], alice["user"]["id"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    friends = client.get("/api/v1/friends", headers=auth(alice["access_token"])).json()
    assert [f["username"] for f in friends] == ["bob"]


def test_add_existing_friend_conflicts(client, friends):
    alice, bob, _conv = friends
    resp = _send_request(client, alice["access_token"], bob["user"]["id"])
    assert resp.status_code == 409


def test_only_recipient_can_respond(client, alice, bob):
    request_id = _send_request(client, alice["access_token"], bob["user"]["id"]).json()["id"]
    resp = client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": True},
        headers=auth(alice["access_token"]),
    )
    assert resp.status_code == 404


def test_double_respond_conflicts(client, alice, bob):
    request_id = _send_request(client, alice["access_token"], bob["user"]["id"]).json()["id"]
    client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": True},
        headers=auth(bob["access_token"]),
    )
    resp = client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": True},
        headers=auth(bob["access_token"]),
    )
    assert resp.status_code == 409


def test_friend_list_contains_conversation_id_after_open(client, friends):
    alice, bob, conv_id = friends
    friends_list = client.get("/api/v1/friends", headers=auth(alice["access_token"])).json()
    assert friends_list[0]["conversation_id"] == conv_id
