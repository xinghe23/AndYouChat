<script setup>
import { store, searchUsers, addFriend, openWith } from '../core/store'
import { initial } from '../core/format'

async function onSearch() {
  await searchUsers(store.searchQuery)
}
</script>

<template>
  <div class="pane">
    <div class="search-box">
      <input
        v-model="store.searchQuery"
        placeholder="搜索用户名或昵称"
        @keydown.enter.prevent="onSearch"
      />
      <button :disabled="store.searching" @click="onSearch">
        {{ store.searching ? '…' : '搜索' }}
      </button>
    </div>

    <template v-if="store.searchResults.length">
      <div class="pane-title">搜索结果</div>
      <div v-for="u in store.searchResults" :key="'s' + u.id" class="row">
        <div class="avatar">{{ initial(u.nickname || u.username) }}</div>
        <div class="row-main">
          <div class="row-name">
            {{ u.nickname || u.username }}
            <span v-if="u.online" class="dot"></span>
          </div>
          <div class="row-sub">@{{ u.username }}{{ u.is_friend ? ' · 已是好友' : '' }}</div>
        </div>
        <button v-if="u.is_friend" class="row-action" @click.stop="openWith(u.id)">聊天</button>
        <button v-else-if="u.request_pending" class="row-action ghost" disabled>已申请</button>
        <button v-else class="row-action" @click.stop="addFriend(u.id)">加好友</button>
      </div>
    </template>

    <div class="pane-title">我的好友（{{ store.friends.length }}）</div>
    <div v-if="!store.friends.length" class="empty">还没有好友，用上面的搜索加一个</div>
    <div v-for="f in store.friends" :key="'f' + f.id" class="row">
      <div class="avatar">{{ initial(f.nickname || f.username) }}</div>
      <div class="row-main">
        <div class="row-name">
          {{ f.nickname || f.username }}
          <span v-if="f.online" class="dot"></span>
        </div>
        <div class="row-sub">@{{ f.username }}</div>
      </div>
      <button class="row-action" @click.stop="openWith(f.id)">聊天</button>
    </div>
  </div>
</template>
