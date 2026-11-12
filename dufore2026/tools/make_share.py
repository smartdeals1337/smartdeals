#!/usr/bin/env python3
"""Builds dufore2026/share.jpg (the WhatsApp / iMessage preview card) from scores.json.

Run after updating scores:  python3 dufore2026/tools/make_share.py
Before the first round it shows the tee-off card; afterwards it shows the top 3.
It also bumps the ?v= cache-buster on the og:image tag in index.html.
"""
import json, os, re, hashlib, urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "dufore-fonts")
FONTS = {
    "cinzel": "https://fonts.gstatic.com/s/cinzel/v26/8vIU7ww63mVu7gtR-kwKxNvkNOjw-uTnTYo.ttf",
    "cinzelb": "https://fonts.gstatic.com/s/cinzel/v26/8vIU7ww63mVu7gtR-kwKxNvkNOjw-jHgTYo.ttf",
    "corm": "https://fonts.gstatic.com/s/cormorantgaramond/v21/co3smX5slCNuHLi8bLeY9MK7whWMhyjYrGFEsdtdc62E6zd5wDDOjw.ttf",
}
FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def font(key, size):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, key + ".ttf")
    if not os.path.exists(p):
        try:
            urllib.request.urlretrieve(FONTS[key], p)
        except Exception:
            return ImageFont.truetype(FALLBACK, size)
    try:
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.truetype(FALLBACK, size)


GOLD, GOLDL, CREAM = (207, 168, 69), (232, 207, 134), (247, 242, 228)

d = json.load(open(os.path.join(ROOT, "scores.json")))
par, cap = d["course"]["par"], d["course"]["cap"]
PAR = sum(par)

# ---- standings (same rules as the page) ----
res = []
for p in d["players"]:
    nets, done = [], 0
    for k in ("1", "2", "3", "4"):
        h = d["rounds"].get(k, {}).get(p["id"])
        tg = d.get("totals", {}).get(k, {}).get(p["id"])
        if tg is not None and not h:
            nets.append(tg - p["hcp"] - d.get("bonus", {}).get(k, {}).get(p["id"], 0))
            done += 1
        elif h and len(h) >= 18:
            g = sum(min(x, par[i] + cap) for i, x in enumerate(h))
            nets.append(g - p["hcp"] - d.get("bonus", {}).get(k, {}).get(p["id"], 0))
            done += 1
        else:
            nets.append(None)
    res.append({"p": p, "nets": nets, "done": done, "total": sum(n for n in nets if n is not None)})
played = [r for r in res if r["done"]]
last = max([i for r in played for i, n in enumerate(r["nets"]) if n is not None], default=-1)
played.sort(key=lambda r: r["total"] - PAR * r["done"])

# ---- canvas ----
W, H = 1200, 630
bg = Image.new("RGB", (W, H), (3, 49, 27))
glow = Image.radial_gradient("L").resize((W * 2, H * 2)).crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
bg = Image.composite(Image.new("RGB", (W, H), (2, 31, 18)), Image.new("RGB", (W, H), (14, 80, 46)), glow)
im = bg.convert("RGBA")
dr = ImageDraw.Draw(im)

# frame
dr.rounded_rectangle((18, 18, W - 18, H - 18), radius=6, outline=(207, 168, 69, 120), width=2)

# logo
logo = Image.open(os.path.join(ROOT, "logo.png")).convert("RGBA").resize((470, 470), Image.LANCZOS)
sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(sh).ellipse((70, 120, 540, 590), fill=(0, 0, 0, 160))
im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(24)))
im.alpha_composite(logo, (62, 80))

X = 640
def center_text(y, text, f, fill, x0=X, x1=W - 60):
    w = dr.textlength(text, font=f)
    dr.text((x0 + (x1 - x0 - w) / 2, y), text, font=f, fill=fill)

def spaced(x, y, text, f, fill, sp=6):
    for ch in text:
        dr.text((x, y), ch, font=f, fill=fill)
        x += dr.textlength(ch, font=f) + sp
    return x

def spaced_w(text, f, sp):
    return sum(dr.textlength(c, font=f) + sp for c in text) - sp

def centered_spaced(y, text, f, fill, sp=6):
    w = spaced_w(text, f, sp)
    spaced(X + (W - 60 - X - w) / 2, y, text, f, fill, sp)

centered_spaced(70, "THE DUFORE OPEN  ·  2026", font("cinzel", 26), GOLDL, 7)
dr.line((X + 160, 118, W - 60 - 160, 118), fill=GOLD, width=2)

# automatic champion: any hole in one wins the Dufore Cup
ace = None
for p in d["players"]:
    for ri, k in enumerate(("1", "2", "3", "4")):
        for hi, x in enumerate(d["rounds"].get(k, {}).get(p["id"], []) or []):
            if x == 1 and (ace is None or (ri, hi) < (ace[1], ace[2])):
                ace = (p, ri, hi)

if ace:
    centered_spaced(150, "DUFORE CUP CHAMPION", font("cinzel", 28), GOLD, 8)
    try:
        ph = Image.open(os.path.join(ROOT, ace[0]["photo"])).convert("RGB").resize((190, 190), Image.LANCZOS)
        m = Image.new("L", (190, 190), 0); ImageDraw.Draw(m).ellipse((0, 0, 189, 189), fill=255)
        ring = Image.new("RGBA", (206, 206), GOLD + (255,))
        rm = Image.new("L", (206, 206), 0); ImageDraw.Draw(rm).ellipse((0, 0, 205, 205), fill=255)
        cx = X + (W - 60 - X) // 2
        im.paste(ring, (cx - 103, 200), rm)
        im.paste(ph, (cx - 95, 208), m)
        dr = ImageDraw.Draw(im)
    except Exception:
        pass
    center_text(425, ace[0]["name"].upper(), font("cinzelb", 54), GOLDL)
    center_text(495, "Hole in one \u00b7 Round %d, hole %d" % (ace[1] + 1, ace[2] + 1), font("corm", 38), CREAM)
elif not played:
    centered_spaced(165, "ROUND ONE", font("cinzel", 30), GOLD, 8)
    center_text(215, "Wed 11 Nov", font("cinzelb", 76), GOLDL)
    center_text(315, "9:00 AM", font("cinzelb", 76), GOLDL)
    centered_spaced(430, "PGA RIVIERA MAYA", font("cinzel", 30), CREAM, 7)
    center_text(480, "Mexico · 4 rounds · 1 champion", font("corm", 40), GOLD)
else:
    rn = max(r["done"] for r in played)
    in_progress = any(r["done"] < rn for r in res)
    centered_spaced(142, "STANDINGS", font("cinzel", 28), GOLD, 9)
    center_text(180, ("Round %d in progress" % rn) if in_progress else ("After round %d of 4" % rn if rn < 4 else "Final standings"), font("corm", 36), CREAM)
    y = 232
    for i, r in enumerate(played[:3]):
        rowy = y + i * 110
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle((X, rowy, W - 60, rowy + 94), radius=16, fill=(255, 255, 255, 22 if i else 46), outline=(207, 168, 69, 200 if i == 0 else 110), width=2)
        im.alpha_composite(ov)
        dr = ImageDraw.Draw(im)
        key = lambda q: q["total"] - PAR * q["done"]
        pos = next(j for j in range(len(played)) if key(played[j]) == key(r)) + 1
        tied = sum(1 for q in played if key(q) == key(r)) > 1
        dr.text((X + 24, rowy + 18), ("T" if tied else "") + str(pos), font=font("cinzelb", 40 if tied else 46), fill=GOLDL)
        try:
            ph = Image.open(os.path.join(ROOT, r["p"]["photo"])).convert("RGB").resize((72, 72), Image.LANCZOS)
            m = Image.new("L", (72, 72), 0); ImageDraw.Draw(m).ellipse((0, 0, 71, 71), fill=255)
            ring = Image.new("RGBA", (80, 80), GOLD + (255,))
            rm = Image.new("L", (80, 80), 0); ImageDraw.Draw(rm).ellipse((0, 0, 79, 79), fill=255)
            im.paste(ring, (X + 86, rowy + 7), rm)
            im.paste(ph, (X + 90, rowy + 11), m)
        except Exception:
            pass
        nm = r["p"]["name"].upper()
        nsz = 32
        while nsz > 20 and dr.textlength(nm, font=font("cinzel", nsz)) > (W - 60 - 28 - 110) - (X + 186):
            nsz -= 2
        dr.text((X + 186, rowy + 26 + (32 - nsz) // 2), nm, font=font("cinzel", nsz), fill=CREAM)
        tot = str(r["total"])
        vs = r["total"] - PAR * r["done"]
        vs = "E" if vs == 0 else ("+%d" % vs if vs > 0 else "−%d" % abs(vs))
        f1, f2 = font("cinzelb", 44), font("corm", 30)
        w1 = dr.textlength(tot, font=f1)
        dr.text((W - 60 - 28 - w1, rowy + 8), tot, font=f1, fill=GOLDL)
        w2 = dr.textlength(vs, font=f2)
        dr.text((W - 60 - 28 - w2 / 2 - w1 / 2, rowy + 56), vs, font=f2, fill=CREAM)

center_text(574, "smartdealsclub.com/dufore2026", font("corm", 30), GOLD)

out = os.path.join(ROOT, "share.jpg")
im.convert("RGB").save(out, quality=88, optimize=True)

# bump cache-buster so chat apps re-fetch the preview
v = hashlib.md5(open(out, "rb").read()).hexdigest()[:8]
idx = os.path.join(ROOT, "index.html")
s = open(idx).read()
s2 = re.sub(r"(dufore2026/share\.jpg)(\?v=[0-9a-f]+)?", r"\1?v=" + v, s)
if s2 != s:
    open(idx, "w").write(s2)
print("share.jpg written, v=" + v, "| players ranked:", len(played))
