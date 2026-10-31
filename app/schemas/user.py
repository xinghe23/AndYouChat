from __future__ import annotations

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    avatar_url: str | None = None
    sign: str | None = None
    online: bool = False


class ProfileUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=512)
    sign: str | None = Field(default=None, max_length=128)


class UserSearchItem(UserOut):
    is_friend: bool = False
    request_pending: bool = False
