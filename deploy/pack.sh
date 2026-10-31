#!/usr/bin/env bash
# 生成可上传服务器的部署包（在任意目录执行均可，脚本会自己定位项目根）
#   用法：bash deploy/pack.sh [输出文件名]
#   默认：项目根/andyouchat-deploy.tar.gz
#
# 打包内容 = 后端源码 + 前端构建产物 + 部署模板
# 排除：虚拟环境、node_modules、本地数据库、本地 .env、日志、git 历史、缓存
set -euo pipefail

cd "$(dirname "$0")/.."
OUT="$(pwd)/${1:-andyouchat-deploy.tar.gz}"
TMP="$(mktemp -d)/pack.tar.gz"
trap 'rm -rf "$(dirname "$TMP")"' EXIT

# 保险：shell 脚本必须是 LF 换行。用 Windows 编辑器改过会变成 CRLF，
# 到 Linux 上执行会报 "bad interpreter" 或每行 "\r: command not found"。
for f in deploy/*.sh; do
  [ -f "$f" ] && sed -i 's/\r$//' "$f"
done

if [ ! -f chat/index.html ]; then
  echo "!! chat/index.html 不存在：先在 web/ 下执行 npm run build:chat" >&2
  exit 1
fi

# 用 -f - 输出到 stdout 再由 shell 重定向：Git Bash 的 tar 会把 C:\ 开头的 -f 参数
# 误判成远程主机（Cannot connect to C:），走管道可绕开。先写临时目录再移回，避免把自身打进包。
tar -czf - \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.idea' \
  --exclude='.vscode' \
  --exclude='.workbuddy' \
  --exclude='.git' \
  --exclude='*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='.env' \
  --exclude='deploy/data' \
  --exclude='server.log' \
  --exclude='*.tar.gz' \
  --exclude='*.zip' \
  --exclude='shot-*.png' \
  . > "$TMP" || true

mv "$TMP" "$OUT"

echo "== 已生成：$OUT"
ls -lh "$OUT" | awk '{print "   大小：" $5}'
LIST="$(tar -tzf "$OUT" | tr -d '\r')"
echo "== 包内文件数：$(printf '%s\n' "$LIST" | grep -vc '/$')"
echo "== 关键文件自检（缺任何一个都说明包不完整）："
for f in app/main.py requirements.txt chat/index.html \
         deploy/install.sh deploy/docker-compose.prod.yml deploy/.env.db.example \
         deploy/schema.sql deploy/andyouchat.service deploy/nginx-andyouchat.conf \
         .env.example; do
  if printf '%s\n' "$LIST" | grep -qx "./$f"; then
    echo "   OK   $f"
  else
    echo "   MISS $f"
  fi
done
echo "== 不该出现的文件（应为空）："
printf '%s\n' "$LIST" | grep -E '^\./(\.venv|web/node_modules|deploy/data)(/|$)|^\./(andyou\.db|server\.log|\.env|deploy/\.env)$' || echo "   （无）"
echo "== 环境模板自检："
if printf '%s\n' "$LIST" | grep -qx "./deploy/.env.db.example"; then
  echo "   OK   deploy/.env.db.example"
else
  echo "   MISS deploy/.env.db.example"
fi
