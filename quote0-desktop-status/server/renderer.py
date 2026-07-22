from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from config import BLACK, BUFFER_SIZE, HEIGHT, WHITE, WIDTH


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
        # Linux
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/TTF/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    text = " ".join((text or "").split())
    if not text:
        return []
    lines: list[str] = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, pct: float) -> None:
    pct = max(0.0, min(100.0, pct))
    draw.rectangle([x, y, x + w, y + h], outline=0, width=1)
    fill_w = int((w - 2) * (pct / 100.0))
    if fill_w > 0:
        draw.rectangle([x + 1, y + 1, x + 1 + fill_w, y + h - 1], fill=0)


def render_mc_image(mc: dict) -> Image.Image:
    """Minecraft players page — portrait 152x296."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)
    draw = ImageDraw.Draw(img)
    title_f = _font(16)
    body_f = _font(13)
    small_f = _font(11)

    y = 6
    draw.text((8, y), "Minecraft", font=title_f, fill=0)
    y += 22
    draw.line([(8, y), (WIDTH - 8, y)], fill=0, width=1)
    y += 8

    host = str(mc.get("host") or "?")
    port = mc.get("port") or 25565
    draw.text((8, y), f"{host}:{port}", font=small_f, fill=0)
    y += 16

    if not mc.get("online"):
        draw.text((8, y), "OFFLINE", font=title_f, fill=0)
        y += 22
        for line in _wrap(draw, str(mc.get("error") or "unreachable"), small_f, WIDTH - 16)[:4]:
            draw.text((8, y), line, font=small_f, fill=0)
            y += 13
        draw.text((8, HEIGHT - 16), "page mc", font=small_f, fill=0)
        return img

    online = int(mc.get("players_online") or 0)
    mx = int(mc.get("players_max") or 0)
    draw.text((8, y), f"Players  {online} / {mx}", font=body_f, fill=0)
    y += 18
    if mx > 0:
        _bar(draw, 8, y, WIDTH - 16, 10, 100.0 * online / mx)
        y += 16

    ver = str(mc.get("version") or "")
    if ver:
        draw.text((8, y), ver[:28], font=small_f, fill=0)
        y += 14
    lat = mc.get("latency_ms")
    if lat is not None:
        draw.text((8, y), f"ping {lat:.0f} ms", font=small_f, fill=0)
        y += 16

    motd = str(mc.get("motd") or "")
    if motd:
        for line in _wrap(draw, motd, small_f, WIDTH - 16)[:2]:
            draw.text((8, y), line, font=small_f, fill=0)
            y += 13
        y += 4

    draw.line([(8, y), (WIDTH - 8, y)], fill=0, width=1)
    y += 8
    draw.text((8, y), "Online list", font=body_f, fill=0)
    y += 18

    players = list(mc.get("players") or [])
    if not players:
        draw.text((8, y), "(no sample names)", font=small_f, fill=0)
        y += 14
        draw.text((8, y), "server hid player list", font=small_f, fill=0)
    else:
        for name in players:
            if y > HEIGHT - 28:
                draw.text((8, y), "...", font=small_f, fill=0)
                break
            # strip legacy Minecraft formatting codes §x
            out: list[str] = []
            skip = False
            for ch in str(name):
                if skip:
                    skip = False
                    continue
                if ch == "§":
                    skip = True
                    continue
                if ord(ch) >= 32:
                    out.append(ch)
            clean = "".join(out) or str(name)
            draw.text((8, y), f"· {clean}"[:22], font=small_f, fill=0)
            y += 14

    draw.text((8, HEIGHT - 16), "page mc", font=small_f, fill=0)
    return img


def render_status_image(host: dict, agent: dict) -> Image.Image:
    """Portrait 152x296, black on white."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)
    draw = ImageDraw.Draw(img)
    title_f = _font(16)
    body_f = _font(13)
    small_f = _font(11)

    y = 6
    draw.text((8, y), "Quote/0 · PC", font=title_f, fill=0)
    y += 22
    draw.line([(8, y), (WIDTH - 8, y)], fill=0, width=1)
    y += 8

    draw.text((8, y), f"{host.get('hostname', '?')}", font=body_f, fill=0)
    y += 16
    draw.text((8, y), f"{host.get('ip', '')}  {host.get('time', '')}", font=small_f, fill=0)
    y += 18

    cpu = float(host.get("cpu_percent") or 0)
    mem = float(host.get("mem_percent") or 0)
    draw.text((8, y), f"CPU {cpu:.0f}%", font=small_f, fill=0)
    y += 14
    _bar(draw, 8, y, WIDTH - 16, 10, cpu)
    y += 16
    draw.text(
        (8, y),
        f"MEM {mem:.0f}%  {host.get('mem_used_gb')} / {host.get('mem_total_gb')}G",
        font=small_f,
        fill=0,
    )
    y += 14
    _bar(draw, 8, y, WIDTH - 16, 10, mem)
    y += 16

    load = host.get("load_1m")
    load_s = f"load {load}" if load is not None else ""
    draw.text(
        (8, y),
        f"up {host.get('uptime_human', '?')}  {load_s}".strip(),
        font=small_f,
        fill=0,
    )
    y += 20

    draw.line([(8, y), (WIDTH - 8, y)], fill=0, width=1)
    y += 8
    draw.text((8, y), "Cursor Agent", font=title_f, fill=0)
    y += 20

    state = str(agent.get("state", "idle"))
    badge = {"working": "WORKING", "active": "ACTIVE", "idle": "IDLE"}.get(state, state.upper())
    draw.rectangle([8, y, 8 + 70, y + 16], outline=0, width=1)
    if state == "working":
        draw.rectangle([9, y + 1, 8 + 69, y + 15], fill=0)
        draw.text((14, y + 1), badge, font=small_f, fill=1)
    else:
        draw.text((14, y + 1), badge, font=small_f, fill=0)
    draw.text((84, y + 2), str(agent.get("last_update", "")), font=small_f, fill=0)
    y += 22

    draw.text((8, y), f"proj: {agent.get('project', '—')}", font=small_f, fill=0)
    y += 16

    for line in _wrap(draw, str(agent.get("title", "")), body_f, WIDTH - 16)[:3]:
        draw.text((8, y), line, font=body_f, fill=0)
        y += 15

    y += 4
    for line in _wrap(draw, str(agent.get("snippet", "")), small_f, WIDTH - 16)[:5]:
        if y > HEIGHT - 28:
            break
        draw.text((8, y), line, font=small_f, fill=0)
        y += 13

    draw.text((8, HEIGHT - 16), "page desk", font=small_f, fill=0)
    return img


def image_to_uc8251d_buffer(img: Image.Image) -> bytes:
    """Pack 1-bit image to UC8251D buffer: bit1=white, bit0=black, MSB first."""
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT))
    if img.mode != "1":
        img = img.convert("1")

    pixels = img.load()
    buf = bytearray([0xFF] * BUFFER_SIZE)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            val = pixels[x, y]
            if val == 0:  # black pixel
                idx = y * WIDTH + x
                buf[idx // 8] &= ~(1 << (7 - (idx % 8)))
    return bytes(buf)


def render_page_image(page: str, host: dict, agent: dict, mc: dict) -> Image.Image:
    if page == "cover":
        from settings_store import load_cover_bin

        raw = load_cover_bin()
        if raw:
            # Unpack UC8251D buffer back to 1-bit image for preview path;
            # for frame.bin we short-circuit in render_frame_bin.
            img = Image.new("1", (WIDTH, HEIGHT), color=1)
            px = img.load()
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    idx = y * WIDTH + x
                    bit = (raw[idx // 8] >> (7 - (idx % 8))) & 1
                    px[x, y] = 255 if bit else 0
            return img
        # Fallback placeholder
        img = Image.new("1", (WIDTH, HEIGHT), color=1)
        draw = ImageDraw.Draw(img)
        draw.text((8, 8), "Cover", font=_font(16), fill=0)
        draw.text((8, 32), "(no image)", font=_font(13), fill=0)
        return img
    if page == "mc":
        return render_mc_image(mc)
    return render_status_image(host, agent)


def render_frame_bin(page: str, host: dict, agent: dict, mc: dict) -> bytes:
    if page == "cover":
        from settings_store import load_cover_bin

        raw = load_cover_bin()
        if raw and len(raw) == BUFFER_SIZE:
            return raw
    return image_to_uc8251d_buffer(render_page_image(page, host, agent, mc))


def render_preview_png(page: str, host: dict, agent: dict, mc: dict) -> bytes:
    img = render_page_image(page, host, agent, mc).convert("L")
    preview = img.resize((WIDTH * 2, HEIGHT * 2), Image.NEAREST)
    bio = BytesIO()
    preview.save(bio, format="PNG")
    return bio.getvalue()
