<script setup>
import { store, openConversation } from '../core/store'
import { sameId, initial, fmtTime, previewOf } from '../core/format'

function sub(c) {
  return previewOf(c.last_message) || '暂无消息'
}
</script>

<template>
  <div class="pane">
    <div v-if="!store.conversations.length" class="empty">
      还没有会话<br />去「好友」里搜索并添加对方
    </div>

    <div
      v-for="c in store.conversations"
      :key="c.id"
      class="row"
      :class="{ active: sameId(c.id, store.activeId) }"
      @click="openConversation(c.id)"
    >
      <div class="avatar">{{ initial(c.peer?.nickname || c.title) }}</div>
      <div class="row-main">
        <div class="row-top">
          <span class="row-name">
            {{ c.peer?.nickname || c.title || '会话' }}
            <span v-if="c.peer?.online" class="dot"></span>
          </span>
          <span class="row-time">{{ fmtTime(c.last_message?.created_at || c.updated_at) }}</span>
        </div>
        <div class="row-top">
          <span class="row-sub">{{ sub(c) }}</span>
          <span v-if="c.unread" class="badge">{{ c.unread > 99 ? '99+' : c.unread }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
