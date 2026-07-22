"""One-process launcher: status :8787 + admin :7891."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = Path(__file__).resolve().parent

# Ensure imports resolve on Windows
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "portal"))
sys.path.insert(0, str(WIN))

# Force Windows data dir
os.environ.setdefault("QUOTE0_ADMIN_PORT", "7891")
os.environ.setdefault("QUOTE0_PORT", "8787")


def _wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    import uvicorn

    from admin_app import app as admin_app
    from config import ADMIN_HOST, ADMIN_PORT, PORT
    from main import app as status_app

    def run_status() -> None:
        uvicorn.run(status_app, host="0.0.0.0", port=PORT, log_level="info", access_log=False)

    t = threading.Thread(target=run_status, name="quote0-status", daemon=True)
    t.start()

    print("=" * 50, flush=True)
    print("  Quote/0 Windows", flush=True)
    print(f"  配置页:  http://localhost:{ADMIN_PORT}", flush=True)
    print(f"  设备API: http://0.0.0.0:{PORT}  (局域网访问)", flush=True)
    print("=" * 50, flush=True)

    def _open_browser() -> None:
        time.sleep(1.5)
        try:
            webbrowser.open(f"http://localhost:{ADMIN_PORT}/")
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()

    # Block on admin (localhost only)
    uvicorn.run(admin_app, host=ADMIN_HOST, port=ADMIN_PORT, log_level="info")


if __name__ == "__main__":
    main()
