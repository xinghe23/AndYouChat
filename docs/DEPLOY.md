# 云服务器部署指南

目标：把 AndYouChat 部署到一台云服务器上，通过 `https://你的域名` 访问，支持 WebSocket 实时消息、MySQL 持久化、Redis 在线状态与跨进程投递。

部署形态：

```
浏览器 / App
   │ HTTPS 443
   ▼
Nginx（宝塔管理，负责证书、静态文件、反代）
   ├── /chat/   → 直接读 /www/server/chat_server/chat   （Vue 构建产物）
   ├── /ws      → 127.0.0.1:8200  升级为 WebSocket，超时 3600s
   ├── /api/    → 127.0.0.1:8200
   └── /health  → 127.0.0.1:8200
                    FastAPI（systemd 托管，uvicorn）
                       ├── MySQL 8   127.0.0.1:3306（Docker）
                       └── Redis 7   127.0.0.1:6379（Docker）
```

> 前端在 `/chat/` 子目录、接口在同域的 `/api/`，**属于同源请求，不涉及 CORS**，登录页的「服务器地址」留空即可。

> 全程假设：OpenCloudOS / CentOS 系，宝塔面板已装好 Nginx，域名为 `chat.example.com`（**请全局替换成你自己的域名**），部署目录 `/www/server/chat_server`。

---

## 极速版（一条命令，推荐）

前提：Docker 已装（没装见 1.4 节），代码已解压到 `/www/server/chat_server`。

```bash
cd /www/server/chat_server
bash deploy/install.sh
```

**首次部署，或之前失败过想彻底重来**（会清空数据库并重新生成所有密码）：

```bash
bash deploy/install.sh --reset
```

脚本自己完成全部 7 步，**不需要手工 `cp`/`vim` 任何配置文件，也不需要填密码**：

| 步骤 | 脚本做的事 |
|---|---|
| 0 | 检查 docker / 目录 / 端口占用 |
| 1 | 找 Python ≥ 3.10，找不到就 `dnf install python3.12` |
| 2 | 生成 `deploy/.env`（24 位随机密码）→ 起 MySQL/Redis → 轮询等 `healthy` |
| 3 | 建 `.venv` |
| 4 | 装依赖并验证可导入 |
| 5 | 从 `deploy/.env` 读密码（自动 URL 编码）→ 写后端 `.env` |
| 6 | 生成 systemd 服务（带 `StartLimitBurst=5`）→ `reset-failed` → 启动 |
| 7 | 轮询 `/health`，失败时自动诊断并打印修复命令 |

成功时结尾：

```
    [OK] MySQL 连通
    [OK] Redis 连通
============================================
  部署成功，后端已在 127.0.0.1:8200 运行
============================================
```

`--reset` 具体做四件事：`docker compose down` → 删 `deploy/data` → 删 `deploy/.env` 并重新生成密码 → 重新 `up -d`。**仅在没有业务数据时使用**。

其他安全设计：重跑时沿用已有 `JWT_SECRET`（不踢在线用户）；已有 `.env` 会备份成 `.env.bak.时间戳`；宿主端口被占（如宝塔自带 MySQL）会明确提示，可在 `deploy/.env` 加 `MYSQL_HOST_PORT=3307` 换映射端口。

剩下只有 Nginx 反代与 HTTPS，见第 8 节。

---

## 0. 上线前准备（缺一不可）

| 项目 | 要求 | 说明 |
|---|---|---|
| 服务器规格 | 2 核 4G 起 | MySQL 8 单独就要 400M+，2G 机器必须加 swap（见 1.3） |
| 系统盘 | 40G 起 | 消息数据 + Docker 镜像 + 日志 |
| 域名 + 备案 | 国内服务器**必须**完成 ICP 备案 | 没备案 80/443 会被拦截，走香港/海外服务器可跳过 |
| 域名解析 | A 记录指向服务器公网 IP | `ping chat.example.com` 能看到你的 IP |
| 安全组 | 放行 **80、443**，22 端口限自己 IP | **不要**放行 3306 / 6379 / 8200，这三个只给本机用 |
| 宝塔面板 | 已安装 Nginx | MySQL/Redis 本次用 Docker，不装宝塔版本，避免版本冲突 |

---

## 1. 系统初始化

用 root 或 `sudo -i` 执行。

### 1.1 时区与基础工具

```bash
timedatectl set-timezone Asia/Shanghai
timedatectl                     # 确认 Time zone: Asia/Shanghai

dnf -y update
dnf -y install git curl wget vim tar unzip
```

### 1.2 检查 Python 版本（关键）

项目用了 `str | None` 这类 3.10+ 语法，**Python 必须 ≥ 3.10**，推荐 3.12。

```bash
python3 -V                     # 多半是 3.6 / 3.9，不能直接用
dnf list available | grep -E "^python3\.(1[0-3])"    # 看源里有哪些
```

有输出就装：

```bash
dnf -y install python3.12 python3.12-devel gcc gcc-c++ make
python3.12 -V                  # 期望 Python 3.12.x
```

源里没有（输出为空）就走宝塔：**软件商店 → Python 项目管理器 → 安装 3.12**，装完在命令行验证 `ls /www/server/pyporject_evn/` 找到对应解释器路径，下文 `python3.12` 全部换成该路径。

### 1.3 加 swap（内存 ≤ 2G 必做）

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h                        # 确认 Swap 有 2.0Gi
```

### 1.4 装 Docker（跑 MySQL 与 Redis）

```bash
dnf -y install dnf-plugins-core
dnf config-manager --add-repo https://mirrors.cloud.tencent.com/docker-ce/linux/centos/docker-ce.repo
dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable --now docker
docker --version                # 期望 Docker version 2x.x
docker compose version          # 期望 Docker Compose version v2.x
```

> 镜像拉不动时可配加速器：`/etc/docker/daemon.json` 写入 `{"registry-mirrors":["https://mirror.ccs.tencentyun.com"]}`，再 `systemctl restart docker`。

✅ **检查点**：`python3.12 -V` 输出 3.12.x，`docker compose version` 正常，`free -h` 有 swap。

---

## 2. 拉取代码

**目录约定**：后端部署在 `/www/server/chat_server`，前端产物在同目录下的 `chat/`，最终由 Nginx 走 `/chat/` 对外提供。

> ⚠️ `/www/server` 是宝塔的**软件安装目录**（同级有 `nginx`、`mysql`、`panel`、`pyporject_evn` 等）。**只操作 `chat_server` 这一个子目录**，别误删或改权限到其它目录，否则面板和网站会一起挂。宝塔的「网站备份」不会覆盖这里，所以数据库备份要自己配（见 10.4）。

```bash
mkdir -p /www/server && cd /www/server
git clone https://github.com/xinghe23/AndYouChat.git chat_server
cd chat_server
git log -1 --oneline            # 确认拿到最新提交
ls chat/index.html              # 前端构建产物在仓库里，应当存在
```

私有仓库用 deploy key：

```bash
ssh-keygen -t ed25519 -C "andyouchat-deploy" -f ~/.ssh/andyou_deploy -N ""
cat ~/.ssh/andyou_deploy.pub     # 复制到 GitHub 仓库 Settings → Deploy keys（只读）
```

然后 `GIT_SSH_COMMAND="ssh -i ~/.ssh/andyou_deploy" git clone git@github.com:xinghe23/AndYouChat.git chat_server`。

> 不想用 git，见下面 2.1。

### 2.1 用压缩包上传（不用 git 时）

项目根执行一条命令就能生成干净的部署包（脚本会自动排除不该传的东西）：

```bash
bash deploy/pack.sh            # 生成 andyouchat-deploy.tar.gz，约 200KB / 92 个文件
```

然后把包上传到服务器解压：

```bash
cd /www/server && mkdir -p chat_server && cd chat_server
tar -xzf ~/andyouchat-deploy.tar.gz
ls app/main.py chat/index.html .env.example      # 三个都在说明解压正常
```

也可以直接用宝塔「文件」把 `andyouchat-deploy.tar.gz` 传上去再右键解压。

**要传 / 不用传的完整清单：**

| 必须传 | 说明 |
|---|---|
| `app/` | 后端源码（唯一真正的程序） |
| `requirements.txt` | Python 依赖清单 |
| `chat/` | 前端构建产物，Nginx 直接读盘 |
| `deploy/` | systemd、Nginx、compose、备份脚本模板 |
| `.env.example` | 服务器上据此写 `.env` |
| `docker-compose.yml` + `deploy/docker-compose.prod.yml` | 起 MySQL / Redis |
| `web/`（不含 `node_modules`） | 以后要改前端时用；不打算在服务器构建也可以不传 |
| `static/chat.html` | 网页调试台，排障时很方便；不想暴露可以删 |
| `docs/`、`tests/`、`scripts/` | 可选。`scripts/smoke_test.py` 上线后用得上 |

| 绝对不要传 | 原因 |
|---|---|
| `.venv/` | Windows 的虚拟环境在 Linux 下完全不能用，而且几百 MB；服务器上重建（第 5 节）|
| `web/node_modules/` | 几万个文件、平台相关，解压慢且没用；要构建就 `npm ci` |
| `.env` | 本地这份是 SQLite + fakeredis 配置。传上去会覆盖生产配置，**服务会静默连本地 SQLite、发消息对方收不到** |
| `andyou.db`、`andyou.db-shm/-wal` | 本地测试数据，传上去会污染生产库 |
| `server.log` | 只是一份日志 |
| `__pycache__/`、`*.pyc` | 字节码，版本不一致还会报怪错 |
| `.pytest_cache/`、`.idea/`、`.vscode/` | 开发工具产物 |
| `.workbuddy/` | 本地项目记忆，跟运行无关 |
| `.git/` | 用压缩包发布就不需要，省体积 |

一句话判断标准：**除了 `app/`、`requirements.txt`、`chat/`、`deploy/`、`.env.example` 和两个 compose 文件，其余都是"可以不传、传了也别传 .env 和 .venv"**。

> **如果项目之前部署在别的路径**（比如 `/www/wwwroot/andyouchat`）现在要挪到 `/www/server/chat_server`，光 `mv` 不够：`.venv/bin/uvicorn` 等脚本的 shebang 里写死了旧绝对路径，移动后 systemd 会报 `No such file or directory`。正确做法：
>
> ```bash
> mv /www/wwwroot/andyouchat /www/server/chat_server
> cd /www/server/chat_server && rm -rf .venv
> python3.12 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
> chown -R www:www /www/server/chat_server
> # 再改 service 与 nginx 里的路径，然后 daemon-reload / nginx -s reload
> ```

---

## 3. 启动 MySQL 与 Redis

仓库里的 `deploy/docker-compose.prod.yml` 已经把两件事做好了：只监听 `127.0.0.1`（外网连不到）、数据落本地目录、Redis 设密码并开 AOF。

> 镜像用 `mysql:8.0` 而不是 8.4：8.4 默认关闭 `mysql_native_password`，aiomysql 走 `caching_sha2_password` 需要额外装 `cryptography`，8.0 + native 密码是最省心且已验证的组合。想用 8.4 的话，见 11 节最后一条。
> Redis 里的 `conv:{id}:seq` 丢了不会丢数据——服务会用 `conversations.seq_counter` 兜底恢复序号，只是可能短暂重复，客户端按 `client_msg_id` 幂等。

### 3.1 准备密码文件

```bash
cd /www/server/chat_server/deploy
cp .env.db.example .env

# 生成两个强密码，填进 .env
python3 -c "import secrets;print('MYSQL_PASSWORD=' + secrets.token_urlsafe(24))"
python3 -c "import secrets;print('REDIS_PASSWORD=' + secrets.token_urlsafe(24))"
vim .env                         # 把上面两行输出替换进去
chmod 600 .env
```

`.env` 内容形如：

```ini
MYSQL_ROOT_PASSWORD=<root 强密码>
MYSQL_DATABASE=andyouchat
MYSQL_USER=andyou
MYSQL_PASSWORD=<业务库强密码>
REDIS_PASSWORD=<redis 强密码>
```

### 3.2 起容器

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml ps        # 两个都是 running/healthy
docker compose -f docker-compose.prod.yml logs -f mysql | tail -20
```

容器 `healthy` 后验证：

```bash
# MySQL（在容器里执行 mysql 客户端，避免暴露端口）
docker exec -it andyou-mysql mysql -uandyou -p -e "SHOW DATABASES;" | grep andyouchat

# Redis
docker exec -it andyou-redis redis-cli -a "$(grep REDIS_PASSWORD .env | cut -d= -f2)" ping
# 期望 PONG
```

⚠️ 不要图省事把 `3306:3306` 写成 `0.0.0.0`，MySQL 暴露公网基本等于送数据；本配置是 `127.0.0.1:3306:3306`。

✅ **检查点**：`docker compose ps` 两项 healthy，MySQL 里能看到 `andyouchat` 库。

---

## 4. 配置后端 .env

```bash
cd /www/server/chat_server
cp .env.example .env

# 生成 JWT 密钥（务必换掉默认值，否则任何人都能伪造 token）
python3 -c "import secrets;print(secrets.token_urlsafe(48))"
```

把 `.env` 改成下面这份（值按你的实际密码替换）：

```ini
APP_NAME=AndYouChat
ENV=production

# --- 数据库：指向 Docker 里的 MySQL ---
DATABASE_URL=mysql+aiomysql://andyou:<MYSQL_PASSWORD>@127.0.0.1:3306/andyouchat?charset=utf8mb4

# --- Redis：必须关掉 fakeredis，否则多进程投递失效 ---
REDIS_URL=redis://:<REDIS_PASSWORD>@127.0.0.1:6379/0
USE_FAKEREDIS=false

# --- 安全 ---
JWT_SECRET=<上一步生成的长随机串>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL=604800
REFRESH_TOKEN_TTL=2592000
BCRYPT_ROUNDS=12

# --- 站点 ---
CORS_ORIGINS=https://chat.example.com
SNOWFLAKE_NODE_ID=1
MESSAGE_RECALL_SECONDS=120
```

要点：

- `CORS_ORIGINS` 写实际域名；前后端同域时不会触发跨域，写上只是保险。
- `SNOWFLAKE_NODE_ID` 单机保持 `1`；将来多台机器部署必须各不相同。
- 密码里若含 `@ : / %` 等字符，必须做 URL 编码（`%40` 之类），否则连接串会被解析错。

```bash
chmod 600 .env
```

### 4.1 数据库在哪里建表

**不需要手工执行任何 SQL**。服务启动时 `app/main.py` 的 lifespan 会调用 `init_db()`，对 `Base.metadata` 执行 `create_all`，缺失的表自动创建（已有表不动，不会清数据）。

- 建表逻辑：`app/db/session.py` → `init_db()`
- 表结构定义：`app/models/*.py`（6 张表：`users`、`friendships`、`friend_requests`、`conversations`、`conversation_members`、`messages`）
- 导出的建表语句：`deploy/schema.sql`（MySQL 8.0 方言，仅供查阅或手工建库时使用）

`create_all` 的边界要知道：它**只建缺失的表**，不会给已存在的表加字段、改类型、加索引。后期改模型后需要自己写 `ALTER TABLE`，或引入 Alembic 做迁移（当前项目未启用）。

验证：

```bash
docker exec -it andyou-mysql mysql -uandyou -p andyouchat -e "SHOW TABLES;"
# 期望 6 行
```

### 4.2 修改数据库 / Redis 密码

密码在**两个文件**里各有一份，**必须同时改、保持一致**，否则后端连不上：

| 文件 | 作用 | 相关项 |
|---|---|---|
| `deploy/.env` | 启动 MySQL / Redis 容器 | `MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`、`REDIS_PASSWORD` |
| `/www/server/chat_server/.env` | 后端连接串 | `DATABASE_URL`、`REDIS_URL` |

**A. 改 MySQL 密码**

容器**首次初始化数据目录之后**，`MYSQL_PASSWORD` 环境变量就失效了（MySQL 只在数据目录为空时读它）。所以要分两种情况：

```bash
# 情况一：容器还没起过 / 数据可以丢
cd /www/server/chat_server/deploy
vim .env                                  # 改 MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD
docker compose -f docker-compose.prod.yml down -v   # -v 会删数据卷，谨慎
docker compose -f docker-compose.prod.yml --env-file .env up -d

# 情况二：库里已有数据（正常情况）—— 必须进容器改
docker exec -it andyou-mysql mysql -uroot -p
```

```sql
-- 在 mysql> 里执行，把 <新密码> 换掉
ALTER USER 'andyou'@'%' IDENTIFIED WITH mysql_native_password BY '<新密码>';
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '<新root密码>';
FLUSH PRIVILEGES;
EXIT;
```

然后同步两个文件：

```bash
# 1) 容器侧（让下次重建容器时用的还是新密码）
cd /www/server/chat_server/deploy && vim .env
# 2) 后端侧
cd /www/server/chat_server && vim .env
#    DATABASE_URL=mysql+aiomysql://andyou:<新密码>@127.0.0.1:3306/andyouchat?charset=utf8mb4
```

**B. 改 Redis 密码**

Redis 的密码是**启动参数**（compose 里的 `--requirepass`），不存在"初始化后不生效"的问题，改完重启即可：

```bash
cd /www/server/chat_server/deploy
vim .env                                  # 改 REDIS_PASSWORD
docker compose -f docker-compose.prod.yml --env-file .env up -d redis   # 会重建容器

cd /www/server/chat_server && vim .env
#    REDIS_URL=redis://:<新密码>@127.0.0.1:6379/0
```

**C. 两处都改完后重启并验收**

```bash
systemctl restart andyouchat
curl -s http://127.0.0.1:8200/health
# 必须 db:true redis:true，任一为 false 就是密码/连接串不一致
tail -30 /var/log/messages | grep andyouchat   # 或 journalctl -u andyouchat -n 30
```

三个坑：

1. **密码含 `@ : / # %` 必须 URL 编码**（`@`→`%40`）。最省事的做法是用 `python3 -c "import secrets;print(secrets.token_urlsafe(24))"` 生成，产物只含 `A-Z a-z 0-9 - _`，放进连接串不需要编码。
2. **改了 `deploy/.env` 但没 `up -d`**：配置只写在文件里，容器还在用旧密码跑。改完必须让容器重建。
3. **root 密码也忘了**：`docker exec` 进不去时，临时在 compose 里加 `--skip-grant-tables` 重启容器改密码，改完立刻去掉（这期间任何人可无密码登录，务必先停 Nginx）。

---

## 5. 装 Python 依赖

```bash
cd /www/server/chat_server
python3.12 -m venv .venv
./.venv/bin/pip install -U pip

# 只装运行必需（不装 pytest / fakeredis 这些开发依赖）
./.venv/bin/pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" \
  "sqlalchemy[asyncio]>=2.0.30" "pydantic>=2.7.0" "pydantic-settings>=2.3.0" \
  PyJWT bcrypt "redis>=5.0.0" aiomysql python-dotenv

./.venv/bin/python -c "import fastapi, sqlalchemy, aiomysql, redis; print('deps ok')"
```

---

## 6. 构建前端（输出到 `chat/` 目录）

前端要挂在 `https://你的域名/chat/`，**必须用 `build:chat` 构建**——它把 Vite 的 `base` 设成 `/chat/`，产物里的 JS/CSS 引用才是 `/chat/assets/xxx.js`。用普通 `npm run build` 构建出来的是 `/static/app/` 前缀，放到 `/chat/` 下会白屏 + 控制台一堆 404。

**推荐在本地构建**（Windows 上你已经装好 Node，服务器省内存）：

```bash
# 本地，项目根目录
cd web
npm install
npm run build:chat     # 产物直接输出到 ../chat/
cd ..
git add chat
git commit -m "build: 发布前端到 /chat/"
git push
```

服务器上 `git pull` 即可拿到新产物，Nginx 直接读盘，**不用重启后端**。

也可以直接在服务器构建（需 Node 20+）：

```bash
curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
dnf -y install nodejs
node -v                # 期望 v20.x

cd /www/server/chat_server/web
npm ci && npm run build:chat
```

构建完确认（两个文件都在才算对）：

```bash
ls -l /www/server/chat_server/chat/index.html
grep -o 'src="[^"]*"' /www/server/chat_server/chat/index.html
# 期望看到 src="/chat/assets/index-xxxxxxxx.js"，如果出现 /static/app/ 说明用错了构建命令
```

> `chat/` 目录名不是随便起的，它必须和 Nginx 的 `location /chat/`、Vite 的 `base` 三者一致。想换成 `/app/` 之类的路径，要同时改 `web/.env.chat` 的 `VITE_BASE` 与 `VITE_OUT_DIR`、以及 Nginx 的两个 location。

---

## 7. systemd 托管后端

### 7.1 目录权限

```bash
# 只给项目目录授权，不要 chown -R /www/server（那会改掉宝塔软件目录的属主）
chown -R www:www /www/server/chat_server
mkdir -p /www/wwwlogs && chown www:www /www/wwwlogs

# Selinux 若为 Enforcing，Nginx 读该目录可能被拒（宝塔机器一般是 Disabled）
getenforce
```

> 这一步不能省：服务以 `www` 用户运行，`.env` 是 `600` 权限，属主不是 `www` 时读不到配置——轻则服务起不来（journalctl 里是权限错误），重则回落到默认的 SQLite + fakeredis，数据悄悄写进 `andyou.db` 而不是 MySQL。

> 若 `getenforce` 输出 `Enforcing` 且访问 `/chat/` 报 403，执行 `chcon -R -t httpd_sys_content_t /www/server/chat_server/chat` 或直接 `setenforce 0`（宝塔面板要求关闭 SELinux）。

### 7.2 安装服务

仓库已提供 `deploy/andyouchat.service`：

```bash
cd /www/server/chat_server
cp deploy/andyouchat.service /etc/systemd/system/andyouchat.service
systemctl daemon-reload
systemctl enable --now andyouchat
systemctl status andyouchat --no-pager
```

首次启动**保持 `--workers 1`**：建表是 `create_all`，多进程同时启动可能出现建表竞争。等表建好（见 7.3）再改多进程。

> **关于端口**：服务固定监听 `127.0.0.1:8200`，只对 Nginx 暴露，外网连不到。改端口只需动两处 —— `deploy/andyouchat.service` 的 `--port`，和 `deploy/nginx-andyouchat.conf` 里 `upstream andyouchat_backend` 的 `server` 行。**前端不用改也不用重新构建**：它请求的是同域的 `/api` 和 `/ws`，由 Nginx 转给后端，跟后端端口无关。改完记得 `systemctl daemon-reload && systemctl restart andyouchat` 和 `nginx -s reload`。

### 7.3 验证后端

```bash
curl -s http://127.0.0.1:8200/health
# 期望 {"status":"ok","db":true,"redis":true,"env":"production","online_users":0}

docker exec -it andyou-mysql mysql -uandyou -p -e "USE andyouchat; SHOW TABLES;"
# 期望 6 张表：users / friendships / friend_requests / conversations / conversation_members / messages
```

`db` 或 `redis` 为 `false` 时看日志（应用日志统一走 journald）：

```bash
journalctl -u andyouchat -n 80 --no-pager
# Nginx 层的 502/超时看这里
tail -50 /www/wwwlogs/andyouchat.error.log
```

### 7.4 开多进程（可选，验证过再改）

Redis Pub/Sub 已支持跨进程投递。表建好后改：

```bash
vim /etc/systemd/system/andyouchat.service   # --workers 1 → --workers 2
systemctl daemon-reload && systemctl restart andyouchat
```

验证方法：两个浏览器分别登录两个账号互发消息，能实时收到即说明 Pub/Sub 正常（这两个连接不一定落在同一进程）。

📌 `--workers` 别超过 `CPU 核数`，1 核机器就用 1。SQLite 模式下不允许开多进程。

---

## 8. Nginx 反向代理 + HTTPS

### 8.1 宝塔建站

宝塔 →「网站」→「添加站点」：域名 `chat.example.com`，PHP 版本选「纯静态」，不要创建数据库、不要创建 FTP。

### 8.2 申请证书

站点设置 →「SSL」→ Let's Encrypt → 勾选域名 → 申请 → **开启「强制 HTTPS」**。

### 8.3 替换配置文件

站点设置 →「配置文件」，用 `deploy/nginx-andyouchat.conf` 的内容替换（**记得改域名、证书路径和两处 `root`**）。核心是这五段：

```nginx
# 0. 后端地址：端口只写这一处，以后换端口改这里就行
upstream andyouchat_backend {
    server 127.0.0.1:8200;
}

# 1. 前端：/chat/ 直接读盘
#    ^~ 不能省：宝塔默认有 location ~ .*\.(js|css)?$ 之类的正则段，
#    正则优先级高于普通前缀，会把 /chat/assets/*.js 抢走导致全站 404
location = /chat {
    return 301 /chat/;                 # 补尾斜杠，否则相对路径以 / 为基准解析
}

location ^~ /chat/assets/ {
    root /www/server/chat_server;      # 实际目录 /www/server/chat_server/chat/assets/
    expires 365d;                      # 文件名带 hash，可长缓存
    access_log off;
}

location ^~ /chat/ {
    root /www/server/chat_server;      # 实际目录 /www/server/chat_server/chat/
    index index.html;
    try_files $uri $uri/ /chat/index.html;
    expires -1;                        # 入口 HTML 不缓存，发版后立刻生效
    access_log off;
}

# 2. WebSocket：必须带 Upgrade / Connection 头，且超时调大
location /ws {
    proxy_pass http://andyouchat_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;
}

# 3. 接口：proxy_pass 不带尾斜杠，才能保留 /api/v1/... 原始路径
location /api/ {
    proxy_pass http://andyouchat_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_redirect off;
}

# 4. 根路径直接进前端
location = / {
    return 302 /chat/;
}

# 5. 其余（/health、/docs、/static/chat.html 调试台）交给 FastAPI
location / {
    proxy_pass http://andyouchat_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_redirect off;
}
```

```bash
nginx -t && nginx -s reload
```

> 宝塔里重新申请/续签证书时可能重写 `listen 443` 与证书那几行，改完回来确认一下 `/chat/` 与 `/ws` 两段还在。另外 `listen 443 ssl http2` 在 nginx 1.25+ 会打一条 deprecated 警告，不影响使用。

⚠️ 五个最容易踩的点：

1. **`/chat/` 那段必须加 `^~`**：宝塔默认模板里带 `location ~ .*\.(js|css)?$` 这种正则 location，正则优先级高于普通前缀匹配，会把 `/chat/assets/index-xxx.js` 抢去用站点根目录找文件 → 全站白屏。加了 `^~` 前缀命中后就不再走正则。更省事的做法是把宝塔那几条正则段（js/css/图片）直接删掉。
2. **`location /ws` 必须在 `location /` 之前**，且不能省 `Upgrade`/`Connection` 头，否则 WS 握手直接 400。
3. **`/chat/` 用 `root` 不用 `alias`**，且 `try_files` 的回落目标写 URI（`/chat/index.html`）而不是文件路径。若仍报 404，用 `curl -I https://域名/chat/assets/xxx.js` 确认文件确实在该目录下。
4. **`proxy_read_timeout` 至少 300s**：前端 25s 一次心跳，超时太短会周期性断连重连。
5. **`root` 指向 `/www/server/chat_server` 而不是 `.../chat`**：URI 里的 `/chat/` 已经包含了目录名，反过来写会变成 `/chat/chat/`。

⚠️ 安全提醒：**不要把项目根目录配成整个站点的静态根**（例如写 `root /www/server/chat_server;` 配一个 `location / { try_files ... }`）。那样 `.env`（含 JWT 密钥、数据库密码）、`andyou.db`、`app/` 源码都能被直接下载。本配置里只有 `/chat/` 和 `/chat/assets/` 读盘，`/` 与 `/api/` 都走反向代理，不会泄露。

### 8.4 生产环境收敛接口文档（建议）

`/docs`、`/redoc`、`/openapi.json` 会暴露全部接口结构。单机自用可留，公网建议关掉——把 `deploy/nginx-andyouchat.conf` 末尾的注释段取消注释，改成自己的办公 IP 白名单。

---

## 9. 上线验收

逐条执行，全绿再对外发布。

```bash
# 1) 根路径应 302 跳到 /chat/
curl -sI https://chat.example.com/ | head -3

# 2) 健康检查
curl -s https://chat.example.com/health

# 3) 前端页面与资源（在项目根目录执行，方便取到 assets 文件名）
cd /www/server/chat_server
curl -so /dev/null -w "index:%{http_code}\n" https://chat.example.com/chat/
curl -so /dev/null -w "asset:%{http_code}\n" "https://chat.example.com/chat/assets/$(ls chat/assets | grep '\.js$' | head -1)"

# 4) 接口存活（未登录应 401，不是 502/404）
curl -so /dev/null -w "api:%{http_code}\n" https://chat.example.com/api/v1/auth/me
```

`index` 与 `asset` 都必须是 `200`。`asset` 若是 `404`，说明文件没进 `chat/` 目录，或 Nginx 的 `root` 写成了 `.../chat`。

浏览器实测清单：

| 检查项 | 预期 |
|---|---|
| 打开域名 | 出现登录卡片，地址栏是 `https://` 且无证书警告 |
| 注册两个账号 | 都能进入主界面，右下角显示「实时通道已连接」（绿色） |
| 加好友 → 同意 → 聊天 | 消息秒收，气泡状态从「发送中」变正常 |
| 对方打开会话 | 自己消息旁出现「已读」 |
| F12 → Network → WS | `/ws` 状态 **101**，无红色报错；等待 2 分钟不断线 |
| 刷新页面 | 保持登录态 |
| 手机 4G 访问 | 正常（排除只在本机 hosts 生效的情况） |

---

## 10. 日常运维

### 10.1 常用命令

```bash
systemctl status andyouchat            # 状态
systemctl restart andyouchat           # 重启
journalctl -u andyouchat -f            # 应用实时日志
journalctl -u andyouchat --since "10 min ago" --no-pager
tail -f /www/wwwlogs/andyouchat.error.log   # Nginx 错误日志
docker compose -f deploy/docker-compose.prod.yml ps
docker stats --no-stream               # 看内存占用
```

### 10.2 发布新版本

```bash
cd /www/server/chat_server
git pull
./.venv/bin/pip install -r requirements.txt      # 依赖有变才需要
systemctl restart andyouchat
curl -s http://127.0.0.1:8200/health             # 确认 db/redis 都 true
```

前端改动：本地 `npm run build:chat` → 提交 `chat/` → 服务器 `git pull`（**不用重启后端**，Nginx 直接读盘）。旧 assets 文件名带 hash，可以放心 `git pull` 覆盖；`index.html` 已设不缓存，用户刷新即拿到新版本。

### 10.3 回滚

```bash
git log --oneline -10
git checkout <上一个稳定的 commit 或 tag>
./.venv/bin/pip install -r requirements.txt
systemctl restart andyouchat
```

⚠️ 若该版本改过表结构（本项目目前是 `create_all`，只会新增表/字段），回滚代码后旧代码可能不认识新字段，必要时配合 10.5 的备份恢复。

### 10.4 定时备份

仓库提供 `deploy/backup.sh`：

```bash
mkdir -p /www/backup/andyouchat
cp deploy/backup.sh /www/backup/andyouchat/backup.sh
chmod +x /www/backup/andyouchat/backup.sh
/www/backup/andyouchat/backup.sh          # 先手工跑一次，确认能出 .sql.gz
```

加入 crontab（每天 03:10）：

```bash
crontab -e
10 3 * * * /www/backup/andyouchat/backup.sh >> /www/backup/andyouchat/backup.log 2>&1
```

脚本自动保留最近 14 天。**务必定期把备份拉到本地或对象存储**——备份和服务器在同一块盘上，等于没备份。

恢复：

```bash
gunzip < /www/backup/andyouchat/andyouchat-20261030-031000.sql.gz | \
  docker exec -i andyou-mysql mysql -uandyou -p andyouchat
```

### 10.5 安全加固清单

- [ ] `.env` 权限 `600`，不进 git（已在 `.gitignore`）
- [ ] `JWT_SECRET` 已换成 48 位随机串，不是示例值
- [ ] MySQL / Redis 只监听 `127.0.0.1`，安全组未放行 3306 / 6379
- [ ] 后端端口 8200 **未**在安全组/防火墙放行，只允许本机 Nginx 访问
- [ ] `ss -lntp | grep 8200` 显示的是 `127.0.0.1:8200` 而不是 `0.0.0.0:8200`
- [ ] Redis 设了 `requirepass`，容器重启后配置仍生效（写在 compose 里）
- [ ] 系统每月 `dnf -y update`，重启后确认服务自启
- [ ] 宝塔面板改过默认端口、开了面板 SSL、绑定了授权 IP
- [ ] `/docs` 已关闭或限制来源 IP
- [ ] 备份任务在跑，且验证过一次恢复

---

## 11. 常见故障排查

| 现象 | 大概率原因 | 处理 |
|---|---|---|
| 502 Bad Gateway | 后端没起 / 端口不对 | `systemctl status andyouchat`；`curl 127.0.0.1:8200/health` |
| 502 但 `curl 8200` 正常 | Nginx 里 `proxy_pass` 指向的端口和 systemd 不一致 | 改 `upstream andyouchat_backend` 的 `server` 行，`nginx -t && nginx -s reload` |
| 外网能直接打开 `http://IP:8200` | 监听成了 `0.0.0.0` | `--host` 必须是 `127.0.0.1`；安全组也别放行 8200 |
| 页面能开但白屏，控制台 404 assets | 构建时 base 不是 `/chat/`，或 Nginx `root` 指错 | 看 `chat/index.html` 里是不是 `/chat/assets/...`；`curl -I https://域名/chat/assets/xxx.js` |
| `/chat` 能开、`/chat/` 404 | 少了 `location = /chat { return 301 /chat/; }` | 补上重定向 |
| 访问 `/chat/` 返回 403 | `/www/server` 权限不足，或 SELinux 拦截 | `ls -ld /www/server` 应为 `drwxr-xr-x`；`getenforce` 若 Enforcing 见 7.1 的处理 |
| `/chat/assets/` 全 404 | `root` 写成了 `.../chat`，路径变成 `/chat/chat/` | `root` 指到项目根 `/www/server/chat_server` |
| 打开是调试台而不是 Vue 界面 | `chat/index.html` 不存在 | `npm run build:chat` 重新构建并 `git pull` |
| 登录提示「连不上服务器」 | https 页面里请求了 http（混合内容） | 登录页「服务器地址」**留空** |
| 登录 401 且密码正确 | `JWT_SECRET` 变过，旧 token 失效 | 清 sessionStorage 重新登录 |
| WS 一直连不上（400/404） | Nginx 缺 Upgrade 头，或 `/ws` 被 `location /` 吃掉 | 检查 `location /ws` 顺序与头部 |
| 每 1~2 分钟断线重连 | `proxy_read_timeout` 太短 | 调到 `3600s` 并 reload |
| 消息发出去对方收不到 | `USE_FAKEREDIS=true`（进程内假 Redis） | 改 `false` 并重启；确认 Redis 密码正确 |
| `/health` 里 `db:false` | 连接串密码错 / MySQL 未 healthy / 密码含特殊字符未编码 | 看 `journalctl`；用 `docker exec` 手工连一次 |
| 日志 `Access denied for user 'andyou'@'localhost'` | **容器数据目录是用旧密码初始化的**，`MYSQL_PASSWORD` 只在首次初始化生效 | 无数据时：`down` → `rm -rf data/mysql` → `up -d`；有数据时用 4.2 节 `ALTER USER` |
| 启动后端口被占 `address already in use`（3306） | 宿主机已有 MySQL（宝塔自带） | 停掉它，或在 `deploy/.env` 写 `MYSQL_HOST_PORT=3307` 换映射端口 |
| `systemctl` 日志刷出上千次重启 | 配置错误 + `Restart=always` 无限重试 | 已加 `StartLimitBurst=5`；重新安装 service 后最多重试 5 次即停 |
| `/health` 里 `redis:false` | Redis 密码错，或 `REDIS_URL` 少了 `:` 前缀 | 格式必须是 `redis://:<密码>@127.0.0.1:6379/0` |
| 中文变问号 | 库表字符集不是 utf8mb4 | 连接串带 `?charset=utf8mb4`；库已建错需重建 |
| 时间显示差 8 小时 | 容器/系统时区 | `timedatectl set-timezone Asia/Shanghai`，compose 里已设 `TZ` |
| `create_all` 报 table already exists | 多 worker 同时建表 | 先 `--workers 1` 启动一次，建完再改多进程 |
| 内存吃满被 OOM | MySQL 默认缓冲池过大 | compose 已设 `innodb_buffer_pool_size=256M`，按内存调 |
| 报 `cryptography is required for sha256_password` | 用了 MySQL 8.4+ 的 caching_sha2 认证 | 换回 `mysql:8.0`，或在 venv 里 `pip install cryptography` 并去掉 `--default-authentication-plugin` 参数 |

---

## 12. 验收 Checklist

- [ ] `https://域名` 正常打开，证书有效，HTTP 自动跳 HTTPS
- [ ] `https://域名/` 302 到 `/chat/`，页面是 Vue 界面而不是调试台
- [ ] `https://域名/chat/assets/xxx.js` 返回 200（不是 404）
- [ ] `curl https://域名/health` → `db:true redis:true env:production`
- [ ] 两个账号能注册、加好友、实时互发、已读、撤回
- [ ] F12 里 `/ws` 是 101，挂机 5 分钟不掉线
- [ ] `systemctl enable andyouchat` 开机自启；`reboot` 后站点自动可用
- [ ] 备份脚本跑通，`/www/backup/andyouchat` 有 `.sql.gz`
- [ ] 安全组只开 80/443/22；3306、6379 外网不可达（可用手机 4G + telnet 验证）
- [ ] `.env` 里的 `JWT_SECRET`、MySQL、Redis 密码都已替换为强随机值

---

## 附：一条命令速查

```bash
# 更新发布
cd /www/server/chat_server && git pull && systemctl restart andyouchat && sleep 2 && curl -s http://127.0.0.1:8200/health

# 看实时日志
journalctl -u andyouchat -f

# 重启全家桶
docker compose -f deploy/docker-compose.prod.yml restart && systemctl restart andyouchat
```
