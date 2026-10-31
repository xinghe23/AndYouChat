from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class FriendRequestIn(BaseModel):
    to_user_id: int
    message: str | None = Field(default=None, max_length=128)


class FriendRequestActionIn(BaseModel):
    accept: bool


class FriendRequestOut(BaseModel):
    id: int
    from_user: UserOut
    to_user: UserOut
    message: str | None = None
    status: str
    created_at: int


class FriendOut(UserOut):
    remark: str | None = None
    conversation_id: int | None = None
