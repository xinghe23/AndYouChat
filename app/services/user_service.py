from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import ProfileUpdateIn


class UsernameTaken(Exception):
    pass


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(select(User).where(User.username == username))


async def create_user(
    db: AsyncSession, username: str, password: str, nickname: str | None = None
) -> User:
    if await get_by_username(db, username):
        raise UsernameTaken(username)
    user = User(
        username=username,
        password_hash=hash_password(password),
        nickname=nickname or username,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:  # 并发注册同名
        await db.rollback()
        raise UsernameTaken(username) from exc
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User | None:
    user = await get_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


async def search_users(
    db: AsyncSession, keyword: str, exclude_id: int, limit: int = 20
) -> list[User]:
    kw = f"%{keyword.strip()}%"
    stmt = (
        select(User)
        .where(User.id != exclude_id)
        .where(or_(User.username.ilike(kw), User.nickname.ilike(kw)))
        .order_by(User.id)
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def update_profile(db: AsyncSession, user: User, data: ProfileUpdateIn) -> User:
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        if value is not None:
            setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user
