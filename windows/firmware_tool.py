"""ESP32-C3 firmware backup / flash / restore via esptool."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WIN_DIR = Path(__file__).resolve().parent
FW_DIR = WIN_DIR / "firmware"
CUSTOM_DIR = FW_DIR / "custom"
STOCK_PATH = FW_DIR / "stock_full_4mb.bin"
BACKUP_DIR = WIN_DIR / "data" / "backups"
FLASH_SIZE = 0x400000  # 4MB


class FirmwareError(RuntimeError):
    pass


def _esptool_cmd() -> list[str]:
    # Prefer module form so Windows venv works
    return [sys.executable, "-m", "esptool"]


def find_serial_ports() -> list[str]:
    ports: list[str] = []
    try:
        from serial.tools import list_ports

        for p in list_ports.comports():
            desc = f"{p.device} {p.description} {p.manufacturer or ''}".lower()
            if any(k in desc for k in ("acm", "usb", "esp", "jtag", "serial", "uart", "ch340", "cp210")):
                ports.append(p.device)
            elif p.device.upper().startswith("COM"):
                ports.append(p.device)
    except Exception:
        pass
    import glob as _glob

    for g in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        ports.extend(sorted(_glob.glob(g)))
    seen: set[str] = set()
    out: list[str] = []
    for p in ports:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def stock_available() -> bool:
    return STOCK_PATH.is_file() and STOCK_PATH.stat().st_size >= 1024 * 1024


def custom_available() -> bool:
    return all((CUSTOM_DIR / n).is_file() for n in ("bootloader.bin", "partitions.bin", "firmware.bin"))


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(BACKUP_DIR.glob("*.bin"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    return items


def _run(args: list[str], timeout: int = 300) -> str:
    cmd = _esptool_cmd() + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise FirmwareError("未找到 esptool，请确认已 pip install esptool") from e
    except subprocess.TimeoutExpired as e:
        raise FirmwareError(f"esptool 超时: {' '.join(args[:6])}") from e
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise FirmwareError(out[-1500:] or f"esptool exit {proc.returncode}")
    return out


def backup_flash(port: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
    dest = BACKUP_DIR / name
    _run(
        [
            "--chip",
            "esp32c3",
            "--port",
            port,
            "--baud",
            "921600",
            "read-flash",
            "0",
            hex(FLASH_SIZE),
            str(dest),
        ],
        timeout=600,
    )
    if not dest.is_file() or dest.stat().st_size < FLASH_SIZE // 2:
        raise FirmwareError("备份文件异常或不完整")
    return dest


def restore_stock(port: str) -> str:
    if not stock_available():
        raise FirmwareError(
            f"缺少原版镜像：请将 Quote/0 原厂 4MB dump 放到\n{STOCK_PATH}"
        )
    return _run(
        [
            "--chip",
            "esp32c3",
            "--port",
            port,
            "--baud",
            "921600",
            "write-flash",
            "--flash-mode",
            "dio",
            "--flash-freq",
            "80m",
            "--flash-size",
            "4MB",
            "0x0",
            str(STOCK_PATH),
        ],
        timeout=600,
    )


def flash_custom(port: str) -> str:
    if not custom_available():
        raise FirmwareError(f"缺少第三方固件文件，目录: {CUSTOM_DIR}")
    boot = CUSTOM_DIR / "bootloader.bin"
    part = CUSTOM_DIR / "partitions.bin"
    app = CUSTOM_DIR / "firmware.bin"
    # Matches firmware/partitions.csv: bootloader@0, table@0x8000, factory@0x20000
    return _run(
        [
            "--chip",
            "esp32c3",
            "--port",
            port,
            "--baud",
            "921600",
            "write-flash",
            "--flash-mode",
            "dio",
            "--flash-freq",
            "80m",
            "--flash-size",
            "4MB",
            "0x0",
            str(boot),
            "0x8000",
            str(part),
            "0x20000",
            str(app),
        ],
        timeout=300,
    )


def flash_upload(port: str, path: Path, mode: str = "auto") -> str:
    """Flash an uploaded .bin. auto: 4MB→full chip, else treat as app@0x20000."""
    size = path.stat().st_size
    if mode == "full" or (mode == "auto" and size >= FLASH_SIZE - 64 * 1024):
        return _run(
            [
                "--chip",
                "esp32c3",
                "--port",
                port,
                "--baud",
                "921600",
                "write-flash",
                "--flash-mode",
                "dio",
                "--flash-freq",
                "80m",
                "--flash-size",
                "4MB",
                "0x0",
                str(path),
            ],
            timeout=600,
        )
    # App image (ESP magic 0xE9) → 0x20000 for our partition layout
    return _run(
        [
            "--chip",
            "esp32c3",
            "--port",
            port,
            "--baud",
            "921600",
            "write-flash",
            "--flash-mode",
            "dio",
            "--flash-freq",
            "80m",
            "--flash-size",
            "4MB",
            "0x20000",
            str(path),
        ],
        timeout=300,
    )


def restore_backup(port: str, name: str) -> str:
    path = BACKUP_DIR / Path(name).name
    if not path.is_file():
        raise FirmwareError("备份不存在")
    return flash_upload(port, path, mode="full")


def chip_info(port: str) -> str:
    return _run(["--chip", "esp32c3", "--port", port, "chip-id"], timeout=30)
