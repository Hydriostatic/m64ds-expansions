#!/usr/bin/env python3
"""
Builds banjotooie.exp (Banjo-Tooie, USA) from your own ROM.

    python3 make_banjotooie.py "Banjo-Tooie (USA).z64" [banjotooie.exp] [preview.png]

The bottom screen is a Nintendo DS style touch page: a 248x216 canvas that the emulator scales up
by a whole number (5x on the AYN Thor, 1240x1080) with no smoothing. All art is read from the ROM:
the game's three fonts, its HUD icons and wood textures from its levels. Nothing from the ROM is
stored in this repo.

Memory addresses and collectible flags come from the Archipelago Banjo-Tooie tools
(MIT, (c) 2025 g0goTBC, Austin, jjjj12212), checked against the USA GameShark codes.
"""
import io, json, struct, sys, zipfile, zlib
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

# Bump on every change to what the .exp shows (history in CHANGELOG.md).
VERSION = "1.2"

ROM_PATH = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'banjotooie.exp'
PREVIEW = sys.argv[3] if len(sys.argv) > 3 else None

rom = open(ROM_PATH, 'rb').read()
if rom[:4] == b'\x37\x80\x40\x12':                      # .v64 (byte-swapped) -> .z64
    rom = b''.join(rom[i + 1:i + 2] + rom[i:i + 1] for i in range(0, len(rom), 2))
if rom[0x3B:0x3F] != b'NB7E':
    sys.exit('This is not Banjo-Tooie (USA): game id %r' % rom[0x3B:0x3F])

# ---------------------------------------------------------------------------------------------
# The game's asset files. 0x5180: count; 0x5188: one u32 per asset, (offset << 6) | flags, with
# offsets from 0x12B24. Each asset is a u16 (size / 16) followed by a raw deflate stream.
# ---------------------------------------------------------------------------------------------
N_ASSETS = struct.unpack('>I', rom[0x5180:0x5184])[0]
TABLE = [struct.unpack('>I', rom[0x5188 + 4 * i:0x518C + 4 * i])[0] for i in range(N_ASSETS + 1)]

def asset(i):
    raw = rom[0x12B24 + (TABLE[i] >> 6):0x12B24 + (TABLE[i + 1] >> 6)]
    try:
        out = zlib.decompressobj(-15).decompress(raw[2:])
        if out: return out
    except zlib.error:
        pass
    return raw

def rgba16(v):
    return ((v >> 11 & 31) * 255 // 31, (v >> 6 & 31) * 255 // 31, (v >> 1 & 31) * 255 // 31, 255 if v & 1 else 0)

BPP = {1: 4, 4: 8, 0x40: 8, 0x400: 16, 0x800: 32}       # CI4, CI8, I8, RGBA16, RGBA32

def pixels(b, p, fmt, w, h):
    pal = None
    if fmt in (1, 4):
        n = 16 if fmt == 1 else 256
        pal = [rgba16(struct.unpack('>H', b[p + 2 * i:p + 2 * i + 2])[0]) for i in range(n)]
        p += 2 * n
    bpp = BPP[fmt]
    data = b[p:p + w * h * bpp // 8]
    px = []
    for i in range(w * h):
        if bpp == 4: v = data[i // 2] >> 4 if i % 2 == 0 else data[i // 2] & 15
        elif bpp == 8: v = data[i]
        elif bpp == 16: v = data[2 * i] << 8 | data[2 * i + 1]
        else: v = tuple(data[4 * i:4 * i + 4])
        if fmt == 0x400: px.append(rgba16(v))
        elif fmt == 0x800: px.append(v)
        elif pal: px.append(pal[v])
        else: px.append((255, 255, 255, v))
    im = Image.new('RGBA', (w, h)); im.putdata(px)
    return im

def sprite(i, rows=None):
    """A HUD sprite (header: frames, format, 00BE 00BE, w, h; data offsets at 0x10): frame 0."""
    b = asset(i)
    fc, fmt = struct.unpack('>HH', b[:4]); w, h = struct.unpack('>HH', b[8:12])
    o0, o1 = struct.unpack('>II', b[0x10:0x18])
    if fc == 1:                                          # single images can be shorter than w x h
        h = min(h, (o1 - o0 - {1: 32, 4: 512}.get(fmt, 0)) * 8 // (w * BPP[fmt]))
    im = pixels(b, o0, fmt, w, rows or h)
    return im.crop(im.getbbox())

def sprite_frames(i):
    """Every frame of an animated HUD sprite (shared palette, one entry per frame at 0x1C + 12*k),
    cropped to one common box so the animation doesn't wobble."""
    b = asset(i)
    fc, fmt = struct.unpack('>HH', b[:4]); w, h = struct.unpack('>HH', b[8:12])
    o0 = struct.unpack('>I', b[0x10:0x14])[0]
    palb = {1: 32, 4: 512}.get(fmt, 0); nb = w * h * BPP[fmt] // 8
    out = []
    for k in range(fc):
        off = struct.unpack('>I', b[0x1C + 12 * k + 8:0x1C + 12 * k + 12])[0]
        out.append(pixels(b[o0:o0 + palb] + b[o0 + off:o0 + off + nb], 0, fmt, w, h))
    box = out[0].getbbox()
    for f in out[1:]:
        bb = f.getbbox()
        if bb: box = (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
    return [f.crop(box) for f in out]

def model_texture(i, k):
    """Texture k of a level model (texture list: u32 size, u16 count, then 8-byte entries)."""
    b = asset(i)
    tl = struct.unpack('>H', b[8:10])[0]
    cnt = struct.unpack('>h', b[tl + 4:tl + 6])[0]
    off, typ, w, h = struct.unpack('>IHBB', b[tl + 8 + 8 * k:tl + 16 + 8 * k])
    return pixels(b, tl + 8 + 8 * cnt + off, {1: 1, 2: 4, 4: 0x400, 8: 0x800}[typ], w, h)

class Font:
    """A game font: count, 0x0100, then per glyph (w, h, advance, h) and the offset of its IA8 data."""
    def __init__(self, i, chars):
        b = asset(i)
        n = struct.unpack('>H', b[:2])[0]; base = 0x10 + 8 * n
        self.g = {}
        for k in range(n):
            tw, h, adv, _ = b[0xC + 8 * k:0x10 + 8 * k]
            off = struct.unpack('>I', b[0x10 + 8 * k:0x14 + 8 * k] if k < n - 1 else b[0x8:0xC])[0]
            d = b[base + off:base + off + tw * h]
            px = [((v >> 4) * 17,) * 3 + ((v & 15) * 17,) for v in d] + [(0, 0, 0, 0)] * (tw * h - len(d))
            im = Image.new('RGBA', (tw, h)); im.putdata(px)
            self.g[k] = (im, adv)
        self.map = dict(chars)
        self.h = max(im.height for im, a in self.g.values())
        if "'" not in self.map and '"' in self.map:       # apostrophe: one stroke of the quote mark
            im, adv = self.g[self.map['"']]
            half = im.crop((0, 0, adv // 2, im.height))           # the strokes touch: keep the left one
            self.g['apos'] = (half, half.width + 1); self.map["'"] = 'apos'

    def render(self, text, top, bottom=None, outline=(36, 18, 0), spacing=0, space=None):
        bottom = bottom or top
        space = self.h // 3 if space is None else space
        parts, w = [], 0
        for ch in text:
            if ch == ' ': parts.append(None); w += space; continue
            if ch not in self.map: continue
            im, adv = self.g[self.map[ch]]; parts.append((im, adv)); w += adv + spacing
        out = Image.new('RGBA', (max(1, w - spacing) + 2, self.h + 2)); x = 1
        for p in parts:
            if p is None: x += space; continue
            out.paste(p[0], (x, 1), p[0]); x += p[1] + spacing
        grad = Image.new('RGBA', out.size)
        for y in range(out.height):                      # vertical tint, keeping the glyph shading
            t = y / max(1, out.height - 1)
            grad.paste(tuple(int(top[j] + (bottom[j] - top[j]) * t) for j in range(3)) + (255,), (0, y, out.width, y + 1))
        tinted = ImageChops.multiply(out, grad); tinted.putalpha(out.split()[3])
        if not outline: return tinted
        ol = Image.new('RGBA', out.size, outline + (255,)); ol.putalpha(out.split()[3].filter(ImageFilter.MaxFilter(3)))
        ol.alpha_composite(tinted)
        return ol

TITLE_CHARS = {c: i for i, c in enumerate('0123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ')}
TITLE_CHARS.update({'?': 39, '(': 40, ')': 41, '<': 42, '>': 43, '"': 44, '.': 45, ';': 46, '-': 47, '!': 48, '/': 49})
TEXT_CHARS = {chr(0x21 + i): i for i in range(0x5A - 0x20)}       # '!' .. 'Z'
DIGIT_CHARS = {c: i for i, c in enumerate('0123456789:-')}

title = Font(0x0C22, TITLE_CHARS)      # big title font
text = Font(0x0C21, TEXT_CHARS)        # dialogue font
small = Font(0x0C23, DIGIT_CHARS)      # small HUD digits

YEL = ((255, 248, 150), (255, 165, 30))
CREAM = ((255, 244, 214), (236, 206, 150))
GREEN = ((200, 255, 170), (70, 200, 40))

ic = {n: sprite(i) for n, i in dict(
    jiggy=0x0BE6, note=0x0BE9, honey_empty=0x0BEA, glowbo=0x0BE8, cheato=0x0BE7, jamjars=0x0BB4,
    clock=0x0B98, egg_blue=0x0B81, egg_fire=0x0B83, egg_grenade=0x0B84, egg_ice=0x0B82, egg_clock=0x09C5,
    feather_red=0x0B4A, feather_gold=0x0B4B, btn_start=0x0B60, jinjo=0x0BD0).items()}

# Icons the game animates on its HUD: all their frames go in the .exp and play on the page
ANIM = dict(jinjo=0x0BD0, glowbo=0x0BE8, jamjars=0x0BB4, clock=0x0B98, egg_blue=0x09D7, egg_fire=0x09C1,
            egg_grenade=0x09C2, egg_ice=0x09C0, egg_clock=0x09C5, feather_red=0x0B4A, feather_gold=0x0B4B)
anim = {k: sprite_frames(i) for k, i in ANIM.items()}
FPS = 15

# ---------------------------------------------------------------------------------------------
# Drawing helpers (DS-style cards: textured fill, outline, 1px bevel, drop shadow)
# ---------------------------------------------------------------------------------------------
GW, GH = 248, 216
HEAD, TABS = 26, 36

def tile(img, w, h, ox=0, oy=0):
    out = Image.new('RGBA', (w, h))
    for y in range(-oy, h, img.height):
        for x in range(-ox, w, img.width):
            out.paste(img, (x, y))
    return out

def bright(im, f): return ImageEnhance.Brightness(im).enhance(f)

def shrink(im, size):
    s = size / max(im.size)
    if s >= 1: return im
    r = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BOX)
    r.putalpha(r.split()[3].point(lambda v: 255 if v > 110 else 0))
    return r

def put(c, im, x, y, anchor='lt'):
    if anchor[0] == 'c': x -= im.width // 2
    if anchor[0] == 'r': x -= im.width
    if anchor[1] == 'c': y -= im.height // 2
    if anchor[1] == 'b': y -= im.height
    c.alpha_composite(im, (int(x), int(y)))

def rmask(w, h, r):
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m

def card(c, x, y, w, h, tex, f, r=4, sunk=False, shadow=True):
    if shadow:
        sh = Image.new('RGBA', (w, h), (0, 0, 0, 0)); sh.putalpha(rmask(w, h, r).point(lambda v: v * 110 // 255))
        c.alpha_composite(sh, (x + 2, y + 2))
    m = rmask(w, h, r)
    im = Image.new('RGBA', (w, h)); im.paste(bright(tile(tex, w, h, x % tex.width, y % tex.height), f), (0, 0), m)
    d = ImageDraw.Draw(im)
    hi, lo = ((255, 230, 170, 150), (40, 20, 0, 170)) if not sunk else ((40, 20, 0, 170), (255, 230, 170, 90))
    d.line((r, 1, w - r - 1, 1), fill=hi); d.line((1, r, 1, h - r - 1), fill=hi)
    d.line((r, h - 2, w - r - 1, h - 2), fill=lo); d.line((w - 2, r, w - 2, h - r - 1), fill=lo)
    d.rounded_rectangle((0, 0, w - 1, h - 1), r, outline=(28, 14, 2, 255))
    c.alpha_composite(im, (x, y))

# ---------------------------------------------------------------------------------------------
# Banjo-Tooie (USA) memory. Flags are (byte << 3) | bit in the block the u32 at 0x8012C770 points
# to. Worlds in flag order; Isle o' Hags last (its Jiggies: King Jingaling + the 9 Jinjo families).
# ---------------------------------------------------------------------------------------------
WORLDS = ["MAYAHEM TEMPLE", "GLITTER GULCH MINE", "WITCHYWORLD", "JOLLY ROGER'S LAGOON", "TERRYDACTYLAND",
          "GRUNTY INDUSTRIES", "HAILFIRE PEAKS", "CLOUD CUCKOOLAND", "ISLE O' HAGS"]
MAPS = {  # map id (u16 at 0x80132DC2) -> world
    0: [0xB7, 0xB8, 0xB9, 0xBB, 0xC4, 0xC5, 0x177, 0x178, 0x17A],
    1: [0xC7, 0xCA, 0xCC, 0xCD, 0xCE, 0xCF, 0xD1, 0xD2, 0xD3, 0xD7, 0xD8, 0xDA, 0x163],
    2: [0xD5, 0xD6, 0xDD, 0xE1, 0xE6, 0xE7, 0xEA, 0xEB, 0xEC, 0xF9, 0x176],
    3: [0xED, 0xEE, 0xEF, 0xF4, 0xF6, 0xF7, 0xF8, 0xFA, 0xFC, 0xFF, 0x181, 0x1A6, 0x1A7, 0x1A8, 0x1A9],
    4: [0x112, 0x113, 0x114, 0x115, 0x116, 0x117, 0x118, 0x119, 0x11A, 0x123],
    5: [0x100, 0x101, 0x102, 0x103, 0x104, 0x106, 0x108, 0x109, 0x10A, 0x10B, 0x10D, 0x10E, 0x10F, 0x110, 0x111, 0x187],
    6: [0x127, 0x128, 0x129, 0x12A, 0x12B, 0x12C, 0x12D, 0x131, 0x132, 0x133],
    7: [0x136, 0x137, 0x138, 0x139, 0x13A, 0x13D, 0x13E, 0x13F, 0x140],
    8: [0xAD, 0xAE, 0xAF, 0x142, 0x143, 0x14F, 0x150, 0x152, 0x154, 0x155, 0x15A],
}
CLEFS = list(range(0x437, 0x4C0, 0x11))                       # one Treble Clef per world (20 notes)
NESTS = [f for f in range(0x427, 0x4C0) if f not in CLEFS]    # 16 note nests per world (5 notes)
JIGGIES = list(range(0x228, 0x278)) + [0x281] + list(range(0x278, 0x281))
W_JIGGIES = [JIGGIES[w * 10:w * 10 + 10] for w in range(9)]
W_NESTS = [NESTS[w * 16:w * 16 + 16] for w in range(9)]
W_JINJOS = [list(range(0x1CC + 5 * w, 0x1D1 + 5 * w)) for w in range(9)]
W_HONEY = [list(range(0x1FA + 3 * w, 0x1FD + 3 * w)) for w in range(8)] + [[0x212]]
W_PAGES = [list(range(0x2B3 + 3 * w, 0x2B6 + 3 * w)) for w in range(8)] + [[0x2CB]]
W_GLOWBO = [[0x217, 0x218], [0x219, 0x21A], [0x21B, 0x21C], [0x21D, 0x21E], [0x21F, 0x220],
            [0x221, 0x222], [0x02E, 0x223, 0x224], [0x225, 0x226], [0x227]]
W_MOVES = [[0xDA, 0xDB, 0xD9], [0xDE, 0xDF], [0xE1, 0xE0, 0xEE], [0xE2, 0xE3, 0xE4], [0xEB, 0xEC, 0xED],
           [0xE8, 0xEA, 0xE9], [0xE7, 0xE6], [0xEF], [0xF4, 0xF2, 0xF1, 0xF3]]   # Jamjars' moves
FLAGS = {"ptr": "0x8012C770", "offset": "0"}

def cons(i):                       # consumables: u16 at 0x8011B080 + i * 0x0C
    return {"type": "u16", "addr": "0x%08X" % (0x8011B080 + i * 0x0C)}

values = {
    "map": {"type": "u16", "addr": "0x80132DC2"},
    "world": {"type": "lookup", "value": "map", "keep_last": True, "default": -1,
              "table": {"0x%X" % m: w for w, ms in MAPS.items() for m in ms}},
    "blue_eggs": cons(0), "fire_eggs": cons(1), "ice_eggs": cons(2), "grenade_eggs": cons(3),
    "clockwork_eggs": cons(4), "red_feathers": cons(6), "gold_feathers": cons(7),
}
STATS = {  # name -> per-world flag lists (notes are nests + clef, counted below)
    "jiggies": W_JIGGIES, "jinjos": W_JINJOS, "glowbos": W_GLOWBO, "pages": W_PAGES, "honey": W_HONEY, "moves": W_MOVES,
}
for w in range(9):
    for name, per in STATS.items():
        values["w%d_%s" % (w, name)] = dict(type="flags", bits=per[w], **FLAGS)
        values["w%d_%s_done" % (w, name)] = dict(type="flags", bits=per[w], mode="all", **FLAGS)
        values["w%d_%s_max" % (w, name)] = {"type": "const", "value": "/%d" % len(per[w])}
    values["w%d_nests" % w] = dict(type="flags", bits=W_NESTS[w], **FLAGS)
    values["w%d_clef" % w] = dict(type="flags", bits=[CLEFS[w]], **FLAGS)
    values["w%d_notes" % w] = {"type": "sum", "terms": [{"value": "w%d_nests" % w, "times": 5},
                                                        {"value": "w%d_clef" % w, "times": 20}]}
    values["w%d_notes_done" % w] = dict(type="flags", bits=W_NESTS[w] + [CLEFS[w]], mode="all", **FLAGS)
    values["w%d_notes_max" % w] = {"type": "const", "value": "/100"}
for name in list(STATS) + ["notes"]:
    for suffix, default in (("", "-"), ("_done", 0), ("_max", "")):
        values["here_" + name + suffix] = {"type": "select", "index": "world", "default": default,
                                           "options": ["w%d_%s%s" % (w, name, suffix) for w in range(9)]}
        # "here_X_todo": shown in yellow until the world's set is complete
    values["here_%s_todo" % name] = {"type": "lookup", "value": "here_%s_done" % name, "table": {"0": 1}, "default": 0}

# ---------------------------------------------------------------------------------------------
# Glyph sets for the numbers (file names as the emulator asks for them: 0-9, slash, minus, colon)
# ---------------------------------------------------------------------------------------------
files = {}
GLYPH_NAME = {'/': 'slash', '-': 'minus', ':': 'colon'}

def glyphs(folder, font, chars, col, boost=1.0):
    for ch in chars:
        im = font.render(ch, *col)
        if boost != 1.0: im = bright(im, boost)      # the dialogue font is greyish; lift it for numbers
        l, _, r, _ = im.getbbox()                    # tight width: the outline keeps them apart
        files["%s/%s.png" % (folder, GLYPH_NAME.get(ch, ch))] = im.crop((l, 0, r - 1, im.height))  # outlines overlap by 1px
NUM_YEL = ((255, 255, 210), (255, 196, 50))
NUM_GREEN = ((220, 255, 200), (90, 230, 60))
glyphs("ny", text, "0123456789/-:", NUM_YEL, 1.4)   # big yellow
glyphs("ng", text, "0123456789/-:", NUM_GREEN, 1.4) # big green (set complete)
glyphs("ns", small, "0123456789-:", CREAM)     # small cream
sl = text.render('/', *CREAM); l, _, r, _ = sl.getbbox()
files["ns/slash.png"] = sl.crop((l, 4, r, 4 + files["ns/0.png"].height))

# ---------------------------------------------------------------------------------------------
# Static art, one background per world: each world's page is built from textures of that world's
# own levels (background tile, header strip, card fill, ammo strip). "model:texture" in the ROM.
# ---------------------------------------------------------------------------------------------
def tex(spec):
    m, k = spec.split(':')
    return model_texture(int(m, 16), int(k))

WOOD = {"back": "05FA:0", "back_f": 0.45, "head": "05E1:0", "card": "0674:1", "card_f": 0.9,
        "strip": "05FA:0", "strip_f": 0.7, "bar": "06D4:0", "bar_f": 0.55}
THEMES = {
    0: {"back": "1CF9:12", "back_f": 0.5, "head": "082E:1", "card": "0968:1", "card_f": 0.8, "strip": "0866:6"},
    1: {"back": "0817:6", "back_f": 0.6, "head": "08D5:2", "card": "06E9:2", "card_f": 0.85, "strip": "08F0:1"},
    2: {"back": "085D:8", "back_f": 0.5, "head": "0701:0", "card": "0876:0", "card_f": 0.6, "strip": "08BD:0"},
    3: {"back": "08B8:5", "back_f": 0.5, "head": "05E1:0", "card": "0674:1", "card_f": 0.9, "strip": "08C1:1"},
    4: {"back": "099B:2", "back_f": 0.5, "head": "1CF9:62", "card": "08DD:1", "card_f": 0.8, "strip": "080B:4"},
    5: {"back": "0817:3", "back_f": 0.7, "head": "087C:0", "card": "0755:2", "card_f": 0.9, "strip": "08F0:1"},
    6: {"back": "0865:0", "back_f": 0.5, "head": "07BB:1", "card": "06CB:4", "card_f": 0.8, "strip": "08C1:1"},
    7: {"back": "080B:38", "back_f": 0.7, "head": "06F2:3", "card": "0999:0", "card_f": 0.85, "strip": "080B:36"},
    8: {},
}

CARDS = [("jiggies", "jiggy"), ("notes", "note"), ("jinjos", "jinjo"), ("glowbos", "glowbo"),
         ("pages", "cheato"), ("honey", "honey_empty"), ("moves", "jamjars"), ("time", "clock")]
CW, CH, CG = 56, 54, 4
CX0, CY0 = (GW - 4 * CW - 3 * CG) // 2, HEAD + 5
AY = CY0 + 2 * (CH + CG) + 2
AMMO = [("blue_eggs", "egg_blue"), ("fire_eggs", "egg_fire"), ("grenade_eggs", "egg_grenade"), ("ice_eggs", "egg_ice"),
        ("clockwork_eggs", "egg_clock"), ("red_feathers", "feather_red"), ("gold_feathers", "feather_gold")]
STEP = (GW - 2 * CX0 - 4) / len(AMMO)
TY = GH - TABS
T1 = (8, TY + 3, 44, TABS - 5)
BUTTONS = ((60, 86, "MENU", 'btn_start', "menu"), (152, 88, "SAVE/QUIT", None, "save_quit"))

def static_art(theme):
    th = dict(WOOD, **theme)
    back, head, cardt, strip, bar = (tex(th[k]) for k in ("back", "head", "card", "strip", "bar"))
    wood, light = tex(WOOD["back"]), tex(WOOD["card"])
    bg = bright(tile(back, GW, GH), th["back_f"]).convert('RGBA')
    ov = Image.new('RGBA', (GW, GH)); d = ImageDraw.Draw(ov)
    for k in range(-GH, GW, 12):
        d.line((k, 0, k + GH, GH), fill=(255, 220, 160, 14), width=4)
    bg.alpha_composite(ov)
    bg.alpha_composite(tile(head, GW, HEAD), (0, 0))
    ov = Image.new('RGBA', (GW, HEAD), (0, 0, 0, 60)); bg.alpha_composite(ov)          # keep the title readable
    d = ImageDraw.Draw(bg)
    d.line((0, HEAD - 2, GW, HEAD - 2), fill=(255, 220, 150, 120)); d.line((0, HEAD - 1, GW, HEAD - 1), fill=(24, 12, 0, 255))
    for k, (name, icon) in enumerate(CARDS):
        x = CX0 + (k % 4) * (CW + CG); y = CY0 + (k // 4) * (CH + CG)
        card(bg, x, y, CW, CH, cardt, th["card_f"])
        plate = Image.new('RGBA', (CW - 8, 15), (0, 0, 0, 0))
        plate.putalpha(rmask(CW - 8, 15, 3).point(lambda v: v * 120 // 255))
        bg.alpha_composite(plate, (x + 4, y + CH - 19))                                # number plate
        if icon not in anim: put(bg, ic[icon], x + CW // 2, y + 18, 'cc')
    card(bg, CX0, AY, GW - 2 * CX0, 24, strip, th["strip_f"], sunk=True, shadow=False)
    ov = Image.new('RGBA', (GW - 2 * CX0 - 4, 20), (0, 0, 0, 70)); bg.alpha_composite(ov, (CX0 + 2, AY + 2))
    for k, (name, icon) in enumerate(AMMO):
        x = CX0 + 4 + int(k * STEP)
        if icon not in anim: put(bg, shrink(ic[icon], 17), x, AY + 12, 'lc')
    bg.alpha_composite(bright(tile(bar, GW, TABS), th["bar_f"]), (0, TY))
    d = ImageDraw.Draw(bg)
    d.line((0, TY, GW, TY), fill=(24, 12, 0, 255)); d.line((0, TY + 1, GW, TY + 1), fill=(255, 210, 150, 90))
    card(bg, *T1, light, 1.0, r=5)                       # tab 1: this page (raised, lit)
    put(bg, shrink(ic['jiggy'], 24), T1[0] + T1[2] // 2, T1[1] + T1[3] // 2, 'cc')
    d.polygon([(T1[0] + 18, TY + 1), (T1[0] + 26, TY + 1), (T1[0] + 22, TY - 3)], fill=(255, 214, 40, 255))
    for (x, w, label, icon, action) in BUTTONS:          # menu, save and quit
        y, h = TY + 6, TABS - 9
        card(bg, x, y, w, h, wood, 0.62, r=5, shadow=True)
        lab = text.render(label, *CREAM)
        if icon:
            im = shrink(ic[icon], 18)
            put(bg, im, x + 6, y + h // 2, 'lc'); put(bg, lab, x + 6 + im.width + 4, y + h // 2 + 1, 'lc')
        else:
            put(bg, lab, x + w // 2, y + h // 2 + 1, 'cc')
    return bg

# Dynamic layers: the world's background, its name, the numbers
backs = {"default": "images/bg_none.png"}
files["images/bg_none.png"] = static_art({})
for w in range(9):
    files["images/bg_%d.png" % w] = static_art(THEMES[w]); backs[str(w)] = "images/bg_%d.png" % w
layers = [{"image": "images/bg_none.png", "x": 0, "y": 0},          # before the game runs
          {"pick": "world", "images": backs, "x": 0, "y": 0}]
def frames_layer(icon, size, x, y, phase):
    fr = anim[icon]
    s = min(1, size / max(fr[0].size)) if size else 1
    for f, im in enumerate(fr):
        files["anim/%s_%d.png" % (icon, f)] = shrink(im, max(im.size) * s) if s < 1 else im
    return {"frames": "anim/%s_{f}.png" % icon, "length": len(fr), "fps": FPS, "phase": phase,
            "anchor": "center", "x": x, "y": y}
for k, (name, icon) in enumerate(CARDS):
    if icon in anim:
        x = CX0 + (k % 4) * (CW + CG); y = CY0 + (k // 4) * (CH + CG)
        layers.append(frames_layer(icon, 0, x + CW // 2, y + 18, k * 2))
for k, (name, icon) in enumerate(AMMO):
    x = CX0 + 4 + int(k * STEP)
    w = shrink(ic[icon], 17).width
    layers.append(frames_layer(icon, 17, x + w // 2, AY + 12, k * 3))
for k, (name, icon) in enumerate(CARDS):
    x = CX0 + (k % 4) * (CW + CG); y = CY0 + (k // 4) * (CH + CG)
    cx, ny = x + CW // 2, y + CH - 19
    if name == "time":
        layers.append({"number": "time", "glyphs": "ny/{c}.png", "align": "center", "x": cx, "y": ny})
        continue
    split = cx - 4
    layers += [
        {"number": "here_" + name, "glyphs": "ny/{c}.png", "align": "right", "x": split, "y": ny, "show": "here_%s_todo" % name},
        {"number": "here_" + name, "glyphs": "ng/{c}.png", "align": "right", "x": split, "y": ny, "show": "here_%s_done" % name},
        {"number": "here_%s_max" % name, "glyphs": "ns/{c}.png", "x": split - 1, "y": ny + 3},
    ]
for k, (name, icon) in enumerate(AMMO):
    x = CX0 + 4 + int(k * STEP)
    layers.append({"number": name, "glyphs": "ns/{c}.png", "x": x + shrink(ic[icon], 17).width + 1, "y": AY + 6})
buttons = [{"x": x, "y": TY + 6, "w": w, "h": TABS - 9, "action": a} for (x, w, _, _, a) in BUTTONS]

# World names for the header (picked by the world value), squeezed to fit like a DS title bar
def header(name):
    for sp, space in ((0, None), (-1, 5), (-2, 5), (-3, 4)):
        im = title.render(name, *YEL, spacing=sp, space=space)
        if im.width <= GW - 6: return im
    return title.render(name.split(' ')[0] + ' ' + name.split(' ')[1], *YEL, spacing=-2, space=5)
pick = {"default": "images/w_none.png"}
files["images/w_none.png"] = header("BANJO-TOOIE")
for w, name in enumerate(WORLDS):
    files["images/w_%d.png" % w] = header(name)
    pick[str(w)] = "images/w_%d.png" % w
layers.insert(2, {"pick": "world", "images": pick, "anchor": "center", "x": GW // 2, "y": HEAD // 2 + 1})

manifest = {
    "format": 1,
    "id": "banjotooie-usa",
    "name": "Banjo-Tooie",
    "game": "Banjo-Tooie (USA)",
    "version": VERSION,
    "author": "Hydriostatic",
    "match": {"header": "BANJO TOOIE", "country": "E"},
    "theme": {"background": "#2A1709"},
    "screen": {"title": "Banjo-Tooie"},
    "pixel_screen": {"size": [GW, GH], "fill": "#2A1709", "layers": layers, "buttons": buttons,
                     "transition": {"value": "world", "style": "jigsaw", "ms": 850, "cols": 8, "rows": 7}},
    "values": values,
}

def png(im):
    b = io.BytesIO(); im.save(b, 'PNG', optimize=True); return b.getvalue()

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    for path, im in files.items(): z.writestr(path, png(im))
print('wrote', OUT, '(%d files)' % (len(files) + 1))

# ---------------------------------------------------------------------------------------------
# Optional preview: draws the pixel_screen the way the emulator does, evaluating the manifest's
# values against a made-up flag block and counters.
# ---------------------------------------------------------------------------------------------
if PREVIEW:
    import random
    random.seed(3)
    import os
    world_map = int(os.environ.get('PREVIEW_MAP', '0xB8'), 16)   # default: Mayahem Temple
    flags = set(random.sample(range(0x228, 0x4C0), 260)) | set(W_JIGGIES[0][:3]) | set(W_GLOWBO[0])
    flags -= set(W_JIGGIES[0][3:]) | set(W_HONEY[0])
    mem = {"map": world_map, "blue_eggs": 100, "fire_eggs": 50, "ice_eggs": 50, "grenade_eggs": 25,
           "clockwork_eggs": 10, "red_feathers": 50, "gold_feathers": 10}

    def val(key):
        if key == "time": return "12:34"
        dfn = values[key]; t = dfn["type"]
        if key in mem: return mem[key]
        if t == "flags":
            n = sum(1 for b in dfn["bits"] if b in flags)
            mode = dfn.get("mode", "count")
            return int(n > 0) if mode == "any" else int(n == len(dfn["bits"])) if mode == "all" else n
        if t == "sum": return sum(val(x["value"]) * x.get("times", 1) for x in dfn["terms"])
        if t == "const": return dfn["value"]
        if t == "select":
            i = val(dfn["index"])
            return val(dfn["options"][i]) if isinstance(i, int) and 0 <= i < len(dfn["options"]) else dfn.get("default")
        if t == "lookup":
            v = val(dfn["value"])
            return dfn["table"].get(str(v), dfn["table"].get("0x%X" % v if isinstance(v, int) else "", dfn.get("default")))
        raise ValueError(key)

    def truthy(k):
        v = val(k)
        return v not in (None, 0, "", "0")

    canvas = Image.new('RGBA', (GW, GH))
    def draw(path, x, y, center=False):
        im = files[path]
        if center: x, y = x - im.width // 2, y - im.height // 2
        canvas.alpha_composite(im, (int(x), int(y)))
    for ly in layers:
        if 'show' in ly and not truthy(ly['show']): continue
        if 'hide' in ly and truthy(ly['hide']): continue
        c = ly.get('anchor') == 'center'
        if 'image' in ly: draw(ly['image'], ly['x'], ly['y'], c)
        elif 'frames' in ly: draw(ly['frames'].replace('{f}', str(int(ly['phase']) % ly['length'])), ly['x'], ly['y'], c)
        elif 'pick' in ly: draw(ly['images'].get(str(val(ly['pick'])), ly['images']['default']), ly['x'], ly['y'], c)
        elif 'number' in ly:
            s = str(val(ly['number']))
            paths = [ly['glyphs'].replace('{c}', GLYPH_NAME.get(ch, ch)) for ch in s]
            tot = sum(files[p].width for p in paths)
            x = ly['x'] - tot if ly.get('align') == 'right' else ly['x'] - tot / 2 if ly.get('align') == 'center' else ly['x']
            for p in paths: draw(p, x, ly['y']); x += files[p].width
    canvas.resize((GW * 5, GH * 5), Image.NEAREST).save(PREVIEW)
    print('preview', PREVIEW)
