"""Windows / local admin UI on http://localhost:7891"""

from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "portal"))

from config import ADMIN_PORT, PORT  # noqa: E402
from host_info import primary_ip  # noqa: E402
from settings_store import (  # noqa: E402
    clear_cover,
    has_cover,
    load_settings,
    save_cover_bin,
    save_settings,
)

try:
    from device import DeviceError, FRAME_BYTES, Quote0Device, get_device
    from image_util import frame_to_png_preview, image_to_frame

    HAS_DEVICE = True
except Exception:
    HAS_DEVICE = False
    DeviceError = RuntimeError  # type: ignore
    FRAME_BYTES = 5624

app = FastAPI(title="Quote/0 配置", version="1.0.0")
_last_device_preview: bytes | None = None
_last_cover_preview: bytes | None = None


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quote/0 配置</title>
<style>
  :root { --bg:#f4f0e8; --ink:#1a1a1a; --line:#c9c0b0; --acc:#0b5fff; --ok:#1b7f4a; --bad:#b33; }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 "Segoe UI","Microsoft YaHei",system-ui,sans-serif;background:var(--bg);color:var(--ink)}
  header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--line);background:#fff8}
  h1{margin:0;font-size:1.35rem}
  main{max-width:960px;margin:0 auto;padding:1.25rem 1.5rem 3rem;display:grid;gap:1rem}
  section{background:#fff;border:1px solid var(--line);padding:1rem 1.1rem}
  h2{margin:0 0 .75rem;font-size:1.05rem}
  .row{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.4rem 0}
  input,button,select{font:inherit;padding:.45rem .65rem;border:1px solid var(--line);background:#fff}
  button{cursor:pointer;background:var(--acc);color:#fff;border-color:var(--acc)}
  button.secondary{background:#fff;color:var(--ink)}
  button.danger{background:var(--bad);border-color:var(--bad)}
  .s{font-size:.9rem;opacity:.85}.ok{color:var(--ok)}.err{color:var(--bad)}
  code{background:#eee;padding:.1rem .3rem}
  img.preview{border:1px solid var(--line);image-rendering:pixelated;background:#ddd}
  ul{margin:.4rem 0;padding-left:1.1rem}
  .grid2{display:grid;gap:1rem}@media(min-width:760px){.grid2{grid-template-columns:1fr 200px}}
</style>
</head>
<body>
<header>
  <h1>Quote/0 配置</h1>
  <p class="s">本页 <code>http://localhost:7891</code> · 设备拉帧端口 <code>8787</code> · 轮播页每 30 秒切换</p>
</header>
<main>
  <section>
    <h2>本机状态</h2>
    <p class="s" id="pcinfo">加载中…</p>
    <p class="s">把设备「服务端地址」写成下面的局域网 IP + 端口 8787。</p>
  </section>

  <section>
    <h2>Minecraft 服务器</h2>
    <div class="row">
      <input id="mc_host" placeholder="主机" style="min-width:14rem">
      <input id="mc_port" type="number" value="25565" style="width:6rem">
      <button onclick="saveMc()">保存</button>
    </div>
    <span id="mcmsg" class="s"></span>
  </section>

  <section>
    <h2>首页图（cover）</h2>
    <p class="s">上传后会与 desk / mc 一起每 30 秒轮播一页。</p>
    <div class="grid2">
      <div>
        <div class="row">
          <input type="file" id="cover_file" accept="image/*">
          <label><input type="checkbox" id="cover_inv"> 反色</label>
          <button onclick="uploadCover()">上传首页图</button>
          <button class="danger" onclick="clearCover()">清除</button>
        </div>
      </div>
      <img class="preview" id="cover_prev" width="152" height="296" alt="cover">
    </div>
    <span id="covermsg" class="s"></span>
  </section>

  <section>
    <h2>USB 设备（可选）</h2>
    <p class="s">插上 Quote/0 后连接，可写 WiFi / 服务端到设备。</p>
    <div class="row">
      <select id="port"></select>
      <button onclick="connect()">连接设备</button>
      <button class="secondary" onclick="refreshDev()">刷新</button>
      <span id="conn" class="s">未连接</span>
    </div>
    <ul id="wifi"></ul>
    <div class="row">
      <input id="ssid" placeholder="SSID">
      <input id="pass" placeholder="密码可空">
      <button onclick="wifiAdd()">添加 WiFi</button>
    </div>
    <div class="row">
      <input id="dev_host" placeholder="电脑局域网 IP">
      <input id="dev_sport" type="number" value="8787" style="width:5rem">
      <button class="secondary" onclick="fillLan()">填本机IP</button>
      <button onclick="setDevServer()">写入服务端</button>
      <button onclick="saveDev()">保存到设备</button>
      <button class="secondary" onclick="rebootDev()">重启设备</button>
    </div>
    <pre id="raw" class="s" style="white-space:pre-wrap"></pre>
    <span id="devmsg" class="s"></span>
  </section>

  <section>
    <h2>固件管理</h2>
    <p class="s">烧录前请先点「断开设备串口」。整片备份/还原约需 1–2 分钟，请勿拔线。</p>
    <div class="row">
      <select id="fw_port"></select>
      <button class="secondary" onclick="loadFwPorts()">刷新串口</button>
      <button class="secondary" onclick="disconnectDev()">断开设备串口</button>
    </div>
    <div class="row">
      <button onclick="fwBackup()">备份当前固件</button>
      <button onclick="fwFlashCustom()">写入第三方固件（桌面状态版）</button>
      <button class="danger" onclick="fwRestoreStock()">还原原版 Quote/0</button>
    </div>
    <div class="row">
      <input type="file" id="fw_file" accept=".bin">
      <select id="fw_mode">
        <option value="auto">自动识别</option>
        <option value="full">整片 4MB</option>
        <option value="app">仅应用区 @0x20000</option>
      </select>
      <button onclick="fwUpload()">写入所选文件</button>
    </div>
    <p class="s" id="fwinfo">加载固件状态…</p>
    <ul id="fw_backups"></ul>
    <pre id="fwlog" class="s" style="white-space:pre-wrap;max-height:12rem;overflow:auto;background:#f7f7f7;padding:.5rem"></pre>
    <span id="fwmsg" class="s"></span>
  </section>
</main>
<script>
let lanIp='';
async function api(path, opts){
  const r=await fetch(path,opts);
  const j=await r.json().catch(()=>({ok:false,error:'bad json'}));
  const err=j.error||(j.detail&&(j.detail.error||j.detail))||r.statusText;
  if(!r.ok||j.ok===false) throw new Error(typeof err==='string'?err:JSON.stringify(err));
  return j;
}
function msg(id,t,ok){const el=document.getElementById(id);el.textContent=t;el.className='s '+(ok?'ok':'err');}
async function loadPc(){
  const j=await api('/api/pc');
  lanIp=j.lan_ip;
  const el=document.getElementById('pcinfo');
  el.innerHTML='局域网 IP: <code>'+j.lan_ip+'</code> · 状态服务 '+(j.server_up?'<span class=ok>:8787 在线</span>':'<span class=err>:8787 离线</span>')+
    ' · 轮播页: <code>'+(j.pages||[]).join(', ')+'</code>';
  document.getElementById('mc_host').value=j.settings.mc_host||'';
  document.getElementById('mc_port').value=j.settings.mc_port||25565;
  document.getElementById('dev_host').value=j.lan_ip;
  if(j.has_cover) document.getElementById('cover_prev').src='/api/cover.png?t='+Date.now();
}
async function saveMc(){
  try{
    await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mc_host:mc_host.value,mc_port:+mc_port.value})});
    msg('mcmsg','已保存 MC 地址',true); await loadPc();
  }catch(e){msg('mcmsg',e.message,false)}
}
async function uploadCover(){
  const f=cover_file.files[0]; if(!f){msg('covermsg','请选择图片',false);return}
  const fd=new FormData(); fd.append('file',f); fd.append('invert',cover_inv.checked?'1':'0');
  try{
    const r=await fetch('/api/cover',{method:'POST',body:fd}); const j=await r.json();
    if(!r.ok||j.ok===false) throw new Error(j.error||'fail');
    cover_prev.src='/api/cover.png?t='+Date.now();
    msg('covermsg','首页图已加入轮播',true); await loadPc();
  }catch(e){msg('covermsg',e.message,false)}
}
async function clearCover(){
  try{await api('/api/cover',{method:'DELETE'}); cover_prev.removeAttribute('src'); msg('covermsg','已清除',true); await loadPc();}
  catch(e){msg('covermsg',e.message,false)}
}
async function loadPorts(){
  try{const j=await api('/api/ports');
    const opts=(j.ports||[]).map(p=>`<option value="${p}">${p}</option>`).join('')||'<option value="">(无)</option>';
    port.innerHTML=opts; fw_port.innerHTML=opts;
  }catch(e){port.innerHTML='<option>(无串口库)</option>'; fw_port.innerHTML=port.innerHTML}
}
async function loadFwPorts(){ await loadPorts(); await loadFw(); }
async function connect(){
  try{const j=await api('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:port.value})});
    conn.textContent='已连接 '+j.port; conn.className='s ok'; msg('devmsg','已连接',true); await refreshDev();}
  catch(e){conn.textContent='失败'; conn.className='s err'; msg('devmsg',e.message,false)}
}
async function disconnectDev(){
  try{await api('/api/disconnect',{method:'POST'}); conn.textContent='已断开'; conn.className='s'; msg('devmsg','串口已释放，可烧录',true);}
  catch(e){msg('devmsg',e.message,false)}
}
async function refreshDev(){
  try{const j=await api('/api/device'); raw.textContent=JSON.stringify(j.config,null,2);
    wifi.innerHTML=(j.config.wifi||[]).map(w=>`<li>${w.ssid} ${w.has_pass?'🔒':''} <button class=secondary onclick="wifiDel('${w.ssid.replace(/'/g,"\\'")}')">删</button></li>`).join('')||'<li>(空)</li>';
    if(j.config.server_host) dev_host.value=j.config.server_host;
    if(j.config.server_port) dev_sport.value=j.config.server_port;
  }catch(e){msg('devmsg',e.message,false)}
}
async function wifiAdd(){try{await api('/api/wifi/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:ssid.value,password:pass.value})});pass.value='';await refreshDev();msg('devmsg','已添加',true)}catch(e){msg('devmsg',e.message,false)}}
async function wifiDel(s){try{await api('/api/wifi/del',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:s})});await refreshDev();msg('devmsg','已删',true)}catch(e){msg('devmsg',e.message,false)}}
function fillLan(){if(lanIp)dev_host.value=lanIp}
async function setDevServer(){try{await api('/api/device/server',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:dev_host.value,port:+dev_sport.value})});await refreshDev();msg('devmsg','服务端已写',true)}catch(e){msg('devmsg',e.message,false)}}
async function saveDev(){try{await api('/api/device/save',{method:'POST'});msg('devmsg','已保存',true)}catch(e){msg('devmsg',e.message,false)}}
async function rebootDev(){try{await api('/api/device/reboot',{method:'POST'});msg('devmsg','重启中',true)}catch(e){msg('devmsg',e.message,false)}}

async function loadFw(){
  try{
    const j=await api('/api/fw/status');
    fwinfo.innerHTML='原版镜像: '+(j.has_stock?'<span class=ok>已就绪</span>':'<span class=err>缺失</span>')+
      ' · 第三方固件: '+(j.has_custom?'<span class=ok>已就绪</span>':'<span class=err>缺失</span>');
    fw_backups.innerHTML=(j.backups||[]).map(b=>
      `<li>${b.name} (${Math.round(b.size/1048576*10)/10} MB, ${b.mtime})
       <a href="/api/fw/backup/${encodeURIComponent(b.name)}">下载</a>
       <button class="secondary" onclick="fwRestoreBackup('${b.name}')">用此备份恢复</button></li>`
    ).join('')||'<li>（暂无备份）</li>';
  }catch(e){fwinfo.textContent=e.message}
}
async function fwPost(path, body){
  msg('fwmsg','进行中，请稍候…',true); fwlog.textContent='';
  try{
    const j=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    fwlog.textContent=(j.log||j.msg||JSON.stringify(j)).slice(-2000);
    msg('fwmsg',j.msg||'完成',true); await loadFw();
  }catch(e){fwlog.textContent=e.message; msg('fwmsg',e.message,false)}
}
function fwPort(){return fw_port.value||port.value}
async function fwBackup(){await fwPost('/api/fw/backup',{port:fwPort()})}
async function fwFlashCustom(){if(!confirm('写入第三方桌面状态固件？'))return; await fwPost('/api/fw/flash-custom',{port:fwPort()})}
async function fwRestoreStock(){if(!confirm('还原原版 Quote/0？当前固件会被覆盖。'))return; await fwPost('/api/fw/restore-stock',{port:fwPort()})}
async function fwRestoreBackup(name){if(!confirm('用备份 '+name+' 整片恢复？'))return; await fwPost('/api/fw/restore-backup',{port:fwPort(),name})}
async function fwUpload(){
  const f=fw_file.files[0]; if(!f){msg('fwmsg','请选择 .bin',false);return}
  if(!confirm('写入文件 '+f.name+'？'))return;
  msg('fwmsg','上传并烧录中…',true); fwlog.textContent='';
  const fd=new FormData(); fd.append('file',f); fd.append('port',fwPort()); fd.append('mode',fw_mode.value);
  try{
    const r=await fetch('/api/fw/flash-upload',{method:'POST',body:fd});
    const j=await r.json(); if(!r.ok||j.ok===false) throw new Error(j.error||j.detail||r.statusText);
    fwlog.textContent=(j.log||'').slice(-2000); msg('fwmsg',j.msg||'完成',true); await loadFw();
  }catch(e){fwlog.textContent=e.message; msg('fwmsg',e.message,false)}
}
loadPc(); loadPorts(); loadFw();
</script>
</body>
</html>
"""


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1.2) as r:
            return r.status == 200
    except Exception:
        return False


def _pages() -> list[str]:
    pages = ["desk", "mc"]
    if has_cover():
        pages.append("cover")
    return pages


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/pc")
def pc():
    return {
        "ok": True,
        "lan_ip": primary_ip(),
        "server_up": _server_up(),
        "settings": load_settings(),
        "has_cover": has_cover(),
        "pages": _pages(),
        "status_port": PORT,
        "admin_port": ADMIN_PORT,
        "has_device_support": HAS_DEVICE,
    }


@app.post("/api/settings")
def settings(body: dict):
    return {"ok": True, "settings": save_settings(body)}


@app.post("/api/cover")
async def cover_upload(file: UploadFile = File(...), invert: str = Form("0")):
    global _last_cover_preview
    raw = await file.read()
    inv = invert in ("1", "true", "on", "True")
    if HAS_DEVICE:
        frame = image_to_frame(raw, invert=inv)
        _last_cover_preview = frame_to_png_preview(frame)
    else:
        from io import BytesIO

        from PIL import Image, ImageOps
        from renderer import BUFFER_SIZE, HEIGHT, WIDTH, render_preview_png

        img = Image.open(BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("L")
        img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        pixels = img.load()
        out = bytearray(BUFFER_SIZE)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                white = pixels[x, y] != 0
                if inv:
                    white = not white
                if white:
                    idx = y * WIDTH + x
                    out[idx // 8] |= 1 << (7 - (idx % 8))
        frame = bytes(out)
        save_cover_bin(frame)
        _last_cover_preview = render_preview_png("cover", {}, {}, {})
        return {"ok": True, "bytes": len(frame)}
    save_cover_bin(frame)
    return {"ok": True, "bytes": len(frame)}


@app.delete("/api/cover")
def cover_delete():
    clear_cover()
    return {"ok": True}


@app.get("/api/cover.png")
def cover_png():
    global _last_cover_preview
    if _last_cover_preview:
        return Response(content=_last_cover_preview, media_type="image/png")
    try:
        from renderer import render_preview_png

        return Response(content=render_preview_png("cover", {}, {}, {}), media_type="image/png")
    except Exception:
        raise HTTPException(404, detail="no cover") from None


@app.get("/api/ports")
def ports():
    ports_list: list[str] = []
    if HAS_DEVICE:
        ports_list.extend(Quote0Device.find_ports())
    try:
        import firmware_tool as ft

        for p in ft.find_serial_ports():
            if p not in ports_list:
                ports_list.append(p)
    except Exception:
        pass
    return {"ok": True, "ports": ports_list}


@app.post("/api/disconnect")
def disconnect():
    if HAS_DEVICE:
        try:
            get_device().close()
        except Exception:
            pass
    return {"ok": True, "msg": "disconnected"}


@app.post("/api/connect")
def connect(body: dict):
    if not HAS_DEVICE:
        raise HTTPException(400, detail={"ok": False, "error": "未安装 pyserial"})
    try:
        port = get_device().connect(body.get("port") or None)
        return {"ok": True, "port": port}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.get("/api/device")
def device_status():
    if not HAS_DEVICE:
        raise HTTPException(400, detail={"ok": False, "error": "无设备支持"})
    dev = get_device()
    if not dev.connected:
        raise HTTPException(400, detail={"ok": False, "error": "未连接设备"})
    try:
        return {"ok": True, "config": json.loads(dev.get_json_line())}
    except Exception as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/wifi/add")
def wifi_add(body: dict):
    dev = get_device()
    msg = dev.wifi_add(body.get("ssid", ""), body.get("password", ""))
    if msg.startswith("ERR"):
        raise HTTPException(400, detail={"ok": False, "error": msg})
    return {"ok": True, "msg": msg}


@app.post("/api/wifi/del")
def wifi_del(body: dict):
    msg = get_device().wifi_del(body.get("ssid", ""))
    if msg.startswith("ERR"):
        raise HTTPException(400, detail={"ok": False, "error": msg})
    return {"ok": True, "msg": msg}


@app.post("/api/device/server")
def device_server(body: dict):
    msg = get_device().set_server(body.get("host", ""), int(body.get("port", 8787)))
    if msg.startswith("ERR"):
        raise HTTPException(400, detail={"ok": False, "error": msg})
    return {"ok": True, "msg": msg}


@app.post("/api/device/save")
def device_save():
    msg = get_device().save()
    if msg.startswith("ERR"):
        raise HTTPException(400, detail={"ok": False, "error": msg})
    return {"ok": True, "msg": msg}


@app.post("/api/device/reboot")
def device_reboot():
    try:
        return {"ok": True, "msg": get_device().reboot()}
    except DeviceError as e:
        return {"ok": True, "msg": f"rebooting ({e})"}


def _release_serial() -> None:
    if HAS_DEVICE:
        try:
            get_device().close()
        except Exception:
            pass


def _fw_port(body: dict | None = None) -> str:
    import firmware_tool as ft

    port = (body or {}).get("port") or ""
    if not port:
        found = ft.find_serial_ports()
        if not found:
            raise FirmwareError("未找到串口")
        port = found[0]
    return port


# late import name for errors
try:
    from firmware_tool import FirmwareError
except Exception:

    class FirmwareError(RuntimeError):  # type: ignore
        pass


@app.get("/api/fw/status")
def fw_status():
    import firmware_tool as ft

    return {
        "ok": True,
        "has_stock": ft.stock_available(),
        "has_custom": ft.custom_available(),
        "stock_path": str(ft.STOCK_PATH),
        "custom_dir": str(ft.CUSTOM_DIR),
        "backups": ft.list_backups(),
        "ports": ft.find_serial_ports(),
    }


@app.post("/api/fw/backup")
def fw_backup(body: dict):
    import firmware_tool as ft

    _release_serial()
    try:
        path = ft.backup_flash(_fw_port(body))
        return {"ok": True, "msg": f"已备份 {path.name}", "name": path.name, "log": str(path)}
    except FirmwareError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.get("/api/fw/backup/{name}")
def fw_backup_download(name: str):
    import firmware_tool as ft
    from fastapi.responses import FileResponse

    path = ft.BACKUP_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, detail="not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.post("/api/fw/restore-stock")
def fw_restore_stock(body: dict):
    import firmware_tool as ft

    _release_serial()
    try:
        log = ft.restore_stock(_fw_port(body))
        return {"ok": True, "msg": "已还原原版固件", "log": log[-2000:]}
    except FirmwareError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/fw/flash-custom")
def fw_flash_custom(body: dict):
    import firmware_tool as ft

    _release_serial()
    try:
        log = ft.flash_custom(_fw_port(body))
        return {"ok": True, "msg": "已写入第三方固件", "log": log[-2000:]}
    except FirmwareError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/fw/restore-backup")
def fw_restore_backup(body: dict):
    import firmware_tool as ft

    _release_serial()
    try:
        log = ft.restore_backup(_fw_port(body), body.get("name", ""))
        return {"ok": True, "msg": "已用备份恢复", "log": log[-2000:]}
    except FirmwareError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/fw/flash-upload")
async def fw_flash_upload(
    file: UploadFile = File(...),
    port: str = Form(""),
    mode: str = Form("auto"),
):
    import tempfile

    import firmware_tool as ft

    _release_serial()
    raw = await file.read()
    if not raw:
        raise HTTPException(400, detail={"ok": False, "error": "空文件"})
    suffix = Path(file.filename or "upload.bin").suffix or ".bin"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        body = {"port": port}
        log = ft.flash_upload(_fw_port(body), tmp_path, mode=mode)
        return {"ok": True, "msg": f"已写入 {file.filename}", "log": log[-2000:]}
    except FirmwareError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e
    finally:
        try:
            tmp_path.unlink(missing_ok=True)  # type: ignore[name-defined]
        except Exception:
            pass
