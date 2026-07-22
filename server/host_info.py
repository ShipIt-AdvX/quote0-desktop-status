from __future__ import annotations

import os
import platform
import socket
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import psutil


@dataclass
class HostInfo:
    hostname: str
    ip: str
    os: str
    cpu_percent: float
    mem_percent: float
    mem_used_gb: float
    mem_total_gb: float
    load_1m: float | None
    uptime_human: str
    battery_percent: float | None
    time: str


def primary_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _primary_ip() -> str:
    return primary_ip()


def _uptime_human() -> str:
    boot = psutil.boot_time()
    secs = int(time.time() - boot)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def collect_host() -> HostInfo:
    vm = psutil.virtual_memory()
    load: float | None
    try:
        load = os.getloadavg()[0]
    except (AttributeError, OSError):
        load = None

    batt_pct: float | None = None
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            batt_pct = float(batt.percent)
    except Exception:
        batt_pct = None

    # Non-blocking CPU sample; first call after boot may be 0.0
    cpu = float(psutil.cpu_percent(interval=0.15))

    return HostInfo(
        hostname=socket.gethostname(),
        ip=_primary_ip(),
        os=f"{platform.system()} {platform.release().split('-')[0]}",
        cpu_percent=cpu,
        mem_percent=float(vm.percent),
        mem_used_gb=round(vm.used / (1024**3), 1),
        mem_total_gb=round(vm.total / (1024**3), 1),
        load_1m=round(load, 2) if load is not None else None,
        uptime_human=_uptime_human(),
        battery_percent=batt_pct,
        time=datetime.now().strftime("%H:%M"),
    )


def host_as_dict() -> dict[str, Any]:
    return asdict(collect_host())
