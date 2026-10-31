from __future__ import annotations

from tests.conftest import auth, register


def test_register_returns_token_and_user(client):
    data = register(client, "alice")
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["expires_in"] > 0
    assert data["user"]["username"] == "alice"
    assert data["user"]["nickname"] == "ALICE"
    assert isinstance(data["user"]["id"], int) and data["user"]["id"] > 0


def test_duplicate_username_rejected(client):
    register(client, "alice")
    resp = client.post(
        "/api/v1/auth/register", json={"username": "alice", "password": "pass1234"}
    )
    assert resp.status_code == 409


def test_short_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/register", json={"username": "bob", "password": "123"}
    )
    assert resp.status_code == 422


def test_invalid_username_rejected(client):
    resp = client.post(
        "/api/v1/auth/register", json={"username": "有中文", "password": "pass1234"}
    )
    assert resp.status_code == 422


def test_login_success_and_me(client):
    register(client, "alice")
    resp = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "pass1234"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_wrong_password(client):
    register(client, "alice")
    resp = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrong-pass"}
    )
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth("bad.token.here")).status_code == 401


def test_refresh_token_flow(client):
    data = register(client, "alice")
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_access_token_cannot_be_used_as_refresh(client):
    data = register(client, "alice")
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["access_token"]}
    )
    assert resp.status_code == 401


def test_update_profile(client, alice):
    resp = client.patch(
        "/api/v1/users/me",
        json={"nickname": "爱丽丝", "sign": "hello there"},
        headers=auth(alice["access_token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "爱丽丝"
    assert resp.json()["sign"] == "hello there"
