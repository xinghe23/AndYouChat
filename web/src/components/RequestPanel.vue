<script setup>
import { store, respondRequest } from '../core/store'
import { initial, fmtTime } from '../core/format'
</script>

<template>
  <div class="pane">
    <div v-if="!store.requests.length" class="empty">没有待处理的申请</div>
    <div v-for="r in store.requests" :key="r.id" class="row">
      <div class="avatar">{{ initial(r.from_user.nickname || r.from_user.username) }}</div>
      <div class="row-main">
        <div class="row-name">{{ r.from_user.nickname || r.from_user.username }}</div>
        <div class="row-sub">{{ r.message || '请求加你为好友' }}</div>
        <div class="row-sub">{{ fmtTime(r.created_at) }}</div>
      </div>
      <button class="row-action" @click.stop="respondRequest(r.id, true)">同意</button>
      <button class="row-action ghost" @click.stop="respondRequest(r.id, false)">拒绝</button>
    </div>
  </div>
</template>
