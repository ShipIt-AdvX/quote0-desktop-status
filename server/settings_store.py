from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

# Prefer project-local data dir; Windows package uses windows/data
_DATA_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "windows" / "data",
    Path(__file__).resolve().parent / "data",
]


def data_dir() -> Path:
    for p in _DATA_CANDIDATES:
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            continue
    p = Path.cwd() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return data_dir() / "settings.json"


def cover_bin_path() -> Path:
    return data_dir() / "cover.bin"


_DEFAULTS: dict[str, Any] = {
    "mc_host": "frp-web.com",
    "mc_port": 11520,
    "poll_hint_sec": 30,
    "page_rotate_sec": 30,
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def load_settings() -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
        path = settings_path()
        data = dict(_DEFAULTS)
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data.update({k: raw[k] for k in raw if k in _DEFAULTS or k in ("mc_host", "mc_port")})
            except (OSError, json.JSONDecodeError):
                pass
        _cache = data
        return dict(data)


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    global _cache
    with _lock:
        data = load_settings() if _cache is None else dict(_cache)
        if "mc_host" in updates and updates["mc_host"] is not None:
            data["mc_host"] = str(updates["mc_host"]).strip() or data["mc_host"]
        if "mc_port" in updates and updates["mc_port"] is not None:
            data["mc_port"] = int(updates["mc_port"])
        if "poll_hint_sec" in updates and updates["poll_hint_sec"] is not None:
            data["poll_hint_sec"] = max(10, int(updates["poll_hint_sec"]))
        if "page_rotate_sec" in updates and updates["page_rotate_sec"] is not None:
            data["page_rotate_sec"] = max(5, int(updates["page_rotate_sec"]))
        settings_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = data
        return dict(data)


def has_cover() -> bool:
    p = cover_bin_path()
    return p.is_file() and p.stat().st_size == 5624


def save_cover_bin(data: bytes) -> None:
    if len(data) != 5624:
        raise ValueError("cover must be 5624 bytes")
    cover_bin_path().write_bytes(data)


def load_cover_bin() -> bytes | None:
    if not has_cover():
        return None
    return cover_bin_path().read_bytes()


def clear_cover() -> None:
    p = cover_bin_path()
    if p.is_file():
        p.unlink()
