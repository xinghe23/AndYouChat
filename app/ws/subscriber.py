from __future__ import annotations

import asyncio
import json
import logging

from app.core import redis as rds
from app.ws.manager import manager

logger = logging.getLogger(__name__)


async def run_subscriber(stop_event: asyncio.Event) -> None:
    """订阅 Redis 频道，把其他 worker 进程产生的事件转投给本地连接。"""
    while not stop_event.is_set():
        pubsub = None
        try:
            pubsub = await rds.subscribe()
            async for message in pubsub.listen():
                if stop_event.is_set():
                    break
                if message.get("type") != "message":
                    continue
                try:
                    body = json.loads(message["data"])
                except (ValueError, TypeError):
                    continue
                if body.get("_origin") == rds.PROCESS_ID:
                    continue
                payload = body.get("payload") or {}
                for uid in body.get("to") or []:
                    await manager.send(int(uid), payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("redis subscriber error: %s", exc)
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
