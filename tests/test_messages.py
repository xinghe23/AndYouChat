from __future__ import annotations

from tests.conftest import auth


def _send(client, token, conv_id, text, client_msg_id):
    return client.post(
        "/api/v1/messages",
        json={
            "conversation_id": conv_id,
            "client_msg_id": client_msg_id,
            "msg_type": "text",
            "content": text,
        },
        headers=auth(token),
    )


def test_cannot_open_conversation_with_stranger(client, alice, bob):
    resp = client.post(
        "/api/v1/conversations/single",
        json={"peer_id": bob["user"]["id"]},
        headers=auth(alice["access_token"]),
    )
    assert resp.status_code == 403


def test_open_conversation_is_idempotent(client, friends):
    alice, bob, conv_id = friends
    again = client.post(
        "/api/v1/conversations/single",
        json={"peer_id": bob["user"]["id"]},
        headers=auth(alice["access_token"]),
    )
    assert again.status_code == 200
    assert again.json()["id"] == conv_id
    assert again.json()["peer"]["username"] == "bob"


def test_send_message_increments_seq(client, friends):
    alice, _bob, conv_id = friends
    r1 = _send(client, alice["access_token"], conv_id, "第一条", "msg-0001")
    assert r1.status_code == 200, r1.text
    assert r1.json()["message"]["seq"] == 1
    assert r1.json()["duplicated"] is False

    r2 = _send(client, alice["access_token"], conv_id, "第二条", "msg-0002")
    assert r2.json()["message"]["seq"] == 2


def test_duplicate_client_msg_id_is_idempotent(client, friends):
    alice, _bob, conv_id = friends
    first = _send(client, alice["access_token"], conv_id, "hi", "msg-dup-1").json()
    second = _send(client, alice["access_token"], conv_id, "hi again", "msg-dup-1").json()

    assert second["duplicated"] is True
    assert second["message"]["id"] == first["message"]["id"]
    assert second["message"]["seq"] == first["message"]["seq"]
    assert second["message"]["content"] == "hi"


def test_peer_unread_and_mark_read(client, friends):
    alice, bob, conv_id = friends
    _send(client, alice["access_token"], conv_id, "1", "msg-u-0001")
    _send(client, alice["access_token"], conv_id, "2", "msg-u-0002")

    convs = client.get("/api/v1/conversations", headers=auth(bob["access_token"])).json()
    assert convs[0]["unread"] == 2
    assert convs[0]["last_message"]["content"] == "2"

    resp = client.post(
        f"/api/v1/conversations/{conv_id}/read",
        json={"conversation_id": conv_id, "seq": 2},
        headers=auth(bob["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["unread"] == 0

    convs = client.get("/api/v1/conversations", headers=auth(bob["access_token"])).json()
    assert convs[0]["unread"] == 0
    assert convs[0]["last_read_seq"] == 2


def test_sender_does_not_get_unread(client, friends):
    alice, _bob, conv_id = friends
    _send(client, alice["access_token"], conv_id, "1", "msg-s-0001")
    convs = client.get("/api/v1/conversations", headers=auth(alice["access_token"])).json()
    assert convs[0]["unread"] == 0


def test_history_pagination(client, friends):
    alice, _bob, conv_id = friends
    for i in range(1, 6):
        _send(client, alice["access_token"], conv_id, f"m{i}", f"msg-p-{i:04d}")

    page1 = client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        params={"limit": 2},
        headers=auth(alice["access_token"]),
    ).json()
    assert [m["content"] for m in page1["items"]] == ["m4", "m5"]
    assert page1["has_more"] is True
    assert page1["max_seq"] == 5

    oldest_seq = page1["items"][0]["seq"]
    page2 = client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        params={"limit": 2, "before_seq": oldest_seq},
        headers=auth(alice["access_token"]),
    ).json()
    assert [m["content"] for m in page2["items"]] == ["m2", "m3"]


def test_incremental_pull_after_seq(client, friends):
    alice, _bob, conv_id = friends
    for i in range(1, 6):
        _send(client, alice["access_token"], conv_id, f"m{i}", f"msg-a-{i:04d}")

    resp = client.get(
        f"/api/v1/conversations/{conv_id}/messages",
        params={"after_seq": 3},
        headers=auth(alice["access_token"]),
    ).json()
    assert [m["content"] for m in resp["items"]] == ["m4", "m5"]
    assert resp["has_more"] is False


def test_outsider_cannot_send_or_read(client, friends, client_factory):
    alice, _bob, conv_id = friends
    carol = client_factory("carol")
    resp = _send(client, carol["access_token"], conv_id, "偷看", "msg-x-0001")
    assert resp.status_code == 403

    resp = client.get(
        f"/api/v1/conversations/{conv_id}/messages", headers=auth(carol["access_token"])
    )
    assert resp.status_code == 403


def test_empty_conversation_list(client, alice):
    resp = client.get("/api/v1/conversations", headers=auth(alice["access_token"]))
    assert resp.json() == []
