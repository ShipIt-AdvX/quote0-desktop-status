# Quote/0 Windows 一键版

## 用法

1. 安装 [Python 3.11+](https://www.python.org/downloads/)（勾选 Add python.exe to PATH）
2. 双击 **`start.bat`**
3. 浏览器打开 **http://localhost:7891**

## 配置页功能

- 查看本机局域网 IP（写给墨水屏设备当服务端）
- 修改 **Minecraft 服务器** 地址/端口
- 上传 **首页图（cover）**：与 desk / mc 每 30 秒轮播
- （可选）USB 连接设备，写入 WiFi / 服务端 IP

## 端口

| 用途 | 地址 |
|------|------|
| 配置网页 | `http://localhost:7891` |
| 设备拉帧 / 发现 | `0.0.0.0:8787`（TCP）与 UDP `18787` |

首次使用请在 Windows 防火墙放行 **8787/TCP** 和 **18787/UDP**。

## 固件管理（配置页底部）

- **备份当前固件**：整片 4MB 读出，保存在 `windows/data/backups/`，可下载
- **写入第三方固件**：烧录自带的桌面状态固件（`windows/firmware/custom/`）
- **还原原版 Quote/0**：烧录 `windows/firmware/stock_full_4mb.bin`
- **写入所选文件**：可上传任意 `.bin`（整片或仅应用区）

烧录前请先「断开设备串口」。原版镜像约 4MB，请随本目录一起拷贝到 Windows。
