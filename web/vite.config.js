import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // 构建时资源前缀：默认给 FastAPI 的 /static/app 托管；--mode chat 时给 Nginx 的 /chat/
  const base = command === 'build' ? env.VITE_BASE || '/static/app/' : '/'
  const outDir = env.VITE_OUT_DIR || '../static/app'
  // dev 代理指向的后端，与生产端口保持一致（生产端口写在 deploy/nginx-andyouchat.conf 的 upstream）
  const backend = env.VITE_BACKEND || 'http://127.0.0.1:8200'
  const wsBackend = backend.replace(/^http/, 'ws')

  return {
    base,
    plugins: [vue()],
    build: {
      outDir,
      emptyOutDir: true,
      chunkSizeWarningLimit: 900,
      // 兼容旧版手机浏览器/微信内置浏览器：不降级会把 @media (max-width:768px)
      // 压成 @media (width<=768px) 这种新语法，旧内核直接忽略整段规则
      target: ['es2019', 'chrome80', 'safari13'],
      cssTarget: ['chrome80', 'safari13'],
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/ws': { target: wsBackend, ws: true },
        '/health': { target: backend, changeOrigin: true },
      },
    },
  }
})
