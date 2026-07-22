from __future__ import annotations

import socket
import threading
import time

from config import PORT
from host_info import primary_ip

DISCOVER_PORT = 18787
DISCOVER_REQ = b"QUOTE0_DISCOVER"
DISCOVER_RSP_PREFIX = "QUOTE0_SERVER"
ANNOUNCE_PREFIX = "QUOTE0_ANNOUNCE"
ANNOUNCE_INTERVAL_SEC = 3.0


def _payload(prefix: str, http_port: int) -> bytes:
    ip = primary_ip()
    return f"{prefix} {ip} {http_port}\n".encode("ascii")


def _reply_many(sock: socket.socket, addr: tuple, http_port: int) -> None:
    """Send several replies — UDP on conference Wi-Fi drops packets often."""
    payload = _payload(DISCOVER_RSP_PREFIX, http_port)
    for i in range(3):
        try:
            sock.sendto(payload, addr)
        except OSError as e:
            print(f"[discover] reply failed: {e}", flush=True)
            return
        time.sleep(0.03)
    print(f"[discover] replied x3 to {addr[0]} -> {payload.decode().strip()}", flush=True)


def discovery_loop(http_port: int = PORT, stop_event: threading.Event | None = None) -> None:
    """UDP discovery responder + periodic LAN announce for Quote/0 devices."""
    stop_event = stop_event or threading.Event()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", DISCOVER_PORT))
    sock.settimeout(0.5)
    print(f"[discover] listening UDP :{DISCOVER_PORT} + announce every {ANNOUNCE_INTERVAL_SEC}s", flush=True)

    next_announce = 0.0
    while not stop_event.is_set():
        now = time.time()
        if now >= next_announce:
            next_announce = now + ANNOUNCE_INTERVAL_SEC
            announce = _payload(ANNOUNCE_PREFIX, http_port)
            try:
                sock.sendto(announce, ("255.255.255.255", DISCOVER_PORT))
            except OSError as e:
                print(f"[discover] announce failed: {e}", flush=True)

        try:
            data, addr = sock.recvfrom(256)
        except socket.timeout:
            continue
        except OSError as e:
            print(f"[discover] socket error: {e}", flush=True)
            break

        text = data.decode("utf-8", "ignore").strip()
        if text.startswith("QUOTE0_DISCOVER"):
            _reply_many(sock, addr, http_port)
        # ignore our own announces / noise

    sock.close()


_started = False
_lock = threading.Lock()


def start_discovery_thread(http_port: int = PORT) -> threading.Thread | None:
    global _started
    with _lock:
        if _started:
            return None
        _started = True
    t = threading.Thread(target=discovery_loop, args=(http_port,), daemon=True, name="quote0-discover")
    t.start()
    return t
