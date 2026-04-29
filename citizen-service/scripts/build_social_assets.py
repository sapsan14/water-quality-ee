#!/usr/bin/env python3
"""Generate static social-preview assets for h2oatlas.ee.

Produces:
  frontend/public/apple-touch-icon.png   180x180  (iOS / Android home-screen)
  frontend/public/og-default.png         1200x630 (Open Graph default fallback)

Run once when branding changes. Outputs are committed to git so the OG worker
fallback / apple-touch-icon are always available even when the worker is down.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC = REPO_ROOT / "frontend" / "public"

BRAND_TOP = (15, 110, 253)   # #0f6efd
BRAND_BOTTOM = (23, 176, 255)  # #17b0ff
DROP_TOP = (223, 244, 255)
DROP_BOTTOM = (169, 221, 255)
DEEP_BLUE = (7, 58, 122)


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    base = Image.new("RGB", size, top)
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return base


def _diagonal_gradient(size: tuple[int, int], a: tuple[int, int, int], b: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    diag = (w - 1) + (h - 1)
    for y in range(h):
        for x in range(w):
            t = (x + y) / diag
            px[x, y] = (
                int(a[0] * (1 - t) + b[0] * t),
                int(a[1] * (1 - t) + b[1] * t),
                int(a[2] * (1 - t) + b[2] * t),
            )
    return img


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _droplet_path(cx: float, cy: float, height: float) -> list[tuple[float, float]]:
    """Polygon approximation of the SVG droplet: pointy top, rounded bottom."""
    # Use a simple superellipse-ish shape: tip at top, semicircle bottom.
    pts: list[tuple[float, float]] = []
    half_w = height * 0.45
    # Tip
    pts.append((cx, cy - height * 0.55))
    # Right curve to widest point
    steps = 28
    for i in range(1, steps + 1):
        t = i / steps
        # cubic ease-out from tip to right widest at y=cy+height*0.05
        y = cy - height * 0.55 + (height * 0.6) * t
        x = cx + half_w * (t ** 0.65)
        pts.append((x, y))
    # Bottom semicircle from right widest to left widest
    import math
    for i in range(1, steps + 1):
        ang = -math.pi / 2 + (math.pi) * (i / steps)  # from -pi/2 (right) sweeping down to pi/2 (left)
        # Actually want from angle 0 (right) downward to pi (left) through bottom (pi/2)
        ang = (math.pi) * (i / steps)
        x = cx + half_w * math.cos(ang)
        y = cy + 0.05 * height + half_w * math.sin(ang)
        pts.append((x, y))
    # Left curve back to tip
    for i in range(1, steps + 1):
        t = 1 - i / steps
        y = cy - height * 0.55 + (height * 0.6) * t
        x = cx - half_w * (t ** 0.65)
        pts.append((x, y))
    return pts


def _draw_logo(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Render the H2O Atlas logo glyph (gradient bg + droplet + sparkline) inside box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    # Logo layer (RGBA)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bg = _diagonal_gradient((w, h), BRAND_TOP, BRAND_BOTTOM)
    bg = _round_corners(bg, int(min(w, h) * 0.21))
    layer.alpha_composite(bg)

    # Droplet
    cx = w * 0.5
    cy = h * 0.48
    drop_h = h * 0.78
    drop_pts = _droplet_path(cx, cy, drop_h)
    drop_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dd = ImageDraw.Draw(drop_img)
    dd.polygon(drop_pts, fill=DROP_TOP)
    # Vertical gradient fill via mask
    grad = _vertical_gradient((w, h), DROP_TOP, DROP_BOTTOM).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(drop_pts, fill=255)
    layer.paste(grad, (0, 0), mask)

    # Inner highlight (smaller droplet, white-ish)
    inner_pts = _droplet_path(cx, cy + h * 0.02, drop_h * 0.62)
    highlight = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).polygon(inner_pts, fill=(255, 255, 255, 92))
    layer.alpha_composite(highlight)

    # Sparkline bottom
    spark = ImageDraw.Draw(layer)
    spark_w = w * 0.78
    spark_x = (w - spark_w) / 2
    spark_y = h * 0.74
    pts = [
        (spark_x, spark_y + 8),
        (spark_x + spark_w * 0.18, spark_y + 8),
        (spark_x + spark_w * 0.30, spark_y - 8),
        (spark_x + spark_w * 0.46, spark_y + 14),
        (spark_x + spark_w * 0.62, spark_y + 4),
        (spark_x + spark_w * 0.92, spark_y + 8),
    ]
    spark.line(pts, fill=DEEP_BLUE, width=max(3, int(h * 0.04)), joint="curve")
    r = max(3, int(h * 0.045))
    cx2 = pts[-1][0]
    cy2 = pts[-1][1]
    spark.ellipse((cx2 - r, cy2 - r, cx2 + r, cy2 + r), fill=DEEP_BLUE)

    img.alpha_composite(layer.convert("RGBA"), (x0, y0))


def _safe_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _safe_font_regular(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def build_apple_touch_icon(out: Path) -> None:
    size = 180
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_logo(img, (0, 0, size, size))
    img = img.filter(ImageFilter.SMOOTH)
    img.save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} B)")


def build_og_default(out: Path) -> None:
    w, h = 1200, 630
    bg = _diagonal_gradient((w, h), BRAND_TOP, BRAND_BOTTOM).convert("RGBA")
    # Soft vignette
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, h - 220, w, h), fill=(7, 58, 122, 70))
    bg.alpha_composite(overlay)

    # Logo at left
    logo_size = 320
    margin = 70
    _draw_logo(bg, (margin, (h - logo_size) // 2, margin + logo_size, (h - logo_size) // 2 + logo_size))

    d = ImageDraw.Draw(bg)
    text_x = margin + logo_size + 60
    title_font = _safe_font(96)
    sub_font = _safe_font_regular(38)
    tag_font = _safe_font_regular(28)

    title = "H2O Atlas"
    subtitle = "Water Quality Map of Estonia"
    tagline = "Terviseamet open data · ML risk assessment"

    title_y = (h - 96 - 38 - 28 - 24) // 2 - 30
    d.text((text_x + 3, title_y + 3), title, font=title_font, fill=(0, 0, 0, 70))
    d.text((text_x, title_y), title, font=title_font, fill=(255, 255, 255))
    d.text((text_x, title_y + 110), subtitle, font=sub_font, fill=(232, 246, 255))
    d.text((text_x, title_y + 170), tagline, font=tag_font, fill=(199, 230, 255))

    # Footer URL strip
    d.text((margin, h - 70), "h2oatlas.ee", font=_safe_font(34), fill=(255, 255, 255, 230))

    bg.convert("RGB").save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} B)")


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    build_apple_touch_icon(PUBLIC / "apple-touch-icon.png")
    build_og_default(PUBLIC / "og-default.png")


if __name__ == "__main__":
    main()
