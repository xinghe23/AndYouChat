/* Vue 前端端到端验证：注册两个账号 -> 加好友 -> 实时收发 -> 已读回执 -> 撤回 */
const { chromium } = require('playwright-core')

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const BASE = process.env.BASE || 'http://127.0.0.1:8010/static/app/index.html'
const stamp = String(Date.now()).slice(-6)
const U1 = `v${stamp}a`
const U2 = `v${stamp}b`
const PW = 'pass1234'

const logs = []
const results = []
function ok(name, detail = '') {
  results.push({ name, ok: true, detail })
  console.log(`  PASS  ${name}${detail ? '  ' + detail : ''}`)
}
function fail(name, detail = '') {
  results.push({ name, ok: false, detail })
  console.log(`  FAIL  ${name}${detail ? '  ' + detail : ''}`)
}

async function register(page, username) {
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('.card', { timeout: 10000 })
  await page.click('.switch a')
  await page.waitForSelector('.card h1:text("注册新账号")')
  const inputs = page.locator('.card .field input')
  await inputs.nth(1).fill(username)
  await inputs.nth(2).fill(PW)
  await page.click('.btn-primary')
  await page.waitForSelector('.shell', { timeout: 15000 })
}

async function send(page, text) {
  await page.fill('.composer textarea', text)
  await page.click('.composer button')
}

;(async () => {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-proxy-server'],
  })
  const mkCtx = () => browser.newContext({ viewport: { width: 1280, height: 820 } })
  const ctxA = await mkCtx()
  const ctxB = await mkCtx()
  const A = await ctxA.newPage()
  const B = await ctxB.newPage()

  const tag = (n) => (m) => logs.push(`[${n}] ${m.type()}: ${m.text()}`)
  A.on('console', tag('A'))
  B.on('console', tag('B'))
  A.on('pageerror', (e) => logs.push(`[A] pageerror: ${e.message}`))
  B.on('pageerror', (e) => logs.push(`[B] pageerror: ${e.message}`))

  try {
    // 1. 注册
    await register(A, U1)
    ok('账号 A 注册并进入主界面', U1)
    await register(B, U2)
    ok('账号 B 注册并进入主界面', U2)

    // 2. 实时通道
    await A.waitForSelector('.conn.live', { timeout: 10000 })
    await B.waitForSelector('.conn.live', { timeout: 10000 })
    ok('双方 WebSocket 均已连接')

    // 3. A 搜索 B 并发起好友申请
    await A.click('.tabs .tab >> nth=1')
    await A.fill('.search-box input', U2)
    await A.click('.search-box button')
    await A.waitForSelector('.row-action:text("加好友")', { timeout: 10000 })
    await A.click('.row-action:text("加好友")')
    await A.waitForSelector('.row-action:text("已申请")', { timeout: 10000 })
    ok('A 搜索到 B 并发出好友申请')

    // 4. B 收到申请并同意
    await B.click('.tabs .tab >> nth=2')
    await B.waitForSelector('.row:has-text("同意")', { timeout: 10000 })
    await B.click('.row-action:text("同意")')
    await B.waitForSelector('.empty:has-text("没有待处理的申请")', { timeout: 10000 })
    ok('B 收到申请并同意')

    // 5. A 重新搜索 -> 已是好友 -> 进入聊天
    await A.click('.search-box button')
    await A.waitForSelector('.row-action:text("聊天")', { timeout: 10000 })
    await A.click('.row-action:text("聊天")')
    await A.waitForSelector('.chat', { timeout: 10000 })
    ok('A 从好友列表打开单聊会话')

    // 6. A 发消息
    const text1 = '你好，这是 Vue 版前端发出的第一条消息'
    await send(A, text1)
    await A.waitForSelector(`.msg.me .bubble:text("${text1}")`, { timeout: 10000 })
    ok('A 消息乐观上屏')

    // 7. B 会话列表实时出现新会话与消息预览
    await B.click('.tabs .tab >> nth=0')
    await B.waitForSelector(`.row-sub:text("${text1}")`, { timeout: 10000 })
    ok('B 会话列表实时刷新出新会话与预览')

    // 8. B 打开会话看到消息内容
    await B.click(`.row:has-text("${U1}")`)
    await B.waitForSelector(`.bubble:text("${text1}")`, { timeout: 10000 })
    ok('B 打开会话读到 A 的消息')

    // 9. A 侧确认 ack（临时态消失、meta 不再显示"发送中"）
    await A.waitForFunction(
      () => !document.querySelector('.msg.me .meta')?.textContent.includes('发送中'),
      null,
      { timeout: 10000 },
    )
    ok('A 侧收到 msg.ack，消息转为已发送态')

    // 10. B 打开会话 -> A 收到已读回执
    await A.waitForSelector('.read-mark:text("已读")', { timeout: 10000 })
    ok('B 打开会话后 A 看到「已读」')

    // 10. B 回复 -> A 实时收到
    const text2 = '收到，界面和调试台一致，实时链路正常'
    await send(B, text2)
    await A.waitForSelector(`.msg:not(.me) .bubble:text("${text2}")`, { timeout: 10000 })
    ok('B 回复后 A 实时收到')

    // 11. 撤回
    await B.hover('.msg.me')
    await B.click('.msg.me .recall-btn')
    await A.waitForSelector('.bubble.revoked:text("[消息已撤回]")', { timeout: 10000 })
    ok('B 撤回消息，A 侧同步为已撤回')

    // 12. 刷新保持登录（sessionStorage + /auth/me）
    await A.reload({ waitUntil: 'networkidle' })
    await A.waitForSelector('.shell', { timeout: 10000 })
    ok('刷新页面后自动恢复登录态')

    // 13. 退出登录
    await A.click('.me .link-btn >> nth=1')
    await A.waitForSelector('.card', { timeout: 10000 })
    ok('退出登录回到登录页')

    // 截图
    await A.screenshot({ path: 'shot-login.png' })
    await B.screenshot({ path: 'shot-chat.png' })
  } catch (e) {
    fail('执行中断', e.message.split('\n')[0])
  } finally {
    const errs = logs.filter((l) => l.includes('pageerror') || l.includes('error:'))
    console.log('\n--- 控制台异常 ---')
    console.log(errs.length ? errs.join('\n') : '无')
    console.log('\n--- 汇总 ---')
    const passed = results.filter((r) => r.ok).length
    console.log(`${passed}/${results.length} 通过`)
    await browser.close()
    process.exit(results.every((r) => r.ok) ? 0 : 1)
  }
})()
