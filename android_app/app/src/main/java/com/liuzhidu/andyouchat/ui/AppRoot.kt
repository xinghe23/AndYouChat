package com.liuzhidu.andyouchat.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.liuzhidu.andyouchat.data.AppContainer
import com.liuzhidu.andyouchat.ui.chat.ChatScreen
import com.liuzhidu.andyouchat.ui.home.HomeScreen
import com.liuzhidu.andyouchat.ui.login.LoginScreen

@Composable
fun AppRoot(container: AppContainer) {
    val loggedIn by container.session.loggedIn.collectAsState()

    // WS 生命周期：登录后启动，登出停止
    LaunchedEffect(loggedIn) {
        if (loggedIn) container.ws.start() else container.ws.stop()
    }

    // WS 鉴权失效（4401）：清会话回登录页
    LaunchedEffect(Unit) {
        container.ws.authFailed.collect { container.session.clear() }
    }

    if (!loggedIn) {
        LoginScreen(container)
    } else {
        val nav = rememberNavController()
        NavHost(navController = nav, startDestination = "home") {
            composable("home") {
                HomeScreen(container, onOpenChat = { convId -> nav.navigate("chat/$convId") })
            }
            composable("chat/{convId}") { entry ->
                val convId = entry.arguments?.getString("convId")?.toLongOrNull()
                if (convId != null) {
                    ChatScreen(container, convId, onBack = { nav.popBackStack() })
                }
            }
        }
    }
}
