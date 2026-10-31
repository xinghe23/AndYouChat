"""WebSocket 连接管理与事件投递。

单进程内直发；跨进程通过 Redis Pub/Sub 转发，业务层调用 deliver() 即可。
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.core import redis as rds

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def add(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._conns[user_id].add(ws)

    async def remove(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(user_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    self._conns.pop(user_id, None)

    def local_count(self, user_id: int) -> int:
        return len(self._conns.get(user_id, ()))

    def online_users(self) -> set[int]:
        return set(self._conns.keys())

    async def send(self, user_id: int, payload: dict[str, Any]) -> int:
        conns = list(self._conns.get(user_id, ()))
        sent = 0
        for ws in conns:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                await self.remove(user_id, ws)
        return sent


manager = ConnectionManager()


async def deliver(user_ids: list[int], payload: dict[str, Any]) -> None:
    """先投本地连接，再发到 Redis 让其他 worker 进程转投。"""
    targets = list(dict.fromkeys(user_ids))
    if not targets:
        return
    for uid in targets:
        await manager.send(uid, payload)
    try:
        await rds.publish({"to": targets, "payload": payload})
    except Exception as exc:  # Redis 挂了不影响本进程投递
        logger.warning("redis publish failed: %s", exc)
