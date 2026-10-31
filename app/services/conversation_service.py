from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.snowflake import next_id
from app.db.base import to_ms
from app.models import Conversation, ConversationMember, Message, User
from app.models.conversation import TYPE_SINGLE
from app.services.serializers import user_dict


def single_key(a: int, b: int) -> str:
    lo, hi = (a, b) if a < b else (b, a)
    return f"{lo}:{hi}"


async def get_conversation(db: AsyncSession, conv_id: int) -> Conversation | None:
    return await db.get(Conversation, conv_id)


async def get_member(
    db: AsyncSession, conv_id: int, user_id: int
) -> ConversationMember | None:
    stmt = select(ConversationMember).where(
        ConversationMember.conversation_id == conv_id,
        ConversationMember.user_id == user_id,
    )
    return await db.scalar(stmt)


async def get_or_create_single(db: AsyncSession, a: int, b: int) -> Conversation:
    key = single_key(a, b)
    conv = await db.scalar(select(Conversation).where(Conversation.single_key == key))
    if conv:
        return conv

    conv = Conversation(id=next_id(), type=TYPE_SINGLE, single_key=key)
    db.add(conv)
    db.add_all(
        [
            ConversationMember(conversation_id=conv.id, user_id=a),
            ConversationMember(conversation_id=conv.id, user_id=b),
        ]
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        conv = await db.scalar(select(Conversation).where(Conversation.single_key == key))
        if conv is None:
            raise
    return conv


async def count_unread(
    db: AsyncSession, conv_id: int, user_id: int, after_seq: int
) -> int:
    stmt = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conv_id,
            Message.seq > after_seq,
            Message.sender_id != user_id,
        )
    )
    return int(await db.scalar(stmt) or 0)


async def mark_read(
    db: AsyncSession, conv_id: int, user_id: int, seq: int
) -> ConversationMember | None:
    member = await get_member(db, conv_id, user_id)
    if not member:
        return None
    if seq > member.last_read_seq:
        member.last_read_seq = seq
    member.unread = await count_unread(db, conv_id, user_id, member.last_read_seq)
    await db.commit()
    await db.refresh(member)
    return member


async def list_conversations(db: AsyncSession, user_id: int) -> list[dict]:
    members = list(
        (
            await db.scalars(
                select(ConversationMember).where(ConversationMember.user_id == user_id)
            )
        ).all()
    )
    if not members:
        return []

    conv_ids = [m.conversation_id for m in members]
    convs = {
        c.id: c
        for c in (
            await db.scalars(select(Conversation).where(Conversation.id.in_(conv_ids)))
        ).all()
    }

    peer_rows = list(
        (
            await db.scalars(
                select(ConversationMember).where(
                    ConversationMember.conversation_id.in_(conv_ids),
                    ConversationMember.user_id != user_id,
                )
            )
        ).all()
    )
    peer_map: dict[int, int] = {}
    for p in peer_rows:
        peer_map.setdefault(p.conversation_id, p.user_id)

    peer_ids = list(set(peer_map.values()))
    users = (
        {
            u.id: u
            for u in (await db.scalars(select(User).where(User.id.in_(peer_ids)))).all()
        }
        if peer_ids
        else {}
    )

    msg_ids = [c.last_msg_id for c in convs.values() if c.last_msg_id]
    msgs = (
        {
            m.id: m
            for m in (await db.scalars(select(Message).where(Message.id.in_(msg_ids)))).all()
        }
        if msg_ids
        else {}
    )

    items: list[dict] = []
    for mem in members:
        conv = convs.get(mem.conversation_id)
        if not conv:
            continue
        peer = users.get(peer_map.get(conv.id, 0))
        last = msgs.get(conv.last_msg_id) if conv.last_msg_id else None
        updated = to_ms(conv.last_msg_at or conv.created_at) or 0
        items.append(
            {
                "id": conv.id,
                "type": conv.type,
                "title": conv.title or (peer.nickname if peer else None),
                "peer": user_dict(peer) if peer else None,
                "last_message": (
                    {
                        "id": last.id,
                        "conversation_id": last.conversation_id,
                        "seq": last.seq,
                        "sender_id": last.sender_id,
                        "msg_type": last.msg_type,
                        "content": "" if last.revoked else last.content,
                        "extra": last.extra,
                        "client_msg_id": last.client_msg_id,
                        "revoked": last.revoked,
                        "created_at": to_ms(last.created_at),
                    }
                    if last
                    else None
                ),
                "unread": mem.unread,
                "last_read_seq": mem.last_read_seq,
                "pinned": mem.pinned,
                "muted": mem.muted,
                "updated_at": updated,
                "peer_online": False,
            }
        )

    items.sort(key=lambda x: (0 if x["pinned"] else 1, -(x["updated_at"] or 0)))
    return items


async def member_user_ids(db: AsyncSession, conv_id: int) -> list[int]:
    stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conv_id
    )
    return list((await db.scalars(stmt)).all())


async def conversation_detail(
    db: AsyncSession, conv: Conversation, user_id: int
) -> dict:
    member = await get_member(db, conv.id, user_id)
    if not member:
        raise PermissionError("你不在该会话中")

    peer = None
    if conv.type == TYPE_SINGLE:
        ids = await member_user_ids(db, conv.id)
        peer_id = next((i for i in ids if i != user_id), None)
        if peer_id:
            peer = await db.get(User, peer_id)

    last = await db.get(Message, conv.last_msg_id) if conv.last_msg_id else None
    return {
        "id": conv.id,
        "type": conv.type,
        "title": conv.title or (peer.nickname if peer else None),
        "peer": user_dict(peer) if peer else None,
        "last_message": (
            {
                "id": last.id,
                "conversation_id": last.conversation_id,
                "seq": last.seq,
                "sender_id": last.sender_id,
                "msg_type": last.msg_type,
                "content": "" if last.revoked else last.content,
                "extra": last.extra,
                "client_msg_id": last.client_msg_id,
                "revoked": last.revoked,
                "created_at": to_ms(last.created_at),
            }
            if last
            else None
        ),
        "unread": member.unread,
        "last_read_seq": member.last_read_seq,
        "pinned": member.pinned,
        "muted": member.muted,
        "updated_at": to_ms(conv.last_msg_at or conv.created_at),
        "peer_online": False,
    }
