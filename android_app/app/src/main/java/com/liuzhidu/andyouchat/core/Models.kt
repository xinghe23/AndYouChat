package com.liuzhidu.andyouchat.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * 与后端 Pydantic 模型逐字段对齐（docs/PROTOCOL.md）。
 * 雪花 ID 一律 Long（19 位，不能用 Int）；时间一律毫秒时间戳。
 */
@Serializable
data class UserOut(
    val id: Long,
    val username: String,
    val nickname: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val sign: String? = null,
    val online: Boolean = false,
)

/** GET /users/search 返回项 */
@Serializable
data class UserSearchItem(
    val id: Long,
    val username: String,
    val nickname: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val sign: String? = null,
    val online: Boolean = false,
    @SerialName("is_friend") val isFriend: Boolean = false,
    @SerialName("request_pending") val requestPending: Boolean = false,
)

/** GET /friends 返回项（继承 UserOut 全部字段） */
@Serializable
data class FriendOut(
    val id: Long,
    val username: String,
    val nickname: String,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val sign: String? = null,
    val online: Boolean = false,
    val remark: String? = null,
    @SerialName("conversation_id") val conversationId: Long? = null,
)

@Serializable
data class FriendRequestOut(
    val id: Long,
    @SerialName("from_user") val fromUser: UserOut,
    @SerialName("to_user") val toUser: UserOut? = null,
    val message: String? = null,
    val status: String,
    @SerialName("created_at") val createdAt: Long = 0,
)

@Serializable
data class TokenOut(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    @SerialName("expires_in") val expiresIn: Long = 0,
    val user: UserOut? = null,
)

@Serializable
data class MessageOut(
    val id: Long,
    @SerialName("conversation_id") val conversationId: Long,
    val seq: Long,
    @SerialName("sender_id") val senderId: Long,
    @SerialName("msg_type") val msgType: String = "text",
    val content: String = "",
    val extra: JsonObject? = null,
    @SerialName("client_msg_id") val clientMsgId: String? = null,
    val revoked: Boolean = false,
    @SerialName("created_at") val createdAt: Long = 0,
)

@Serializable
data class MessagePage(
    val items: List<MessageOut>,
    @SerialName("has_more") val hasMore: Boolean = false,
    @SerialName("max_seq") val maxSeq: Long = 0,
)

@Serializable
data class ConversationOut(
    val id: Long,
    val type: String = "single",
    val title: String? = null,
    val peer: UserOut? = null,
    @SerialName("last_message") val lastMessage: MessageOut? = null,
    val unread: Int = 0,
    @SerialName("last_read_seq") val lastReadSeq: Long = 0,
    val pinned: Boolean = false,
    val muted: Boolean = false,
    @SerialName("updated_at") val updatedAt: Long? = null,
    @SerialName("peer_online") val peerOnline: Boolean = false,
)

@Serializable
data class SendMessageOut(
    val message: MessageOut,
    val duplicated: Boolean = false,
)

/* ---------------- 请求体 ---------------- */

@Serializable
data class RegisterIn(val username: String, val password: String, val nickname: String? = null)

@Serializable
data class LoginIn(val username: String, val password: String)

@Serializable
data class RefreshIn(@SerialName("refresh_token") val refreshToken: String)

@Serializable
data class ProfileUpdateIn(val nickname: String? = null, val sign: String? = null)

@Serializable
data class FriendRequestIn(
    @SerialName("to_user_id") val toUserId: Long,
    val message: String? = null,
)

@Serializable
data class FriendActionIn(val accept: Boolean)

@Serializable
data class SingleIn(@SerialName("peer_id") val peerId: Long)

@Serializable
data class ReadIn(
    @SerialName("conversation_id") val conversationId: Long,
    val seq: Long,
)

@Serializable
data class SendMessageIn(
    @SerialName("conversation_id") val conversationId: Long,
    @SerialName("client_msg_id") val clientMsgId: String,
    @SerialName("msg_type") val msgType: String = "text",
    val content: String,
    val extra: JsonObject? = null,
)
