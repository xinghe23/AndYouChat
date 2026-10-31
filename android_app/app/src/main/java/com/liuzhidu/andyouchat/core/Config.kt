package com.liuzhidu.andyouchat.core

/**
 * 服务器地址配置。
 *
 * 开发期走明文 HTTP（已在 network_security_config.xml 白名单放行），
 * 上线切 HTTPS 时把 SCHEME 改成 "https" 并删除该 xml 文件即可。
 */
object Config {
    const val DEFAULT_HOST = "www.liuzhidu.site"
    private const val SCHEME = "http"

    /** Retrofit baseUrl，必须以 / 结尾 */
    fun restBase(host: String) = "$SCHEME://$host/chat/api/"

    /** WebSocket 基址（不含 query） */
    fun wsBase(host: String) = "$SCHEME://$host/chat/ws".replaceFirst("http", "ws")
}
