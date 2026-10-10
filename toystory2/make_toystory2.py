#!/usr/bin/env python3
"""
Builds toystory2.exp (Toy Story 2: Buzz Lightyear to the Rescue!, USA Rev 1) from your own ROM.

    python3 make_toystory2.py "Toy Story 2 - Buzz Lightyear to the Rescue! (USA) (Rev 1).z64" [toystory2.exp] [preview.png]

The bottom screen is a 248x216 pixel page that the emulator scales 5x (1240x1080 on the AYN Thor)
with no smoothing. Every image is read from the ROM: the game's menu font (psxfont) for the level
name, its small font (tahoma08) for labels and hints, the HUD sprites (Buzz, battery, coin, gold
digits), the level-complete icons and the spinning Pizza Planet token. Nothing from the ROM is
stored in this repo.

How the ROM is laid out (worked out for this expansion):
  0x0D8E78  file table: name\\0 (padded to 4), u32 stored size, u32 0
  0x0DC380  file data, in table order, each file aligned to 8 bytes
  Most files are RNC method 1 ("RNC\\x01"). .tpg = 16 page codes + 256-colour RGBA5551 palette + pages
  (a 4-bit page in slot N uses palette entries N*16..N*16+15). .fnt = glyph table + 16 colours + 4-bit glyphs.
"""
import io, json, re, struct, sys, zipfile
from PIL import Image, ImageDraw

# Bump on every change to what the .exp shows (history in CHANGELOG.md).
VERSION = "1.2"

ROM_PATH = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'toystory2.exp'
PREVIEW = sys.argv[3] if len(sys.argv) > 3 else None

rom = open(ROM_PATH, 'rb').read()
if rom[:4] == b'\x37\x80\x40\x12':                      # .v64 (byte-swapped) -> .z64
    rom = b''.join(rom[i + 1:i + 2] + rom[i:i + 1] for i in range(0, len(rom), 2))
if rom[0x3B:0x3F] != b'NTHE':
    sys.exit('This is not Toy Story 2 (USA): game id %r' % rom[0x3B:0x3F])
if rom[0x3F] != 1:
    print('warning: this ROM is not Rev 1; the memory addresses in this expansion are for Rev 1')

# ------------------------------------------------------------------------------------------------
# Files
# ------------------------------------------------------------------------------------------------
FILES = {}
p, data = 0xD8E78, 0xDC380
while True:
    m = re.match(rb'([ -~]{3,40})\x00', rom[p:p + 48])
    if not m: break
    name = m.group(1).decode(); q = (p + len(name) + 1 + 3) & ~3
    size, zero = struct.unpack('>II', rom[q:q + 8])
    if zero or size > 0x200000: break
    FILES[name] = (data, size); data += (size + 7) & ~7; p = q + 8

def rnc1(src, off):
    usize = struct.unpack('>I', src[off + 4:off + 8])[0]
    out = bytearray(); pos = [off + 18]
    def w(a): return (src[a] if a < len(src) else 0) | ((src[a + 1] if a + 1 < len(src) else 0) << 8)
    st = {'buf': w(pos[0]), 'cnt': 16}
    def adv(n):
        st['buf'] >>= n; st['cnt'] -= n
        if st['cnt'] < 16:
            pos[0] += 2; st['buf'] |= w(pos[0]) << st['cnt']; st['cnt'] += 16
    def read(mask, n):
        r = st['buf'] & mask; adv(n); return r
    def fix():
        st['cnt'] -= 16; st['buf'] &= (1 << st['cnt']) - 1
        st['buf'] |= w(pos[0]) << st['cnt']; st['cnt'] += 16
    def table():
        num = read(0x1f, 5)
        if not num: return []
        lens = [read(0xf, 4) for _ in range(num)]; t = []; code = 0
        for L in range(1, max(1, max(lens)) + 1):
            for v in range(num):
                if lens[v] == L:
                    t.append((int('{:0{}b}'.format(code, L)[::-1], 2), L, v)); code += 1
            code <<= 1
        return t
    def huf(t):
        for code, L, v in t:
            if st['buf'] & ((1 << L) - 1) == code:
                adv(L)
                if v >= 2:
                    base = 1 << (v - 1); return base | read(base - 1, v - 1)
                return v
        raise ValueError('RNC decode error')
    adv(2)
    while len(out) < usize:
        raw, dist, ln = table(), table(), table()
        cnt = read(0xffff, 16)
        while True:
            n = huf(raw)
            if n:
                out += src[pos[0]:pos[0] + n]; pos[0] += n; fix()
            cnt -= 1
            if cnt <= 0: break
            d = huf(dist) + 1; n = huf(ln) + 2
            for _ in range(n): out.append(out[-d])
    return bytes(out[:usize])

def file(name):
    off, size = FILES[name]
    return rnc1(rom, off) if rom[off:off + 4] == b'RNC\x01' else rom[off:off + size]

def rgba16(v):
    return ((v >> 11 & 31) * 255 // 31, (v >> 6 & 31) * 255 // 31, (v >> 1 & 31) * 255 // 31, 255 if v & 1 else 0)

PAGE = {4: (0x200, 32, 32), 7: (0x800, 64, 64), 39: (0x800, 64, 64)}  # the CI4 page kinds used here

def tpg_page(name, slot):
    b = file(name); codes = struct.unpack('>16I', b[:64])
    pal = [rgba16(struct.unpack('>H', b[0x40 + 2 * i:0x42 + 2 * i])[0]) for i in range(256)]
    p = 0x240
    for s, c in enumerate(codes):
        if c == 0xffffffff: continue
        size, w, h = PAGE.get(c, (0x800, 64, 64))
        if s == slot:
            raw = b[p:p + size]; px = []
            for i in range(w * h):
                v = raw[i >> 1] >> 4 if i % 2 == 0 else raw[i >> 1] & 15
                px.append(pal[s * 16 + v])
            im = Image.new('RGBA', (w, h)); im.putdata(px); return im
        p += size
    raise KeyError((name, slot))

def trim(im):
    bb = im.getbbox(); return im.crop(bb) if bb else im

def font(name):
    """name.fnt -> {char: (image, advance, yoff)}"""
    b = file(name); ents = []; p = 8
    while True:
        w, h, yo, z = b[p], b[p + 1], struct.unpack('b', b[p + 2:p + 3])[0], b[p + 3]
        off = struct.unpack('>I', b[p + 4:p + 8])[0]
        if z or not w or w > 64 or h > 64 or (ents and off <= ents[-1][3]): break
        ents.append((w, h, yo, off)); p += 8
    pal = [rgba16(struct.unpack('>H', b[p + 8 + 2 * i:p + 10 + 2 * i])[0]) for i in range(16)]
    base = p + 40; g = {}
    for i, (w, h, yo, off) in enumerate(ents):
        rb = (w + 2) // 2; im = Image.new('RGBA', (rb * 2, h)); px = []
        for y in range(h):
            for x in range(rb * 2):
                v = b[base + off + y * rb + x // 2]
                px.append(pal[v >> 4 if x % 2 == 0 else v & 15])
        im.putdata(px); g[chr(0x21 + i)] = (im, w, yo)
    return g

PSX = font('fonts\\psxfont.fnt')          # menu font: yellow with a blue outline (level names)
TAH = font('fonts\\tahoma08.fnt')         # small white font with an outline

def text(s, fnt, space, tint=None, spacing=0):
    items = []; x = 0
    letters = [fnt[c] for c in 'AHMbdfghjklpqy' if c in fnt]   # fixed baseline: letters only
    top = min(yo for _, _, yo in letters)
    bot = max(yo + im.height for im, _, yo in letters)
    for ch in s:
        if ch not in fnt: x += space; continue
        im, w, yo = fnt[ch]
        if tint:
            im = im.copy(); px = im.load()
            for yy in range(im.height):
                for xx in range(im.width):
                    r, gg, bb, a = px[xx, yy]
                    if a and r > 200 and gg > 200 and bb > 200: px[xx, yy] = tint
        items.append((x, im, yo)); x += w + spacing
    out = Image.new('RGBA', (max(1, x + 2), bot - top))
    for xx, im, yo in items: out.alpha_composite(im, (xx, yo - top))
    return out

YELLOW = (255, 230, 40, 255)

def wrap(s, width, maxlines=4):
    """Hint text with ^highlight^ words in yellow, wrapped to width; long hints keep whole sentences."""
    while True:
        out = _wrap(s, width)
        if out.height <= (maxlines - 1) * 10 + 12: return out
        cut = s.rstrip('.!').rfind('. ')
        s = s[:cut + 1] if cut > 0 else ' '.join(s.split(' ')[:-1])

def _wrap(s, width):
    lines = [[]]; x = 0
    for word in s.split(' '):
        hl = '^' in word
        im = text(word.replace('^', ''), TAH, 3, YELLOW if hl else None)
        if x and x + im.width > width: lines.append([]); x = 0
        lines[-1].append((x, im)); x += im.width + 3
    lh = 10; out = Image.new('RGBA', (width, lh * (len(lines) - 1) + 12))
    for i, ln in enumerate(lines):
        for xx, im in ln: out.alpha_composite(im.crop((0, 0, im.width, min(im.height, 12))), (xx, i * lh))
    return out

# ------------------------------------------------------------------------------------------------
# Art
# ------------------------------------------------------------------------------------------------
GW, GH = 248, 216
BG, PANEL, EDGE, CARD, CARD_EDGE = '#0E1A4A', (10, 22, 70, 255), (255, 214, 0, 255), (24, 44, 104, 255), (96, 116, 176, 255)
files = {}

def panel(w, h, fill=PANEL, edge=EDGE, r=6, bw=2):
    im = Image.new('RGBA', (w, h)); ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=edge, width=bw)
    return im

hud = 'fx\\toyfx00.tpg'
files['images/buzz.png'] = trim(tpg_page(hud, 4).crop((0, 0, 32, 32)))
files['images/battery.png'] = trim(tpg_page(hud, 3).crop((0, 0, 24, 32)))
coinpage = tpg_page(hud, 3)
COIN = [coinpage.crop((x, y, x + 16, y + 16)) for x, y in
        [(32, 16), (48, 16), (0, 32), (16, 32), (32, 32), (48, 32), (0, 48), (16, 48), (32, 48), (48, 48)]]
COIN = COIN + COIN[::-1][1:-1]
for i, im in enumerate(COIN): files['anim/coin_%d.png' % i] = im
digits = tpg_page(hud, 1)
for i, ch in enumerate('0123456789'):
    files['digits/%s.png' % ch] = digits.crop(((i % 4) * 16 + 1, (i // 4) * 16, (i % 4) * 16 + 14, (i // 4) * 16 + 16))
files['digits/slash.png'] = digits.crop((2 * 16 + 1, 2 * 16, 2 * 16 + 14, 3 * 16))
hudfont = tpg_page(hud, 6)
HUDG = {}
for r, row in enumerate(['ABCDEFGH', 'IJKLMNOP', 'QRSTUVWX', 'YZ012345', '6789.,:;']):
    for c, ch in enumerate(row): HUDG[ch] = hudfont.crop((c * 8, r * 8, c * 8 + 8, r * 8 + 8))
for ch in '0123456789': files['small/%s.png' % ch] = HUDG[ch]
files['small/x.png'] = HUDG['X']
files['images/of50.png'] = Image.new('RGBA', (13 * 3, 16))
for i, ch in enumerate(['slash', '5', '0']):
    g = files['digits/%s.png' % ch]; files['images/of50.png'].alpha_composite(g, (i * 13, 0))

TOKEN = []                                # 32-frame spin, read 4 top / 4 bottom halves per group
for g in (0, 8):
    for pages, half in ((range(g, g + 4), 0), (range(g, g + 4), 1), (range(g + 4, g + 8), 0), (range(g + 4, g + 8), 1)):
        for pg in pages:
            TOKEN.append(tpg_page('level16\\token256.tpg', pg).crop((0, half * 32, 64, half * 32 + 32)))
bb = None
for im in TOKEN:
    b = im.getbbox(); bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]))
for i, im in enumerate(TOKEN): files['anim/token_%d.png' % i] = im.crop(bb)
def small(im, h=18):                              # half-size token for under each card
    w = max(1, round(im.width * h / im.height)); s2 = im.resize((w, h), Image.LANCZOS)
    a = s2.getchannel('A').point(lambda v: 255 if v >= 110 else 0); s2.putalpha(a); return s2
for i, im in enumerate(TOKEN): files['anim/token_s_%d.png' % i] = small(im.crop(bb))

def icon(tpg, slot): return trim(tpg_page('level00\\%s.tpg' % tpg, slot).crop((0, 0, 32, 32)))
HAMM, RACE, SECRET = icon('levcomp1', 10), icon('levcomp1', 11), icon('levcomp1', 12)

# level -> (name, mission label, mission icon slot, boss label, boss icon slot) ; boss stages have no cards
LEVELS = {
    1: ("Andy's House", 'Sheep', 0, 'Tin Robot', 0),
    2: ("Andy's Neighborhood", 'Troops', 1, 'Zurg Kite', 1),
    3: ("Bombs Away!", None, None, None, None),
    4: ("Construction Yard", 'Tikes', 2, 'Jackhammer', 2),
    5: ("Alleys and Gullies", 'Ducks', 3, 'Clown Top', 3),
    6: ("Slime Time", None, None, None, None),
    7: ("Al's Toy Barn", 'Chicks', 4, 'Boss', 4),
    8: ("Al's Space Land", 'Aliens', 5, 'Boss', 5),
    9: ("Toy Barn Encounter", None, None, None, None),
    10: ("Elevator Hop", 'Mice', 6, 'Spider', 6),
    11: ("Al's Penthouse", 'Critter', 7, 'Gunslinger', 7),
    12: ("Prospector Showdown", None, None, None, None),
    13: ("Airport Infiltration", 'Tikes', 8, 'Prospector', 8),
    14: ("Tarmac Trouble", 'Luggage', 9, 'Blacksmith', 9),
    15: ("The Evil Emperor Zurg", None, None, None, None),
}
HINTS = {                                   # Hamm's coin hint for each level, from the game's own text
    1: "^hamm^ is sitting on the sofa in the living room.",
    2: "^hamm^ is on the first branch of the ^tree^. climb the ^swing set^ to get to him.",
    4: "i think i saw hamm over by the ^wheelbarrow^.",
    5: "i saw ^hamm^ in the market place near an ^umbrella^.",
    7: "i saw ^hamm^ on the table in the ^office^.",
    8: "i saw ^hamm^ at the end of the ^laser battle zone^.",
    10: "^hamm^ is in the ^electrical room^. use the ^pole swings^ to get to him. watch out for the electricity!",
    11: "^hamm^ is in the ^bathroom!^. you can reach the bathroom through a hidden vent. look out for any ^locks^ that you can shoot!",
    13: "^hamm^ is on the shelf at the end of the x-ray room.",
    14: "i think i saw ^hamm^ in zone ^5^.",
}
BOSS_HINT = "defeat the ^boss^ to get a pizza planet ^token^!"

# layout (pixels of the 248x216 page): 4 px margins and gaps, room inside every panel
M = 4
HX, HY, HW, HH = M, M, GW - 2 * M, 48       # header: level name, level number, spinning token
SY, SH = HY + HH + M, 38                    # status row
BY, BH = SY + SH + M, 72                    # token cards
NY = BY + BH + M; NH = GH - M - NY          # hint panel
files['images/bg.png'] = Image.new('RGBA', (GW, GH), BG)
files['images/header.png'] = panel(HW, HH)
files['images/status.png'] = panel(GW - 2 * M, SH)
files['images/board.png'] = panel(GW - 2 * M, BH)
files['images/hint.png'] = panel(GW - 2 * M, NH)
files['images/hamm.png'] = HAMM
SEGS, SEG = 14, 3                           # battery: 14 segments, 3 px apart
seg_on = Image.new('RGBA', (SEG, 18)); ImageDraw.Draw(seg_on).rectangle((0, 0, 1, 17), fill=(120, 255, 60, 255))
seg_off = Image.new('RGBA', (SEG * SEGS, 18))
for i in range(SEGS): ImageDraw.Draw(seg_off).rectangle((i * SEG, 0, i * SEG + 1, 17), fill=(40, 62, 40, 255))
files['images/seg_on.png'] = seg_on; files['images/seg_off.png'] = seg_off

CW, CG = 42, 4                              # card width, gap between cards
CX0 = M + (GW - 2 * M - (5 * CW + 4 * CG)) // 2
CH = BH - 12
def card(ic):
    c = panel(CW, CH, fill=CARD, edge=CARD_EDGE, r=5, bw=1)
    c.alpha_composite(ic, ((c.width - ic.width) // 2, 34 - ic.height))
    return c

NAME_W = HW - 8 - 64                        # name area (the right side holds LEVEL n and the token)
names, boards, hints = {}, {}, {}
for lv, (nm, mlab, mslot, blab, bslot) in LEVELS.items():
    head = Image.new('RGBA', (HW - 8, HH - 6))
    t = text('LEVEL %d' % lv, TAH, 3, YELLOW); head.alpha_composite(t, (head.width - t.width - 4, 1))
    one = text(nm, PSX, 5)
    if one.width <= NAME_W:
        head.alpha_composite(one, (4, (head.height - one.height) // 2))
    else:                                     # long names: two lines, split where the lines are most even
        words = nm.split(' ')
        best = min(range(1, len(words)), key=lambda k: max(text(' '.join(words[:k]), PSX, 5).width,
                                                           text(' '.join(words[k:]), PSX, 5).width))
        l1, l2 = text(' '.join(words[:best]), PSX, 5), text(' '.join(words[best:]), PSX, 5)
        head.alpha_composite(l1, (4, 0)); head.alpha_composite(l2, (4, head.height - l2.height))
    files['names/%d.png' % lv] = head; names[str(lv)] = 'names/%d.png' % lv
    b = Image.new('RGBA', (GW - 2 * M, BH))
    if mlab:
        cards = [HAMM, icon('levcomp1', mslot), RACE, icon('levcomp2', bslot), SECRET]
        for i, ic in enumerate(cards): b.alpha_composite(card(ic), (CX0 - M + i * (CW + CG), 6))
    else:
        t = text('BOSS STAGE', PSX, 5); b.alpha_composite(t, ((b.width - t.width) // 2, 5))
    files['boards/%d.png' % lv] = b; boards[str(lv)] = 'boards/%d.png' % lv
    hint = wrap(HINTS.get(lv, BOSS_HINT), GW - 2 * M - 52, maxlines=2)
    hb = Image.new('RGBA', (hint.width, NH - 4)); hb.alpha_composite(hint, (0, (hb.height - hint.height) // 2))
    files['hints/%d.png' % lv] = hb; hints[str(lv)] = 'hints/%d.png' % lv
title = Image.new('RGBA', (HW - 8, HH - 6))
t = text('Toy Story 2', PSX, 5); title.alpha_composite(t, (4, (title.height - t.height) // 2))
files['names/title.png'] = title; names['default'] = 'names/title.png'
files['boards/none.png'] = Image.new('RGBA', (1, 1)); boards['default'] = 'boards/none.png'
files['hints/none.png'] = Image.new('RGBA', (1, 1)); hints['default'] = 'hints/none.png'

# ------------------------------------------------------------------------------------------------
# Memory (USA Rev 1). The stats are the public GameShark addresses moved by +0x450 for Rev 1; the
# game's code adds 4 to the battery and caps it at 14, and warns when it is low. The level is the
# number the game uses to load the level's title card (pictures\\lvlNNx.pic).
# ------------------------------------------------------------------------------------------------
values = {
    "level":   {"type": "u32", "addr": "0x801EFBEC"},
    "battery": {"type": "u16", "addr": "0x800BB556"},
    "lives":   {"type": "u16", "addr": "0x800BB55A"},
    "coins":   {"type": "u16", "addr": "0x800BB55E"},
    "in_level": {"type": "lookup", "value": "level", "table": {str(k): 1 for k in LEVELS}, "default": 0},
    "card_level": {"type": "lookup", "value": "level", "table": {str(k): 1 for k, v in LEVELS.items() if v[1]}, "default": 0},
    "boss_stage": {"type": "lookup", "value": "level", "table": {str(k): 1 for k, v in LEVELS.items() if not v[1]}, "default": 0},
}

# ------------------------------------------------------------------------------------------------
# Page
# ------------------------------------------------------------------------------------------------
L = [{"image": "images/bg.png", "x": 0, "y": 0},
     {"image": "images/header.png", "x": HX, "y": HY},
     {"pick": "level", "images": names, "x": HX + 4, "y": HY + 3},
     {"frames": "anim/token_{f}.png", "length": len(TOKEN), "fps": 20, "phase": 0, "anchor": "center",
      "x": GW - M - 34, "y": HY + 30},
     {"image": "images/status.png", "x": M, "y": SY},
     {"image": "images/buzz.png", "anchor": "center", "x": M + 20, "y": SY + SH // 2},
     {"image": "small/x.png", "x": M + 37, "y": SY + 15},
     {"number": "lives", "glyphs": "small/{c}.png", "advance": 8, "x": M + 46, "y": SY + 15},
     {"image": "images/battery.png", "anchor": "center", "x": M + 82, "y": SY + SH // 2},
     {"image": "images/seg_off.png", "x": M + 98, "y": SY + 10},
     {"repeat": "images/seg_on.png", "count": "battery", "max": SEGS, "dx": SEG, "x": M + 98, "y": SY + 10},
     {"frames": "anim/coin_{f}.png", "length": len(COIN), "fps": 14, "phase": 0, "anchor": "center",
      "x": M + 157, "y": SY + SH // 2},
     {"number": "coins", "glyphs": "digits/{c}.png", "advance": 13, "align": "right", "x": GW - M - 47, "y": SY + 11},
     {"image": "images/of50.png", "x": GW - M - 47, "y": SY + 11},
     {"image": "images/board.png", "x": M, "y": BY},
     {"pick": "level", "images": boards, "x": M, "y": BY}]
L += [{"frames": "anim/token_s_{f}.png", "length": len(TOKEN), "fps": 20, "phase": i * 6, "anchor": "center",
       "x": CX0 + i * (CW + CG) + CW // 2, "y": BY + 6 + 46, "show": "card_level"} for i in range(5)]
L += [{"frames": "anim/token_{f}.png", "length": len(TOKEN), "fps": 20, "phase": 8, "anchor": "center",
       "x": GW // 2, "y": BY + 46, "show": "boss_stage"},
     {"image": "images/hint.png", "x": M, "y": NY},
     {"image": "images/hamm.png", "anchor": "center", "x": M + 22, "y": NY + NH // 2, "show": "in_level"},
     {"pick": "level", "images": hints, "x": M + 44, "y": NY + 2}]

manifest = {
    "format": 1,
    "id": "toystory2-usa",
    "name": "Toy Story 2",
    "game": "Toy Story 2: Buzz Lightyear to the Rescue! (USA) (Rev 1)",
    "version": VERSION,
    "author": "Hydriostatic",
    "match": {"header": "Toy Story 2", "country": "E"},
    "theme": {"background": BG},
    "screen": {"title": "Toy Story 2"},
    "pixel_screen": {"size": [GW, GH], "fill": BG, "layers": L,
                     "transition": {"value": "level", "style": "fade", "ms": 500}},
    "values": values,
}

def png(im):
    b = io.BytesIO(); im.save(b, 'PNG', optimize=True); return b.getvalue()

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    for path, im in files.items(): z.writestr(path, png(im))
print('wrote', OUT, '(%d files)' % (len(files) + 1))

# ------------------------------------------------------------------------------------------------
# Optional preview: draws the page the way the emulator does, with made-up values.
# PREVIEW_LEVEL picks the level (default 1); PREVIEW_FRAME the animation frame.
# ------------------------------------------------------------------------------------------------
if PREVIEW:
    import os
    mem = {"level": int(os.environ.get('PREVIEW_LEVEL', '1')), "battery": 9, "lives": 3, "coins": 37}
    frame = int(os.environ.get('PREVIEW_FRAME', '0'))
    def val(k):
        d = values[k]
        if d["type"] == "lookup": return d["table"].get(str(val(d["value"])), d.get("default"))
        return mem[k]
    GL = {'/': 'slash'}
    canvas = Image.new('RGBA', (GW, GH))
    def draw(path, x, y, center=False):
        im = files[path]
        if center: x, y = x - im.width // 2, y - im.height // 2
        canvas.alpha_composite(im, (int(x), int(y)))
    for ly in L:
        if 'show' in ly and not val(ly['show']): continue
        c = ly.get('anchor') == 'center'
        if 'image' in ly: draw(ly['image'], ly['x'], ly['y'], c)
        elif 'frames' in ly: draw(ly['frames'].replace('{f}', str((frame + ly['phase']) % ly['length'])), ly['x'], ly['y'], c)
        elif 'pick' in ly: draw(ly['images'].get(str(val(ly['pick'])), ly['images']['default']), ly['x'], ly['y'], c)
        elif 'repeat' in ly:
            for i in range(min(val(ly['count']), ly['max'])): draw(ly['repeat'], ly['x'] + i * ly['dx'], ly['y'])
        elif 'number' in ly:
            s = str(val(ly['number'])); paths = [ly['glyphs'].replace('{c}', GL.get(ch, ch)) for ch in s]
            adv = ly.get('advance'); tot = sum(adv or files[p].width for p in paths)
            x = ly['x'] - tot if ly.get('align') == 'right' else ly['x']
            for p in paths: draw(p, x, ly['y']); x += adv or files[p].width
    canvas.resize((GW * 5, GH * 5), Image.NEAREST).save(PREVIEW)
    print('preview', PREVIEW)
