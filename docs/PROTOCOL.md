# 接口与实时协议

Android 客户端按本文档实现即可，字段名与后端严格一致。

- REST 前缀：`/api/v1`
- WebSocket：`/ws?token=<access_token>`
- 认证头：`Authorization: Bearer <access_token>`
- 错误：非 2xx 时返回 `{"detail": "中文错误说明"}`，客户端直接展示 `detail`
- `detail` **永远是字符串**（含 422 校验错误，例如 `{"detail": "用户名至少需要 3 个字符"}`），不会返回数组，客户端无需解析 `loc/msg`
- 所有时间字段为 **毫秒时间戳（int）**，UTC

## 1. 认证

| 方法 | 路径 | 入参 | 返回 |
|---|---|---|---|
| POST | `/auth/register` | `{username, password, nickname?}` | `TokenOut` |
| POST | `/auth/login` | `{username, password}` | `TokenOut` |
| POST | `/auth/refresh` | `{refresh_token}` | `TokenOut` |
| GET | `/auth/me` | - | `User` |

`TokenOut`：`{access_token, refresh_token, token_type, expires_in, user}`

注册约束：`username` 3–32 位字母/数字/下划线且唯一；`password` 6–64 位。
错误码：409 用户名占用、401 账号或密码错误。

## 2. 用户

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/users/search?q=` | 搜索用户，返回 `User[] + is_friend + request_pending`，自动排除自己 |
| PATCH | `/users/me` | `{nickname?, avatar_url?, sign?}` |
| GET | `/users/{user_id}` | 用户资料 |

```json
// User
{ "id": 374534240328486912, "username": "alice", "nickname": "爱丽丝",
  "avatar_url": null, "sign": null, "online": false }
```

> `id` 是 19 位雪花 ID，Kotlin 必须用 `Long`，不能用 `Int`；JSON 解析别用 Double。

## 3. 好友

| 方法 | 路径 | 入参 | 说明 |
|---|---|---|---|
| GET | `/friends` | - | 好友列表，含 `remark`、`conversation_id`（未建会话为 null） |
| GET | `/friends/requests` | - | 收到且待处理的申请 |
| POST | `/friends/requests` | `{to_user_id, message?}` | 发起申请；对方已先申请则直接互加，返回 `status=accepted` |
| POST | `/friends/requests/{id}/respond` | `{accept: bool}` | 同意/拒绝 |

错误：400 加自己、404 用户不存在、409 已是好友或申请已处理。

## 4. 会话

| 方法 | 路径 | 入参 | 说明 |
|---|---|---|---|
| GET | `/conversations` | - | 会话列表，按「置顶优先 + 最后消息时间倒序」 |
| POST | `/conversations/single` | `{peer_id}` | 打开/创建单聊，需已是好友，返回会话详情 |
| GET | `/conversations/{id}` | - | 会话详情 |
| POST | `/conversations/{id}/read` | `{conversation_id, seq}` | 标记已读到某 seq（HTTP 兜底，推荐用 WS） |

```json
// Conversation
{ "id": 37453..., "type": "single", "title": "bob", "peer": {User},
  "last_message": {Message} | null, "unread": 2, "last_read_seq": 0,
  "pinned": false, "muted": false, "updated_at": 1730000000000, "peer_online": true }
```

## 5. 消息

| 方法 | 路径 | 入参 | 说明 |
|---|---|---|---|
| GET | `/conversations/{id}/messages` | `before_seq?` / `after_seq?` / `limit(1-100, 默认30)` | 分页与增量 |
| POST | `/messages` | `SendMessageIn` | 发送（HTTP 兜底，优先 WS） |
| POST | `/messages/{id}/recall` | - | 2 分钟内撤回自己的消息 |

`SendMessageIn`：`{conversation_id, client_msg_id(8-64), msg_type: "text"|"image", content, extra?}`
返回：`{message: Message, duplicated: bool}`

```json
// Message
{ "id": 3745..., "conversation_id": 3745..., "seq": 12, "sender_id": 3745...,
  "msg_type": "text", "content": "你好", "extra": null,
  "client_msg_id": "a1b2c3d4", "revoked": false, "created_at": 1730000000000 }
```

分页语义：
- 首屏不带参数 → 返回最新 `limit` 条（`items` 已按 seq 升序），`has_more` 表示还能往前翻
- 向上翻页 → 传 `before_seq = items[0].seq`
- 断线补拉 → 传 `after_seq = 本地最大 seq`

## 6. WebSocket

### 连接

```
ws://host/ws?token=<access_token>
```

鉴权失败服务端以 `4401` 关闭，客户端应清 token 并跳登录页。

### 帧格式

```json
{ "type": "msg.send", "request_id": "可选，用于请求-响应配对", "data": { } }
```

### 客户端 → 服务端

| type | data | 说明 |
|---|---|---|
| `ping` | `{}` | 心跳，建议 25s 一次 |
| `msg.send` | `{conversation_id, client_msg_id, msg_type, content, extra?}` | 发送消息 |
| `msg.read` | `{conversation_id, seq}` | 标记已读 |
| `typing` | `{conversation_id}` | 正在输入，节流 ≥2s |

### 服务端 → 客户端

| type | data | 说明 |
|---|---|---|
| `pong` | `{user_id, online?}` | 连接成功与心跳响应 |
| `msg.ack` | `{message, duplicated}` | 发送成功回执（落到本地即变「已发送」） |
| `msg.new` | `{message}` | 收到新消息（**不含自己发的**，自己的走 ack） |
| `msg.read` | `{conversation_id, user_id, seq}` | 已读回执，`seq` 是对方读到的位置 |
| `msg.recalled` | `{message}` | 消息被撤回 |
| `typing` | `{conversation_id, user_id}` | 对方正在输入 |
| `presence` | `{user_id, online}` | 好友上/下线 |
| `error` | `{code, message}` | `forbidden` / `bad_request` / `unknown_type` |

### 客户端实现要点（Android）

1. **乐观发送**：本地先插一条 `seq = -1`、状态 `SENDING` 的消息，收到 `msg.ack` 后按 `client_msg_id` 替换成服务端消息（含真实 `seq`、`id`）。
2. **去重**：以 `id` 为主键入库，以 `client_msg_id` 匹配临时消息。
3. **重连**：`onClose` 后指数退避（1s→1.6^n，上限 15s），重连成功先发 `pong` 确认，再对当前会话 `after_seq = 本地最大 seq` 补拉，最后刷新会话列表。
4. **已读**：进入会话或收到 `msg.new` 且页面可见时，发 `msg.read`；对方发来 `msg.read` 时把 `seq <= 回执seq` 的己方消息标为「已读」。
5. **心跳**：25s `ping`，60s 内无任何帧视为断线，主动重连。
6. **在线状态**：`presence` 只覆盖好友；App 启动时可先用会话列表的 `peer_online` 做初值。
7. **好友申请无推送**：协议目前只覆盖消息类事件，对方发来好友申请不会实时通知。Web 端用 20s 轮询 `GET /friends/requests` + 切换面板时刷新兜底；App 端同样建议轮询，或后续在协议中新增 `friend.request` 事件。
