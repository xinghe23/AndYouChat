"""测试装配：独立 SQLite 库 + fakeredis，进程内跑完整链路。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = (Path(__file__).resolve().parent.parent / "test_andyou.db").as_posix()

# 必须在导入 app 之前设置，覆盖 .env
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["USE_FAKEREDIS"] = "true"
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-only"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402,F401

from app.main import app  # noqa: E402

TABLES = [
    "messages",
    "conversation_members",
    "conversations",
    "friend_requests",
    "friendships",
    "users",
]


def _reset_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="session")
def client():
    try:
        if Path(DB_PATH).exists():
            Path(DB_PATH).unlink()
    except OSError:
        pass
    with TestClient(app) as c:
        yield c
    try:
        if Path(DB_PATH).exists():
            Path(DB_PATH).unlink()
    except OSError:
        pass


@pytest.fixture(autouse=True)
def clean(client):
    _reset_db()
    yield


def register(client: TestClient, username: str, password: str = "pass1234") -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "nickname": username.upper()},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(client):
    return register(client, "alice")


@pytest.fixture
def bob(client):
    return register(client, "bob")


@pytest.fixture
def client_factory(client):
    """按需再开几个账号，例如旁观者 carol。"""

    def _make(username: str, password: str = "pass1234") -> dict:
        return register(client, username, password)

    return _make


@pytest.fixture
def friends(client, alice, bob):
    """让 alice 和 bob 互为好友，返回 (alice, bob, conversation_id)。"""
    resp = client.post(
        "/api/v1/friends/requests",
        json={"to_user_id": bob["user"]["id"], "message": "hi"},
        headers=auth(alice["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    request_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/friends/requests/{request_id}/respond",
        json={"accept": True},
        headers=auth(bob["access_token"]),
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/conversations/single",
        json={"peer_id": bob["user"]["id"]},
        headers=auth(alice["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    return alice, bob, resp.json()["id"]
