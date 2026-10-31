from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.snowflake import next_id
from app.db.base import Base, utcnow

TYPE_SINGLE = "single"
TYPE_GROUP = "group"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    type: Mapped[str] = mapped_column(String(16), default=TYPE_SINGLE, nullable=False)
    # 单聊去重键 "小id:大id"，保证 A↔B 永远只有一个会话；群聊为 NULL
    single_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seq_counter: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_msg_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_member"),
        Index("ix_member_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_read_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    unread: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_message_seq"),
        UniqueConstraint("client_msg_id", name="uq_message_client_id"),
        Index("ix_message_conv_seq", "conversation_id", "seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    msg_type: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    content: Mapped[str] = mapped_column(String(4096), default="", nullable=False)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    client_msg_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
