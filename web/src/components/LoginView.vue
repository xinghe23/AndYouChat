<script setup>
import { ref } from 'vue'
import { login } from '../core/store'
import { session } from '../core/session'

const base = ref(session.base || '')
const username = ref('')
const password = ref('')
const registerMode = ref(false)
const error = ref('')
const busy = ref(false)

function toggleMode() {
  registerMode.value = !registerMode.value
  error.value = ''
}

async function submit() {
  error.value = ''
  const name = username.value.trim()
  if (!name) {
    error.value = '请输入用户名'
    return
  }
  if (!password.value) {
    error.value = '请输入密码'
    return
  }
  if (registerMode.value) {
    if (!/^[A-Za-z0-9_]{3,32}$/.test(name)) {
      error.value = '用户名需 3-32 位字母、数字或下划线'
      return
    }
    if (password.value.length < 6) {
      error.value = '密码至少 6 位'
      return
    }
  } else if (name.length < 3) {
    error.value = '用户名至少 3 位'
    return
  }

  busy.value = true
  try {
    await login({
      username: name,
      password: password.value,
      base: base.value,
      register: registerMode.value,
    })
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="card" @submit.prevent="submit">
      <h1>{{ registerMode ? '注册新账号' : '登录 AndYouChat' }}</h1>
      <p class="hint">开两个浏览器标签页分别登录不同账号，即可验证实时链路。</p>

      <div class="field">
        <label>服务器地址</label>
        <input v-model="base" placeholder="留空表示当前域名，如 http://127.0.0.1:8000" @input="error = ''" />
      </div>
      <div class="field">
        <label>用户名（3-32 位字母/数字/下划线）</label>
        <input v-model="username" autocomplete="username" placeholder="alice" @input="error = ''" />
      </div>
      <div class="field">
        <label>密码（至少 6 位）</label>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="pass1234"
          @input="error = ''"
        />
      </div>

      <button class="btn-primary" type="submit" :disabled="busy">
        {{ busy ? '处理中…' : registerMode ? '注册并登录' : '登录' }}
      </button>

      <div class="switch">
        <span>{{ registerMode ? '已有账号？' : '没有账号？' }}</span>
        <a @click="toggleMode">{{ registerMode ? '去登录' : '注册一个' }}</a>
      </div>

      <div class="err">{{ error }}</div>
    </form>
  </div>
</template>
