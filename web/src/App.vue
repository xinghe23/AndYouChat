<script setup>
import { computed, onMounted } from 'vue'
import LoginView from './components/LoginView.vue'
import SideBar from './components/SideBar.vue'
import ChatPanel from './components/ChatPanel.vue'
import ProfileDialog from './components/ProfileDialog.vue'
import { store, bootstrap } from './core/store'

onMounted(bootstrap)

const CONN_TEXT = {
  idle: '未连接',
  connecting: '连接中…',
  live: '实时通道已连接',
  down: '连接已断开，重连中…',
  unauthorized: '登录已失效',
}

const connText = computed(() => CONN_TEXT[store.conn] || '未连接')
const connClass = computed(() => {
  if (store.conn === 'live') return 'live'
  if (store.conn === 'down' || store.conn === 'unauthorized') return 'down'
  return ''
})
</script>

<template>
  <div v-if="!store.ready" class="boot">加载中…</div>

  <LoginView v-else-if="!store.me" />

  <div v-else class="shell" :class="{ 'in-chat': store.mobileView === 'chat' }">
    <SideBar />

    <ChatPanel v-if="store.activeId" />

    <div v-else class="placeholder">
      <div class="big">选择一个会话开始聊天</div>
      <div>实时通道状态显示在右下角</div>
    </div>

    <div class="conn" :class="connClass">{{ connText }}</div>

    <ProfileDialog v-if="store.profileOpen" />

    <Transition name="toast">
      <div v-if="store.toast" class="toast" :class="store.toast.kind">
        {{ store.toast.text }}
      </div>
    </Transition>
  </div>
</template>
