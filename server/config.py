from __future__ import annotations

import os
from pathlib import Path

HOST = os.environ.get("QUOTE0_HOST", "0.0.0.0")
PORT = int(os.environ.get("QUOTE0_PORT", "8787"))
ADMIN_HOST = os.environ.get("QUOTE0_ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(os.environ.get("QUOTE0_ADMIN_PORT", "7891"))

# Cursor agent transcripts live under ~/.cursor/projects/*/agent-transcripts
CURSOR_PROJECTS = Path(
    os.environ.get("CURSOR_PROJECTS", Path.home() / ".cursor" / "projects")
).expanduser()

# How often the device should poll (hint only; firmware has its own interval)
POLL_HINT_SEC = int(os.environ.get("QUOTE0_POLL_HINT_SEC", "30"))

# Auto-rotate pages on the server
PAGE_ROTATE_SEC = int(os.environ.get("QUOTE0_PAGE_ROTATE_SEC", "30"))

# Minecraft Java server defaults (overridden by settings.json / env)
MC_HOST = os.environ.get("MC_HOST", "frp-web.com")
MC_PORT = int(os.environ.get("MC_PORT", "11520"))

# Display geometry for Quote/0 UC8251D
WIDTH = 152
HEIGHT = 296
BUFFER_SIZE = (WIDTH * HEIGHT) // 8

# 1 = white, 0 = black (matches MindReset UC8251D driver convention)
WHITE = 1
BLACK = 0


def runtime_poll_hint() -> int:
    try:
        from settings_store import load_settings

        return int(load_settings().get("poll_hint_sec") or POLL_HINT_SEC)
    except Exception:
        return POLL_HINT_SEC


def runtime_page_rotate() -> int:
    try:
        from settings_store import load_settings

        return int(load_settings().get("page_rotate_sec") or PAGE_ROTATE_SEC)
    except Exception:
        return PAGE_ROTATE_SEC


def runtime_mc() -> tuple[str, int]:
    try:
        from settings_store import load_settings

        s = load_settings()
        return str(s.get("mc_host") or MC_HOST), int(s.get("mc_port") or MC_PORT)
    except Exception:
        return MC_HOST, MC_PORT
