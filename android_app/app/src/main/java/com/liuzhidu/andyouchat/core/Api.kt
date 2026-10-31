package com.liuzhidu.andyouchat.core

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Headers
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** REST 接口：与 docs/PROTOCOL.md 严格对齐，路径基于 baseUrl（<host>/chat/api/） */
interface Api {

    /* ---- 认证 ---- */

    @Headers("X-No-Auth: 1")
    @POST("v1/auth/register")
    suspend fun register(@Body body: RegisterIn): Response<TokenOut>

    @Headers("X-No-Auth: 1")
    @POST("v1/auth/login")
    suspend fun login(@Body body: LoginIn): Response<TokenOut>

    @Headers("X-No-Auth: 1")
    @POST("v1/auth/refresh")
    suspend fun refresh(@Body body: RefreshIn): Response<TokenOut>

    @GET("v1/auth/me")
    suspend fun me(): Response<UserOut>

    /* ---- 用户 ---- */

    @GET("v1/users/search")
    suspend fun searchUsers(@Query("q") q: String): Response<List<UserSearchItem>>

    @PATCH("v1/users/me")
    suspend fun updateProfile(@Body body: ProfileUpdateIn): Response<UserOut>

    @GET("v1/users/{user_id}")
    suspend fun user(@Path("user_id") userId: Long): Response<UserOut>

    /* ---- 好友 ---- */

    @GET("v1/friends")
    suspend fun friends(): Response<List<FriendOut>>

    @GET("v1/friends/requests")
    suspend fun friendRequests(): Response<List<FriendRequestOut>>

    @POST("v1/friends/requests")
    suspend fun sendFriendRequest(@Body body: FriendRequestIn): Response<FriendRequestOut>

    @POST("v1/friends/requests/{id}/respond")
    suspend fun respondFriendRequest(@Path("id") id: Long, @Body body: FriendActionIn): Response<FriendRequestOut>

    /* ---- 会话 ---- */

    @GET("v1/conversations")
    suspend fun conversations(): Response<List<ConversationOut>>

    @POST("v1/conversations/single")
    suspend fun openSingle(@Body body: SingleIn): Response<ConversationOut>

    @GET("v1/conversations/{id}")
    suspend fun conversation(@Path("id") id: Long): Response<ConversationOut>

    @POST("v1/conversations/{id}/read")
    suspend fun markReadHttp(@Path("id") id: Long, @Body body: ReadIn): Response<Unit>

    /* ---- 消息 ---- */

    @GET("v1/conversations/{id}/messages")
    suspend fun messages(
        @Path("id") id: Long,
        @Query("before_seq") beforeSeq: Long? = null,
        @Query("after_seq") afterSeq: Long? = null,
        @Query("limit") limit: Int = 30,
    ): Response<MessagePage>

    @POST("v1/messages")
    suspend fun sendMessage(@Body body: SendMessageIn): Response<SendMessageOut>

    @POST("v1/messages/{id}/recall")
    suspend fun recall(@Path("id") id: Long): Response<MessageOut>
}

/** 统一解包：非 2xx 抛 ApiError(detail 中文文案) */
fun <T> Response<T>.unwrap(): T {
    if (isSuccessful) {
        body()?.let { return it }
        // 204 等空体场景
        @Suppress("UNCHECKED_CAST")
        return Unit as T
    }
    val raw = try {
        errorBody()?.string()
    } catch (_: Exception) {
        null
    }
    throw ApiError(code(), ErrorParser.fromBody(code(), raw))
}
