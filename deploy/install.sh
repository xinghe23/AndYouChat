#!/usr/bin/env bash
# ============================================================================
# AndYouChat 一键部署脚本
#
# 用法：
#     bash deploy/install.sh              # 常规安装（保留已有数据）
#     bash deploy/install.sh --reset      # 彻底重来：删容器 + 删数据 + 换新密码
#     MYSQL_HOST_PORT=3307 bash deploy/install.sh --reset   # 手动指定宿主端口
#
# 它自动完成：
#   0. 环境检查（docker / 目录 / 端口）
#   1. 找一个 Python ≥ 3.10（没有就尝试自动安装）
#   2. 准备 MySQL / Redis：生成密码文件、起容器、等 healthy
#   3. 建 .venv 并装依赖
#   4. 生成后端 .env（从 deploy/.env 读密码，自动 URL 编码）
#   5. 安装 systemd 服务并启动
#   6. 自检 /health，失败了自动诊断并给出修复命令
#
# 密码全程自动生成，不需要手工编辑任何文件。
# ============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8200}"
# 宿主端口：留空则自动探测（3306 常被宝塔自带 MySQL 占用，会自动切 3307）
MYSQL_HOST_PORT="${MYSQL_HOST_PORT:-}"
REDIS_HOST_PORT="${REDIS_HOST_PORT:-}"
SERVICE_NAME="${SERVICE_NAME:-andyouchat}"
COMPOSE_FILE="$APP_DIR/deploy/docker-compose.prod.yml"
DB_ENV="$APP_DIR/deploy/.env"
PYBIN="$APP_DIR/.venv/bin/python"
PIPBIN="$APP_DIR/.venv/bin/pip"
RESET=0

for arg in "$@"; do
    case "$arg" in
        --reset) RESET=1 ;;
        -h|--help)
            sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "未知参数：$arg（可用：--reset / --help）" >&2; exit 2 ;;
    esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[1;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '    \033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m[失败]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. 环境检查
say "0/7 环境检查"
[ -f "$APP_DIR/requirements.txt" ] || die "当前不是项目根目录，请先 cd 到 /www/server/chat_server"
[ -f "$APP_DIR/app/main.py" ]      || die "缺 app/main.py，部署包不完整，请重新上传解压"
[ -f "$COMPOSE_FILE" ]             || die "缺 deploy/docker-compose.prod.yml，部署包不完整"
command -v docker >/dev/null 2>&1  || die "未安装 Docker，见 DEPLOY.md 1.4 节"
docker compose version >/dev/null 2>&1 || die "Docker Compose 不可用（需要 v2）"
ok "目录：$APP_DIR"

if [ "$RESET" = 1 ]; then
    warn "已指定 --reset：将删除容器与 MySQL/Redis 全部数据，并重新生成密码"
fi

# 宿主端口自动避让。3306 / 6379 常被宝塔自带的 MySQL、Redis 占用，
# 被占时容器会因「address already in use」起不来。这里提前探测并换端口，
# 探测结果会写进 deploy/.env，保证 compose 映射与后端连接串始终一致。
taken_by_others() {   # $1=端口  $2=本项目容器名（自己占的不算占用）
    local out names n
    command -v ss >/dev/null 2>&1 || return 1
    # 不用 `ss | grep -q`：脚本开了 pipefail，grep 提前退出会让 ss 吃 SIGPIPE
    # 使整条管道返回 141，被误判成「端口空闲」。
    out="$(ss -lnt 2>/dev/null || true)"
    case "$out" in
        *":$1 "*) ;;
        *) return 1 ;;
    esac
    names="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
    while IFS= read -r n; do
        # 是本项目自己的容器，说明端口被自己占着，不算冲突
        if [ "$n" = "$2" ]; then return 1; fi
    done <<< "$names"
    return 0
}
if [ -z "$MYSQL_HOST_PORT" ]; then
    if taken_by_others 3306 andyou-mysql; then
        MYSQL_HOST_PORT=3307
        warn "宿主 3306 已被占用（多为宝塔 MySQL），MySQL 自动改用 3307"
    else
        MYSQL_HOST_PORT=3306
    fi
fi
if [ -z "$REDIS_HOST_PORT" ]; then
    if taken_by_others 6379 andyou-redis; then
        REDIS_HOST_PORT=6380
        warn "宿主 6379 已被占用，Redis 自动改用 6380"
    else
        REDIS_HOST_PORT=6379
    fi
fi
ok "宿主端口：MySQL ${MYSQL_HOST_PORT} / Redis ${REDIS_HOST_PORT}"

if command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q ":${PORT} "; then
    warn "端口 ${PORT} 已被占用（可能是旧进程）：ss -lntp | grep ${PORT}"
fi

# ---------------------------------------------------------------- 1. Python
say "1/7 查找 Python ≥ 3.10"
pick_python() {
    local v
    for v in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$v" >/dev/null 2>&1 &&
           "$v" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            echo "$v"; return 0
        fi
    done
    return 1
}

if PY="$(pick_python)"; then
    ok "使用 $PY（$("$PY" -V 2>&1)）"
else
    warn "未找到 3.10+，尝试自动安装 python3.12 ..."
    if command -v dnf >/dev/null 2>&1; then
        dnf -y install python3.12 python3.12-devel gcc gcc-c++ make
    elif command -v yum >/dev/null 2>&1; then
        yum -y install python3.12 python3.12-devel gcc gcc-c++ make
    elif command -v apt-get >/dev/null 2>&1; then
        apt-get update && apt-get -y install python3.12 python3.12-venv python3.12-dev build-essential
    else
        die "无法自动安装，请手动装 Python 3.10+ 后重跑"
    fi
    PY="$(pick_python)" || die "安装后仍找不到 Python 3.10+，请检查 PATH"
    ok "已安装并用 $PY"
fi

# ---------------------------------------------------------------- 2. 数据库容器
say "2/7 准备 MySQL / Redis"
cd "$APP_DIR/deploy"

if [ "$RESET" = 1 ]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$DB_ENV" down --remove-orphans 2>/dev/null || true
    # 僵死容器兜底：报 "tried to kill container, but did not receive an exit event"
    # 时 down 是删不掉的（进程卡在不可中断 I/O），必须 docker rm -f 硬删，
    # 否则下一步 up 会一直卡在 Recreate 上。
    for c in andyou-mysql andyou-redis; do
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$c"; then
            docker rm -f "$c" >/dev/null 2>&1 \
                || die "无法删除僵死容器 $c（多半是磁盘满/I/O 卡住）。执行：systemctl restart docker 后重跑本脚本"
            ok "已强制删除残留容器 $c"
        fi
    done
    if [ -d data ]; then
        rm -rf data
        ok "已删除旧数据目录 deploy/data"
    fi
    rm -f "$DB_ENV"
    ok "已删除旧密码文件 deploy/.env"
fi

if [ ! -f "$DB_ENV" ]; then
    "$PY" - "$DB_ENV" "$MYSQL_HOST_PORT" "$REDIS_HOST_PORT" <<'PYEOF'
import secrets, sys
t = lambda: secrets.token_urlsafe(24)
lines = [
    "MYSQL_ROOT_PASSWORD=" + t(),
    "MYSQL_DATABASE=andyouchat",
    "MYSQL_USER=andyou",
    "MYSQL_PASSWORD=" + t(),
    "REDIS_PASSWORD=" + t(),
]
mp, rp = sys.argv[2], sys.argv[3]
if mp and mp != "3306":          # 默认端口不写，保持文件干净
    lines.append("MYSQL_HOST_PORT=" + mp)
if rp and rp != "6379":
    lines.append("REDIS_HOST_PORT=" + rp)
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(lines) + "\n")
PYEOF
    chmod 600 "$DB_ENV"
    ok "已生成新密码：$DB_ENV（32 位随机串，含字母数字和 _-）"
else
    ok "沿用已有密码文件：$DB_ENV"
    # 旧版脚本生成的 .env 里没有端口行；宿主端口被占时必须补上，
    # 否则 compose 仍按默认 3306 绑定，容器再次起不来。
    if [ "$MYSQL_HOST_PORT" != "3306" ] && ! grep -q '^MYSQL_HOST_PORT=' "$DB_ENV"; then
        printf 'MYSQL_HOST_PORT=%s\n' "$MYSQL_HOST_PORT" >> "$DB_ENV"
        ok "已补写 MYSQL_HOST_PORT=${MYSQL_HOST_PORT}（原文件没有该行）"
    fi
    if [ "$REDIS_HOST_PORT" != "6379" ] && ! grep -q '^REDIS_HOST_PORT=' "$DB_ENV"; then
        printf 'REDIS_HOST_PORT=%s\n' "$REDIS_HOST_PORT" >> "$DB_ENV"
        ok "已补写 REDIS_HOST_PORT=${REDIS_HOST_PORT}（原文件没有该行）"
    fi
fi

get_val() {
    grep -E "^$1=" "$DB_ENV" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '\r' || true
}

MYSQL_USER_V="$(get_val MYSQL_USER)";        [ -n "$MYSQL_USER_V" ] || MYSQL_USER_V="andyou"
MYSQL_DB_V="$(get_val MYSQL_DATABASE)";      [ -n "$MYSQL_DB_V" ]   || MYSQL_DB_V="andyouchat"
MYSQL_PW_V="$(get_val MYSQL_PASSWORD)"
REDIS_PW_V="$(get_val REDIS_PASSWORD)"
MYSQL_HOST_PORT_V="$(get_val MYSQL_HOST_PORT)"; [ -n "$MYSQL_HOST_PORT_V" ] || MYSQL_HOST_PORT_V="3306"
REDIS_HOST_PORT_V="$(get_val REDIS_HOST_PORT)"; [ -n "$REDIS_HOST_PORT_V" ] || REDIS_HOST_PORT_V="6379"
[ -n "$MYSQL_PW_V" ] || die "读不到 MYSQL_PASSWORD，请删掉 $DB_ENV 后重跑本脚本"
[ -n "$REDIS_PW_V" ] || die "读不到 REDIS_PASSWORD，请删掉 $DB_ENV 后重跑本脚本"
ok "用户 ${MYSQL_USER_V} / 库 ${MYSQL_DB_V} / 端口 ${MYSQL_HOST_PORT_V},${REDIS_HOST_PORT_V}"

# 宿主端口被占时给出明确提示，而不是让 docker 抛天书
for hp in "$MYSQL_HOST_PORT_V" "$REDIS_HOST_PORT_V"; do
    if command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q ":${hp} "; then
        if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qE '^andyou-(mysql|redis)$'; then
            warn "宿主端口 ${hp} 已被其他程序占用（可能是宝塔自带 MySQL）"
            warn "处理：停掉它，或在 $DB_ENV 里加 MYSQL_HOST_PORT=3307 后重跑"
        fi
    fi
done

say "启动容器"
# bind mount 的数据目录属主必须是容器内的运行用户。mysql:8.0 与 redis:7-alpine
# 里 mysql / redis 用户的 UID 都是 999；一旦被改成 www（旧版脚本的 chown -R 造成），
# mysqld 启动时就会报 "Operating system error number 13 ... does not have the
# access rights"，容器照样显示 running 却在崩溃循环里，后端建表必然失败。
for d in "$APP_DIR/deploy/data/mysql" "$APP_DIR/deploy/data/redis"; do
    if [ -d "$d" ]; then
        chown -R 999:999 "$d" 2>/dev/null \
            || warn "无法调整 $(basename "$d") 目录属主，可能引发容器 EACCES 错误"
    fi
done
if ! docker compose -f "$COMPOSE_FILE" --env-file "$DB_ENV" up -d; then
    printf '\n' >&2
    warn "常见原因与处理："
    printf '   1) did not receive an exit event（僵死容器）\n' >&2
    printf '      docker rm -f andyou-mysql andyou-redis || systemctl restart docker\n' >&2
    printf '   2) address already in use（端口冲突）\n' >&2
    printf '      echo "MYSQL_HOST_PORT=3307" >> %s 后重跑\n' "$DB_ENV" >&2
    printf '   3) no space left on device（磁盘满）\n' >&2
    printf '      df -h / && docker system prune -af\n' >&2
    die "容器启动失败，日志：docker compose -f $COMPOSE_FILE logs --tail=30"
fi
ok "容器已启动"

say "等待 MySQL / Redis 变为 healthy（首次初始化需 20~40 秒）"
READY=0
for _ in $(seq 1 45); do
    sleep 2
    SM="$(docker inspect -f '{{.State.Health.Status}}' andyou-mysql 2>/dev/null || echo unknown)"
    SR="$(docker inspect -f '{{.State.Health.Status}}' andyou-redis 2>/dev/null || echo unknown)"
    if [ "$SM" = healthy ] && [ "$SR" = healthy ]; then READY=1; break; fi
done
if [ "$READY" = 1 ]; then
    ok "MySQL healthy"
    ok "Redis healthy"
else
    docker compose -f "$COMPOSE_FILE" --env-file "$DB_ENV" ps || true
    docker compose -f "$COMPOSE_FILE" --env-file "$DB_ENV" logs --tail=20 mysql || true
    docker compose -f "$COMPOSE_FILE" --env-file "$DB_ENV" logs --tail=20 redis || true
    printf '\n' >&2
    warn "健康检查自测（可手动确认服务是否真的可用）："
    printf '   docker exec andyou-redis sh -c '"'"'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping'"'"'\n' >&2
    printf '   docker exec andyou-mysql mysqladmin ping -h127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD"\n' >&2
    die "容器未在 90 秒内变为 healthy。常见原因：宿主端口被占（见上面的警告）"
fi

# ---------------------------------------------------------------- 3. venv
say "3/7 创建虚拟环境"
cd "$APP_DIR"
if [ -x "$PYBIN" ]; then
    ok "复用已有 .venv"
else
    rm -rf .venv
    "$PY" -m venv .venv || die "创建 venv 失败，可能需要安装 ${PY}-venv 或 ${PY}-devel"
    ok "已创建 .venv"
fi
"$PYBIN" -m pip install -q -U pip setuptools wheel || warn "pip 自升级失败，继续"
ok "$("$PYBIN" -V 2>&1)"

# ---------------------------------------------------------------- 4. 依赖
say "4/7 安装依赖（首次 1~3 分钟）"
"$PIPBIN" install -q -r requirements.txt || die "依赖安装失败：检查网络，或内存不足（DEPLOY.md 1.3 节加 swap）"
"$PYBIN" -c "import fastapi, sqlalchemy, aiomysql, redis, jwt, bcrypt" || die "依赖导入失败，删掉 .venv 后重跑"
ok "依赖就绪"

# ---------------------------------------------------------------- 5. 后端 .env
say "5/7 生成后端配置 .env"
enc() {
    "$PYBIN" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}
MYSQL_PW_ENC="$(enc "$MYSQL_PW_V")"
REDIS_PW_ENC="$(enc "$REDIS_PW_V")"

JWT_V="$("$PYBIN" -c 'import secrets; print(secrets.token_urlsafe(48))')"
if [ -f .env ]; then
    OLD_JWT="$(grep -E '^JWT_SECRET=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true)"
    if [ -n "${OLD_JWT:-}" ]; then
        JWT_V="$OLD_JWT"
        ok "沿用已有 JWT_SECRET（避免把在线用户踢下线）"
    fi
    BAK=".env.bak.$(date +%Y%m%d%H%M%S)"
    cp .env "$BAK"
    warn "旧 .env 已备份为 $BAK"
fi

cat > .env <<EOF
APP_NAME=AndYouChat
ENV=production

DATABASE_URL=mysql+aiomysql://${MYSQL_USER_V}:${MYSQL_PW_ENC}@127.0.0.1:${MYSQL_HOST_PORT_V}/${MYSQL_DB_V}?charset=utf8mb4
REDIS_URL=redis://:${REDIS_PW_ENC}@127.0.0.1:${REDIS_HOST_PORT_V}/0
USE_FAKEREDIS=false

JWT_SECRET=${JWT_V}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL=604800
REFRESH_TOKEN_TTL=2592000

CORS_ORIGINS=*
SNOWFLAKE_NODE_ID=1
MESSAGE_RECALL_SECONDS=120
EOF
chmod 600 .env
ok "已写入 $APP_DIR/.env"

# ---------------------------------------------------------------- 6. systemd
say "6/7 安装 systemd 服务"
RUN_USER="www"
if ! id -u "$RUN_USER" >/dev/null 2>&1; then
    RUN_USER="root"
    warn "系统无 www 用户（未装宝塔），改用 root 运行"
fi
# 只把运行真正需要的路径交给运行用户。
# 绝不能 `chown -R "$APP_DIR"`：那会把 deploy/data/mysql、deploy/data/redis
# 一起改成 www，mysqld / redis 随即失去数据目录访问权（OS error 13），
# 容器进入崩溃循环，而 docker ps 里看起来仍是 running，极难排查。
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/.venv" 2>/dev/null || true
if [ -f "$APP_DIR/.env" ]; then
    chown "$RUN_USER:$RUN_USER" "$APP_DIR/.env" 2>/dev/null || true
    chmod 600 "$APP_DIR/.env" 2>/dev/null || true
fi
chown "$RUN_USER:$RUN_USER" "$APP_DIR" 2>/dev/null || true   # 目录本身可写，便于落日志
ok "运行用户：$RUN_USER（仅授权 .venv 与 .env，不动 deploy/data）"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=AndYouChat FastAPI Service
After=network-online.target docker.service
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Asia/Shanghai
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1 --timeout-keep-alive 75
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl reset-failed "$SERVICE_NAME" 2>/dev/null || true
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"
ok "服务已启动：$SERVICE_NAME"

# ---------------------------------------------------------------- 7. 自检
say "7/7 健康检查"
HEALTH=""
for _ in $(seq 1 25); do
    sleep 1
    if HEALTH="$(curl -fsS --noproxy '*' "http://127.0.0.1:${PORT}/health" 2>/dev/null)"; then
        [ -n "$HEALTH" ] && break
    fi
    HEALTH=""
done

if [ -z "$HEALTH" ]; then
    LOG="$(journalctl -u "$SERVICE_NAME" -n 150 --no-pager 2>/dev/null || true)"
    printf '\n'
    systemctl status "$SERVICE_NAME" --no-pager -l 2>/dev/null | head -12 || true
    printf '\n---- 最近的错误日志 ----\n'
    printf '%s\n' "$LOG" | grep -viE 'Scheduled restart|Started andyouchat|Consumed .* CPU' | tail -20 || true
    printf '\n\033[1;33m---- 自动诊断 ----\033[0m\n'

    if printf '%s' "$LOG" | grep -qiE "Lost connection|gone away|\(2006,|\(2013,"; then
        warn "MySQL 连接被掐断——多半是容器内部崩了（最常见：数据目录属主被改成 www，InnoDB 报 error 13）"
        printf '  查：docker logs andyou-mysql --tail 20 | grep -i error\n'
        printf '  修：chown -R 999:999 %s/deploy/data && docker restart andyou-mysql\n' "$APP_DIR"
    elif printf '%s' "$LOG" | grep -q "Access denied for user"; then
        warn "MySQL 密码与库内不一致（数据目录是旧密码初始化的）"
        printf '  一条命令重来：bash %s/deploy/install.sh --reset\n' "$APP_DIR"
    elif printf '%s' "$LOG" | grep -qE "Can't connect to (local )?MySQL|Connection refused"; then
        warn "连不上 MySQL。检查容器：docker compose -f %s ps" "$COMPOSE_FILE"
        printf '  确认端口映射：ss -lntp | grep %s\n' "$MYSQL_HOST_PORT_V"
    elif printf '%s' "$LOG" | grep -qiE "AuthenticationError|invalid password|WRONGPASS|NOAUTH"; then
        warn "Redis 密码不正确，同样用 --reset 重来最快"
        printf '  bash %s/deploy/install.sh --reset\n' "$APP_DIR"
    elif printf '%s' "$LOG" | grep -q "ModuleNotFoundError"; then
        warn "依赖缺失"
        printf '  rm -rf %s/.venv && bash %s/deploy/install.sh\n' "$APP_DIR" "$APP_DIR"
    elif printf '%s' "$LOG" | grep -q "Address already in use"; then
        warn "端口 %s 被占用：ss -lntp | grep %s" "$PORT" "$PORT"
    else
        warn "未匹配到已知错误模式，请把上面的日志发我"
    fi
    die "服务未能在 25 秒内响应"
fi

printf '    %s\n\n' "$HEALTH"
DB_OK=false; REDIS_OK=false
printf '%s' "$HEALTH" | grep -q '"db"[[:space:]]*:[[:space:]]*true'    && DB_OK=true
printf '%s' "$HEALTH" | grep -q '"redis"[[:space:]]*:[[:space:]]*true' && REDIS_OK=true

if [ "$DB_OK" = true ] && [ "$REDIS_OK" = true ]; then
    ok "MySQL 连通"
    ok "Redis 连通"
    printf '\n\033[1;32m============================================\033[0m\n'
    printf '\033[1;32m  部署成功，后端已在 127.0.0.1:%s 运行\033[0m\n' "$PORT"
    printf '\033[1;32m============================================\033[0m\n'
    printf '\n验证建表（6 张表）：\n'
    printf '  docker exec -it andyou-mysql mysql -u%s -p%s -e "SHOW TABLES;"\n' "$MYSQL_USER_V" "$MYSQL_DB_V"
    printf '\n常用命令：\n'
    printf '  systemctl status %s --no-pager\n' "$SERVICE_NAME"
    printf '  systemctl restart %s\n' "$SERVICE_NAME"
    printf '  journalctl -u %s -n 30 --no-pager\n' "$SERVICE_NAME"
    printf '\n下一步：配置 Nginx 反代，见 deploy/nginx-andyouchat.conf\n'
else
    [ "$DB_OK" = true ]    || warn "MySQL 未连通（db:false）"
    [ "$REDIS_OK" = true ] || warn "Redis 未连通（redis:false）"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
    die "服务起来了但依赖未连通，建议：bash $APP_DIR/deploy/install.sh --reset"
fi
