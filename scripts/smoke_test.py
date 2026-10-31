"""端到端冒烟：注册 -> 加好友 -> 建会话 -> WS 实时收发 -> 已读回执。

用法：
    ./.venv/Scripts/python.exe scripts/smoke_test.py [base_url]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"
SUFFIX = str(int(time.time()))[-6:]
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")

passed = 0
failed = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {extra}")


async def recv_until(ws, wanted: str, limit: int = 12) -> dict:
    for _ in range(limit):
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if frame.get("type") == wanted:
            return frame
    raise AssertionError(f"未收到 {wanted}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=10, trust_env=False) as http:
        print(f"目标服务: {BASE}")

        health = (await http.get("/health")).json()
        check("健康检查", health["status"] == "ok", str(health))
        check("数据库连通", health["db"] is True)
        check("Redis 连通", health["redis"] is True)

        alice_name, bob_name = f"alice{SUFFIX}", f"bob{SUFFIX}"
        alice = (await http.post("/api/v1/auth/register",
                                json={"username": alice_name, "password": "pass1234"})).json()
        bob = (await http.post("/api/v1/auth/register",
                              json={"username": bob_name, "password": "pass1234"})).json()
        check("注册两个账号", bool(alice.get("access_token") and bob.get("access_token")))

        ha = {"Authorization": f"Bearer {alice['access_token']}"}
        hb = {"Authorization": f"Bearer {bob['access_token']}"}

        dup = await http.post("/api/v1/auth/register",
                              json={"username": alice_name, "password": "pass1234"})
        check("重复用户名被拒绝", dup.status_code == 409, str(dup.status_code))

        bad = await http.post("/api/v1/auth/login",
                              json={"username": alice_name, "password": "wrong"})
        check("错误密码被拒绝", bad.status_code == 401)

        found = (await http.get("/api/v1/users/search", params={"q": bob_name}, headers=ha)).json()
        check("搜索用户", len(found) == 1 and found[0]["username"] == bob_name)

        req = (await http.post("/api/v1/friends/requests",
                               json={"to_user_id": bob["user"]["id"], "message": "hi"},
                               headers=ha)).json()
        inbox = (await http.get("/api/v1/friends/requests", headers=hb)).json()
        check("好友申请送达", any(r["id"] == req["id"] for r in inbox))

        await http.post(f"/api/v1/friends/requests/{req['id']}/respond",
                        json={"accept": True}, headers=hb)
        friends = (await http.get("/api/v1/friends", headers=ha)).json()
        check("同意后互为好友", [f["username"] for f in friends] == [bob_name])

        conv = (await http.post("/api/v1/conversations/single",
                                json={"peer_id": bob["user"]["id"]}, headers=ha)).json()
        conv_id = conv["id"]
        check("创建单聊会话", isinstance(conv_id, int) and conv_id > 0)

        async with websockets.connect(f"{WS_BASE}/ws?token={alice['access_token']}") as ws_a:
            await recv_until(ws_a, "pong")
            async with websockets.connect(f"{WS_BASE}/ws?token={bob['access_token']}") as ws_b:
                await recv_until(ws_b, "pong")

                await ws_a.send(json.dumps({
                    "type": "msg.send",
                    "request_id": "smoke-1",
                    "data": {
                        "conversation_id": conv_id,
                        "client_msg_id": f"smoke{SUFFIX}01",
                        "msg_type": "text",
                        "content": "冒烟测试消息",
                    },
                }))
                ack = await recv_until(ws_a, "msg.ack")
                new = await recv_until(ws_b, "msg.new")
                check("发送方收到 ack", ack["data"]["message"]["seq"] == 1)
                check("接收方实时收到", new["data"]["message"]["content"] == "冒烟测试消息")

                await ws_b.send(json.dumps({
                    "type": "msg.read",
                    "data": {"conversation_id": conv_id, "seq": new["data"]["message"]["seq"]},
                }))
                receipt = await recv_until(ws_a, "msg.read")
                check("已读回执", receipt["data"]["user_id"] == bob["user"]["id"])

        convs = (await http.get("/api/v1/conversations", headers=hb)).json()
        check("会话列表未读归零", convs[0]["unread"] == 0, str(convs[0]["unread"]))

        hist = (await http.get(f"/api/v1/conversations/{conv_id}/messages",
                               params={"after_seq": 0}, headers=ha)).json()
        check("历史消息可拉取", len(hist["items"]) >= 1)

        page = await http.get("/static/chat.html")
        check("网页调试器可访问", page.status_code == 200 and "AndYouChat" in page.text)

    print(f"\n结果：{passed} 项通过，{failed} 项失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
