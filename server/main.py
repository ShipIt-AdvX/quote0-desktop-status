from __future__ import annotations

import time
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, File, Form, Query, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image, ImageOps

from agent_status import agent_as_dict
from config import ADMIN_PORT, BUFFER_SIZE, PORT, runtime_page_rotate, runtime_poll_hint
from discovery import DISCOVER_PORT, start_discovery_thread
from host_info import host_as_dict, primary_ip
from mc_status import mc_as_dict
from renderer import HEIGHT, WIDTH, render_frame_bin, render_preview_png
from settings_store import (
    clear_cover,
    has_cover,
    load_cover_bin,
    load_settings,
    save_cover_bin,
    save_settings,
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_discovery_thread(PORT)
    yield


app = FastAPI(title="Quote/0 Desktop Status", version="0.4.0", lifespan=lifespan)


def page_list() -> list[str]:
    pages = ["desk", "mc"]
    if has_cover():
        pages.append("cover")
    return pages


def current_page(explicit: str | None = None) -> str:
    pages = page_list()
    if explicit in pages or explicit in ("desk", "mc", "cover"):
        if explicit == "cover" and not has_cover():
            return "desk"
        if explicit in ("desk", "mc", "cover"):
            return explicit
    rotate = max(1, runtime_page_rotate())
    slot = int(time.time()) // rotate
    return pages[slot % len(pages)]


def remaining_sec() -> int:
    period = max(1, runtime_page_rotate())
    return period - (int(time.time()) % period)


def _image_file_to_frame(data: bytes, invert: bool = False) -> bytes:
    img = Image.open(BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    pixels = img.load()
    out = bytearray(BUFFER_SIZE)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            white = pixels[x, y] != 0
            if invert:
                white = not white
            if white:
                idx = y * WIDTH + x
                out[idx // 8] |= 1 << (7 - (idx % 8))
    return bytes(out)


@app.get("/health")
def health():
    return {
        "ok": True,
        "poll_hint_sec": runtime_poll_hint(),
        "page_rotate_sec": runtime_page_rotate(),
        "page": current_page(),
        "pages": page_list(),
        "page_remaining_sec": remaining_sec(),
        "lan_ip": primary_ip(),
        "discover_udp_port": DISCOVER_PORT,
        "http_port": PORT,
        "admin_port": ADMIN_PORT,
        "has_cover": has_cover(),
        "settings": load_settings(),
    }


@app.get("/api/status")
def status(page: str | None = Query(default=None)):
    p = current_page(page)
    return JSONResponse(
        {
            "page": p,
            "pages": page_list(),
            "page_rotate_sec": runtime_page_rotate(),
            "page_remaining_sec": remaining_sec(),
            "host": host_as_dict(),
            "agent": agent_as_dict(),
            "mc": mc_as_dict(),
            "poll_hint_sec": runtime_poll_hint(),
            "has_cover": has_cover(),
        }
    )


@app.get("/api/frame.bin")
def frame_bin(page: str | None = Query(default=None)):
    p = current_page(page)
    host = host_as_dict()
    agent = agent_as_dict()
    mc = mc_as_dict()
    data = render_frame_bin(p, host, agent, mc)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(len(data)),
            "X-Quote0-Width": "152",
            "X-Quote0-Height": "296",
            "X-Quote0-Page": p,
            "X-Poll-Hint-Sec": str(runtime_poll_hint()),
            "X-Page-Rotate-Sec": str(runtime_page_rotate()),
            "Cache-Control": "no-store",
        },
    )


@app.get("/preview.png")
def preview_png(page: str | None = Query(default=None)):
    p = current_page(page)
    return Response(
        content=render_preview_png(p, host_as_dict(), agent_as_dict(), mc_as_dict()),
        media_type="image/png",
    )


@app.get("/api/settings")
def get_settings():
    return {"ok": True, "settings": load_settings(), "has_cover": has_cover(), "lan_ip": primary_ip()}


@app.post("/api/settings")
def post_settings(body: dict):
    s = save_settings(body)
    return {"ok": True, "settings": s}


@app.post("/api/cover")
async def upload_cover(file: UploadFile = File(...), invert: str = Form("0")):
    raw = await file.read()
    frame = _image_file_to_frame(raw, invert=invert in ("1", "true", "on", "True"))
    save_cover_bin(frame)
    return {"ok": True, "bytes": len(frame), "pages": page_list()}


@app.delete("/api/cover")
def delete_cover():
    clear_cover()
    return {"ok": True, "pages": page_list()}


@app.get("/api/cover.png")
def cover_preview():
    raw = load_cover_bin()
    if not raw:
        return Response(status_code=404)
    # reuse renderer unpack via preview
    png = render_preview_png("cover", {}, {}, {})
    return Response(content=png, media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def index():
    p = current_page()
    pages = ", ".join(page_list())
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Quote/0 Desktop Status</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}}
img{{border:1px solid #333;image-rendering:pixelated}}
code{{background:#f2f2f2;padding:0.1rem 0.3rem}}
</style></head><body>
<h1>Quote/0 Desktop Status</h1>
<p>当前页: <code>{p}</code>（每 {runtime_page_rotate()}s 轮播: {pages}）</p>
<p>配置页: <a href="http://127.0.0.1:{ADMIN_PORT}/">http://localhost:{ADMIN_PORT}</a></p>
<p>
<a href="/preview.png?page=desk">desk</a> ·
<a href="/preview.png?page=mc">mc</a> ·
<a href="/preview.png?page=cover">cover</a>
</p>
<p><img src="/preview.png" width="304" height="592" alt="preview"></p>
<script>setTimeout(()=>location.reload(), {runtime_poll_hint() * 1000});</script>
</body></html>"""


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
