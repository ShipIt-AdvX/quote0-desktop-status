# Quote/0 USB 配置门户（跑在电脑上）

插上设备 USB 后：

```bash
cd ~/quote0-desktop-status/portal
./run.sh
```

浏览器打开 **http://0.1.2.3:8080** → 点「连接」，即可改 WiFi / 服务端 / 图片。

同时建议开状态服务：

```bash
cd ~/quote0-desktop-status/server
.venv/bin/python main.py
```

服务端地址填电脑局域网 IP（不要填 0.1.2.3）。
