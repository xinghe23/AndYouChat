from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.message import MessageOut, MessagePage, SendMessageIn, SendMessageOut
from app.services import conversation_service, message_service
from app.ws import protocol as P
from app.ws.manager import deliver

router = APIRouter(tags=["消息"])


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=MessagePage,
    summary="历史消息（before_seq 向上翻页 / after_seq 断线补拉）",
)
async def list_messages(
    conv_id: int,
    before_seq: int | None = Query(default=None, ge=0),
    after_seq: int | None = Query(default=None, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await message_service.list_messages(
            db, current.id, conv_id, before_seq, after_seq, limit
        )
    except message_service.NotMemberError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/messages", response_model=SendMessageOut, summary="发送消息（HTTP 兜底）")
async def send_message(
    payload: SendMessageIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        msg, duplicated = await message_service.send_message(
            db,
            current.id,
            payload.conversation_id,
            payload.client_msg_id,
            payload.msg_type,
            payload.content,
            payload.extra,
        )
    except message_service.NotMemberError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    members = await conversation_service.member_user_ids(db, payload.conversation_id)
    await deliver(
        [m for m in members if m != current.id],
        P.frame(P.MSG_NEW, {"message": msg}),
    )
    return {"message": msg, "duplicated": duplicated}


@router.post("/messages/{message_id}/recall", response_model=MessageOut, summary="撤回")
async def recall(
    message_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        msg = await message_service.recall_message(db, current.id, message_id)
    except message_service.MessageError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    members = await conversation_service.member_user_ids(db, msg["conversation_id"])
    await deliver(members, P.frame(P.MSG_RECALLED, {"message": msg}))
    return msg
