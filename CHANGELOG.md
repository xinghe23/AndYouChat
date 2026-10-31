# 更新记录

## v1.0.0 — 2026-10-31

首个可用版本。账号、好友、单聊、实时消息完整闭环，Web 端已在云服务器（www.liuzhidu.site/chat/）稳定运行。

### 新功能

- **账号体系**：用户名 + 密码注册 / 登录，bcrypt 哈希，JWT（access 7 天 / refresh 30 天），昵称与签名修改
- **好友关系**：用户搜索、发起申请、同意 / 拒绝、好友列表；双向申请自动成好友，重复申请幂等
- **单聊会话**：会话唯一去重（A↔B 仅一个）、会话列表、未读计数、已读游标
- **消息**：文本消息、会话内 seq 单调自增、`client_msg_id` 幂等、历史分页、`after_seq` 增量补拉、2 分钟内撤回
- **实时通道**：WebSocket 收发、ack 回执、已读回执、正在输入、在线状态、25s 心跳 + 指数退避重连、Redis Pub/Sub 跨进程广播
- **Web 客户端**：Vue 3 + Vite 8，登录注册、三页签侧栏、聊天气泡与投递状态、乐观发送与失败重发、消息撤回、资料编辑
- **全端响应式**：≥1025px 双栏（侧栏 300px）、769–1024px 收窄双栏（260px）、≤768px 单栏切换（列表 ↔ 聊天，带「‹」返回）
- **调试台**：`static/chat.html` 单文件客户端，双标签页登录两个账号互测
- **部署工具链**：`deploy/install.sh` 一键部署（端口自动避让、随机密码生成、容器健康等待、systemd 装配、健康检查）、`pack.sh` 打包自检、`schema.sql` 建表脚本、Nginx 子目录片段

### 修复

- 容器 bind mount 目录被宿主 `chown` 导致 MySQL 报 `OS error 13 (EACCES)`、建表失败
- Redis healthcheck 因未向容器传 `REDIS_PASSWORD` 永远停在 `health: starting`
- `--reset` 重置时丢失 `MYSQL_HOST_PORT`，与宝塔 MySQL 反复抢占 3306
- Vite 8 默认把 `@media (max-width:768px)` 压成 `@media (width<=768px)`，旧内核整段忽略响应式规则（已固定 `cssTarget`）
- 雪花 ID 超出 JS 安全整数范围导致精度丢失（前端统一字符串化）
- 子路径部署时接口前缀拼成 `/chat/api/api/...` 全部 404
- `HTTP_PROXY` 劫持 `127.0.0.1` 导致本地探测失败

### 测试

- pytest 41 项通过
- 冒烟脚本 16/16
- 浏览器 e2e 15/15，60s 心跳稳定性采样通过

### 已知限制

- 图片 / 语音未接对象存储；无离线推送；好友申请靠轮询；无群聊 UI；建表用 `create_all` 未接 Alembic
