package com.liuzhidu.andyouchat.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.filled.PersonAddAlt1
import androidx.compose.material.icons.outlined.PersonAddAlt1
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
import com.liuzhidu.andyouchat.core.FriendOut
import com.liuzhidu.andyouchat.core.FriendRequestIn
import com.liuzhidu.andyouchat.core.FriendRequestOut
import com.liuzhidu.andyouchat.core.FriendActionIn
import com.liuzhidu.andyouchat.core.MessageOut
import com.liuzhidu.andyouchat.core.SingleIn
import com.liuzhidu.andyouchat.core.UserSearchItem
import com.liuzhidu.andyouchat.data.AppContainer
import com.liuzhidu.andyouchat.ui.common.Avatar
import com.liuzhidu.andyouchat.ui.common.EmptyHint
import com.liuzhidu.andyouchat.ui.common.UnreadBadge
import com.liuzhidu.andyouchat.ui.profile.ProfileSheet
import com.liuzhidu.andyouchat.ui.theme.Line
import com.liuzhidu.andyouchat.ui.theme.OkGreen
import com.liuzhidu.andyouchat.ui.theme.RowHover
import com.liuzhidu.andyouchat.ui.theme.TextMuted
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonPrimitive

data class ToastEvent(val id: Long, val text: String)

class HomeViewModel(private val container: AppContainer) : ViewModel() {
    private val api get() = container.api

    val tab = MutableStateFlow("conversations")
    val conversations = MutableStateFlow<List<ConversationOut>>(emptyList())
    val friends = MutableStateFlow<List<FriendOut>>(emptyList())
    val requests = MutableStateFlow<List<FriendRequestOut>>(emptyList())
    val searchResults = MutableStateFlow<List<UserSearchItem>?>(null)
    val searching = MutableStateFlow(false)
    val toast = MutableStateFlow<ToastEvent?>(null)

    private var toastSeq = 0L

    init {
        refreshConversations()
        refreshFriends()
        refreshRequests()
        pollRequests()
        pollConversations()
        collectFrames()
        collectConn()
        collectReading()
    }

    fun toast(text: String) {
        toast.value = ToastEvent(++toastSeq, text)
    }

    fun refreshConversations() {
        viewModelScope.launch {
            try {
                conversations.value = api.conversations().unwrap()
            } catch (e: ApiError) {
                toast(e.message ?: "刷新失败")
            } catch (e: Exception) {
                toast("连不上服务器")
            }
        }
    }

    fun refreshFriends() {
        viewModelScope.launch {
            try {
                friends.value = api.friends().unwrap()
            } catch (_: Exception) {
                // 静默：面板切换时会重试
            }
        }
    }

    fun refreshRequests() {
        viewModelScope.launch {
            try {
                requests.value = api.friendRequests().unwrap()
            } catch (_: Exception) {
                // 静默轮询
            }
        }
    }

    /** 好友申请没有推送通道：20s 轮询兜底（对齐网页版） */
    private fun pollRequests() {
        viewModelScope.launch {
            while (isActive) {
                delay(20_000)
                refreshRequests()
            }
        }
    }

    /** 会话列表轻量轮询：兜底补齐离线期间的未读/预览 */
    private fun pollConversations() {
        viewModelScope.launch {
            while (isActive) {
                delay(30_000)
                refreshConversations()
            }
        }
    }

    private fun collectConn() {
        viewModelScope.launch {
            container.ws.conn.collect { c ->
                if (c == Conn.LIVE) refreshConversations() // 重连成功后补拉
            }
        }
    }

    private fun collectReading() {
        viewModelScope.launch {
            container.readingConvId.collect { reading ->
                if (reading != null) {
                    conversations.value = conversations.value.map {
                        if (it.id == reading) it.copy(unread = 0) else it
                    }
                }
            }
        }
    }

    private fun collectFrames() {
        viewModelScope.launch {
            container.ws.frames.collect { f ->
                when (f.type) {
                    "msg.new" -> {
                        val m = runCatching {
                            container.json.decodeFromJsonElement<MessageOut>(f.data["message"]!!)
                        }.getOrNull()
                        if (m != null && container.readingConvId.value != m.conversationId) {
                            refreshConversations()
                        }
                    }
                    "msg.recalled" -> refreshConversations()
                    "presence" -> {
                        val uid = runCatching { f.data["user_id"]!!.jsonPrimitive.long }.getOrNull()
                        val online = runCatching { f.data["online"]!!.jsonPrimitive.content == "true" }.getOrNull()
                        if (uid != null && online != null) {
                            container.presence.value = container.presence.value + (uid to online)
                            friends.value = friends.value.map {
                                if (it.id == uid) it.copy(online = online) else it
                            }
                            conversations.value = conversations.value.map {
                                if (it.peer?.id == uid) it.copy(peerOnline = online) else it
                            }
                        }
                    }
                }
            }
        }
    }

    fun search(q: String) {
        if (q.isBlank()) {
            searchResults.value = null
            return
        }
        viewModelScope.launch {
            searching.value = true
            try {
                searchResults.value = api.searchUsers(q.trim()).unwrap()
            } catch (e: ApiError) {
                toast(e.message ?: "搜索失败")
            } catch (_: Exception) {
                toast("连不上服务器")
            }
            searching.value = false
        }
    }

    fun clearSearch() {
        searchResults.value = null
    }

    fun addFriend(userId: Long) {
        viewModelScope.launch {
            try {
                api.sendFriendRequest(FriendRequestIn(userId)).unwrap()
                toast("申请已发送")
                // 对方已先申请时直接互加，刷新两侧
                refreshFriends()
                searchResults.value?.let { list ->
                    searchResults.value = list.map {
                        if (it.id == userId) it.copy(isFriend = true, requestPending = true) else it
                    }
                }
            } catch (e: ApiError) {
                toast(e.message ?: "发送失败")
            } catch (_: Exception) {
                toast("连不上服务器")
            }
        }
    }

    fun respond(requestId: Long, accept: Boolean) {
        viewModelScope.launch {
            try {
                api.respondFriendRequest(requestId, FriendActionIn(accept)).unwrap()
                refreshRequests()
                refreshFriends()
                if (accept) refreshConversations()
            } catch (e: ApiError) {
                toast(e.message ?: "操作失败")
            } catch (_: Exception) {
                toast("连不上服务器")
            }
        }
    }

    /** 打开/创建与好友的单聊并进入聊天页 */
    fun openWithFriend(friend: FriendOut, onOpenChat: (Long) -> Unit) {
        viewModelScope.launch {
            try {
                val conv = api.openSingle(SingleIn(friend.id)).unwrap()
                friends.value = friends.value.map {
                    if (it.id == friend.id) it.copy(conversationId = conv.id) else it
                }
                onOpenChat(conv.id)
            } catch (e: ApiError) {
                toast(e.message ?: "打开会话失败")
            } catch (_: Exception) {
                toast("连不上服务器")
            }
        }
    }

    class Factory(private val container: AppContainer) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = HomeViewModel(container) as T
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(container: AppContainer, onOpenChat: (Long) -> Unit) {
    val vm: HomeViewModel = viewModel(factory = HomeViewModel.Factory(container))
    val scope = rememberCoroutineScope()
    val tab by vm.tab.collectAsState()
    val conversations by vm.conversations.collectAsState()
    val friends by vm.friends.collectAsState()
    val requests by vm.requests.collectAsState()
    val searchResults by vm.searchResults.collectAsState()
    val searching by vm.searching.collectAsState()
    val conn by container.ws.conn.collectAsState()
    val toast by vm.toast.collectAsState()
    val myName = container.session.me?.nickname ?: container.session.me?.username ?: ""

    var showProfile by remember { mutableStateOf(false) }

    val context = androidx.compose.ui.platform.LocalContext.current
    androidx.compose.runtime.LaunchedEffect(toast) {
        toast?.let { android.widget.Toast.makeText(context, it.text, android.widget.Toast.LENGTH_SHORT).show() }
    }

    val unreadTotal = conversations.sumOf { it.unread }

    Scaffold(
        containerColor = androidx.compose.ui.graphics.Color(0xFFF5F6F8),
        topBar = {
            TopAppBar(
                title = { Text(myName, fontWeight = FontWeight.SemiBold, fontSize = 17.sp) },
                actions = {
                    // 实时通道状态点
                    val (dotColor, label) = when (conn) {
                        Conn.LIVE -> OkGreen to "已连接"
                        Conn.CONNECTING -> TextMuted to "连接中"
                        Conn.DOWN -> Color(0xFFE24B4A) to "重连中"
                        Conn.UNAUTHORIZED -> Color(0xFFE24B4A) to "登录失效"
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(end = 6.dp),
                    ) {
                        Box(
                            modifier = Modifier.size(8.dp).background(dotColor, CircleShape),
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(label, color = TextMuted, fontSize = 11.sp)
                    }
                    IconButton(onClick = { showProfile = true }) {
                        Avatar(myName, size = 30.dp)
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                BottomItem("会话", tab == "conversations", unreadTotal, Icons.Filled.ChatBubble, Icons.Outlined.ChatBubbleOutline) {
                    vm.tab.value = "conversations"; vm.refreshConversations()
                }
                BottomItem("好友", tab == "friends", 0, Icons.Filled.Groups, Icons.Outlined.Groups) {
                    vm.tab.value = "friends"; vm.refreshFriends()
                }
                BottomItem("申请", tab == "requests", requests.size, Icons.Filled.PersonAddAlt1, Icons.Outlined.PersonAddAlt1) {
                    vm.tab.value = "requests"; vm.refreshRequests()
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            when (tab) {
                "conversations" -> ConversationsTab(conversations) { conv -> onOpenChat(conv.id) }
                "friends" -> FriendsTab(vm, friends, searchResults, searching, onOpenChat)
                "requests" -> RequestsTab(requests, vm)
            }
        }
    }

    if (showProfile) {
        ProfileSheet(container, onDismiss = { showProfile = false })
    }
}

@Composable
private fun BottomItem(
    label: String,
    selected: Boolean,
    badge: Int,
    iconSelected: androidx.compose.ui.graphics.vector.ImageVector,
    iconNormal: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
) {
    NavigationBarItem(
        selected = selected,
        onClick = onClick,
        icon = {
            BadgedBox(badge = { if (badge > 0) Badge { Text(badge.toString()) } }) {
                Icon(if (selected) iconSelected else iconNormal, contentDescription = label)
            }
        },
        label = { Text(label, fontSize = 11.sp) },
    )
}

/* ---------------- 会话 tab ---------------- */

@Composable
private fun ConversationsTab(list: List<ConversationOut>, onOpen: (ConversationOut) -> Unit) {
    if (list.isEmpty()) {
        EmptyHint("还没有会话\n去「好友」页发起聊天吧", Modifier.fillMaxSize())
        return
    }
    LazyColumn(Modifier.fillMaxSize()) {
        items(list, key = { it.id }) { conv ->
            val title = conv.title ?: conv.peer?.nickname ?: conv.peer?.username ?: "会话"
            Column(Modifier.fillMaxWidth().background(Color.White).clickable { onOpen(conv) }) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box {
                        Avatar(title)
                        if (conv.peerOnline) {
                            Box(
                                Modifier
                                    .size(10.dp)
                                    .align(Alignment.BottomEnd)
                                    .background(OkGreen, CircleShape),
                            )
                        }
                    }
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            title,
                            fontWeight = FontWeight.Medium,
                            fontSize = 15.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            Fmt.preview(conv.lastMessage),
                            color = TextMuted,
                            fontSize = 12.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(Fmt.fmtTime(conv.updatedAt), color = TextMuted, fontSize = 11.sp)
                        Spacer(Modifier.height(4.dp))
                        UnreadBadge(conv.unread)
                    }
                }
                HorizontalDivider(color = Line, thickness = 0.5.dp)
            }
        }
    }
}

/* ---------------- 好友 tab ---------------- */

@Composable
private fun FriendsTab(
    vm: HomeViewModel,
    friends: List<FriendOut>,
    searchResults: List<UserSearchItem>?,
    searching: Boolean,
    onOpenChat: (Long) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color.White)
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = { Text("输入用户名搜索", fontSize = 13.sp) },
                singleLine = true,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            Button(onClick = { vm.search(query) }, enabled = query.isNotBlank()) {
                if (searching) {
                    CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = Color.White)
                } else {
                    Text("搜索", fontSize = 13.sp)
                }
            }
        }

        LazyColumn(Modifier.fillMaxSize()) {
            if (searchResults != null) {
                item {
                    SectionTitle(
                        "搜索结果",
                        trailing = "清除",
                        onTrailing = { vm.clearSearch(); query = "" },
                    )
                }
                if (searchResults.isEmpty()) {
                    item { EmptyHint("没有找到该用户", Modifier.fillMaxWidth().padding(vertical = 24.dp)) }
                }
                items(searchResults, key = { it.id }) { u ->
                    Column(Modifier.fillMaxWidth().background(Color.White)) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Avatar(u.nickname.ifEmpty { u.username })
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    u.nickname.ifEmpty { u.username },
                                    fontWeight = FontWeight.Medium,
                                    fontSize = 15.sp,
                                )
                                Text("@${u.username}", color = TextMuted, fontSize = 12.sp)
                            }
                            when {
                                u.isFriend -> Text("已是好友", color = TextMuted, fontSize = 12.sp)
                                u.requestPending -> Text("已申请", color = TextMuted, fontSize = 12.sp)
                                else -> OutlinedButton(onClick = { vm.addFriend(u.id) }) {
                                    Text("加好友", fontSize = 12.sp)
                                }
                            }
                        }
                        HorizontalDivider(color = Line, thickness = 0.5.dp)
                    }
                }
            }

            item { SectionTitle("我的好友（${friends.size}）") }
            if (friends.isEmpty()) {
                item { EmptyHint("还没有好友\n在上方搜索用户名添加", Modifier.fillMaxWidth().padding(vertical = 24.dp)) }
            }
            items(friends, key = { it.id }) { friend ->
                Column(Modifier.fillMaxWidth().background(Color.White)) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box {
                            Avatar(friend.nickname.ifEmpty { friend.username })
                            if (friend.online) {
                                Box(
                                    Modifier
                                        .size(10.dp)
                                        .align(Alignment.BottomEnd)
                                        .background(OkGreen, CircleShape),
                                )
                            }
                        }
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                friend.remark?.takeIf { it.isNotBlank() }
                                    ?: friend.nickname.ifEmpty { friend.username },
                                fontWeight = FontWeight.Medium,
                                fontSize = 15.sp,
                            )
                            Text(
                                if (friend.online) "在线" else "离线",
                                color = if (friend.online) OkGreen else TextMuted,
                                fontSize = 12.sp,
                            )
                        }
                        Button(onClick = { vm.openWithFriend(friend, onOpenChat) }) {
                            Text("聊天", fontSize = 13.sp)
                        }
                    }
                    HorizontalDivider(color = Line, thickness = 0.5.dp)
                }
            }
        }
    }
}

/* ---------------- 申请 tab ---------------- */

@Composable
private fun RequestsTab(list: List<FriendRequestOut>, vm: HomeViewModel) {
    if (list.isEmpty()) {
        EmptyHint("暂无好友申请", Modifier.fillMaxSize())
        return
    }
    LazyColumn(Modifier.fillMaxSize()) {
        items(list, key = { it.id }) { req ->
            Column(Modifier.fillMaxWidth().background(Color.White)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Avatar(req.fromUser.nickname.ifEmpty { req.fromUser.username })
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            req.fromUser.nickname.ifEmpty { req.fromUser.username },
                            fontWeight = FontWeight.Medium,
                            fontSize = 15.sp,
                        )
                        Text(
                            req.message?.takeIf { it.isNotBlank() } ?: "请求添加你为好友",
                            color = TextMuted,
                            fontSize = 12.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { vm.respond(req.id, true) }) { Text("同意", fontSize = 12.sp) }
                        OutlinedButton(onClick = { vm.respond(req.id, false) }) { Text("拒绝", fontSize = 12.sp) }
                    }
                }
                HorizontalDivider(color = Line, thickness = 0.5.dp)
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String, trailing: String? = null, onTrailing: (() -> Unit)? = null) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFFFAFBFC))
            .padding(horizontal = 14.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text, color = TextMuted, fontSize = 11.sp)
        if (trailing != null && onTrailing != null) {
            Text(
                trailing,
                modifier = Modifier
                    .clickable(onClick = onTrailing)
                    .padding(2.dp),
                color = Brand,
                fontSize = 11.sp,
            )
        }
    }
}
