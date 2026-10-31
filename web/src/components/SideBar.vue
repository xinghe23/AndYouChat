<script setup>
import { watch } from 'vue'
import ConversationList from './ConversationList.vue'
import FriendPanel from './FriendPanel.vue'
import RequestPanel from './RequestPanel.vue'
import { store, signOut, refreshFriends, refreshRequests } from '../core/store'
import { initial } from '../core/format'

// 好友申请没有实时推送，切到对应面板时主动拉一次，避免看到过期列表
watch(
  () => store.pane,
  (pane) => {
    if (pane === 'requests') refreshRequests().catch(() => {})
    if (pane === 'friends') refreshFriends().catch(() => {})
  },
)
</script>

<template>
  <aside class="sidebar">
    <div class="me">
      <div class="avatar">{{ initial(store.me.nickname || store.me.username) }}</div>
      <div class="me-info">
        <div class="me-name">{{ store.me.nickname || store.me.username }}</div>
        <div class="me-sub">
          <span class="dot" :class="{ off: store.conn !== 'live' }"></span>
          <span>@{{ store.me.username }}</span>
        </div>
      </div>
      <button class="link-btn" @click="store.profileOpen = true">资料</button>
      <button class="link-btn" @click="signOut()">退出</button>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: store.pane === 'conversations' }" @click="store.pane = 'conversations'">
        会话<span v-if="store.unreadTotal" class="badge">{{ store.unreadTotal > 99 ? '99+' : store.unreadTotal }}</span>
      </button>
      <button class="tab" :class="{ active: store.pane === 'friends' }" @click="store.pane = 'friends'">
        好友
      </button>
      <button class="tab" :class="{ active: store.pane === 'requests' }" @click="store.pane = 'requests'">
        申请<span v-if="store.requests.length" class="badge">{{ store.requests.length }}</span>
      </button>
    </div>

    <ConversationList v-if="store.pane === 'conversations'" />
    <FriendPanel v-else-if="store.pane === 'friends'" />
    <RequestPanel v-else />
  </aside>
</template>
