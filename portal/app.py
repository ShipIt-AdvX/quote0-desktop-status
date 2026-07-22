from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from device import DeviceError, FRAME_BYTES, get_device
from image_util import frame_to_png_preview, image_to_frame

PORTAL_HOST = os.environ.get("QUOTE0_PORTAL_HOST", "0.1.2.3")
PORTAL_PORT = int(os.environ.get("QUOTE0_PORTAL_PORT", "80"))

app = FastAPI(title="Quote/0 USB 配置门户", version="1.0.0")
_last_preview: bytes | None = None


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quote/0 配置</title>
<style>
  :root { --bg:#f4f0e8; --ink:#1a1a1a; --line:#c9c0b0; --acc:#0b5fff; --ok:#1b7f4a; --bad:#b33; }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 "IBM Plex Sans","Noto Sans SC",system-ui,sans-serif;background:var(--bg);color:var(--ink)}
  header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--line);background:#fff8}
  h1{margin:0;font:600 1.35rem/1.2 "IBM Plex Serif","Noto Serif SC",serif}
  main{max-width:920px;margin:0 auto;padding:1.25rem 1.5rem 3rem;display:grid;gap:1.25rem}
  section{background:#fff;border:1px solid var(--line);padding:1rem 1.1rem}
  h2{margin:0 0 .75rem;font-size:1.05rem}
  .row{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.4rem 0}
  input,button,select{font:inherit;padding:.45rem .65rem;border:1px solid var(--line);background:#fff}
  button{cursor:pointer;background:var(--acc);color:#fff;border-color:var(--acc)}
  button.secondary{background:#fff;color:var(--ink)}
  button.danger{background:var(--bad);border-color:var(--bad)}
  .status{font-size:.9rem;opacity:.85}
  .ok{color:var(--ok)} .err{color:var(--bad)}
  ul{margin:.4rem 0;padding-left:1.1rem}
  img.preview{border:1px solid var(--line);image-rendering:pixelated;max-width:100%;height:auto;background:#ddd}
  .grid2{display:grid;gap:1rem;grid-template-columns:1fr}
  @media(min-width:760px){.grid2{grid-template-columns:1fr 220px}}
  code{background:#eee;padding:.1rem .3rem}
</style>
</head>
<body>
<header>
  <h1>Quote/0 配置门户</h1>
  <p class="status">插上 USB 后访问 <code>http://0.1.2.3:8080</code> · 经串口写入设备（配置跑在电脑上）</p>
</header>
<main>
  <section>
    <h2>设备连接</h2>
    <div class="row">
      <select id="port"></select>
      <button onclick="connect()">连接</button>
      <button class="secondary" onclick="refresh()">刷新状态</button>
      <span id="conn" class="status">未连接</span>
    </div>
    <pre id="raw" class="status" style="white-space:pre-wrap;margin:.6rem 0 0"></pre>
  </section>

  <section>
    <h2>WiFi 列表</h2>
    <p class="status">可保存多个网络，设备会按顺序尝试连接。</p>
    <ul id="wifi"></ul>
    <div class="row">
      <input id="ssid" placeholder="SSID" style="min-width:10rem">
      <input id="pass" placeholder="密码（开放网络可空）" style="min-width:12rem">
      <button onclick="wifiAdd()">添加 / 更新</button>
    </div>
  </section>

  <section>
    <h2>服务端地址</h2>
    <p class="status" id="pcinfo">检测本机状态服务…</p>
    <div class="row">
      <input id="host" placeholder="本机局域网 IP，不是 0.1.2.3" style="min-width:12rem">
      <input id="sport" type="number" value="8787" style="width:6rem">
      <input id="poll" type="number" value="30" style="width:5rem" title="轮询秒">
      <button class="secondary" onclick="useLanIp()">填入本机 IP</button>
      <button onclick="setServer()">写入设备</button>
    </div>
    <p class="status">注意：<code>0.1.2.3</code> 只是配置网页地址；设备要连的是电脑的局域网 IP（例如 <code>10.x.x.x</code>），且电脑需先运行 <code>server/main.py</code>。</p>
  </section>

  <section>
    <h2>墨水屏图片</h2>
    <div class="grid2">
      <div>
        <div class="row">
          <input type="file" id="file" accept="image/*">
          <label><input type="checkbox" id="invert"> 反色</label>
          <button onclick="uploadImg()">上传并显示</button>
        </div>
        <div class="row">
          <button class="secondary" onclick="setMode('image')">只用图片</button>
          <button class="secondary" onclick="setMode('server')">拉 PC 状态</button>
          <button class="danger" onclick="clearImg()">清除图片</button>
        </div>
      </div>
      <div>
        <img class="preview" id="prev" alt="预览" width="152" height="296">
      </div>
    </div>
  </section>

  <section>
    <h2>保存</h2>
    <div class="row">
      <button onclick="save()">保存到设备</button>
      <button class="secondary" onclick="reboot()">重启设备</button>
      <span id="msg" class="status"></span>
    </div>
  </section>
</main>
<script>
async function api(path, opts){
  const r = await fetch(path, opts);
  const j = await r.json().catch(()=>({ok:false,error:'bad json'}));
  const err = j.error || (j.detail && (j.detail.error || j.detail)) || r.statusText;
  if(!r.ok || j.ok===false) throw new Error(typeof err==='string'?err:JSON.stringify(err));
  return j;
}
function msg(t, ok){ const el=document.getElementById('msg'); el.textContent=t; el.className='status '+(ok?'ok':'err'); }
async function loadPorts(){
  const j = await api('/api/ports');
  const sel = document.getElementById('port');
  sel.innerHTML = j.ports.map(p=>`<option value="${p}">${p}</option>`).join('') || '<option value="">(无设备)</option>';
}
async function connect(){
  try{
    const port = document.getElementById('port').value;
    const j = await api('/api/connect', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({port})});
    document.getElementById('conn').textContent = '已连接 '+j.port;
    document.getElementById('conn').className = 'status ok';
    await refresh();
    msg('已连接', true);
  }catch(e){ msg(e.message,false); document.getElementById('conn').textContent='连接失败'; document.getElementById('conn').className='status err'; }
}
async function refresh(){
  const j = await api('/api/status');
  document.getElementById('raw').textContent = JSON.stringify(j.config, null, 2);
  const ul = document.getElementById('wifi');
  ul.innerHTML = (j.config.wifi||[]).map(w=>`<li>${w.ssid} ${w.has_pass?'🔒':'(开放)'} <button class="secondary" onclick="wifiDel('${w.ssid.replace(/'/g,"\\'")}')">删除</button></li>`).join('') || '<li>（空）</li>';
  if(j.config.server_host) document.getElementById('host').value = j.config.server_host;
  if(j.config.server_port) document.getElementById('sport').value = j.config.server_port;
  if(j.config.poll_sec) document.getElementById('poll').value = j.config.poll_sec;
}
async function wifiAdd(){
  try{
    await api('/api/wifi/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ssid:ssid.value, password:pass.value})});
    pass.value=''; await refresh(); msg('已添加 WiFi', true);
  }catch(e){ msg(e.message,false); }
}
async function wifiDel(ssid){
  try{ await api('/api/wifi/del', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ssid})}); await refresh(); msg('已删除', true);}catch(e){msg(e.message,false);}
}
async function setServer(){
  try{
    await api('/api/server', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({host:host.value, port:+sport.value, poll:+poll.value})});
    await refresh(); msg('服务端已写入', true);
  }catch(e){msg(e.message,false);}
}
async function uploadImg(){
  const f = document.getElementById('file').files[0];
  if(!f){ msg('请选择图片', false); return; }
  const fd = new FormData(); fd.append('file', f); fd.append('invert', invert.checked?'1':'0');
  try{
    const r = await fetch('/api/image', {method:'POST', body:fd});
    const j = await r.json();
    if(!r.ok||j.ok===false) throw new Error(j.error||'upload failed');
    document.getElementById('prev').src = '/api/preview.png?t='+Date.now();
    await refresh(); msg('图片已上传并显示', true);
  }catch(e){msg(e.message,false);}
}
async function setMode(mode){
  try{ await api('/api/mode', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode})}); await refresh(); msg('模式: '+mode, true);}catch(e){msg(e.message,false);}
}
async function clearImg(){
  try{ await api('/api/image', {method:'DELETE'}); document.getElementById('prev').removeAttribute('src'); await refresh(); msg('已清除', true);}catch(e){msg(e.message,false);}
}
async function save(){ try{ await api('/api/save', {method:'POST'}); msg('已保存', true);}catch(e){msg(e.message,false);} }
async function reboot(){ try{ await api('/api/reboot', {method:'POST'}); msg('正在重启…', true);}catch(e){msg(e.message,false);} }
async function loadPcInfo(){
  try{
    const j = await api('/api/pcinfo');
    const el = document.getElementById('pcinfo');
    window._lanIp = j.lan_ip;
    if(j.server_up){
      el.innerHTML = '本机局域网 IP: <code>'+j.lan_ip+'</code> · 状态服务 <span class="ok">:8787 在线</span>';
      el.className = 'status ok';
    }else{
      el.innerHTML = '本机局域网 IP: <code>'+j.lan_ip+'</code> · 状态服务 <span class="err">未运行</span>（请先: cd server && .venv/bin/python main.py）';
      el.className = 'status err';
    }
  }catch(e){ document.getElementById('pcinfo').textContent = e.message; }
}
function useLanIp(){ if(window._lanIp){ host.value = window._lanIp; sport.value = 8787; } }
loadPorts(); loadPcInfo();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/ports")
def ports():
    from device import Quote0Device

    return {"ok": True, "ports": Quote0Device.find_ports()}


@app.get("/api/pcinfo")
def pcinfo():
    import socket
    import urllib.request

    lan = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except OSError:
        pass

    server_up = False
    for url in (f"http://{lan}:8787/health", "http://127.0.0.1:8787/health"):
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    server_up = True
                    break
        except Exception:
            continue

    return {"ok": True, "lan_ip": lan, "server_up": server_up, "server_port": 8787}


@app.post("/api/connect")
def connect(body: dict):
    dev = get_device()
    try:
        port = dev.connect(body.get("port") or None)
        return {"ok": True, "port": port}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.get("/api/status")
def status():
    dev = get_device()
    if not dev.connected:
        raise HTTPException(400, detail={"ok": False, "error": "未连接设备"})
    try:
        line = dev.get_json_line()
        cfg = json.loads(line)
        return {"ok": True, "config": cfg}
    except (DeviceError, json.JSONDecodeError) as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/wifi/add")
def wifi_add(body: dict):
    dev = get_device()
    try:
        msg = dev.wifi_add(body.get("ssid", ""), body.get("password", ""))
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/wifi/del")
def wifi_del(body: dict):
    dev = get_device()
    try:
        msg = dev.wifi_del(body.get("ssid", ""))
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/server")
def set_server(body: dict):
    dev = get_device()
    try:
        host = body.get("host", "")
        port = int(body.get("port", 8787))
        poll = int(body.get("poll", 30))
        m1 = dev.set_server(host, port)
        m2 = dev.set_poll(poll)
        if m1.startswith("ERR") or m2.startswith("ERR"):
            raise DeviceError(m1 + " / " + m2)
        return {"ok": True, "msg": m1}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/mode")
def set_mode(body: dict):
    dev = get_device()
    try:
        msg = dev.set_mode(body.get("mode", "server"))
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/image")
async def upload_image(file: UploadFile = File(...), invert: str = Form("0")):
    global _last_preview
    dev = get_device()
    raw = await file.read()
    try:
        frame = image_to_frame(raw, invert=invert in ("1", "true", "on"))
        _last_preview = frame_to_png_preview(frame)
        msg = dev.upload_frame(frame)
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg, "bytes": FRAME_BYTES}
    except Exception as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.delete("/api/image")
def delete_image():
    global _last_preview
    dev = get_device()
    try:
        msg = dev.img_clear()
        _last_preview = None
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.get("/api/preview.png")
def preview_png():
    if not _last_preview:
        raise HTTPException(404, detail="no preview")
    return Response(content=_last_preview, media_type="image/png")


@app.post("/api/save")
def save():
    dev = get_device()
    try:
        msg = dev.save()
        if msg.startswith("ERR"):
            raise DeviceError(msg)
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        raise HTTPException(400, detail={"ok": False, "error": str(e)}) from e


@app.post("/api/reboot")
def reboot():
    """Device resets USB on reboot — treat disconnect as success."""
    dev = get_device()
    try:
        msg = dev.reboot()
        return {"ok": True, "msg": msg}
    except DeviceError as e:
        return {"ok": True, "msg": f"rebooting ({e})"}


def ensure_portal_ip(ip: str = "0.1.2.3") -> None:
    """Best-effort: add 0.1.2.3 to loopback so the browser can open it."""
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", "dev", "lo"], text=True)
        if ip in out:
            return
        subprocess.run(["ip", "addr", "add", f"{ip}/32", "dev", "lo"], check=False)
    except Exception:
        pass


def main():
    import uvicorn

    ensure_portal_ip(PORTAL_HOST)
    print(f"Quote/0 portal → http://{PORTAL_HOST}:{PORTAL_PORT}/", flush=True)
    print("插上设备后点「连接」，即可改 WiFi / 服务端 / 图片。", flush=True)
    uvicorn.run(app, host=PORTAL_HOST, port=PORTAL_PORT, log_level="info")


if __name__ == "__main__":
    main()
