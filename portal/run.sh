#!/usr/bin/env bash
# 启动 USB 配置门户：浏览器打开 http://0.1.2.3
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -U pip
  .venv/bin/pip install -r requirements.txt
fi

IP="${QUOTE0_PORTAL_HOST:-0.1.2.3}"
# 默认 8080，避免卡在 sudo 要端口 80；仍可用 http://0.1.2.3:8080
PORT="${QUOTE0_PORTAL_PORT:-8080}"

# 把 0.1.2.3 绑到回环（若已有权限 / 已配置则跳过）
if ! ip -4 addr show dev lo 2>/dev/null | grep -q "$IP"; then
  if command -v pkexec >/dev/null 2>&1; then
    echo "添加 $IP 到 lo…"
    pkexec ip addr add "$IP/32" dev lo 2>/dev/null || sudo -n ip addr add "$IP/32" dev lo 2>/dev/null || true
  else
    sudo -n ip addr add "$IP/32" dev lo 2>/dev/null || true
  fi
fi

export QUOTE0_PORTAL_HOST="$IP"
export QUOTE0_PORTAL_PORT="$PORT"

# 若 0.1.2.3 没加上，退回 127.0.0.1
if ! ip -4 addr show dev lo 2>/dev/null | grep -q "$IP"; then
  echo "提示: 未能添加 $IP，改用 http://127.0.0.1:$PORT （可手动: sudo ip addr add $IP/32 dev lo）"
  export QUOTE0_PORTAL_HOST="127.0.0.1"
fi

exec "$ROOT/.venv/bin/python" "$ROOT/app.py"
