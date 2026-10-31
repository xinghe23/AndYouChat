from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis as rds
from app.core.snowflake import next_id
from app.db.base import utcnow
from app.models import ConversationMember, Message
from app.services.conversation_service import get_conversation, get_member
from app.services.serializers import message_dict


class NotMemberError(Exception):
    pass


class MessageError(Exception):
    pass


async def require_member(db: AsyncSession, conv_id: int, user_id: int):
    conv = await get_conversation(db, conv_id)
    if not conv:
        raise NotMemberError("会话不存在")
    member = await get_member(db, conv_id, user_id)
    if not member:
        raise NotMemberError("你不在该会话中")
    return conv, member


async def send_message(
    db: AsyncSession,
    sender_id: int,
    conversation_id: int,
    client_msg_id: str,
    msg_type: str = "text",
    content: str = "",
    extra: dict | None = None,
) -> tuple[dict, bool]:
    """返回 (消息字典, 是否幂等命中重复)。"""
    conv, _ = await require_member(db, conversation_id, sender_id)

    existing = await db.scalar(
        select(Message).where(Message.client_msg_id == client_msg_id)
    )
    if existing:
        return message_dict(existing), True

    try:
        seq = await rds.next_seq(conversation_id, floor=conv.seq_counter)
    except Exception:
        # Redis 不可用时退化到 DB 计数（单进程可用，多进程需恢复 Redis）
        seq = conv.seq_counter + 1

    now = utcnow()
    msg = Message(
        id=next_id(),
        conversation_id=conversation_id,
        seq=seq,
        sender_id=sender_id,
        msg_type=msg_type,
        content=content,
        extra=extra,
        client_msg_id=client_msg_id,
        created_at=now,
    )
    db.add(msg)
    conv.seq_counter = max(conv.seq_counter, seq)
    conv.last_msg_id = msg.id
    conv.last_msg_at = now
    await db.execute(
        update(ConversationMember)
        .where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != sender_id,
        )
        .values(unread=ConversationMember.unread + 1)
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        dup = await db.scalar(
            select(Message).where(Message.client_msg_id == client_msg_id)
        )
        if dup:
            return message_dict(dup), True
        raise
    await db.refresh(msg)
    return message_dict(msg), False


async def list_messages(
    db: AsyncSession,
    user_id: int,
    conversation_id: int,
    before_seq: int | None = None,
    after_seq: int | None = None,
    limit: int = 30,
) -> dict:
    conv, _ = await require_member(db, conversation_id, user_id)
    limit = max(1, min(limit, 100))

    if after_seq is not None:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.seq > after_seq)
            .order_by(Message.seq.asc())
            .limit(limit + 1)
        )
        rows = list((await db.scalars(stmt)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
    else:
        stmt = select(Message).where(Message.conversation_id == conversation_id)
        if before_seq is not None:
            stmt = stmt.where(Message.seq < before_seq)
        stmt = stmt.order_by(Message.seq.desc()).limit(limit + 1)
        rows = list((await db.scalars(stmt)).all())
        has_more = len(rows) > limit
        rows = list(reversed(rows[:limit]))

    max_seq = await db.scalar(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation_id)
    )
    return {
        "items": [message_dict(m) for m in rows],
        "has_more": has_more,
        "max_seq": int(max_seq or 0),
    }


async def recall_message(db: AsyncSession, user_id: int, message_id: int) -> dict:
    from app.core.config import settings

    msg = await db.get(Message, message_id)
    if not msg:
        raise MessageError("消息不存在")
    if msg.sender_id != user_id:
        raise MessageError("只能撤回自己发送的消息")
    if msg.revoked:
        return message_dict(msg)
    age = (utcnow() - msg.created_at).total_seconds()
    if age > settings.message_recall_seconds:
        raise MessageError(f"超过 {settings.message_recall_seconds} 秒，无法撤回")
    msg.revoked = True
    msg.content = ""
    await db.commit()
    await db.refresh(msg)
    return message_dict(msg)
