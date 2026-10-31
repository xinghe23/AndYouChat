# AndYouChat Android 客户端开发方案（v1.0 审核稿）

> 状态：**待审核**。审核通过后按此文档开发，产出目录：`android_app/`

## 一、已确认的决策

| 决策项 | 结论 |
|---|---|
| 技术栈 | **Kotlin + Jetpack Compose**（Material 3），单 Activity + Compose Navigation |
| 网络安全 | 开发期**放行明文 HTTP**（networkSecurityConfig 白名单），上线前切 HTTPS 后移除 |
| 功能范围 | **全功能对齐网页版**：登录注册、会话/好友/申请、实时聊天、已读、撤回、正在输入、在线状态、资料编辑 |
| 构建方式 | 生成完整 Gradle 项目，用户用 **Android Studio** 打开构建 APK |
| 后端改动 | **零改动**。完全复用现有 HTTP `/api/v1` + WebSocket 协议（见 docs/PROTOCOL.md） |

## 二、技术选型

| 层 | 选型 | 说明 |
|---|---|---|
| 语言/SDK | Kotlin 2.x，minSdk 26（Android 8.0），targetSdk 35 | 覆盖 98%+ 在用设备 |
| UI | Jetpack Compose + Material 3 | 主题色/圆角/气泡严格对齐网页版 styles.css |
| 网络 | Retrofit + OkHttp + kotlinx.serialization | REST；WS 用 OkHttp 原生 WebSocket |
| 会话存储 | DataStore Preferences | 存 access/refresh/用户信息（对应网页的 sessionStorage） |
| 401 处理 | OkHttp Authenticator | refresh 续期后自动重放（对齐网页逻辑） |
| 依赖注入 | 手动 AppContainer | 小项目不引 Hilt，减少构建问题 |
| 本地数据库 | v1 不引入 Room | 消息进内存 + 分页拉取，行为与网页版一致；v1.2 离线缓存时再上 |

### 明文 HTTP 放行（仅开发期）

`res/xml/network_security_config.xml` 只放行两个地址，不做全局明文：

- `www.liuzhidu.site`
- `101.43.6.205`（IP 直连调试用）

切 HTTPS 时删掉此文件即可，代码零改动（BASE_URL 从 `http` 换 `https`）。

## 三、服务器对接

| 项 | 值 |
|---|---|
| REST 基址 | `http://www.liuzhidu.site/chat/api` → 后端 `/api`（Nginx 剥 `/chat` 前缀） |
| WebSocket | `ws://www.liuzhidu.site/chat/ws?token=...` |
| 认证 | Header `Authorization: Bearer <access>`；过期用 refresh 换新 |
| 心跳/重连 | 25s 心跳、指数退避重连（对齐网页版 ws.js） |
| 好友申请 | 无推送通道，**20s 轮询** + 切到申请页时主动拉取（对齐网页版） |
| 雪花 ID | 全部按**字符串**解析（64 位超 JS/Java Long 安全展示范围的问题，统一 String 处理） |

## 四、页面与 UI（视觉对齐网页版）

配色直接搬 `web/src/styles.css` 的变量：

```
品牌蓝   #2F6BFF   背景   #F5F6F8   卡片   #FFFFFF
分割线   #E5E7EB   文字   #1F2329   次要   #8A9099
我的气泡 #2F6BFF（白字）  对方气泡 #FFFFFF（描边）
成功     #12B76A   危险   #E24B4A
```

页面清单（手机端布局按 App 习惯，视觉风格与网页一致）：

| 页面 | 对应网页 | 说明 |
|---|---|---|
| 登录/注册 | LoginView.vue | 底部可切换，样式同网页卡片 |
| 主页（底部导航 3 tab） | SideBar.vue | **会话 / 好友 / 申请**，带未读角标 |
| 聊天页 | ChatPanel.vue | 全屏 push：顶栏头像+昵称+在线+正在输入；消息列表（日期分割、左右气泡、时间、已读 ✓、发送中/失败重发、长按撤回）；底部输入框+发送 |
| 资料编辑 | ProfileDialog.vue | 弹层：头像首字母、昵称、签名 |

> 差异说明：网页版是「左栏三页签」，手机屏放不下，按主流 IM 惯例改为**底部导航**；聊天窗口从列表页 push 进入，带返回。这是唯一布局差异，其余视觉（颜色/圆角/气泡/字号）保持一致。

## 五、项目结构

```
android_app/
  settings.gradle.kts
  build.gradle.kts
  gradle/ + gradlew            # Gradle wrapper（可命令行构建）
  app/
    build.gradle.kts
    src/main/
      AndroidManifest.xml      # INTERNET / 网络状态权限
      res/xml/network_security_config.xml
      res/...                  # 图标、主题
      java/com/liuzhidu/andyouchat/
        MainActivity.kt        # 单 Activity
        AndYouApp.kt           # Application + AppContainer（手动 DI）
        core/
          Session.kt           # token/用户内存态 + DataStore 持久化
          Api.kt               # Retrofit 接口定义（auth/users/friends/conversations/messages）
          WsClient.kt          # OkHttp WS：连接、心跳、退避重连、事件分发
          Protocol.kt          # WS 事件模型（对齐 docs/PROTOCOL.md）
        ui/
          theme/               # Color/Type/Theme（变量对齐网页）
          nav/                 # 导航图
          login/               # 登录注册
          home/                # 三 tab：conversations/friends/requests
          chat/                # 聊天页（消息 VM + 分页 + 乐观发送）
          profile/             # 资料编辑
        data/                  # Repository：封装 REST/WS，VM 只面对它
```

## 六、开发阶段（每阶段可独立验收）

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| 1 骨架 | Gradle 项目 + 主题 + 导航 + 明文放行 | Android Studio 打开能编译，显示空壳页 |
| 2 网络层 | Retrofit 全接口 + DataStore 会话 + 401 刷新重放 | 登录接口真实返回 token |
| 3 登录注册 | 登录/注册页对接 | 真机注册新账号成功 |
| 4 主页三 tab | 会话/好友/申请列表 + 20s 轮询 + 搜索加好友 | 双端（网页+App）互加好友可见 |
| 5 聊天页 | REST 历史分页 + WS 实时收发 + 乐观发送/重发 | App↔网页 互发消息实时到达 |
| 6 实时细节 | 已读回执、撤回、正在输入、在线状态、未读角标 | 与网页版行为逐项对齐 |
| 7 联调打磨 | 断网重连、后台切换、雪花 ID 字符串、错误提示中文化 | 弱网下不崩、重连自动恢复 |
| 8 出包 | 签名 debug APK + 使用说明 | 可安装可登录可聊天 |

## 七、需要你准备的环境

1. **Android Studio**（最新稳定版，自带 JDK 17 与 SDK 管理器）：https://developer.android.com/studio ，安装时默认勾选 Android SDK
2. 首次打开项目时让它自动下载 Gradle 与依赖（约 10–20 分钟，一次性）
3. 真机调试：手机开启「开发者选项 → USB 调试」，数据线连接；或用 Studio 内置模拟器
4. 不需要改后端、不需要动服务器

## 八、审核时请确认 4 个小项

1. **包名**：`com.liuzhidu.andyouchat`，可以吗？
2. **App 名称/图标**：名称 `AndYouChat`，图标先用默认占位（后续可换成仙逆风格）
3. **底部导航**：手机端用底部 3 tab 替代网页左栏，视觉风格一致 —— 接受吗？
4. **默认服务器**：`http://www.liuzhidu.site`（写死为默认值，登录页长按 logo 可临时改地址调试）—— 可以吗？

> 以上任何一项有异议，直接批注；全部确认后我从阶段 1 开始动工。
