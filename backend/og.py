"""Open Graph card rendering.

Share links from the classifier encode the whole result in the URL, so any
crawler that unfurls the link can be shown a personalised card — this module
paints that card (1200x630 PNG) with Pillow. It also paints the static
site-wide card committed at frontend/img/og.png (scripts/make_og.py).

Fonts are bundled in backend/fonts/ (DejaVu, free license) so rendering is
identical on dev machines, CI, and the slim Docker image.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = Path(__file__).resolve().parent / "fonts"

W, H = 1200, 630

# House palette — keep in sync with the :root CSS vars in frontend/*.html.
BG = "#f7f1e6"
CARD = "#fffdf9"
INK = "#33281e"
MUTED = "#7d7264"
LINE = "#e6dcc9"
ACCENT = "#9a2c12"
ACCENT_SOFT = "#fbeee6"

# Per-era art direction — keep in sync with ERA_UI in frontend/index.html.
# palette = the era's board colours; focus = portrait crop centre (x, y as
# fractions of the source image); glyph = the era's chess-piece emblem.
ERA_ART = {
    "romantic":  {"palette": ("#f0d9b5", "#b58863"), "glyph": "♞", "focus": (0.5, 0.25)},
    "classical": {"palette": ("#eeeed2", "#769656"), "glyph": "♝", "focus": (0.5, 0.22)},
    "soviet":    {"palette": ("#dee3e6", "#8ca2ad"), "glyph": "♜", "focus": (0.5, 0.24)},
    "digital":   {"palette": ("#e9e7e2", "#7e868f"), "glyph": "♛", "focus": (0.5, 0.40)},
    "modern":    {"palette": ("#e2e8ee", "#71829a"), "glyph": "♚", "focus": (0.68, 0.30)},
}
DEFAULT_ART = {"palette": ("#f0d9b5", "#b58863"), "glyph": "♟", "focus": (0.5, 0.3)}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def serif_bold(size): return _font("DejaVuSerif-Bold.ttf", size)
def serif_italic(size): return _font("DejaVuSerif-Italic.ttf", size)
def sans(size): return _font("DejaVuSans.ttf", size)
def sans_bold(size): return _font("DejaVuSans-Bold.ttf", size)


def _fit(draw, text, font_fn, start, max_width, min_size=30):
    """Largest font size (<= start) at which text fits in max_width."""
    size = start
    while size > min_size:
        f = font_fn(size)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 2
    return font_fn(min_size)


def _cover(img: Image.Image, w: int, h: int, focus=(0.5, 0.3)) -> Image.Image:
    """Scale-to-fill then crop a w*h window centred on the focus point."""
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    fx, fy = focus
    left = min(max(round(img.width * fx - w / 2), 0), img.width - w)
    top = min(max(round(img.height * fy - h / 2), 0), img.height - h)
    return img.crop((left, top, left + w, top + h))


def _checker_ribbon(draw, x, y, sq=26, n=8, palette=("#f0d9b5", "#b58863")):
    for i in range(n):
        draw.rectangle([x + i * sq, y, x + (i + 1) * sq, y + sq],
                       fill=palette[i % 2])
    draw.rectangle([x, y, x + n * sq, y + sq], outline=LINE, width=1)


def render_share_card(era_id: str, era_name: str, years, pct: int,
                      player: str = "", games: int = 0) -> Image.Image:
    """The personalised 'I play like the Soviet Era — 62%' unfurl card."""
    art = ERA_ART.get(era_id, DEFAULT_ART)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # Right: era portrait, cover-cropped, with an accent spine.
    px, pw = 760, W - 760
    portrait_path = ROOT / "frontend" / "img" / f"{era_id}.jpg"
    if portrait_path.exists():
        im.paste(_cover(Image.open(portrait_path).convert("RGB"), pw, H,
                        art["focus"]), (px, 0))
    else:  # tests / fresh checkouts: soft panel with a big watermark glyph
        d.rectangle([px, 0, W, H], fill=ACCENT_SOFT)
        d.text((px + pw / 2, H / 2), art["glyph"], font=sans(300),
               fill=LINE, anchor="mm")
    d.rectangle([px - 8, 0, px, H], fill=ACCENT)

    # Left column.
    x, right = 64, px - 56
    d.text((x, 56), art["glyph"], font=sans(44), fill=ACCENT)
    d.text((x + 62, 66), "TIME-MACHINE CHESS", font=sans_bold(26), fill=MUTED)

    d.text((x, 150), "WHICH ERA DO YOU PLAY LIKE?", font=sans_bold(28), fill=ACCENT)

    name_font = _fit(d, era_name, serif_bold, 76, right - x)
    d.text((x, 200), era_name, font=name_font, fill=INK)
    d.text((x, 200 + name_font.size + 22), f"{years[0]}–{years[1]}",
           font=serif_italic(34), fill=MUTED)

    # The big number.
    pct_text = f"{pct}%"
    pct_font = serif_bold(150)
    d.text((x, 350), pct_text, font=pct_font, fill=ACCENT)
    d.text((x + d.textlength(pct_text, font=pct_font) + 24, 452), "match",
           font=sans(34), fill=MUTED)

    # Player line.
    who = player.strip()
    line = who if who else ""
    if games:
        line = f"{line} · {games} games" if line else f"{games} games"
    if line:
        d.text((x, 530 - 6), line, font=sans(28), fill=INK)

    _checker_ribbon(d, x, H - 62, palette=art["palette"])
    d.text((x + 8 * 26 + 24, H - 60), "chess.pharmatools.ai",
           font=sans(26), fill=MUTED)
    return im


def render_site_card(eras: dict) -> Image.Image:
    """The static site-wide card: five portraits under the masthead."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    d.text((W / 2, 92), "Time-Machine Chess", font=serif_bold(72),
           fill=INK, anchor="mm")
    d.text((W / 2, 158), "Play the theory of a past era",
           font=serif_italic(34), fill=ACCENT, anchor="mm")

    ids = list(eras)
    cw, ch, gap = 196, 300, 24
    total = len(ids) * cw + (len(ids) - 1) * gap
    x0, y0 = (W - total) // 2, 210
    for i, era_id in enumerate(ids):
        art = ERA_ART.get(era_id, DEFAULT_ART)
        cx = x0 + i * (cw + gap)
        portrait_path = ROOT / "frontend" / "img" / f"{era_id}.jpg"
        if portrait_path.exists():
            im.paste(_cover(Image.open(portrait_path).convert("RGB"),
                            cw, ch - 66, art["focus"]), (cx, y0))
        else:
            d.rectangle([cx, y0, cx + cw, y0 + ch - 66], fill=ACCENT_SOFT)
            d.text((cx + cw / 2, y0 + (ch - 66) / 2), art["glyph"],
                   font=sans(110), fill=LINE, anchor="mm")
        d.rectangle([cx, y0 + ch - 66, cx + cw, y0 + ch], fill=CARD)
        d.rectangle([cx, y0, cx + cw, y0 + ch], outline=LINE, width=1)
        era = eras[era_id]
        name = era["name"].replace("The ", "")
        d.text((cx + cw / 2, y0 + ch - 46), name,
               font=_fit(d, name, sans_bold, 22, cw - 16, 14),
               fill=INK, anchor="mm")
        d.text((cx + cw / 2, y0 + ch - 19),
               f"{era['years'][0]}–{era['years'][1]}",
               font=sans(18), fill=MUTED, anchor="mm")

    d.text((W / 2, y0 + ch + 52), "chess.pharmatools.ai",
           font=sans(28), fill=MUTED, anchor="mm")
    return im


@lru_cache(maxsize=512)
def share_card_png(era_id: str, era_name: str, years: tuple, pct: int,
                   player: str, games: int) -> bytes:
    buf = BytesIO()
    render_share_card(era_id, era_name, years, pct, player, games).save(
        buf, "PNG", optimize=True)
    return buf.getvalue()
