from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.redis import is_online
from app.db.base import to_ms
from app.db.session import get_db
from app.models import FriendRequest, User
from app.schemas.friend import (
    FriendOut,
    FriendRequestActionIn,
    FriendRequestIn,
    FriendRequestOut,
)
from app.services import friend_service
from app.services.serializers import user_dict

router = APIRouter(prefix="/friends", tags=["好友"])


async def _request_out(db: AsyncSession, req: FriendRequest) -> dict:
    from_user = await db.get(User, req.from_user_id)
    to_user = await db.get(User, req.to_user_id)
    if not from_user or not to_user:
        raise HTTPException(status_code=404, detail="申请关联用户不存在")
    return {
        "id": req.id,
        "from_user": user_dict(from_user),
        "to_user": user_dict(to_user),
        "message": req.message,
        "status": req.status,
        "created_at": to_ms(req.created_at) or 0,
    }


@router.get("", response_model=list[FriendOut], summary="好友列表（含会话 id）")
async def list_friends(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await friend_service.list_friends(db, current.id)
    flags = await asyncio.gather(*[is_online(i["id"]) for i in items])
    for item, flag in zip(items, flags):
        item["online"] = bool(flag)
    return items


@router.get("/requests", response_model=list[FriendRequestOut], summary="收到的好友申请")
async def incoming_requests(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reqs = await friend_service.list_incoming_requests(db, current.id)
    return [await _request_out(db, r) for r in reqs]


@router.post("/requests", response_model=FriendRequestOut, summary="发起好友申请")
async def create_request(
    payload: FriendRequestIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        req, _status = await friend_service.send_request(
            db, current.id, payload.to_user_id, payload.message
        )
    except friend_service.SelfRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except friend_service.TargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except friend_service.AlreadyFriendsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return await _request_out(db, req)


@router.post(
    "/requests/{request_id}/respond",
    response_model=FriendRequestOut,
    summary="同意 / 拒绝好友申请",
)
async def respond_request(
    request_id: int,
    payload: FriendRequestActionIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        req = await friend_service.respond_request(
            db, request_id, current.id, payload.accept
        )
    except friend_service.RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except friend_service.FriendError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return await _request_out(db, req)
