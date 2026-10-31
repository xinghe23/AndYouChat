from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.snowflake import next_id
from app.db.base import Base, utcnow

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_CANCELED = "canceled"


class Friendship(Base):
    """双向各存一条，便于按 user_id 高效拉好友列表。"""

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
        Index("ix_friendship_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    friend_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class FriendRequest(Base):
    __tablename__ = "friend_requests"
    __table_args__ = (
        Index("ix_friend_request_to_status", "to_user_id", "status"),
        Index("ix_friend_request_from_status", "from_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    from_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
