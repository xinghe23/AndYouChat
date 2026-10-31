<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import MessageItem from './MessageItem.vue'
import { store, loadMore, sendText, notifyTyping } from '../core/store'
import { initial, fmtDay, dayKey, sameId } from '../core/format'

const listEl = ref(null)
const taEl = ref(null)
const draft = ref('')
const stickBottom = ref(true)

const conv = computed(
  () => store.conversations.find((c) => sameId(c.id, store.activeId)) || null,
)
const peer = computed(() => conv.value?.peer || null)
const title = computed(() => peer.value?.nickname || conv.value?.title || '会话')
const online = computed(() => Boolean(peer.value?.online))
const isTyping = computed(() => store.typingConv === String(store.activeId))
const statusText = computed(() => {
  if (isTyping.value) return '对方正在输入…'
  return online.value ? '在线' : '离线'
})
const readSeq = computed(() => Number(store.peerReadSeq[String(store.activeId)] || 0))

/** 按天插入日期分隔线 */
const items = computed(() => {
  const out = []
  let lastDay = ''
  for (const m of store.messages) {
    const key = dayKey(m.created_at)
    if (key !== lastDay) {
      out.push({ type: 'day', key: `day-${key}`, label: fmtDay(m.created_at) })
      lastDay = key
    }
    out.push({
      type: 'msg',
      key: `msg-${m.client_msg_id || m.id}`,
      message: m,
    })
  }
  return out
})

function scrollToBottom() {
  const el = listEl.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

async function onScroll() {
  const el = listEl.value
  if (!el) return
  stickBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  if (el.scrollTop > 40 || !store.hasMore || store.loadingMore) return

  // 向上翻页：记录锚点，插入旧消息后保持视觉位置不跳
  const prevHeight = el.scrollHeight
  const prevTop = el.scrollTop
  await loadMore()
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = prevTop + (listEl.value.scrollHeight - prevHeight)
}

watch(
  () => store.activeId,
  async () => {
    stickBottom.value = true
    await nextTick()
    scrollToBottom()
  },
)

watch(
  () => store.messages.length,
  async () => {
    if (!stickBottom.value) return
    await nextTick()
    scrollToBottom()
  },
)

function resize() {
  const el = taEl.value
  if (!el) return
  el.style.height = '42px'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

function onInput() {
  notifyTyping()
  resize()
}

function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  stickBottom.value = true
  sendText(text)
  nextTick(() => {
    resize()
    scrollToBottom()
  })
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <main class="chat">
    <header class="chat-head">
      <button class="back-btn" title="返回列表" @click="store.mobileView = 'list'">‹</button>
      <div class="avatar">{{ initial(title) }}</div>
      <div class="head-main">
        <div class="chat-title">{{ title }}</div>
        <div class="chat-status" :class="{ typing: isTyping }">{{ statusText }}</div>
      </div>
      <span v-if="online" class="pill-online"><span class="dot"></span>在线</span>
    </header>

    <div ref="listEl" class="messages" @scroll.passive="onScroll">
      <div v-if="store.loadingMore" class="load-more">加载更早的消息…</div>
      <div v-else-if="!store.hasMore && store.messages.length" class="load-more">没有更早的消息了</div>

      <div v-if="store.loadingConv" class="empty">加载中…</div>
      <div v-else-if="!store.messages.length" class="empty">还没有消息，说点什么吧</div>

      <template v-for="item in items" :key="item.key">
        <div v-if="item.type === 'day'" class="day">{{ item.label }}</div>
        <MessageItem
          v-else
          :message="item.message"
          :peer="peer"
          :peer-read-seq="readSeq"
        />
      </template>
    </div>

    <div class="composer">
      <textarea
        ref="taEl"
        v-model="draft"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        @input="onInput"
        @keydown="onKeydown"
      ></textarea>
      <button :disabled="!draft.trim()" @click="send">发送</button>
    </div>
  </main>
</template>
