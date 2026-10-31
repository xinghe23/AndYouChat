from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import ws
from app.api.v1.router import api_router
from app.core import redis as rds
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.db.session import dispose_db, init_db
from app.ws.subscriber import run_subscriber

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
WEB_INDEX = STATIC_DIR / "app" / "index.html"
# npm run build:chat 的产物，用于在本地复现「前端挂在 Nginx /chat/ 子目录」的生产路径
CHAT_DIR = BASE_DIR / "chat"
CHAT_INDEX = CHAT_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("database ready: %s", settings.database_url.split("@")[-1])

    stop_event = asyncio.Event()
    subscriber = asyncio.create_task(run_subscriber(stop_event))
    logger.info("redis subscriber started (fakeredis=%s)", settings.use_fakeredis)

    yield

    stop_event.set()
    subscriber.cancel()
    try:
        await asyncio.wait_for(subscriber, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    except Exception:
        pass
    logger.info("shutdown: subscriber stopped")
    await rds.close_redis()
    logger.info("shutdown: redis closed")
    await dispose_db()
    logger.info("shutdown: db disposed")


app = FastAPI(
    title="AndYouChat API",
    version="0.2.0",
    description="私聊系统 P0+P1：账号、好友、单聊、实时消息",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(ws.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if CHAT_DIR.exists():
    # 本地也能按生产路径 /chat/ 访问，方便联调 Nginx 配置
    app.mount("/chat", StaticFiles(directory=str(CHAT_DIR), html=True), name="chat")


@app.get("/health", tags=["运维"], summary="健康检查")
async def health():
    from sqlalchemy import text

    from app.db.session import engine
    from app.ws.manager import manager

    db_ok, redis_ok = False, False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("db health failed: %s", exc)
    try:
        client = await rds.get_redis()
        await client.ping()
        redis_ok = True
    except Exception as exc:
        logger.warning("redis health failed: %s", exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "redis": redis_ok,
        "env": settings.env,
        "online_users": len(manager.online_users()),
    }


@app.get("/", include_in_schema=False)
async def index():
    """前端按 chat/ → static/app/ → 单文件调试台的顺序回落。"""
    if CHAT_INDEX.exists():
        target = "/chat/"
    elif WEB_INDEX.exists():
        target = "/static/app/index.html"
    else:
        target = "/static/chat.html"
    return RedirectResponse(url=target)
