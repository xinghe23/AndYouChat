<script setup>
import { computed } from 'vue'
import { store, canRecall, retryMessage, recallMessage } from '../core/store'
import { initial, fmtTime, sameId } from '../core/format'

const props = defineProps({
  message: { type: Object, required: true },
  peer: { type: Object, default: null },
  peerReadSeq: { type: Number, default: 0 },
})

const mine = computed(() => sameId(props.message.sender_id, store.me?.id))
const read = computed(
  () =>
    mine.value &&
    Number(props.message.seq) > 0 &&
    props.peerReadSeq >= Number(props.message.seq),
)
const avatarText = computed(() =>
  mine.value
    ? initial(store.me?.nickname || store.me?.username)
    : initial(props.peer?.nickname || props.peer?.username),
)
</script>

<template>
  <div
    class="msg"
    :class="{
      me: mine,
      pending: message._pending,
      failed: message._failed,
    }"
  >
    <div class="avatar">{{ avatarText }}</div>
    <div class="bubble-wrap">
      <div class="bubble" :class="{ revoked: message.revoked }">
        {{ message.revoked ? '[消息已撤回]' : message.msg_type === 'image' ? '[图片]' : message.content }}
      </div>
      <div class="meta">
        <span>{{ fmtTime(message.created_at) }}</span>
        <template v-if="mine">
          <span v-if="message._pending">发送中…</span>
          <span v-else-if="message._failed" class="fail-mark">发送失败</span>
          <button v-if="message._failed" class="retry-btn" @click="retryMessage(message)">重发</button>
          <span v-else-if="read" class="read-mark">已读</span>
        </template>
        <button v-if="canRecall(message)" class="recall-btn" @click="recallMessage(message)">撤回</button>
      </div>
    </div>
  </div>
</template>
