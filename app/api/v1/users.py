from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.redis import is_online
from app.db.session import get_db
from app.models import User
from app.schemas.user import ProfileUpdateIn, UserOut, UserSearchItem
from app.services import friend_service, user_service
from app.services.serializers import user_dict

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/search", response_model=list[UserSearchItem], summary="按用户名/昵称搜索")
async def search(
    q: str = Query(min_length=1, max_length=32),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    users = await user_service.search_users(db, q, current.id)
    fids = await friend_service.friend_ids(db, current.id)
    pending = await friend_service.pending_targets(db, current.id, [u.id for u in users])
    online_flags = await asyncio.gather(*[is_online(u.id) for u in users])

    items = []
    for user, flag in zip(users, online_flags):
        item = user_dict(user, bool(flag))
        item["is_friend"] = user.id in fids
        item["request_pending"] = user.id in pending
        items.append(item)
    return items


@router.patch("/me", response_model=UserOut, summary="更新我的资料")
async def update_me(
    payload: ProfileUpdateIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.update_profile(db, current, payload)
    return user_dict(user, await is_online(user.id))


@router.get("/{user_id}", response_model=UserOut, summary="查看某用户资料")
async def get_user(
    user_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user_dict(user, await is_online(user.id))
