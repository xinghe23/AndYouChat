"""雪花 ID：41 位毫秒时间戳 + 10 位节点 + 12 位序列。

消息 ID、用户 ID 都用它，保证全局唯一、趋势递增，便于分库分表后仍不冲突。
"""
from __future__ import annotations

import threading
import time

from app.core.config import settings

EPOCH = 1_704_067_200_000  # 2024-01-01 00:00:00 UTC
NODE_BITS = 10
SEQ_BITS = 12
MAX_SEQ = (1 << SEQ_BITS) - 1
MAX_NODE = (1 << NODE_BITS) - 1


class Snowflake:
    def __init__(self, node_id: int) -> None:
        self.node_id = node_id & MAX_NODE
        self._last_ms = -1
        self._seq = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            now = int(time.time() * 1000)
            if now < self._last_ms:
                # 时钟回拨：等待追上，避免生成重复 ID
                time.sleep((self._last_ms - now) / 1000)
                now = int(time.time() * 1000)
            if now == self._last_ms:
                self._seq = (self._seq + 1) & MAX_SEQ
                if self._seq == 0:
                    while now <= self._last_ms:
                        now = int(time.time() * 1000)
            else:
                self._seq = 0
            self._last_ms = now
            return ((now - EPOCH) << (NODE_BITS + SEQ_BITS)) | (
                self.node_id << SEQ_BITS
            ) | self._seq


snowflake = Snowflake(settings.snowflake_node_id)


def next_id() -> int:
    return snowflake.next_id()
