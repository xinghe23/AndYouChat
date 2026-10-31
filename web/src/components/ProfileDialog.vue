<script setup>
import { ref } from 'vue'
import { store, saveProfile } from '../core/store'

const nickname = ref(store.me?.nickname || '')
const sign = ref(store.me?.sign || '')
const busy = ref(false)

async function submit() {
  if (!nickname.value.trim()) return
  busy.value = true
  try {
    await saveProfile({ nickname: nickname.value.trim(), sign: sign.value.trim() })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="modal-mask" @click.self="store.profileOpen = false">
    <div class="modal-card">
      <h2>个人资料</h2>
      <div class="field">
        <label>昵称</label>
        <input v-model="nickname" maxlength="32" placeholder="昵称" />
      </div>
      <div class="field">
        <label>个性签名</label>
        <input v-model="sign" maxlength="128" placeholder="随便写点什么" />
      </div>
      <div class="field">
        <label>用户名（不可修改）</label>
        <input :value="store.me?.username" disabled />
      </div>
      <div class="modal-actions">
        <button class="btn-ghost" @click="store.profileOpen = false">取消</button>
        <button class="btn-solid" :disabled="busy || !nickname.trim()" @click="submit">
          {{ busy ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>
