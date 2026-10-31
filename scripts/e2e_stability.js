/* 稳定性：登录后保持 60s，验证心跳保活期间 WS 状态始终为 live */
const { chromium } = require('playwright-core')

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = 'http://127.0.0.1:8010/static/app/index.html'
const stamp = String(Date.now()).slice(-6)

;(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-proxy-server'],
  })
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.click('.switch a')
  const inputs = page.locator('.card .field input')
  await inputs.nth(1).fill(`stab${stamp}`)
  await inputs.nth(2).fill('pass1234')
  await page.click('.btn-primary')
  await page.waitForSelector('.shell')

  const samples = []
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(5000)
    const cls = await page.getAttribute('.conn', 'class')
    samples.push(cls.includes('live') ? 'live' : cls)
  }
  const liveCount = samples.filter((s) => s === 'live').length
  console.log(`60s 内 live 采样: ${liveCount}/12 -> ${samples.join(',')}`)
  console.log(`页面 JS 异常: ${errors.length ? errors.join(' | ') : '无'}`)
  console.log(liveCount === 12 && errors.length === 0 ? 'STABLE' : 'UNSTABLE')
  await browser.close()
  process.exit(liveCount === 12 && errors.length === 0 ? 0 : 1)
})()
