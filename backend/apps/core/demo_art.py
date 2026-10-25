"""Drawn pictures for the demo data (LOCAL DEVELOPMENT ONLY, see seed_demo): scenes, portraits and certificates.

Everything here is an ILLUSTRATION made of simple shapes: there are no real photographs and no real people, so nothing in the demo data can
be mistaken for a real person or a real award. Pillow only (already a dependency); no network, no external files except the DejaVu font that the
PDF export ships."""
import colorsys
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
W, H = 1600, 1000

INK = (18, 38, 63)
TEAL = (15, 118, 110)
GOLD = (200, 146, 27)
GOLD_SOFT = (243, 213, 138)
PAPER = (251, 249, 244)
SKINS = [(247, 214, 188), (233, 190, 150), (214, 164, 120), (180, 128, 90), (141, 96, 66)]
HAIRS = [(30, 24, 22), (58, 38, 26), (92, 62, 38), (20, 20, 24), (120, 90, 60)]
SHIRTS = [(15, 118, 110), (29, 95, 168), (200, 146, 27), (160, 60, 80), (90, 70, 160), (60, 130, 80), (18, 38, 63), (200, 90, 50)]


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def jpeg(im, quality=86):
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()


def _gradient(size, top, bottom):
    w, h = size
    im = Image.new("RGB", size, top)
    px = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        px.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return im


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def person(d, x, y, s, rng, shirt=None, kind="adult"):
    """A small figure standing with its feet at (x, y); s = height in pixels."""
    skin, hair = rng.choice(SKINS), rng.choice(HAIRS)
    shirt = shirt or rng.choice(SHIRTS)
    head = s * 0.17
    body_h = s * 0.46
    leg_h = s * 0.30
    cx = x
    top_body = y - leg_h - body_h
    d.rounded_rectangle((cx - s * 0.07, y - leg_h, cx - s * 0.01, y), radius=3, fill=_shade(INK, 1.2))
    d.rounded_rectangle((cx + s * 0.01, y - leg_h, cx + s * 0.07, y), radius=3, fill=_shade(INK, 1.2))
    d.rounded_rectangle((cx - s * 0.15, top_body, cx + s * 0.15, y - leg_h + 6), radius=int(s * 0.07), fill=shirt)
    d.rounded_rectangle((cx - s * 0.20, top_body + 4, cx - s * 0.13, top_body + body_h * 0.8), radius=int(s * 0.03), fill=shirt)
    d.rounded_rectangle((cx + s * 0.13, top_body + 4, cx + s * 0.20, top_body + body_h * 0.8), radius=int(s * 0.03), fill=shirt)
    d.ellipse((cx - head, top_body - head * 1.9, cx + head, top_body - head * 1.9 + head * 2), fill=skin)
    d.pieslice((cx - head * 1.02, top_body - head * 1.95, cx + head * 1.02, top_body - head * 1.95 + head * 2), 180, 360, fill=hair)


def crowd(d, rng, y, n, s, x0=120, x1=W - 120, shirts=None):
    xs = sorted(x0 + (x1 - x0) * i / max(1, n - 1) + rng.randint(-14, 14) for i in range(n))
    for x in xs:
        person(d, x, y + rng.randint(-8, 8), s * rng.uniform(0.92, 1.05), rng, shirt=rng.choice(shirts) if shirts else None)


def _banner(d, text):
    f = font(54, True)
    w = d.textlength(text, font=f)
    d.rounded_rectangle((W / 2 - w / 2 - 40, 70, W / 2 + w / 2 + 40, 170), radius=18, fill=(255, 255, 255), outline=GOLD, width=5)
    d.text((W / 2 - w / 2, 88), text, font=f, fill=INK)


def _label(d, text):
    f = font(26, True)
    w = d.textlength(text, font=f)
    d.rounded_rectangle((W - w - 60, H - 70, W - 24, H - 24), radius=10, fill=(255, 255, 255))
    d.text((W - w - 42, H - 64), text, font=f, fill=INK)


def scene(kind, seed=0, banner=""):
    """A 1600x1000 illustration. kinds: ceremony, classroom, sport, library, lab, building, computer, music, olympiad, garden."""
    rng = random.Random(f"{kind}-{seed}")
    hue = rng.random()
    sky_top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((0.55 + hue * 0.08) % 1, 0.45, 0.95))
    sky_bottom = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((0.52 + hue * 0.05) % 1, 0.12, 1.0))
    im = _gradient((W, H), sky_top, sky_bottom)
    d = ImageDraw.Draw(im, "RGBA")
    indoor = kind in {"classroom", "library", "lab", "computer", "music", "olympiad", "ceremony"}
    if indoor:
        wall = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(0.1 + hue * 0.06, 0.12, 0.97))
        d.rectangle((0, 0, W, H), fill=wall)
        d.rectangle((0, 760, W, H), fill=(196, 160, 118))
        for x in range(0, W, 160):
            d.line([(x, 760), (x - 200, H)], fill=(170, 134, 96), width=3)
        for wx in (140, W - 380):
            d.rounded_rectangle((wx, 170, wx + 240, 450), radius=14, fill=(190, 225, 245), outline=(255, 255, 255), width=14)
            d.line([(wx + 120, 170), (wx + 120, 450)], fill=(255, 255, 255), width=8)
            d.line([(wx, 310), (wx + 240, 310)], fill=(255, 255, 255), width=8)
    if kind == "ceremony":
        d.rectangle((0, 640, W, 780), fill=_shade(TEAL, 0.9))
        d.polygon([(300, 640), (W - 300, 640), (W - 200, 780), (200, 780)], fill=TEAL)
        d.rectangle((W / 2 - 110, 520, W / 2 + 110, 660), fill=_shade(INK, 1.2))
        d.rectangle((W / 2 - 130, 505, W / 2 + 130, 530), fill=GOLD)
        person(d, W / 2 - 330, 650, 340, rng, shirt=INK)
        person(d, W / 2 + 330, 650, 340, rng, shirt=(160, 60, 80))
        for k in range(14):
            cx = 160 + k * 100
            d.polygon([(cx, 200), (cx + 40, 200), (cx + 20, 260)], fill=rng.choice([GOLD, TEAL, (29, 95, 168), (255, 255, 255)]))
        crowd(d, rng, 960, 11, 330)
    elif kind == "classroom":
        d.rounded_rectangle((420, 120, 1180, 440), radius=12, fill=(34, 90, 70), outline=(140, 100, 60), width=14)
        d.line([(480, 200), (800, 200)], fill=(240, 240, 240), width=5)
        d.line([(480, 270), (950, 270)], fill=(240, 240, 240), width=5)
        d.line([(480, 340), (700, 340)], fill=(240, 240, 240), width=5)
        person(d, 1280, 740, 430, rng, shirt=(160, 60, 80))
        for row, y in enumerate((900, 980)):
            for col in range(5):
                x = 220 + col * 290 + row * 50
                d.rounded_rectangle((x - 95, y - 120, x + 95, y - 70), radius=8, fill=(205, 160, 105))
                person(d, x, y - 40, 250, rng)
    elif kind == "sport":
        d.rectangle((0, 520, W, H), fill=(80, 170, 90))
        for k in range(8):
            d.rectangle((0, 520 + k * 60, W, 550 + k * 60), fill=(88, 180, 98))
        d.rectangle((120, 600, W - 120, 940), outline=(255, 255, 255), width=6)
        d.line([(W / 2, 600), (W / 2, 940)], fill=(255, 255, 255), width=6)
        d.ellipse((W / 2 - 90, 700, W / 2 + 90, 840), outline=(255, 255, 255), width=6)
        d.rectangle((60, 660, 120, 880), outline=(255, 255, 255), width=8)
        d.rectangle((W - 120, 660, W - 60, 880), outline=(255, 255, 255), width=8)
        for k in range(6):
            person(d, 300 + k * 200 + rng.randint(-40, 40), 900 + rng.randint(-60, 20), 260, rng, shirt=(200, 60, 60) if k % 2 else (40, 100, 200))
        d.ellipse((800, 790, 850, 840), fill=(255, 255, 255), outline=INK, width=3)
        d.ellipse((1180, 80, 1300, 200), fill=(255, 226, 120))
    elif kind == "library":
        for row in range(3):
            for col in range(2):
                bx = 120 + col * 1140
                by = 150 + row * 180
                d.rectangle((bx, by, bx + 320, by + 150), fill=(140, 100, 60))
                for k in range(16):
                    d.rectangle((bx + 10 + k * 19, by + 12 + (k % 3) * 4, bx + 24 + k * 19, by + 140), fill=tuple(int(c * 255) for c in colorsys.hsv_to_rgb(rng.random(), 0.5, 0.85)))
        d.rounded_rectangle((420, 700, 1180, 780), radius=12, fill=(205, 160, 105))
        for k in range(4):
            person(d, 520 + k * 190, 700, 300, rng)
            d.rectangle((480 + k * 190, 668, 560 + k * 190, 696), fill=(255, 255, 255))
    elif kind == "lab":
        d.rectangle((0, 680, W, 800), fill=(110, 130, 140))
        for k in range(5):
            x = 260 + k * 260
            d.polygon([(x, 560), (x + 60, 560), (x + 100, 680), (x - 40, 680)], fill=(120, 200, 190, 200), outline=(80, 120, 120))
            d.rectangle((x + 8, 520, x + 52, 560), fill=(235, 245, 245), outline=(80, 120, 120))
        person(d, 520, 900, 420, rng, shirt=(245, 245, 245))
        person(d, 1060, 900, 400, rng, shirt=(245, 245, 245))
    elif kind == "building":
        d.rectangle((0, 760, W, H), fill=(90, 160, 90))
        d.rectangle((300, 300, 1300, 780), fill=(236, 220, 188))
        d.polygon([(260, 300), (800, 160), (1340, 300)], fill=(176, 90, 70))
        for r in range(3):
            for c in range(7):
                d.rectangle((350 + c * 135, 350 + r * 125, 420 + c * 135, 440 + r * 125), fill=(120, 170, 215), outline=(255, 255, 255), width=4)
        d.rectangle((740, 640, 860, 780), fill=(120, 80, 50))
        d.line([(1380, 780), (1380, 260)], fill=(90, 90, 90), width=8)
        d.rectangle((1380, 260, 1500, 320), fill=(30, 130, 200))
        d.rectangle((1380, 290, 1500, 300), fill=(255, 255, 255))
        d.rectangle((1380, 300, 1500, 310), fill=(40, 160, 90))
        for tx in (150, 1480):
            d.rectangle((tx - 12, 640, tx + 12, 780), fill=(110, 80, 50))
            d.ellipse((tx - 110, 480, tx + 110, 680), fill=(50, 130, 70))
        crowd(d, rng, 930, 9, 250, 400, 1200)
    elif kind == "computer":
        for k in range(4):
            x = 260 + k * 350
            d.rounded_rectangle((x - 120, 560, x + 120, 700), radius=10, fill=(40, 50, 70), outline=(200, 205, 215), width=6)
            d.rectangle((x - 105, 572, x + 105, 688), fill=(80, 170, 225) if k % 2 else (95, 215, 180))
            d.rectangle((x - 18, 700, x + 18, 740), fill=(90, 95, 105))
            person(d, x, 920, 330, rng)
        d.rectangle((60, 740, W - 60, 790), fill=(205, 160, 105))
    elif kind == "music":
        for k in range(7):
            person(d, 230 + k * 190, 930 - (k % 2) * 40, 330, rng)
        for k in range(10):
            x, y = 200 + k * 140, 200 + (k * 53) % 220
            d.ellipse((x, y, x + 34, y + 26), fill=INK)
            d.line([(x + 32, y + 12), (x + 32, y - 60)], fill=INK, width=6)
            d.line([(x + 32, y - 60), (x + 62, y - 44)], fill=INK, width=6)
        d.polygon([(660, 700), (940, 700), (900, 800), (700, 800)], fill=GOLD)
    elif kind == "olympiad":
        for r in range(2):
            for c in range(6):
                x, y = 200 + c * 250 + r * 60, 860 + r * 100 - 80
                d.rounded_rectangle((x - 80, y - 70, x + 80, y - 30), radius=6, fill=(205, 160, 105))
                d.rectangle((x - 40, y - 100, x + 40, y - 72), fill=(255, 255, 255))
                person(d, x, y + 10, 250, rng)
        d.rounded_rectangle((520, 150, 1080, 280), radius=16, fill=(255, 255, 255), outline=TEAL, width=6)
    elif kind == "garden":
        d.rectangle((0, 560, W, H), fill=(110, 170, 80))
        for k in range(6):
            x = 150 + k * 270
            d.rectangle((x - 14, 400, x + 14, 600), fill=(110, 80, 50))
            d.ellipse((x - 120, 250, x + 120, 480), fill=(50 + k * 10, 130, 70))
        for k in range(7):
            person(d, 200 + k * 200, 930 - (k % 3) * 25, 300, rng)
        d.ellipse((1250, 70, 1380, 200), fill=(255, 226, 120))
    if banner:
        _banner(d, banner)
    _label(d, "DEMO · illyustratsiya")
    return im.filter(ImageFilter.SMOOTH)


def scene_jpeg(kind, seed=0, banner=""):
    im = scene(kind, seed, banner)
    return jpeg(im), jpeg(im.resize((480, 300), Image.Resampling.LANCZOS), 80)


def portrait(seed, size=720):
    """A drawn bust on a coloured background (staff cards)."""
    rng = random.Random(f"portrait-{seed}")
    hue = rng.random()
    bg_top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.25, 0.97))
    bg_bot = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.08) % 1, 0.35, 0.82))
    im = _gradient((size, size), bg_top, bg_bot)
    d = ImageDraw.Draw(im)
    skin, hair, shirt = rng.choice(SKINS), rng.choice(HAIRS), rng.choice(SHIRTS)
    cx, s = size / 2, size
    d.rounded_rectangle((cx - s * 0.36, s * 0.70, cx + s * 0.36, s * 1.2), radius=int(s * 0.2), fill=shirt)
    d.polygon([(cx - s * 0.1, s * 0.70), (cx + s * 0.1, s * 0.70), (cx, s * 0.82)], fill=_shade(skin, 0.92))
    d.rectangle((cx - s * 0.07, s * 0.58, cx + s * 0.07, s * 0.73), fill=_shade(skin, 0.95))
    style = rng.choice(["short", "long", "bun", "bald"])
    if style == "long":
        d.rounded_rectangle((cx - s * 0.25, s * 0.22, cx + s * 0.25, s * 0.72), radius=int(s * 0.12), fill=hair)
    d.ellipse((cx - s * 0.19, s * 0.2, cx + s * 0.19, s * 0.66), fill=skin)
    if style in ("short", "long", "bun"):
        d.pieslice((cx - s * 0.2, s * 0.17, cx + s * 0.2, s * 0.5), 180, 360, fill=hair)
    if style == "bun":
        d.ellipse((cx - s * 0.07, s * 0.1, cx + s * 0.07, s * 0.22), fill=hair)
    for ex in (-0.075, 0.075):
        d.ellipse((cx + s * ex - 9, s * 0.4 - 7, cx + s * ex + 9, s * 0.4 + 7), fill=(40, 30, 30))
    if rng.random() < 0.4:
        for ex in (-0.075, 0.075):
            d.ellipse((cx + s * ex - 24, s * 0.4 - 22, cx + s * ex + 24, s * 0.4 + 22), outline=(40, 40, 50), width=4)
        d.line([(cx - s * 0.04, s * 0.4), (cx + s * 0.04, s * 0.4)], fill=(40, 40, 50), width=4)
    d.arc((cx - s * 0.07, s * 0.46, cx + s * 0.07, s * 0.56), 20, 160, fill=(150, 60, 60), width=5)
    if style != "long" and rng.random() < 0.25:
        d.pieslice((cx - s * 0.17, s * 0.5, cx + s * 0.17, s * 0.74), 0, 180, fill=_shade(hair, 0.9))
        d.ellipse((cx - s * 0.08, s * 0.5, cx + s * 0.08, s * 0.6), fill=skin)
        d.arc((cx - s * 0.07, s * 0.5, cx + s * 0.07, s * 0.6), 20, 160, fill=(150, 60, 60), width=5)
    return im


def portrait_jpeg(seed):
    return jpeg(portrait(seed, 720), 88)


def _star(d, cx, cy, r, fill):
    d.polygon([(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 45)], fill=fill)


def certificate(kind, title, recipient, level, year, seed=0):
    """A certificate / diploma / medal sheet, clearly marked DEMO. kind: certificate | diploma | medal | award | other."""
    rng = random.Random(f"cert-{kind}-{seed}")
    size = (1600, 1131)
    im = Image.new("RGB", size, PAPER)
    d = ImageDraw.Draw(im, "RGBA")
    accent = rng.choice([TEAL, (29, 95, 168), (150, 60, 80), INK])
    d.rectangle((40, 40, size[0] - 40, size[1] - 40), outline=accent, width=10)
    d.rectangle((70, 70, size[0] - 70, size[1] - 70), outline=GOLD, width=4)
    for x, y in ((100, 100), (size[0] - 100, 100), (100, size[1] - 100), (size[0] - 100, size[1] - 100)):
        _star(d, x, y, 46, accent)
        _star(d, x, y, 24, GOLD_SOFT)
    for k in range(0, size[0], 72):
        for j in range(0, size[1], 72):
            if (k + j) % 144 == 0:
                _star(d, k + 36, j + 36, 5, (*accent, 22))
    heading = {"certificate": "SERTIFIKAT", "diploma": "DIPLOM", "medal": "MEDAL SOHIBI", "award": "MUKOFOT", "other": "TAQDIRNOMA"}.get(kind, "SERTIFIKAT")
    f1, f2, f3, f4 = font(96, True), font(34), font(62, True), font(40)
    d.text((size[0] / 2, 230), heading, font=f1, fill=accent, anchor="mm")
    d.text((size[0] / 2, 320), "Mirzacho‘l tumani Xalq ta’limi bo‘limi", font=f2, fill=(80, 90, 110), anchor="mm")
    d.line([(520, 370), (1080, 370)], fill=GOLD, width=4)
    d.text((size[0] / 2, 470), "Taqdirlanadi", font=f2, fill=(80, 90, 110), anchor="mm")
    d.text((size[0] / 2, 570), recipient, font=f3, fill=INK, anchor="mm")
    words = title.split()
    lines, cur = [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=f4) > 1100 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    for i, line in enumerate(lines[:3]):
        d.text((size[0] / 2, 670 + i * 56), line, font=f4, fill=(50, 60, 80), anchor="mm")
    d.text((size[0] / 2, 880), f"{level} · {year}", font=f2, fill=(80, 90, 110), anchor="mm")
    cx, cy = 1320, 850
    for dx in (-34, 34):
        d.polygon([(cx + dx - 26, cy + 40), (cx + dx + 26, cy + 40), (cx + dx + (60 if dx > 0 else -60) * 0.6, cy + 170), (cx + dx, cy + 130), (cx + dx - (0 if dx > 0 else 0), cy + 170)], fill=accent)
    d.ellipse((cx - 90, cy - 90, cx + 90, cy + 90), fill=GOLD, outline=(160, 112, 14), width=8)
    d.ellipse((cx - 66, cy - 66, cx + 66, cy + 66), outline=GOLD_SOFT, width=5)
    _star(d, cx, cy, 44, GOLD_SOFT)
    d.line([(220, 960), (620, 960)], fill=(60, 60, 70), width=3)
    d.text((420, 995), "Bo‘lim boshlig‘i", font=font(26), fill=(100, 105, 120), anchor="mm")
    d.text((size[0] / 2, size[1] - 52), "DEMO — haqiqiy hujjat emas", font=font(24, True), fill=(180, 60, 60), anchor="mm")
    return im


def certificate_jpeg(kind, title, recipient, level, year, seed=0):
    im = certificate(kind, title, recipient, level, year, seed)
    return jpeg(im, 88)


def pdf_bytes(title, lines):
    """A small valid PDF (reportlab is already a dependency for the PDF export) with Cyrillic/Latin-extended text."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    for name, file in (("DemoSans", "DejaVuSans.ttf"), ("DemoSansBold", "DejaVuSans-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    w, h = A4
    c.setFont("DemoSansBold", 18)
    c.drawString(56, h - 80, title[:70])
    c.setFont("DemoSans", 11)
    y = h - 120
    for line in lines:
        for chunk in _wrap(line, 90):
            c.drawString(56, y, chunk)
            y -= 17
        y -= 8
    c.setFont("DemoSans", 9)
    c.drawString(56, 48, "DEMO — namunaviy hujjat, haqiqiy ma’lumot emas.")
    c.showPage()
    c.save()
    return out.getvalue()


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out or [""]
