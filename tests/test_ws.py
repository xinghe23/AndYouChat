from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def recv_until(ws, wanted: str, limit: int = 12) -> dict:
    for _ in range(limit):
        frame = ws.receive_json()
        if frame.get("type") == wanted:
            return frame
    raise AssertionError(f"未在 {limit} 帧内收到 {wanted}")


def test_ws_rejects_missing_or_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=invalid") as ws:
            ws.receive_json()


def test_ws_hello(client, alice):
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws:
        hello = recv_until(ws, "pong")
        assert hello["data"]["online"] is True


def test_ws_ping_pong(client, alice):
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws:
        recv_until(ws, "pong")
        ws.send_json({"type": "ping", "request_id": "r1"})
        frame = recv_until(ws, "pong")
        assert frame["request_id"] == "r1"


def test_realtime_message_delivery(client, friends):
    alice, bob, conv_id = friends
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws_a:
        recv_until(ws_a, "pong")
        with client.websocket_connect(f"/ws?token={bob['access_token']}") as ws_b:
            recv_until(ws_b, "pong")

            ws_a.send_json(
                {
                    "type": "msg.send",
                    "request_id": "req-1",
                    "data": {
                        "conversation_id": conv_id,
                        "client_msg_id": "ws-msg-0001",
                        "msg_type": "text",
                        "content": "实时消息",
                    },
                }
            )

            ack = recv_until(ws_a, "msg.ack")
            assert ack["request_id"] == "req-1"
            assert ack["data"]["duplicated"] is False
            assert ack["data"]["message"]["seq"] == 1

            new = recv_until(ws_b, "msg.new")
            assert new["data"]["message"]["content"] == "实时消息"
            assert new["data"]["message"]["sender_id"] == alice["user"]["id"]


def test_ws_duplicate_send_marked_duplicated(client, friends):
    alice, _bob, conv_id = friends
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws:
        recv_until(ws, "pong")
        payload = {
            "type": "msg.send",
            "data": {
                "conversation_id": conv_id,
                "client_msg_id": "ws-dup-0001",
                "content": "x",
            },
        }
        ws.send_json(payload)
        first = recv_until(ws, "msg.ack")
        ws.send_json(payload)
        second = recv_until(ws, "msg.ack")
        assert first["data"]["duplicated"] is False
        assert second["data"]["duplicated"] is True
        assert second["data"]["message"]["id"] == first["data"]["message"]["id"]


def test_ws_read_receipt(client, friends):
    alice, bob, conv_id = friends
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws_a:
        recv_until(ws_a, "pong")
        with client.websocket_connect(f"/ws?token={bob['access_token']}") as ws_b:
            recv_until(ws_b, "pong")
            ws_a.send_json(
                {
                    "type": "msg.send",
                    "data": {
                        "conversation_id": conv_id,
                        "client_msg_id": "ws-read-0001",
                        "content": "在吗",
                    },
                }
            )
            recv_until(ws_a, "msg.ack")
            msg = recv_until(ws_b, "msg.new")["data"]["message"]

            ws_b.send_json(
                {
                    "type": "msg.read",
                    "data": {"conversation_id": conv_id, "seq": msg["seq"]},
                }
            )
            receipt = recv_until(ws_a, "msg.read")
            assert receipt["data"]["user_id"] == bob["user"]["id"]
            assert receipt["data"]["seq"] == msg["seq"]


def test_ws_send_to_foreign_conversation_returns_error(client, friends, client_factory):
    _alice, _bob, conv_id = friends
    carol = client_factory("carol")
    with client.websocket_connect(f"/ws?token={carol['access_token']}") as ws:
        recv_until(ws, "pong")
        ws.send_json(
            {
                "type": "msg.send",
                "request_id": "req-x",
                "data": {
                    "conversation_id": conv_id,
                    "client_msg_id": "ws-foreign-1",
                    "content": "越权",
                },
            }
        )
        frame = recv_until(ws, "error")
        assert frame["data"]["code"] == "forbidden"


def test_ws_typing_forwarded(client, friends):
    alice, bob, conv_id = friends
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws_a:
        recv_until(ws_a, "pong")
        with client.websocket_connect(f"/ws?token={bob['access_token']}") as ws_b:
            recv_until(ws_b, "pong")
            ws_a.send_json({"type": "typing", "data": {"conversation_id": conv_id}})
            frame = recv_until(ws_b, "typing")
            assert frame["data"]["user_id"] == alice["user"]["id"]


def test_presence_broadcast_to_friend(client, friends):
    alice, bob, _conv = friends
    with client.websocket_connect(f"/ws?token={alice['access_token']}") as ws_a:
        recv_until(ws_a, "pong")
        with client.websocket_connect(f"/ws?token={bob['access_token']}"):
            frame = recv_until(ws_a, "presence")
            assert frame["data"]["user_id"] == bob["user"]["id"]
            assert frame["data"]["online"] is True
