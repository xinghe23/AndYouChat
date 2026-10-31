from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import Conversation, Friendship, FriendRequest, User
from app.models.friend import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    STATUS_REJECTED,
)


class FriendError(Exception):
    """好友业务异常，details 直接回给客户端。"""


class SelfRequestError(FriendError):
    pass


class AlreadyFriendsError(FriendError):
    pass


class TargetNotFoundError(FriendError):
    pass


class RequestNotFoundError(FriendError):
    pass


async def are_friends(db: AsyncSession, a: int, b: int) -> bool:
    stmt = select(Friendship.id).where(
        Friendship.user_id == a, Friendship.friend_id == b
    )
    return (await db.scalar(stmt)) is not None


async def friend_ids(db: AsyncSession, user_id: int) -> set[int]:
    stmt = select(Friendship.friend_id).where(Friendship.user_id == user_id)
    return set((await db.scalars(stmt)).all())


async def _add_both_directions(db: AsyncSession, a: int, b: int) -> None:
    existing = await db.scalars(
        select(Friendship).where(
            Friendship.user_id.in_([a, b]), Friendship.friend_id.in_([a, b])
        )
    )
    have = {(f.user_id, f.friend_id) for f in existing.all()}
    if (a, b) not in have:
        db.add(Friendship(user_id=a, friend_id=b))
    if (b, a) not in have:
        db.add(Friendship(user_id=b, friend_id=a))


async def send_request(
    db: AsyncSession, from_id: int, to_id: int, message: str | None = None
) -> tuple[FriendRequest, str]:
    """返回 (请求对象, 结果状态)。结果状态可能是 pending 或 accepted（对方已先申请）。"""
    if from_id == to_id:
        raise SelfRequestError("不能添加自己为好友")
    target = await db.get(User, to_id)
    if not target:
        raise TargetNotFoundError("用户不存在")
    if await are_friends(db, from_id, to_id):
        raise AlreadyFriendsError("你们已经是好友了")

    reverse = await db.scalar(
        select(FriendRequest).where(
            FriendRequest.from_user_id == to_id,
            FriendRequest.to_user_id == from_id,
            FriendRequest.status == STATUS_PENDING,
        )
    )
    if reverse:
        reverse.status = STATUS_ACCEPTED
        reverse.handled_at = utcnow()
        await _add_both_directions(db, from_id, to_id)
        await db.commit()
        await db.refresh(reverse)
        return reverse, STATUS_ACCEPTED

    mine = await db.scalar(
        select(FriendRequest).where(
            FriendRequest.from_user_id == from_id,
            FriendRequest.to_user_id == to_id,
            FriendRequest.status == STATUS_PENDING,
        )
    )
    if mine:
        return mine, STATUS_PENDING

    req = FriendRequest(from_user_id=from_id, to_user_id=to_id, message=message)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req, STATUS_PENDING


async def respond_request(
    db: AsyncSession, request_id: int, user_id: int, accept: bool
) -> FriendRequest:
    req = await db.get(FriendRequest, request_id)
    if not req or req.to_user_id != user_id:
        raise RequestNotFoundError("申请不存在")
    if req.status != STATUS_PENDING:
        raise FriendError("该申请已处理")

    if accept:
        req.status = STATUS_ACCEPTED
        await _add_both_directions(db, req.from_user_id, req.to_user_id)
    else:
        req.status = STATUS_REJECTED
    req.handled_at = utcnow()
    await db.commit()
    await db.refresh(req)
    return req


async def list_incoming_requests(db: AsyncSession, user_id: int) -> list[FriendRequest]:
    stmt = (
        select(FriendRequest)
        .where(FriendRequest.to_user_id == user_id, FriendRequest.status == STATUS_PENDING)
        .order_by(FriendRequest.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())


async def list_friends(db: AsyncSession, user_id: int) -> list[dict]:
    from app.services.conversation_service import single_key

    rows = list(
        (await db.scalars(select(Friendship).where(Friendship.user_id == user_id))).all()
    )
    if not rows:
        return []

    ids = [r.friend_id for r in rows]
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()}
    keys = [single_key(user_id, fid) for fid in ids]
    convs = (
        await db.scalars(select(Conversation).where(Conversation.single_key.in_(keys)))
    ).all()
    conv_map = {c.single_key: c.id for c in convs}

    result = []
    for rel in rows:
        u = users.get(rel.friend_id)
        if not u:
            continue
        result.append(
            {
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname,
                "avatar_url": u.avatar_url,
                "sign": u.sign,
                "online": False,
                "remark": rel.remark,
                "conversation_id": conv_map.get(single_key(user_id, u.id)),
            }
        )
    return result


async def pending_targets(db: AsyncSession, user_id: int, candidates: list[int]) -> set[int]:
    """我发出的、尚未处理的申请对象，用于搜索结果打标。"""
    if not candidates:
        return set()
    stmt = select(FriendRequest.to_user_id).where(
        FriendRequest.from_user_id == user_id,
        FriendRequest.status == STATUS_PENDING,
        FriendRequest.to_user_id.in_(candidates),
    )
    return set((await db.scalars(stmt)).all())
