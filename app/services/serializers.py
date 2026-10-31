from __future__ import annotations

from typing import Any

from app.db.base import to_ms
from app.models import Message, User


def user_dict(user: User, online: bool = False) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "sign": user.sign,
        "online": online,
    }


def message_dict(msg: Message) -> dict[str, Any]:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "seq": msg.seq,
        "sender_id": msg.sender_id,
        "msg_type": msg.msg_type,
        "content": msg.content if not msg.revoked else "",
        "extra": msg.extra,
        "client_msg_id": msg.client_msg_id,
        "revoked": msg.revoked,
        "created_at": to_ms(msg.created_at),
    }
