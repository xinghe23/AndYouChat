from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core import redis as rds
from app.core.security import ACCESS, TokenError, decode_token
from app.db.session import SessionLocal
from app.services import conversation_service, friend_service, message_service
from app.ws import protocol as P
from app.ws.manager import deliver, manager

logger = logging.getLogger(__name__)
router = APIRouter()


async def _broadcast_presence(user_id: int, online: bool) -> None:
    async with SessionLocal() as db:
        ids = await friend_service.friend_ids(db, user_id)
    if ids:
        await deliver(
            list(ids),
            P.frame(P.PRESENCE, {"user_id": user_id, "online": online}),
        )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    try:
        payload = decode_token(token, expect=ACCESS)
        user_id = int(payload["sub"])
    except (TokenError, ValueError, KeyError):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await manager.add(user_id, websocket)
    await rds.mark_online(user_id)
    await websocket.send_json(P.frame(P.PONG, {"user_id": user_id, "online": True}))
    await _broadcast_presence(user_id, True)

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_frame(websocket, user_id, raw)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # 客户端异常断开
        logger.info("ws error uid=%s: %s", user_id, exc)
    finally:
        await manager.remove(user_id, websocket)
        await rds.mark_offline(user_id)
        if manager.local_count(user_id) == 0:
            await _broadcast_presence(user_id, False)


async def _handle_frame(websocket: WebSocket, user_id: int, raw: str) -> None:
    try:
        frame = json.loads(raw)
    except ValueError:
        await websocket.send_json(P.error("帧格式必须是 JSON"))
        return

    etype = frame.get("type")
    data = frame.get("data") or {}
    request_id = frame.get("request_id")

    if etype == P.PING:
        await websocket.send_json(P.frame(P.PONG, {}, request_id))
        return

    if etype == P.MSG_SEND:
        await _handle_send(websocket, user_id, data, request_id)
        return

    if etype == P.MSG_READ:
        await _handle_read(websocket, user_id, data, request_id)
        return

    if etype == P.TYPING:
        await _handle_typing(user_id, data)
        return

    await websocket.send_json(P.error(f"未知事件类型: {etype}", "unknown_type", request_id))


async def _handle_send(
    websocket: WebSocket, user_id: int, data: dict, request_id: str | None
) -> None:
    client_msg_id = str(data.get("client_msg_id") or "")
    try:
        conv_id = int(data["conversation_id"])
    except (KeyError, TypeError, ValueError):
        await websocket.send_json(P.error("conversation_id 必须是整数", request_id=request_id))
        return
    if not 8 <= len(client_msg_id) <= 64:
        await websocket.send_json(P.error("client_msg_id 长度需在 8~64", request_id=request_id))
        return

    async with SessionLocal() as db:
        try:
            msg, duplicated = await message_service.send_message(
                db,
                user_id,
                conv_id,
                client_msg_id,
                str(data.get("msg_type") or "text"),
                str(data.get("content") or ""),
                data.get("extra"),
            )
        except message_service.NotMemberError as exc:
            await websocket.send_json(P.error(str(exc), "forbidden", request_id))
            return
        members = await conversation_service.member_user_ids(db, conv_id)

    await websocket.send_json(
        P.frame(P.MSG_ACK, {"message": msg, "duplicated": duplicated}, request_id)
    )
    await deliver(
        [m for m in members if m != user_id],
        P.frame(P.MSG_NEW, {"message": msg}),
    )


async def _handle_read(
    websocket: WebSocket, user_id: int, data: dict, request_id: str | None
) -> None:
    try:
        conv_id = int(data["conversation_id"])
        seq = int(data["seq"])
    except (KeyError, TypeError, ValueError):
        await websocket.send_json(P.error("参数不合法", request_id=request_id))
        return

    async with SessionLocal() as db:
        member = await conversation_service.mark_read(db, conv_id, user_id, seq)
        if not member:
            await websocket.send_json(P.error("你不在该会话中", "forbidden", request_id))
            return
        members = await conversation_service.member_user_ids(db, conv_id)

    payload = {
        "conversation_id": conv_id,
        "user_id": user_id,
        "seq": member.last_read_seq,
    }
    await websocket.send_json(P.frame(P.MSG_READ, payload, request_id))
    await deliver([m for m in members if m != user_id], P.frame(P.MSG_READ, payload))


async def _handle_typing(user_id: int, data: dict) -> None:
    try:
        conv_id = int(data["conversation_id"])
    except (KeyError, TypeError, ValueError):
        return
    async with SessionLocal() as db:
        members = await conversation_service.member_user_ids(db, conv_id)
    await deliver(
        [m for m in members if m != user_id],
        P.frame(P.TYPING, {"conversation_id": conv_id, "user_id": user_id}),
    )
