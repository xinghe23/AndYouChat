from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.redis import is_online
from app.db.session import get_db
from app.models import User
from app.schemas.message import ConversationOut, ReadIn
from app.services import conversation_service, friend_service, user_service
from app.ws import protocol as P
from app.ws.manager import deliver

router = APIRouter(prefix="/conversations", tags=["会话"])


class SingleConversationIn(BaseModel):
    peer_id: int


async def _decorate_online(items: list[dict]) -> list[dict]:
    import asyncio

    peers = [it["peer"]["id"] for it in items if it.get("peer")]
    if not peers:
        return items
    flags = await asyncio.gather(*[is_online(pid) for pid in peers])
    flag_map = dict(zip(peers, flags))
    for it in items:
        if it.get("peer"):
            it["peer"]["online"] = bool(flag_map.get(it["peer"]["id"]))
            it["peer_online"] = bool(flag_map.get(it["peer"]["id"]))
    return items


@router.get("", response_model=list[ConversationOut], summary="会话列表")
async def list_conversations(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await conversation_service.list_conversations(db, current.id)
    return await _decorate_online(items)


@router.post("/single", response_model=ConversationOut, summary="打开/创建单聊会话")
async def open_single(
    payload: SingleConversationIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.peer_id == current.id:
        raise HTTPException(status_code=400, detail="不能和自己聊天")
    peer = await user_service.get_user(db, payload.peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not await friend_service.are_friends(db, current.id, peer.id):
        raise HTTPException(status_code=403, detail="需要先添加好友才能聊天")

    conv = await conversation_service.get_or_create_single(db, current.id, peer.id)
    detail = await conversation_service.conversation_detail(db, conv, current.id)
    if detail.get("peer"):
        online = await is_online(peer.id)
        detail["peer"]["online"] = online
        detail["peer_online"] = online
    return detail


@router.get("/{conv_id}", response_model=ConversationOut, summary="会话详情")
async def conversation_detail(
    conv_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await conversation_service.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    try:
        detail = await conversation_service.conversation_detail(db, conv, current.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return await _decorate_online([detail])


@router.post("/{conv_id}/read", summary="标记已读（HTTP 兜底，WS 也支持）")
async def mark_read(
    conv_id: int,
    payload: ReadIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    member = await conversation_service.mark_read(db, conv_id, current.id, payload.seq)
    if not member:
        raise HTTPException(status_code=403, detail="你不在该会话中")

    members = await conversation_service.member_user_ids(db, conv_id)
    await deliver(
        [m for m in members if m != current.id],
        P.frame(
            P.MSG_READ,
            {
                "conversation_id": conv_id,
                "user_id": current.id,
                "seq": member.last_read_seq,
            },
        ),
    )
    return {"conversation_id": conv_id, "last_read_seq": member.last_read_seq, "unread": member.unread}
