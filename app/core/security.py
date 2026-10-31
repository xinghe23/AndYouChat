"""密码哈希与 JWT 令牌。"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

import bcrypt
import jwt
from jwt import PyJWTError

from app.core.config import settings

ACCESS = "access"
REFRESH = "refresh"


class TokenError(Exception):
    """令牌无效 / 过期。"""


def _prehash(password: str) -> bytes:
    # bcrypt 只接受 72 字节以内，先做 sha256 摘要，避免长密码被截断
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _prehash(password), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _encode(subject: int, token_type: str, ttl: int) -> str:
    now = int(time.time())
    payload = {
        "sub": str(subject),
        "typ": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _encode(user_id, ACCESS, settings.access_token_ttl)


def create_refresh_token(user_id: int) -> str:
    return _encode(user_id, REFRESH, settings.refresh_token_ttl)


def decode_token(token: str, expect: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if expect and payload.get("typ") != expect:
        raise TokenError(f"expected {expect} token")
    return payload
