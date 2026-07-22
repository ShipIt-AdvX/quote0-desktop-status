"""USB serial bridge to Quote/0 device."""

from __future__ import annotations

import glob
import threading
import time
from pathlib import Path

import serial
from serial.tools import list_ports

FRAME_BYTES = 5624


class DeviceError(RuntimeError):
    pass


class Quote0Device:
    def __init__(self, port: str | None = None, baud: int = 115200):
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()

    @staticmethod
    def find_ports() -> list[str]:
        ports: list[str] = []
        for p in list_ports.comports():
            desc = f"{p.device} {p.description} {p.manufacturer or ''}".lower()
            if "acm" in p.device.lower() or "usb" in desc or "esp" in desc or "jtag" in desc:
                ports.append(p.device)
        # Prefer ACM first
        ports = sorted(set(ports), key=lambda x: (0 if "ACM" in x else 1, x))
        if not ports:
            ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
        return ports

    def connect(self, port: str | None = None) -> str:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            path = port or self.port
            if not path:
                found = self.find_ports()
                if not found:
                    raise DeviceError("未找到 USB 设备（/dev/ttyACM*）")
                path = found[0]
            self.port = path
            self._ser = serial.Serial(path, self.baud, timeout=0.3, write_timeout=5)
            time.sleep(0.2)
            self._ser.reset_input_buffer()
            # Probe
            self._ser.write(b"PING\n")
            self._ser.flush()
            deadline = time.time() + 2.0
            buf = b""
            while time.time() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    buf += chunk
                    if b"PONG" in buf:
                        return path
            raise DeviceError(f"设备无响应: {path}（请确认已烧录门户固件）")

    def close(self) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None

    @property
    def connected(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def _cmd(self, line: str, expect_prefix: tuple[str, ...] = ("OK", "ERR", "{", "PONG"), timeout: float = 3.0) -> str:
        if not self._ser or not self._ser.is_open:
            raise DeviceError("未连接设备")
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write((line.rstrip() + "\n").encode("utf-8"))
            self._ser.flush()
            deadline = time.time() + timeout
            buf = ""
            while time.time() < deadline:
                chunk = self._ser.read(512)
                if chunk:
                    buf += chunk.decode("utf-8", "ignore")
                    for raw in buf.splitlines():
                        s = raw.strip()
                        if not s:
                            continue
                        if s.startswith(expect_prefix):
                            return s
                else:
                    time.sleep(0.02)
            raise DeviceError(f"超时: {line!r} 缓冲={buf[-200:]!r}")

    def ping(self) -> bool:
        return self._cmd("PING").startswith("PONG")

    def get_json_line(self) -> str:
        return self._cmd("GET_JSON", expect_prefix=("{",))

    def wifi_add(self, ssid: str, password: str = "") -> str:
        # Passwords with spaces not supported in line protocol; strip.
        ssid = ssid.replace("\n", "").strip()
        password = password.replace("\n", "")
        return self._cmd(f"WIFI_ADD {ssid} {password}".rstrip())

    def wifi_del(self, ssid: str) -> str:
        return self._cmd(f"WIFI_DEL {ssid.strip()}")

    def set_server(self, host: str, port: int) -> str:
        return self._cmd(f"SET_SERVER {host.strip()} {int(port)}")

    def set_poll(self, sec: int) -> str:
        return self._cmd(f"SET_POLL {int(sec)}")

    def set_mode(self, mode: str) -> str:
        if mode not in ("image", "server"):
            raise DeviceError("mode 必须是 image 或 server")
        return self._cmd(f"SET_MODE {mode}")

    def save(self) -> str:
        return self._cmd("SAVE")

    def reboot(self) -> str:
        return self._cmd("REBOOT", timeout=1.5)

    def img_clear(self) -> str:
        return self._cmd("IMG_CLEAR")

    def img_show(self) -> str:
        return self._cmd("IMG_SHOW")

    def upload_frame(self, data: bytes) -> str:
        if len(data) != FRAME_BYTES:
            raise DeviceError(f"帧大小必须为 {FRAME_BYTES}，实际 {len(data)}")
        if not self._ser or not self._ser.is_open:
            raise DeviceError("未连接设备")
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write(f"IMG_BEGIN {FRAME_BYTES}\n".encode())
            self._ser.flush()
            deadline = time.time() + 3.0
            buf = ""
            while time.time() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    buf += chunk.decode("utf-8", "ignore")
                    if "OK send" in buf:
                        break
            else:
                raise DeviceError(f"IMG_BEGIN 失败: {buf[-200:]!r}")

            # Send binary in chunks
            for i in range(0, len(data), 256):
                self._ser.write(data[i : i + 256])
                self._ser.flush()
                time.sleep(0.005)

            deadline = time.time() + 8.0
            buf = ""
            while time.time() < deadline:
                chunk = self._ser.read(256)
                if chunk:
                    buf += chunk.decode("utf-8", "ignore")
                    for raw in buf.splitlines():
                        s = raw.strip()
                        if s.startswith("OK") or s.startswith("ERR"):
                            return s
                else:
                    time.sleep(0.02)
            raise DeviceError(f"图片上传超时: {buf[-200:]!r}")


_device = Quote0Device()


def get_device() -> Quote0Device:
    return _device
