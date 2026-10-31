from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    seq: int
    sender_id: int
    msg_type: str
    content: str
    extra: dict[str, Any] | None = None
    client_msg_id: str | None = None
    revoked: bool = False
    created_at: int


class SendMessageIn(BaseModel):
    conversation_id: int
    client_msg_id: str = Field(min_length=8, max_length=64)
    msg_type: Literal["text", "image"] = "text"
    content: str = Field(default="", max_length=4096)
    extra: dict[str, Any] | None = None


class SendMessageOut(BaseModel):
    message: MessageOut
    duplicated: bool = False


class MessagePage(BaseModel):
    items: list[MessageOut]
    has_more: bool
    max_seq: int


class ReadIn(BaseModel):
    conversation_id: int
    seq: int = Field(ge=0)


class TypingIn(BaseModel):
    conversation_id: int


class ConversationOut(BaseModel):
    id: int
    type: str
    title: str | None = None
    peer: UserOut | None = None
    last_message: MessageOut | None = None
    unread: int = 0
    last_read_seq: int = 0
    pinned: bool = False
    muted: bool = False
    updated_at: int | None = None
    peer_online: bool = False
