package com.liuzhidu.andyouchat.ui.login

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.KeyboardOptions
import com.liuzhidu.andyouchat.core.ApiError
import com.liuzhidu.andyouchat.core.LoginIn
import com.liuzhidu.andyouchat.core.RegisterIn
import com.liuzhidu.andyouchat.data.AppContainer
import com.liuzhidu.andyouchat.ui.theme.Brand
import com.liuzhidu.andyouchat.ui.theme.DangerRed
import com.liuzhidu.andyouchat.ui.theme.Line
import com.liuzhidu.andyouchat.ui.theme.TextMuted
import kotlinx.coroutines.launch

/**
 * 登录 / 注册页（对齐网页版 LoginView.vue 的卡片式样）。
 * 长按标题可展开服务器地址设置（调试用）。
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun LoginScreen(container: AppContainer) {
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var mode by rememberSaveable { mutableStateOf("login") } // login | register
    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var nickname by rememberSaveable { mutableStateOf("") }
    var host by rememberSaveable { mutableStateOf(container.session.host) }
    var showHost by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }

    fun submit() {
        if (busy) return
        error = ""
        busy = true
        scope.launch {
            try {
                container.session.setHost(host)
                val token = if (mode == "login") {
                    container.api.login(LoginIn(username.trim(), password)).unwrap()
                } else {
                    container.api.register(
                        RegisterIn(username.trim(), password, nickname.trim().ifEmpty { null })
                    ).unwrap()
                }
                container.session.setTokens(token)
            } catch (e: ApiError) {
                error = e.message ?: "请求失败"
            } catch (e: Exception) {
                error = "连不上服务器，请确认网络与地址"
            } finally {
                busy = false
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color.White, RoundedCornerShape(14.dp))
                .padding(28.dp),
        ) {
            Text(
                text = "AndYouChat",
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(onLongClick = { showHost = true }, onClick = {}),
            )
            Text(
                text = if (mode == "login") "登录你的账号，和好友实时聊天" else "3–32 位字母/数字/下划线，密码至少 6 位",
                color = TextMuted,
                fontSize = 12.sp,
                lineHeight = 18.sp,
                modifier = Modifier.padding(top = 4.dp, bottom = 20.dp),
            )

            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("用户名") },
                singleLine = true,
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("密码") },
                singleLine = true,
                enabled = !busy,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth(),
            )
            if (mode == "register") {
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = nickname,
                    onValueChange = { nickname = it },
                    label = { Text("昵称（可选）") },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (showHost) {
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    label = { Text("服务器地址（调试）") },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            if (error.isNotEmpty()) {
                Text(
                    text = error,
                    color = DangerRed,
                    fontSize = 12.sp,
                    lineHeight = 18.sp,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            Spacer(Modifier.height(12.dp))
            Button(
                onClick = { submit() },
                enabled = !busy && username.isNotBlank() && password.isNotBlank(),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (busy) {
                    CircularProgressIndicator(modifier = Modifier.width(18.dp).height(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (mode == "login") "登录" else "注册并登录")
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center,
            ) {
                TextButton(enabled = !busy, onClick = { mode = if (mode == "login") "register" else "login"; error = "" }) {
                    Text(
                        text = if (mode == "login") "没有账号？去注册" else "已有账号？去登录",
                        color = Brand,
                        fontSize = 12.sp,
                    )
                }
            }
        }
    }
}
