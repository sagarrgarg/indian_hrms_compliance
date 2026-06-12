#!/usr/bin/env python3
"""Generate PWA brand assets (app icons + splash screens) for Indian HRMS & Compliance.

Recreates the finalized "i" monogram app icon from the Claude Design handoff
(Direction A): a single bold person figure (white circular head + rounded white
body + green ground line) on a saffron->terracotta gradient with a soft diagonal
sheen. Renders the square/maskable PWA icons and the cream launch splash screens.

Run from anywhere with a Python that has Pillow + numpy (the bench env has both):

    /home/ubuntu/bench1/env/bin/python frontend/branding/generate_brand_assets.py

Outputs overwrite the files under
indian_hrms_compliance/public/manifest/ that index.html and the PWA manifest
already reference, so no markup paths change.
"""

import glob
import os
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --- design tokens (icon, in the 0..100 design coordinate space) -------------
BG_TOP = (0xF4, 0xA0, 0x4A)   # saffron
BG_BOT = (0xE1, 0x6A, 0x2C)   # terracotta
WHITE = (0xFF, 0xFF, 0xFF, 0xFF)
GREEN = (0x1F, 0x8A, 0x5B, 0xFF)  # ground line
ROUND_RX = 22.3               # rounded-square corner radius (% of side)

# splash palette
CREAM_TOP = (0xFF, 0xFB, 0xF5)
CREAM_BOT = (0xFF, 0xF7, 0xEE)
INK = (0x3A, 0x2A, 0x1E)
MUTED = (0x9A, 0x86, 0x75)
GREEN_RGB = (0x1F, 0x8A, 0x5B)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(
    os.path.join(HERE, "..", "..", "indian_hrms_compliance", "public", "manifest")
)


def _font(size, bold=True):
    for name in (["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _bg_saffron(n):
    """Vertical saffron->terracotta gradient + diagonal white sheen, n x n RGB."""
    t = np.linspace(0, 1, n).reshape(n, 1, 1)
    top = np.array(BG_TOP, dtype="float32").reshape(1, 1, 3)
    bot = np.array(BG_BOT, dtype="float32").reshape(1, 1, 3)
    col = top * (1 - t) + bot * t          # n x 1 x 3
    bg = np.repeat(col, n, axis=1)          # n x n x 3
    xs = np.linspace(0, 1, n).reshape(1, n)
    ys = np.linspace(0, 1, n).reshape(n, 1)
    a = np.clip(1 - (xs + ys), 0, 1) * 0.18  # sheen alpha, peaks top-left
    bg = bg * (1 - a[..., None]) + 255.0 * a[..., None]
    return np.clip(bg, 0, 255).astype("uint8")


def _draw_glyph(n, scale=1.0):
    """The 3 figure shapes (head, body, ground line) on a transparent n x n layer."""
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = n / 100.0
    c = 50.0

    def sx(x):
        return (c + (x - c) * scale) * u

    def sr(r):
        return r * scale * u

    # head: circle cx=50 cy=31 r=11.5
    r = sr(11.5)
    hx, hy = sx(50), sx(31)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=WHITE)
    # body: rounded rect x=42.5 y=47 w=15 h=33 rx=7.5
    d.rounded_rectangle([sx(42.5), sx(47), sx(57.5), sx(80)], radius=sr(7.5), fill=WHITE)
    # ground line: green rounded rect x=33 y=83.5 w=34 h=6.4 rx=3.2
    d.rounded_rectangle([sx(33), sx(83.5), sx(67), sx(89.9)], radius=sr(3.2), fill=GREEN)
    return layer


def render_icon(n, glyph_scale=1.0, rounded=False):
    bg = Image.fromarray(_bg_saffron(n), "RGB").convert("RGBA")
    img = Image.alpha_composite(bg, _draw_glyph(n, glyph_scale))
    if not rounded:
        return img
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, n - 1, n - 1], radius=ROUND_RX * n / 100.0, fill=255
    )
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    inset = 0.6 * n / 100.0
    ImageDraw.Draw(out).rounded_rectangle(
        [inset, inset, n - 1 - inset, n - 1 - inset],
        radius=21.9 * n / 100.0,
        outline=(0, 0, 0, int(0.06 * 255)),
        width=max(1, round(1.2 * n / 100.0)),
    )
    return out


def _bg_cream(w, h):
    t = np.linspace(0, 1, h).reshape(h, 1, 1)
    top = np.array(CREAM_TOP, dtype="float32").reshape(1, 1, 3)
    bot = np.array(CREAM_BOT, dtype="float32").reshape(1, 1, 3)
    col = (top * (1 - t) + bot * t).astype("float32")
    arr = np.broadcast_to(col, (h, w, 3))
    return np.ascontiguousarray(np.clip(arr, 0, 255).astype("uint8"))


def render_splash(w, h, tile_rounded):
    s = min(w, h)
    img = Image.fromarray(_bg_cream(w, h), "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)
    cx = w // 2

    tile = round(0.30 * s)
    tile_img = tile_rounded.resize((tile, tile), Image.LANCZOS)

    f1 = _font(round(0.072 * s), bold=True)
    f2 = _font(round(0.033 * s), bold=True)
    wm1, wm2 = "Indian HRMS", "& COMPLIANCE"
    _, t1, _, b1 = f1.getbbox(wm1)
    h1 = b1 - t1
    _, t2, _, b2 = f2.getbbox(wm2)
    h2 = b2 - t2
    ls = 0.22 * round(0.033 * s)

    gap1, gap2 = round(0.06 * s), round(0.024 * s)
    group_h = tile + gap1 + h1 + gap2 + h2
    top = (h - group_h) // 2 - round(0.03 * h)

    # soft shadow under the tile
    sh = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [0, 0, tile - 1, tile - 1], radius=ROUND_RX * tile / 100.0, fill=(0, 0, 0, 26)
    )
    from PIL import ImageFilter

    sh = sh.filter(ImageFilter.GaussianBlur(max(1, round(0.012 * s))))
    img.alpha_composite(sh, (cx - tile // 2, top + max(1, round(0.012 * s))))
    img.alpha_composite(tile_img, (cx - tile // 2, top))

    y1 = top + tile + gap1 + h1 / 2
    draw.text((cx, y1), wm1, font=f1, fill=INK + (255,), anchor="mm")

    # letter-spaced wordmark line 2
    total = sum(f2.getlength(ch) for ch in wm2) + ls * (len(wm2) - 1)
    x = cx - total / 2
    y2 = y1 + h1 / 2 + gap2 + h2 / 2
    for ch in wm2:
        draw.text((x, y2), ch, font=f2, fill=MUTED + (255,), anchor="lm")
        x += f2.getlength(ch) + ls

    # loading dots
    n = 4
    r = max(2, round(0.0055 * s))
    gap = round(0.030 * s)
    x0 = cx - (n - 1) * gap // 2
    dy = round(h * 0.84)
    for i, alpha in enumerate((255, 170, 100, 60)):
        dx = x0 + i * gap
        draw.ellipse([dx - r, dy - r, dx + r, dy + r], fill=GREEN_RGB + (alpha,))

    return img.convert("RGB")


def main():
    os.makedirs(OUT, exist_ok=True)
    master_square = render_icon(1024, glyph_scale=1.0, rounded=False)
    master_maskable = render_icon(1024, glyph_scale=0.82, rounded=False)
    master_rounded = render_icon(1024, glyph_scale=1.0, rounded=True)

    def save_square(master, size, name):
        master.resize((size, size), Image.LANCZOS).convert("RGB").save(
            os.path.join(OUT, name)
        )
        print("icon", name, f"{size}x{size}")

    save_square(master_square, 196, "favicon-196.png")
    save_square(master_square, 180, "apple-icon-180.png")
    save_square(master_maskable, 192, "manifest-icon-192.maskable.png")
    save_square(master_maskable, 512, "manifest-icon-512.maskable.png")

    for fp in sorted(glob.glob(os.path.join(OUT, "apple-splash-*.jpg"))):
        m = re.search(r"apple-splash-(\d+)-(\d+)\.jpg$", os.path.basename(fp))
        if not m:
            continue
        w, h = int(m.group(1)), int(m.group(2))
        render_splash(w, h, master_rounded).save(fp, "JPEG", quality=90)
        print("splash", os.path.basename(fp), f"{w}x{h}")


if __name__ == "__main__":
    main()
