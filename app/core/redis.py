"""Redis 接入层：会话 seq 分配、在线状态、跨进程事件广播。

所有对 Redis 的访问都收在这里，方便以后换成集群 / 加哨兵，业务层不用改。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis, from_url

from app.core.config import settings

_client: Redis | None = None
PROCESS_ID = uuid.uuid4().hex
CHAT_CHANNEL = "andyou:events"


async def get_redis() -> Redis:
    global _client
    if _client is None:
        if settings.use_fakeredis:
            import fakeredis.aioredis

            _client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        else:
            _client = from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def seq_key(conversation_id: int) -> str:
    return f"conv:{conversation_id}:seq"


def presence_key(user_id: int) -> str:
    return f"presence:{user_id}"


async def next_seq(conversation_id: int, floor: int = 0) -> int:
    """分配会话内单调递增的序号。Redis 不可用时会抛异常，由调用方降级到 DB。"""
    r = await get_redis()
    key = seq_key(conversation_id)
    if floor > 0:
        await r.set(key, floor, nx=True)
    return int(await r.incr(key))


async def current_seq(conversation_id: int) -> int:
    r = await get_redis()
    val = await r.get(seq_key(conversation_id))
    return int(val) if val else 0


async def reset_seq(conversation_id: int, value: int) -> None:
    r = await get_redis()
    await r.set(seq_key(conversation_id), value)


async def mark_online(user_id: int) -> None:
    r = await get_redis()
    await r.incr(presence_key(user_id))
    await r.expire(presence_key(user_id), 300)


async def mark_offline(user_id: int) -> None:
    r = await get_redis()
    key = presence_key(user_id)
    left = await r.decr(key)
    if left <= 0:
        await r.delete(key)


async def is_online(user_id: int) -> bool:
    r = await get_redis()
    val = await r.get(presence_key(user_id))
    return bool(val and int(val) > 0)


async def publish(payload: dict[str, Any]) -> None:
    """发布到 Redis，其他 worker 进程订阅后投递给本地连接。"""
    r = await get_redis()
    body = dict(payload)
    body["_origin"] = PROCESS_ID
    await r.publish(CHAT_CHANNEL, json.dumps(body, ensure_ascii=False))


async def subscribe():
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(CHAT_CHANNEL)
    return pubsub
