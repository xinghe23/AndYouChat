"""WebSocket 事件协议。客户端与服务端共用这份约定。"""
from __future__ import annotations

from typing import Any

PING = "ping"
PONG = "pong"
MSG_SEND = "msg.send"
MSG_ACK = "msg.ack"
MSG_NEW = "msg.new"
MSG_READ = "msg.read"
MSG_RECALLED = "msg.recalled"
TYPING = "typing"
PRESENCE = "presence"
ERROR = "error"

CODE_UNAUTHORIZED = 4401


def frame(event_type: str, data: dict[str, Any] | None = None, request_id: str | None = None) -> dict:
    payload: dict[str, Any] = {"type": event_type, "data": data or {}}
    if request_id:
        payload["request_id"] = request_id
    return payload


def error(message: str, code: str = "bad_request", request_id: str | None = None) -> dict:
    return frame(ERROR, {"code": code, "message": message}, request_id)
