package com.liuzhidu.andyouchat.ui.chat

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.liuzhidu.andyouchat.core.ApiError
import com.liuzhidu.andyouchat.core.Conn
import com.liuzhidu.andyouchat.core.ConversationOut
import com.liuzhidu.andyouchat.core.Fmt
import com.liuzhidu.andyouchat.core.MessageOut
import com.liuzhidu.andyouchat.core.ReadIn
import com.liuzhidu.andyouchat.core.SendMessageIn
import com.liuzhidu.andyouchat.data.AppContainer
import com.liuzhidu.andyouchat.ui.common.Avatar
import com.liuzhidu.andyouchat.ui.common.EmptyHint
import com.liuzhidu.andyouchat.ui.theme.Brand
import com.liuzhidu.andyouchat.ui.theme.BubbleMeColor
import com.liuzhidu.andyouchat.ui.theme.BubbleOther
import com.liuzhidu.andyouchat.ui.theme.DangerRed
import com.liuzhidu.andyouchat.ui.theme.Line
import com.liuzhidu.andyouchat.ui.theme.OkGreen
import com.liuzhidu.andyouchat.ui.theme.TextMuted
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.util.UUID

/** 消息 UI 包装：msg + 发送状态（对齐网页版 pending/failed 语义） */
data class UiMessage(val msg: MessageOut, val status: String) // ok | sending | failed

class ChatViewModel(
    private val container: AppContainer,
    val convId: Long,
) : ViewModel() {
    private val api get() = container.api
    private val json = container.json

    var conv by MutableStateFlow<ConversationOut?>(null)
        private set
    val messages = MutableStateFlow<List<UiMessage>>(emptyList())
    var hasMore by MutableStateFlow(false)
        private set
    var loadingMore by MutableStateFlow(false)
        private set
    var loading by MutableStateFlow(true)
        private set
    var peerReadSeq by MutableStateFlow(0L)
        private set
    var peerTyping by MutableStateFlow(false)
        private set
    var error by MutableStateFlow<String?>(null)
        private set

    private var maxSeq = 0L
    private var lastTypingSent = 0L
    private var typingClearJob: Job? = null
    private var lastReadSent = 0L

    private val myId: Long get() = container.session.me?.id ?: 0L

    init {
        container.readingConvId.value = convId
        loadInitial()
        collectWs()
        collectConn()
    }

    override fun onCleared() {
        if (container.readingConvId.value == convId) container.readingConvId.value = null
    }

    private fun loadInitial() {
        viewModelScope.launch {
            try {
                conv = api.conversation(convId).unwrap()
                val page = api.messages(convId).unwrap()
                messages.value = page.items.map { UiMessage(it, "ok") }
                hasMore = page.hasMore
                maxSeq = maxOf(maxSeq, page.maxSeq)
                markRead(page.maxSeq)
            } catch (e: ApiError) {
                error = e.message
            } catch (_: Exception) {
                error = "连不上服务器"
            }
            loading = false
        }
    }

    private fun collectConn() {
        viewModelScope.launch {
            container.ws.conn.collect { c ->
                if (c == Conn.LIVE) catchUp()
            }
        }
    }

    /** 重连后增量补拉（after_seq = 本地最大 seq） */
    fun catchUp() {
        viewModelScope.launch {
            try {
                if (maxSeq <= 0) return@launch
                val page = api.messages(convId, afterSeq = maxSeq).unwrap()
                page.items.forEach { onServerMessage(it, fromSelf = false) }
            } catch (_: Exception) {
                // 静默，下轮心跳/轮询兜底
            }
        }
    }

    private fun collectWs() {
        viewModelScope.launch {
            container.ws.frames.collect { f ->
                val data = f.data
                when (f.type) {
                    "msg.new" -> {
                        val m = decodeMessage(data["message"]) ?: return@collect
                        if (m.conversationId == convId) onServerMessage(m, fromSelf = false)
                    }
                    "msg.ack" -> {
                        val m = decodeMessage(data["message"]) ?: return@collect
                        if (m.conversationId == convId) {
                            // 按 client_msg_id 替换乐观消息
                            val list = messages.value.toMutableList()
                            val idx = list.indexOfFirst {
                                (it.msg.clientMsgId != null && it.msg.clientMsgId == m.clientMsgId) ||
                                    it.msg.id == m.id
                            }
                            if (idx >= 0) list[idx] = UiMessage(m, "ok") else list.add(UiMessage(m, "ok"))
                            messages.value = list
                            maxSeq = maxOf(maxSeq, m.seq)
                            markRead(m.seq)
                        }
                    }
                    "msg.recalled" -> {
                        val m = decodeMessage(data["message"]) ?: return@collect
                        if (m.conversationId == convId) {
                            messages.value = messages.value.map {
                                if (it.msg.id == m.id) UiMessage(m, "ok") else it
                            }
                        }
                    }
                    "msg.read" -> {
                        val cid = longOf(data["conversation_id"])
                        val uid = longOf(data["user_id"])
                        val seq = longOf(data["seq"])
                        if (cid == convId && uid != null && uid != myId && seq != null) {
                            peerReadSeq = maxOf(peerReadSeq, seq)
                        }
                    }
                    "typing" -> {
                        val cid = longOf(data["conversation_id"])
                        val uid = longOf(data["user_id"])
                        if (cid == convId && uid != null && uid != myId) {
                            peerTyping = true
                            typingClearJob?.cancel()
                            typingClearJob = viewModelScope.launch {
                                delay(3000)
                                peerTyping = false
                            }
                        }
                    }
                }
            }
        }
    }

    private fun decodeMessage(element: kotlinx.serialization.json.JsonElement?): MessageOut? =
        element?.let { runCatching { json.decodeFromJsonElement<MessageOut>(it) }.getOrNull() }

    private fun longOf(element: kotlinx.serialization.json.JsonElement?): Long? =
        (element as? JsonPrimitive)?.content?.toLongOrNull()

    /** 服务端消息入库：按 id 去重，插入到列表尾部（收到顺序即 seq 顺序） */
    private fun onServerMessage(m: MessageOut, fromSelf: Boolean) {
        if (messages.value.any { it.msg.id == m.id }) return
        messages.value = messages.value + UiMessage(m, "ok")
        maxSeq = maxOf(maxSeq, m.seq)
        if (!m.revoked) markRead(m.seq)
    }

    /** 标记已读：WS 优先，断线时 HTTP 兜底 */
    private fun markRead(seq: Long) {
        if (seq <= lastReadSent) return
        lastReadSent = seq
        val sent = container.ws.send(
            "msg.read",
            buildJsonObject {
                put("conversation_id", convId)
                put("seq", seq)
            },
        )
        if (!sent) {
            viewModelScope.launch {
                runCatching { api.markReadHttp(convId, ReadIn(convId, seq)) }
            }
        }
    }

    fun loadMore() {
        val anchor = messages.value.firstOrNull { it.msg.seq > 0 }?.msg?.seq ?: return
        if (loadingMore || !hasMore) return
        viewModelScope.launch {
            loadingMore = true
            try {
                val page = api.messages(convId, beforeSeq = anchor).unwrap()
                val old = page.items.map { UiMessage(it, "ok") }
                messages.value = old + messages.value
                hasMore = page.hasMore
            } catch (_: Exception) {
                // 静默
            }
            loadingMore = false
        }
    }

    /** 发送：乐观插入 → WS；WS 不可用走 HTTP 兜底 */
    fun send(text: String) {
        val content = text.trim()
        if (content.isEmpty()) return
        val clientMsgId = UUID.randomUUID().replace("-", "").take(32)
        val optimistic = MessageOut(
            id = -System.currentTimeMillis(),
            conversationId = convId,
            seq = 0,
            senderId = myId,
            msgType = "text",
            content = content,
            clientMsgId = clientMsgId,
            createdAt = System.currentTimeMillis(),
        )
        messages.value = messages.value + UiMessage(optimistic, "sending")
        markRead(maxSeq)

        val sent = container.ws.send(
            "msg.send",
            buildJsonObject {
                put("conversation_id", convId)
                put("client_msg_id", clientMsgId)
                put("msg_type", "text")
                put("content", content)
            },
        )
        if (!sent) sendViaHttp(clientMsgId, content)
    }

    fun retry(clientMsgId: String?) {
        if (clientMsgId == null) return
        val item = messages.value.firstOrNull { it.msg.clientMsgId == clientMsgId && it.status == "failed" } ?: return
        messages.value = messages.value.map { if (it.msg.clientMsgId == clientMsgId) it.copy(status = "sending") else it }
        val sent = container.ws.send(
            "msg.send",
            buildJsonObject {
                put("conversation_id", convId)
                put("client_msg_id", clientMsgId)
                put("msg_type", "text")
                put("content", item.msg.content)
            },
        )
        if (!sent) sendViaHttp(clientMsgId, item.msg.content)
    }

    private fun sendViaHttp(clientMsgId: String, content: String) {
        viewModelScope.launch {
            try {
                val out = api.sendMessage(SendMessageIn(convId, clientMsgId, content = content)).unwrap()
                val list = messages.value.toMutableList()
                val idx = list.indexOfFirst { it.msg.clientMsgId == clientMsgId }
                if (idx >= 0) list[idx] = UiMessage(out.message, "ok") else list.add(UiMessage(out.message, "ok"))
                messages.value = list
                maxSeq = maxOf(maxSeq, out.message.seq)
                markRead(out.message.seq)
            } catch (e: ApiError) {
                markFailed(clientMsgId, e.message ?: "发送失败")
            } catch (_: Exception) {
                markFailed(clientMsgId, "网络异常，发送失败")
            }
        }
    }

    private fun markFailed(clientMsgId: String, reason: String) {
        messages.value = messages.value.map {
            if (it.msg.clientMsgId == clientMsgId) UiMessage(it.msg.copy(content = it.msg.content), "failed") else it
        }
        sendFailReason.value = reason
    }

    val sendFailReason = MutableStateFlow<String?>(null)

    fun recall(message: MessageOut) {
        viewModelScope.launch {
            try {
                val m = api.recall(message.id).unwrap()
                messages.value = messages.value.map {
                    if (it.msg.id == m.id) UiMessage(m, "ok") else it
                }
            } catch (e: ApiError) {
                sendFailReason.value = e.message ?: "撤回失败"
            } catch (_: Exception) {
                sendFailReason.value = "网络异常，撤回失败"
            }
        }
    }

    /** 正在输入：≥2s 节流（对齐协议要求） */
    fun onInputChanged() {
        val now = System.currentTimeMillis()
        if (now - lastTypingSent < 2000) return
        lastTypingSent = now
        container.ws.send("typing", buildJsonObject { put("conversation_id", convId) })
    }

    class Factory(
        private val container: AppContainer,
        private val convId: Long,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = ChatViewModel(container, convId) as T
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun ChatScreen(container: AppContainer, convId: Long, onBack: () -> Unit) {
    val vm: ChatViewModel = viewModel(key = "chat_$convId", factory = ChatViewModel.Factory(container, convId))
    val conv by vm.conv.collectAsState()
    val messages by vm.messages.collectAsState()
    val hasMore by vm.hasMore.collectAsState()
    val loadingMore by vm.loadingMore.collectAsState()
    val loading by vm.loading.collectAsState()
    val peerReadSeq by vm.peerReadSeq.collectAsState()
    val peerTyping by vm.peerTyping.collectAsState()
    val error by vm.error.collectAsState()
    val failReason by vm.sendFailReason.collectAsState()
    val presence by container.presence.collectAsState()
    val conn by container.ws.conn.collectAsState()

    var input by remember { mutableStateOf("") }
    var recallTarget by remember { mutableStateOf<MessageOut?>(null) }
    val listState = rememberLazyListState()
    val context = LocalContext.current
    val scope = androidx.compose.runtime.rememberCoroutineScope()

    val title = conv?.title ?: conv?.peer?.nickname ?: conv?.peer?.username ?: "聊天"
    val online = conv?.peer?.id?.let { presence[it] } ?: conv?.peerOnline ?: false

    LaunchedEffect(error) { error?.let { android.widget.Toast.makeText(context, it, android.widget.Toast.LENGTH_LONG).show() } }
    LaunchedEffect(failReason) { failReason?.let { android.widget.Toast.makeText(context, it, android.widget.Toast.LENGTH_SHORT).show(); vm.sendFailReason.value = null } }

    // 新消息到达自动滚底
    LaunchedEffect(messages.size, messages.lastOrNull()?.msg?.id) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }
    // 首条消息加载完也滚到底
    LaunchedEffect(loading) { if (!loading && messages.isNotEmpty()) listState.scrollToItem(messages.size - 1) }

    Scaffold(
        containerColor = Color(0xFFF5F6F8),
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                },
                title = {
                    Column {
                        Text(title, fontWeight = FontWeight.Medium, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            text = when {
                                peerTyping -> "正在输入…"
                                conn == Conn.LIVE && online -> "在线"
                                conn == Conn.DOWN -> "重连中…"
                                else -> "离线"
                            },
                            color = if (peerTyping) Brand else TextMuted,
                            fontSize = 12.sp,
                        )
                    }
                },
                actions = {
                    Avatar(title, size = 30.dp)
                    Spacer(Modifier.width(12.dp))
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding(),
        ) {
            HorizontalDivider(color = Line, thickness = 0.5.dp)

            if (loading) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (error != null) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text(error!!, color = TextMuted, fontSize = 13.sp)
                }
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp, vertical = 12.dp),
                ) {
                    if (hasMore) {
                        item {
                            Box(Modifier.fillMaxWidth().padding(bottom = 8.dp), contentAlignment = Alignment.Center) {
                                if (loadingMore) {
                                    CircularProgressIndicator(Modifier.width(18.dp).height(18.dp), strokeWidth = 2.dp)
                                } else {
                                    Text(
                                        "加载更早的消息",
                                        color = Brand,
                                        fontSize = 12.sp,
                                        modifier = Modifier
                                            .clickableNoIndication { vm.loadMore() }
                                            .padding(6.dp),
                                    )
                                }
                            }
                        }
                    }
                    items(messages, key = { it.msg.id }) { ui ->
                        val prev = messages.getOrNull(messages.indexOf(ui) - 1)
                        Column {
                            if (prev == null || !Fmt.sameDay(prev.msg.createdAt, ui.msg.createdAt)) {
                                Text(
                                    Fmt.fmtDay(ui.msg.createdAt),
                                    color = TextMuted,
                                    fontSize = 11.sp,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 10.dp)
                                        .wrapContentWidth(Alignment.CenterHorizontally),
                                )
                            }
                            MessageRow(
                                ui = ui,
                                isMine = ui.msg.senderId == container.session.me?.id,
                                peerReadSeq = peerReadSeq,
                                canRecall = ui.msg.senderId == container.session.me?.id &&
                                    !ui.msg.revoked && ui.msg.id > 0 &&
                                    System.currentTimeMillis() - ui.msg.createdAt <= 120_000,
                                onRecall = { recallTarget = ui.msg },
                                onRetry = { vm.retry(ui.msg.clientMsgId) },
                            )
                        }
                    }
                }
            }

            HorizontalDivider(color = Line, thickness = 0.5.dp)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Color.White)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = {
                        input = it
                        vm.onInputChanged()
                    },
                    placeholder = { Text("发消息…", color = TextMuted, fontSize = 14.sp) },
                    modifier = Modifier.weight(1f),
                    maxLines = 4,
                    shape = RoundedCornerShape(10.dp),
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = {
                        vm.send(input)
                        input = ""
                    },
                    enabled = input.isNotBlank(),
                    modifier = Modifier.height(48.dp),
                ) {
                    Icon(Icons.Filled.Send, contentDescription = "发送", tint = Color.White)
                }
            }
        }
    }

    if (recallTarget != null) {
        AlertDialog(
            onDismissRequest = { recallTarget = null },
            title = { Text("撤回消息") },
            text = { Text("确定撤回这条消息吗？") },
            confirmButton = {
                Button(onClick = { vm.recall(recallTarget!!); recallTarget = null }) { Text("撤回") }
            },
            dismissButton = {
                TextButton(onClick = { recallTarget = null }) { Text("取消") }
            },
        )
    }
}

private fun Modifier.clickableNoIndication(onClick: () -> Unit): Modifier =
    this.then(androidx.compose.foundation.clickable(this, onClick = onClick))

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun MessageRow(
    ui: UiMessage,
    isMine: Boolean,
    peerReadSeq: Long,
    canRecall: Boolean,
    onRecall: () -> Unit,
    onRetry: () -> Unit,
) {
    val m = ui.msg
    val bubbleColor = if (isMine && !m.revoked) BubbleMeColor else BubbleOther
    val textColor = if (isMine && !m.revoked) Color.White else MaterialTheme.colorScheme.onSurface

    Row(
        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        horizontalArrangement = if (isMine) Arrangement.End else Arrangement.Start,
    ) {
        if (!isMine) {
            Avatar("对方", size = 28.dp)
            Spacer(Modifier.width(8.dp))
        }
        Column(horizontalAlignment = if (isMine) Alignment.End else Alignment.Start) {
            if (isMine && !m.revoked && m.seq > 0) {
                Text(
                    text = if (m.seq <= peerReadSeq) "已读" else "",
                    color = Brand,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(bottom = 2.dp),
                )
            }
            Box(
                modifier = Modifier
                    .widthIn(max = 280.dp)
                    .background(
                        if (m.revoked) Color(0xFFF5F6F8) else bubbleColor,
                        RoundedCornerShape(10.dp),
                    )
                    .then(
                        if (m.revoked || !isMine) {
                            Modifier.border(0.5.dp, Line, RoundedCornerShape(10.dp))
                        } else Modifier
                    )
                    .combinedClickable(onClick = {}, onLongClick = if (canRecall) onRecall else null)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            ) {
                Text(
                    text = if (m.revoked) "消息已撤回" else m.content,
                    color = if (m.revoked) TextMuted else textColor,
                    fontSize = 14.sp,
                    lineHeight = 21.sp,
                    fontStyle = if (m.revoked) FontStyle.Italic else FontStyle.Normal,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 2.dp)) {
                when (ui.status) {
                    "sending" -> {
                        CircularProgressIndicator(Modifier.width(10.dp).height(10.dp), strokeWidth = 1.5.dp)
                        Spacer(Modifier.width(4.dp))
                        Text("发送中", color = TextMuted, fontSize = 10.sp)
                    }
                    "failed" -> {
                        Text(
                            "未发送，点击重试",
                            color = DangerRed,
                            fontSize = 10.sp,
                            modifier = Modifier.clickableNoIndication(onRetry),
                        )
                    }
                    else -> Text(Fmt.fmtTime(m.createdAt), color = TextMuted, fontSize = 10.sp)
                }
            }
        }
        if (isMine) {
            Spacer(Modifier.width(8.dp))
            Avatar("我", size = 28.dp)
        }
    }
}
