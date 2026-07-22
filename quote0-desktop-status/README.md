# Quote/0 Desktop Status

MindReset **Quote/0**（ESP32-C3 + UC8251D 墨水屏）第三方固件与配套服务：在墨水屏上轮播本机状态、Cursor Agent、Minecraft 玩家，并支持自定义首页图。

> 刷第三方固件会覆盖原厂系统。仓库内附带原厂 4MB 全盘镜像，可一键还原。

## 功能

| 功能 | 说明 |
|------|------|
| 桌面状态页 `desk` | CPU / 内存 / 本机 IP / Cursor Agent 工作状态 |
| Minecraft 页 `mc` | 在线人数、MOTD、玩家名单（可配置服务器地址） |
| 首页图 `cover` | 上传任意图片，与上两页一起每 30 秒轮播 |
| USB 配置门户 | 电脑端网页写 WiFi / 服务端地址 / 图片到设备 |
| 固件管理 | 备份整片 Flash、烧录本项目固件、还原原厂 |
| 省电策略 | 拉帧成功后关 WiFi，间隔后再开；屏幕保持上一帧 |

默认轮播间隔 **30 秒**（可改）。

## 架构

```
┌─────────────────────────────┐         WiFi / HTTP
│  PC                         │  /api/frame.bin
│  ├─ 状态服务   :8787        │ ──────────────────► Quote/0 固件
│  ├─ 配置页     :7891        │                         │
│  └─ UDP 发现   :18787       │                    UC8251D
└─────────────────────────────┘                   152 × 296
```

- **8787**：设备拉帧、预览、发现回复里的 HTTP 端口  
- **7891**：本机配置网页（Windows 一键启动）  
- **18787/UDP**：局域网自动发现 PC

## 目录结构

```
quote0-desktop-status/
├── firmware/          # ESP-IDF / PlatformIO 固件源码
├── server/            # 状态服务（系统信息 + MC + 渲染）
├── portal/            # Linux 下 USB 配置门户（可选）
└── windows/           # Windows 一键包（推荐日常使用）
    ├── start.bat      # 双击启动
    ├── firmware/
    │   ├── stock_full_4mb.bin   # 原厂全盘镜像
    │   └── custom/              # 本项目第三方固件
    └── data/          # 运行时设置、备份（本地生成）
```

## 快速开始（Windows，推荐）

1. 安装 [Python 3.11+](https://www.python.org/downloads/)，安装时勾选 **Add to PATH**  
2. 将本仓库完整拷贝到电脑（含 `windows/firmware/stock_full_4mb.bin`）  
3. 双击 `windows/start.bat`  
4. 浏览器打开 **http://localhost:7891**

在配置页可以：

- 查看本机局域网 IP（写给墨水屏当服务端）  
- 修改 Minecraft 地址  
- 上传首页图（cover）  
- USB 连接设备后写 WiFi / 服务端  
- **备份 / 烧录第三方 / 还原原厂固件**

Windows 防火墙请放行 **TCP 8787**、**UDP 18787**。

设备上的「服务端地址」填：`你的局域网IP` + 端口 `8787`（不要填 `localhost` 或 `7891`）。

## Linux：只跑状态服务

```bash
cd server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

预览：http://127.0.0.1:8787/  
配置（可选 USB 门户）：

```bash
cd portal
./run.sh
# 默认 http://0.1.2.3:8080 （需把 0.1.2.3 绑到 lo）
```

Minecraft 也可在配置页改；或用环境变量：

```bash
export MC_HOST=mc.example.com
export MC_PORT=25565
```

## 编译与烧录固件

依赖：[PlatformIO](https://platformio.org/)

```bash
cd firmware
# 如需代理下载工具链
export http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890

pio run -t upload --upload-port /dev/ttyACM0   # Linux
# Windows 串口多为 COM3、COM4 等
```

也可用配置页「写入第三方固件」，无需本地装 PlatformIO。

### 串口命令（备用）

波特率 115200：

```text
PING
GET_JSON
WIFI_ADD <ssid> [password]
SET_SERVER <host> <port>
SET_POLL 30
SET_MODE server|image
SAVE
REBOOT
```

## 固件行为摘要

1. 仅 STA 连场地 WiFi（配置通过 USB 网页写入）  
2. 连上后拉 `/api/frame.bin`，刷新墨水屏  
3. 成功后关闭 WiFi，保持画面约 `poll_sec`（默认 30s）  
4. 再开 WiFi 拉下一帧  

## 硬件

- 设备：MindReset Quote/0（ESP32-C3，约 2.66" 墨水屏）  
- 驱动：UC8251D，分辨率 **152×296**，1bpp  
- Flash：4MB  

## 还原原厂

配置页 → 固件管理 → **还原原版 Quote/0**（使用 `windows/firmware/stock_full_4mb.bin`）。

或手动：

```bash
esptool.py --chip esp32c3 --port <PORT> write-flash 0x0 windows/firmware/stock_full_4mb.bin
```

## 注意

- 刷机有风险；建议先「备份当前固件」再操作  
- 墨水屏全刷较慢，轮询不建议短于 15–30 秒  
- Cursor Agent 状态来自本机 `~/.cursor/projects/*/agent-transcripts/`  
- 本项目与 MindReset 官方无关，为个人/社区用途  

## License

按个人使用与分享目的提供；原厂固件镜像版权归 MindReset / 相关权利方所有，仅供备份与还原。
