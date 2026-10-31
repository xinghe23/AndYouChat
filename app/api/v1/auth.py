from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import (
    REFRESH,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut
from app.schemas.user import UserOut
from app.services import user_service
from app.services.serializers import user_dict

router = APIRouter(prefix="/auth", tags=["认证"])


def _token_payload(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl,
        "user": user_dict(user),
    }


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="注册（成功即返回令牌，免二次登录）",
)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    try:
        user = await user_service.create_user(
            db, payload.username, payload.password, payload.nickname
        )
    except user_service.UsernameTaken:
        raise HTTPException(status_code=409, detail="用户名已被占用")
    return _token_payload(user)


@router.post("/login", response_model=TokenOut, summary="用户名 + 密码登录")
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await user_service.authenticate(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _token_payload(user)


@router.post("/refresh", response_model=TokenOut, summary="用 refresh_token 换新令牌")
async def refresh(payload: RefreshIn, db: AsyncSession = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token, expect=REFRESH)
        user_id = int(data["sub"])
    except (TokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return _token_payload(user)


@router.get("/me", response_model=UserOut, summary="当前登录用户")
async def me(current: User = Depends(get_current_user)):
    return user_dict(current)
