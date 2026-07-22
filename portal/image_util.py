"""Convert arbitrary images to Quote/0 152x296 1bpp frames."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

WIDTH = 152
HEIGHT = 296
FRAME_BYTES = (WIDTH * HEIGHT) // 8


def image_to_frame(data: bytes, invert: bool = False) -> bytes:
    img = Image.open(BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    # Cover fit
    img = ImageOps.fit(img, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    # Floyd–Steinberg dither to 1-bit
    img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    pixels = img.load()
    out = bytearray(FRAME_BYTES)
    # Driver: bit 1 = white, 0 = black (matches UC8251D convention in this project)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            # PIL 1-mode: 0=black, 255=white
            white = pixels[x, y] != 0
            if invert:
                white = not white
            if white:
                byte_index = (y * WIDTH + x) // 8
                bit = 7 - ((y * WIDTH + x) % 8)
                out[byte_index] |= 1 << bit
    return bytes(out)


def frame_to_png_preview(frame: bytes) -> bytes:
    if len(frame) != FRAME_BYTES:
        raise ValueError("bad frame size")
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    px = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_index = (y * WIDTH + x) // 8
            bit = 7 - ((y * WIDTH + x) % 8)
            white = (frame[byte_index] >> bit) & 1
            px[x, y] = 255 if white else 0
    buf = BytesIO()
    img.resize((WIDTH * 2, HEIGHT * 2), Image.Resampling.NEAREST).save(buf, format="PNG")
    return buf.getvalue()
