"""统一错误响应：把 Pydantic 的英文校验数组翻译成中文单句。

这样 Android 客户端只需读 `detail` 字符串，不用解析 loc/msg 结构。
"""
from __future__ import annotations

import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

FIELD_LABELS = {
    "username": "用户名",
    "password": "密码",
    "nickname": "昵称",
    "sign": "签名",
    "avatar_url": "头像地址",
    "to_user_id": "对方用户",
    "peer_id": "对方用户",
    "conversation_id": "会话",
    "client_msg_id": "消息标识",
    "msg_type": "消息类型",
    "content": "消息内容",
    "extra": "附加数据",
    "seq": "已读位置",
    "q": "搜索关键字",
    "accept": "是否同意",
    "limit": "每页数量",
    "before_seq": "翻页位置",
    "after_seq": "补拉位置",
    "access_token": "访问令牌",
    "refresh_token": "刷新令牌",
}

PATTERN_HINT = {
    "^[A-Za-z0-9_]+$": "只能用字母、数字或下划线",
}


def translate_validation_msg(msg: str, ctx: dict | None = None) -> str:
    text = re.sub(r"^Value error,\s*", "", msg or "")
    ctx = ctx or {}

    m = re.search(r"at least (\d+) character", text)
    if m:
        return f"至少需要 {m.group(1)} 个字符"
    m = re.search(r"at most (\d+) character", text)
    if m:
        return f"最多 {m.group(1)} 个字符"
    if "Field required" in text:
        return "不能为空"
    if "String should match pattern" in text:
        pattern = str(ctx.get("pattern", ""))
        return PATTERN_HINT.get(pattern, "格式不正确")
    if "valid integer" in text:
        return "必须是整数"
    if "valid string" in text:
        return "必须是文本"
    if "greater than or equal to" in text:
        m = re.search(r"greater than or equal to (\d+)", text)
        return f"不能小于 {m.group(1)}" if m else "取值过小"
    if "less than or equal to" in text:
        m = re.search(r"less than or equal to (\d+)", text)
        return f"不能大于 {m.group(1)}" if m else "取值过大"
    if "Input should be" in text:
        return "取值不合法"
    return text


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError):
        parts: list[str] = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p != "body"]
            key = loc[0] if loc else ""
            field = FIELD_LABELS.get(key, key or "参数")
            parts.append(f"{field}{translate_validation_msg(err.get('msg', ''), err.get('ctx'))}")
        detail = "；".join(dict.fromkeys(parts)) or "请求参数不合法"
        return JSONResponse(status_code=422, content={"detail": detail})
