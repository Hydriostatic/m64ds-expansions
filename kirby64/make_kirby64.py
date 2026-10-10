#!/usr/bin/env python3
"""
Builds kirby64.exp (Kirby 64: The Crystal Shards, USA) from your own ROM.

    python3 make_kirby64.py "Kirby 64 - The Crystal Shards (USA).z64" [kirby64.exp] [preview.png]

All art is cut from the ROM's own HUD and menu sprites (the game's image banks), so the panel uses
the game's colours and fonts. Nothing from the ROM is stored in this repo. The page is a
"pixel_screen": a 248x199 canvas that the emulator scales up by a whole number, with no smoothing.

Memory addresses come from the Kirby 64 decompilation (github.com/farisawan-2000/kirby64), which
matches the USA ROM (sha1 6cea2d46b929a3bb347b060a77fccc83526fb855).
"""
import io, json, random, struct, sys, zipfile, hashlib
from PIL import Image, ImageDraw, ImageOps

ROM_PATH = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else 'kirby64.exp'
PREVIEW = sys.argv[3] if len(sys.argv) > 3 else None

rom = open(ROM_PATH, 'rb').read()
if rom[:4] == b'\x37\x80\x40\x12':                      # .v64 (byte-swapped) -> .z64
    rom = b''.join(rom[i + 1:i + 2] + rom[i:i + 1] for i in range(0, len(rom), 2))
if rom[0x3B:0x3F] != b'NK4E':
    sys.exit('This is not Kirby 64 (USA): game id %r' % rom[0x3B:0x3F])

# ---------------------------------------------------------------------------------------------
# The game's image files. ovl1 is loaded at 0x8009B540 from ROM 0x43790; gFileTable (0x800D0184)
# holds 8 bank headers, each with an image offset table and the ROM base of its images.
# ---------------------------------------------------------------------------------------------
def v2r(v): return 0x43790 + (v - 0x8009B540)
def u32(a): return struct.unpack('>I', rom[a:a + 4])[0]
BANKS = [u32(v2r(0x800D0184) + 4 * i) for i in range(8)]

def image_file(bank, index):
    h = struct.unpack('>8I', rom[v2r(BANKS[bank]):v2r(BANKS[bank]) + 32])
    t = v2r(h[2]) + 4 * index
    return h[3] + u32(t)

def rgba16(v):
    return ((v >> 11 & 31) * 255 // 31, (v >> 6 & 31) * 255 // 31, (v >> 1 & 31) * 255 // 31, 255 if v & 1 else 0)

def sprite(bank, index):
    """Decode one image file: 16-byte header (fmt, size, -, -, w, h, data offset, palette offset)."""
    a = image_file(bank, index)
    fmt, siz = rom[a], rom[a + 1]
    w, h = struct.unpack('>HH', rom[a + 4:a + 8])
    bpp = [4, 8, 16, 32][siz]
    stride = ((w * bpp + 7) // 8 + 7) // 8 * 8          # rows are padded to 8 bytes
    pal = None
    if fmt == 2:
        po = u32(a + 12)
        n = 16 if bpp == 4 else 256
        pal = [rgba16(struct.unpack('>H', rom[a + po + 2 * i:a + po + 2 * i + 2])[0]) for i in range(n)]
    px = []
    for y in range(h):
        row = rom[a + 16 + y * stride:a + 16 + (y + 1) * stride]
        for x in range(w):
            v = (row[x // 2] >> 4 if x % 2 == 0 else row[x // 2] & 15) if bpp == 4 else \
                row[x] if bpp == 8 else (row[2 * x] << 8 | row[2 * x + 1]) if bpp == 16 else tuple(row[4 * x:4 * x + 4])
            if fmt == 0: px.append(rgba16(v) if bpp == 16 else v)
            elif fmt == 2: px.append(pal[v])
            elif fmt == 3:
                px.append(((v >> 1) * 36,) * 3 + (255 if v & 1 else 0,) if bpp == 4 else ((v >> 4) * 17,) * 3 + ((v & 15) * 17,))
            else:
                c = v * 17 if bpp == 4 else v
                px.append((c, c, c, c))
    im = Image.new('RGBA', (w, h))
    im.putdata(px)
    return im

# --- Sprites used (bank 5 = HUD, wood theme; bank 3 = menus) --------------------------------
frame = sprite(5, 0x01)                                   # 320x48 HUD bar, wood theme
digit = {d: sprite(5, 0xBF + d) for d in range(10)}       # HUD digits, wood theme (18x30)
cell = sprite(5, 0xA2)                                    # full health cell
star = sprite(5, 0xAC)                                    # star meter segment, lit (pale yellow)
ICON_IDS = [0xF1, 0xF2, 0xF3, 0xF8, 0xF4, 0xF5, 0xF6, 0xF7, 0xF9, 0xFA]   # D_800D5310, theme 0
icon = {i: sprite(5, ICON_IDS[i]) for i in range(1, 10)}  # 1 fire .. 7 cutter, 8-9 specials
world_name = {w: sprite(3, i) for w, i in enumerate([0x1F6, 0x1FC, 0x1FB, 0x1F8, 0x1F7, 0x1F9, 0x1FA])}
level_word = sprite(3, 0x1FD)                             # "Level"
level_num = {n: sprite(3, 0x1FE + n) for n in range(1, 8)} # outlined 1..7
small = {d: sprite(3, 0x1C2 + d) for d in range(10)}      # outlined small digits
small_slash = sprite(3, 0x1CC)

# HUD ability index (0..37) -> left/right element icon (table D_800D55F8, 2 bytes each)
pairs = rom[v2r(0x800D55F8):v2r(0x800D55F8) + 2 * 38]
AB_L = {i: pairs[2 * i] for i in range(38)}
AB_R = {i: pairs[2 * i + 1] for i in range(38)}

# ---------------------------------------------------------------------------------------------
# Static art: one background with everything that never changes
# ---------------------------------------------------------------------------------------------
GW, GH = 248, 199
DARK, EDGE = (106, 74, 8, 255), (246, 197, 98, 255)
X0 = (GW - 206) // 2                                       # left edge of the content (21)
Y_HUD, Y_WORLD, Y_ABIL, Y_TOTAL = 4, 58, 90, 144

def rounded(d, x, y, w, h, fill):
    d.rectangle((x + 2, y, x + w - 3, y + h - 1), fill=fill)
    d.rectangle((x, y + 2, x + w - 1, y + h - 3), fill=fill)
    d.rectangle((x + 1, y + 1, x + w - 2, y + h - 2), fill=fill)

SHARD = ["...a...", "..aba..", ".abbca.", ".abbca.", "abbbcca", "abbbcca", ".abbca.", ".abcca.", "..aca..", "...a..."]
def shard_img(got):
    pal = {'a': (40, 72, 160, 255), 'b': (170, 230, 255, 255), 'c': (90, 170, 240, 255)} if got else \
          {'a': (70, 48, 6, 255), 'b': (84, 58, 8, 255), 'c': (84, 58, 8, 255)}
    im = Image.new('RGBA', (7, 10))
    for j, row in enumerate(SHARD):
        for i, ch in enumerate(row):
            if ch != '.': im.putpixel((i, j), pal[ch])
    return im
SHARD_ON, SHARD_OFF = shard_img(True), shard_img(False)
SHARD_POS = [(3, 18), (14, 18), (8, 32)]                   # inside a stage box

def stage_box(n):
    im = Image.new('RGBA', (24, 44))
    rounded(ImageDraw.Draw(im), 0, 0, 24, 44, DARK)
    im.alpha_composite(small[n], (7, 3))
    for (sx, sy) in SHARD_POS: im.alpha_composite(SHARD_OFF, (sx, sy))
    return im

bg = Image.new('RGBA', (GW, GH))
stripe = frame.crop((12, 2, 13, 24)).resize((GW, 22), Image.NEAREST)  # the HUD's wood stripes
for y in range(0, GH, 22): bg.paste(stripe, (0, y))
d = ImageDraw.Draw(bg)
bg.alpha_composite(frame.crop((10, 1, 216, 45)), (X0, Y_HUD))          # lives box + health + stars
rounded(d, X0, Y_WORLD, 206, 26, DARK)                                  # world strip
bg.alpha_composite(level_word, (X0 + 132, Y_WORLD + 6))
bg.alpha_composite(frame.crop((216, 1, 310, 45)), (X0, Y_ABIL))          # ability slot, as in the HUD
for k in range(3): bg.alpha_composite(stage_box(k + 1), (X0 + 100 + k * 27, Y_ABIL + 1))
rounded(d, X0, Y_TOTAL, 206, 48, DARK)                                  # totals
for (sx, sy) in [(10, 8), (20, 8), (15, 24)]: bg.alpha_composite(SHARD_ON, (X0 + sx, Y_TOTAL + sy))
TOT_SLASH_X = X0 + 120
bg.alpha_composite(small_slash.resize((16, 24), Image.NEAREST), (TOT_SLASH_X, Y_TOTAL + 12))
bg.alpha_composite(digit[7], (TOT_SLASH_X + 20, Y_TOTAL + 9))
bg.alpha_composite(digit[4], (TOT_SLASH_X + 40, Y_TOTAL + 9))

ring = Image.new('RGBA', (26, 46))
rounded(ImageDraw.Draw(ring), 0, 0, 26, 46, EDGE)
ImageDraw.Draw(ring).rectangle((1, 1, 24, 44), fill=(0, 0, 0, 0))       # just the gold edge

# ---------------------------------------------------------------------------------------------
# Values (addresses from the decomp's symbol list)
# ---------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------
# Intro screens: the bottom screen follows the boot sequence (white behind the N64 and HAL logos,
# the title screen's green checker behind the title). Bank 0 image 0x19 is the title background.
# These layers are bigger than the canvas so they also cover the letterbox around it.
# ---------------------------------------------------------------------------------------------
title_bg = sprite(0, 0x19)                                   # 300x220, checker + logo
tile = title_bg.crop((6, 118, 38, 150))                      # one clean 32x32 checker period
IX, IY, IW, IH = -40, -40, GW + 80, GH + 80
intro_title = Image.new('RGBA', (IW, IH))
for ty in range(0, IH, 32):
    for tx in range(0, IW, 32): intro_title.paste(tile, (tx, ty))
intro_white = Image.new('RGBA', (IW, IH), (255, 255, 255, 255))

def cork_board(src, IW, IH, rect, BX=10, BT=8, BB=6, seed=64):
    """Cork texture everywhere, with the board's embossed frame around rect=(x,y,w,h).
    Built from bank 3 image 0x02 (the 300x220 'Select File' board): the cork is re-assembled
    from random 6x6 blocks of clean cork (no notes, sign or shadows), and the frame bands come
    from the straight parts of the original border."""
    rnd = random.Random(seed)
    areas = [(14, 20, 40, 46), (258, 20, 284, 46), (102, 70, 108, 190), (192, 70, 198, 190), (282, 60, 286, 190)]
    blocks = []
    for (l, t, r, b) in areas:
        for y in range(t, b - 5, 3):
            for x in range(l, r - 5, 3):
                blocks.append(src.crop((x, y, x + 6, y + 6)))
    T = Image.new('RGBA', (IW, IH))
    for y in range(0, IH, 6):
        for x in range(0, IW, 6):
            blk = rnd.choice(blocks)
            if rnd.random() < .5: blk = ImageOps.mirror(blk)
            if rnd.random() < .5: blk = ImageOps.flip(blk)
            T.paste(blk, (x, y))
    x0, y0, w, h = rect
    SW, SH = src.size
    top = src.crop((20, 0, 280, BT)); bottom = src.crop((20, SH - BB, 280, SH))
    left = src.crop((0, BT, BX, SH - BB)); right = src.crop((SW - BX, BT, SW, SH - BB))
    for x in range(x0 + BX, x0 + w - BX, top.width):
        cw = min(top.width, x0 + w - BX - x)
        T.paste(top.crop((0, 0, cw, BT)), (x, y0)); T.paste(bottom.crop((0, 0, cw, BB)), (x, y0 + h - BB))
    for y in range(y0 + BT, y0 + h - BB, left.height):
        ch = min(left.height, y0 + h - BB - y)
        T.paste(left.crop((0, 0, BX, ch)), (x0, y)); T.paste(right.crop((0, 0, BX, ch)), (x0 + w - BX, y))
    T.paste(src.crop((0, 0, BX, BT)), (x0, y0)); T.paste(src.crop((SW - BX, 0, SW, BT)), (x0 + w - BX, y0))
    T.paste(src.crop((0, SH - BB, BX, SH)), (x0, y0 + h - BB)); T.paste(src.crop((SW - BX, SH - BB, SW, SH)), (x0 + w - BX, y0 + h - BB))
    return T

# File select (game state 10): the 'Select File' cork board (bank 3 image 0x02) without its sign
# and notes, with the board's frame around the visible canvas
intro_files = cork_board(sprite(3, 0x02), IW, IH, (-IX, -IY, GW, GH))

# Fades: the game draws a full-screen rectangle (util.c) whose colour is at 0x800D6B28 and whose
# opacity (0-255) is at 0x800D6B2E while its object (0x800D6B24) exists. The bottom screen draws
# the same colour at the same opacity, in FADE_STEPS steps.
FADE_STEPS = 16
fade_img = {}
for c, rgb in (("k", (0, 0, 0)), ("w", (255, 255, 255))):
    for n in range(1, FADE_STEPS + 1):
        fade_img["images/fade_%s%d.png" % (c, n)] = Image.new('RGBA', (IW, IH), rgb + (round(255 * n / FADE_STEPS),))

values = {
    "lives": {"type": "u32", "addr": "0x800D6E88", "add": -1},          # what the HUD shows: its lives copy - 1
    "hp": {"type": "f32", "addr": "0x800D6E50"},                        # gKirbyHp (0..6)
    "stars": {"type": "u32", "addr": "0x800D6E60"},                     # gKirbyStars (30 = 1UP)
    "ability": {"type": "u32", "addr": "0x800D6E90"},                   # ability shown on the HUD
    "ability_l": {"type": "lookup", "value": "ability", "default": 0, "table": {str(k): v for k, v in AB_L.items()}},
    "ability_r": {"type": "lookup", "value": "ability", "default": 0, "table": {str(k): v for k, v in AB_R.items()}},
    "world": {"type": "u32", "addr": "0x800BE500"},                     # gGameState: 0 Pop Star .. 5 Ripple Star, 6 Dark Star
    "stage": {"type": "u32", "addr": "0x800BE504"},                     # gGameState: 0-based stage in the world
    "is_dark": {"type": "lookup", "value": "world", "default": 0, "table": {"6": 1}},
    "has4": {"type": "lookup", "value": "world", "default": 1, "table": {"0": 0, "5": 0, "6": 0}},
    "world_no": {"type": "u32", "addr": "0x800BE500", "add": 1},
    # Shards: one byte per stage at 0x800D6BC8 + world*4 + stage, bits 0-2 = the 3 shards
    "stage_shards": {"type": "flags", "addr": "0x800D6BC8",
                     "bits": [(w * 4 + s) << 3 | b for w in range(6) for s in range(4 if w not in (0, 5) else 3) for b in range(3)]},
    "boss_shards": {"type": "flags", "addr": "0x800D6BC0", "bits": [w << 3 for w in range(6)]},
    "shards": {"type": "sum", "terms": ["stage_shards", "boss_shards", {"value": "intro_shards", "times": 1}]},
    "intro_shards": {"type": "const", "value": 2},
    # gGameState: 1 = N64/HAL logos, 3/5/7/9 = title screen (between attract demos)
    "scene": {"type": "u32", "addr": "0x800BE4F0"},
    "is_logo": {"type": "lookup", "value": "scene", "default": 0, "table": {"1": 1}},
    "is_title": {"type": "lookup", "value": "scene", "default": 0, "table": {"3": 1, "5": 1, "7": 1, "9": 1}},
    "is_files": {"type": "lookup", "value": "scene", "default": 0, "table": {"10": 1}},
    # 0 = power-on, 2 = between logos and title, 11 = world select (no panel yet): black
    "is_blank": {"type": "lookup", "value": "scene", "default": 0, "table": {"0": 1, "2": 1}},
    "is_play": {"type": "lookup", "value": "scene", "default": 1,
                "table": {str(s): 0 for s in (0, 1, 2, 3, 5, 7, 9, 10, 11, 12, *range(22, 35))}},
    "fade_obj": {"type": "u32", "addr": "0x800D6B24"},
    "fade_on": {"type": "lookup", "value": "fade_obj", "default": 1, "table": {"0": 0}},
    "fade_alpha": {"type": "s16", "addr": "0x800D6B2E"},
    "fade_lvl": {"type": "lookup", "value": "fade_alpha", "default": 0,
                 "table": {str(a): round(a * FADE_STEPS / 255) for a in range(256)}},
    "fade_r": {"type": "u8", "addr": "0x800D6B28"},
    "fade_is_black": {"type": "lookup", "value": "fade_r", "default": 0, "table": {"0": 1}},
    "fade_is_white": {"type": "lookup", "value": "fade_r", "default": 0, "table": {"255": 1}},
    "zero": {"type": "const", "value": 0},
    "fade_black": {"type": "select", "index": "fade_on", "options": ["zero", "fade_is_black"]},
    "fade_white": {"type": "select", "index": "fade_on", "options": ["zero", "fade_is_white"]},
}
for k in range(4):
    values["cur%d" % k] = {"type": "lookup", "value": "stage", "default": 0, "table": {str(k): 1}}
    for j in range(3):
        values["s%d_%d" % (k, j)] = {"type": "flags", "mode": "any", "bits": [j],
                                     "chain": ["0x800D6BC8", {"value": "world", "times": 4}, str(k)]}

# ---------------------------------------------------------------------------------------------
# Layers (canvas pixels)
# ---------------------------------------------------------------------------------------------
L = [{"image": "images/bg.png", "x": 0, "y": 0, "show": "is_play"}]
L.append({"number": "lives", "glyphs": "digits/{c}.png", "pad": 2, "advance": 20, "x": X0 + 22, "y": Y_HUD + 8})
L.append({"repeat": "images/cell.png", "count": "hp", "max": 6, "dx": 20, "x": X0 + 80, "y": Y_HUD + 2})
L.append({"repeat": "images/star.png", "count": "stars", "max": 30, "dx": 4, "x": X0 + 80, "y": Y_HUD + 32})
L.append({"pick": "world", "images": {str(w): "images/world_%d.png" % w for w in range(7)}, "x": X0 + 8, "y": Y_WORLD + 3})
L.append({"pick": "world_no", "images": {str(n): "images/level_%d.png" % n for n in range(1, 8)}, "x": X0 + 178, "y": Y_WORLD + 6})
L.append({"pick": "ability_l", "images": {str(i): "icons/ab_%d.png" % i for i in range(1, 10)}, "anchor": "center", "x": X0 + 25, "y": Y_ABIL + 21})
L.append({"pick": "ability_r", "images": {str(i): "icons/ab_%d.png" % i for i in range(1, 10)}, "anchor": "center", "x": X0 + 60, "y": Y_ABIL + 21})
L.append({"image": "images/stage4.png", "x": X0 + 100 + 3 * 27, "y": Y_ABIL + 1, "show": "has4"})
for k in range(4):
    bx = X0 + 100 + k * 27
    L.append({"image": "images/ring.png", "x": bx - 1, "y": Y_ABIL, "show": "cur%d" % k, "hide": "is_dark"})
    for j, (sx, sy) in enumerate(SHARD_POS):
        L.append({"image": "icons/shard.png", "x": bx + sx, "y": Y_ABIL + 1 + sy, "show": "s%d_%d" % (k, j), "hide": "is_dark"})
L.append({"number": "shards", "glyphs": "digits/{c}.png", "advance": 20, "align": "right", "x": TOT_SLASH_X - 2, "y": Y_TOTAL + 9})
L.append({"image": "images/black.png", "x": IX, "y": IY, "show": "is_blank"})
L.append({"image": "images/intro_white.png", "x": IX, "y": IY, "show": "is_logo"})
L.append({"image": "images/intro_title.png", "x": IX, "y": IY, "show": "is_title"})
L.append({"image": "images/intro_files.png", "x": IX, "y": IY, "show": "is_files"})
for col, val in (("k", "fade_black"), ("w", "fade_white")):
    L.append({"pick": "fade_lvl", "show": val, "x": IX, "y": IY,
              "images": {str(n): "images/fade_%s%d.png" % (col, n) for n in range(1, FADE_STEPS + 1)}})

# ---------------------------------------------------------------------------------------------
# Menus. Everything is cut from the game's own menu art (bank 3).
#   File select (state 10): a big note in the selected save's colour (the 3 notes of the
#   'Select File' board), with the save's title, its % and every crystal it has, per world.
#   Stage select (state 12): world + level, the coloured 'N Stage' plate (or the boss name) and
#   the selected stage's crystals, big.
# Saves live at 0x800ECA08 + 0x58*n (gSaveBuffer1.files[n]); the cursor is saveCurrentFileNum.
# In a save: +0x00 world (0x99999999 = empty), +0x10 %, +0x34 boss flags (1 byte per world),
# +0x3C crystals (1 byte per stage, 4 per world, bits 0-2).
# ---------------------------------------------------------------------------------------------
board = sprite(3, 0x02)
lvl_parts = sprite(3, 0x04)
SH_BIG = lvl_parts.crop((16, 28, 43, 57))                        # the game's crystal icon (27x29)
PCT = lvl_parts.crop((43, 30, 57, 46))                           # '%'
def crystal_tint(im):
    """The menu crystal is pale grey; collected ones are tinted to the in-game crystal blue
    (dark outline -> blue -> pale cyan highlights), keeping the game's own shape and shading."""
    out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            if not a: continue
            l = (r + g + b) / 765
            if l < .45: c = (30, 50, 140)
            elif l < .7: c = (70, 140, 235)
            elif l < .82: c = (130, 200, 255)
            else: c = (210, 245, 255)
            out.putpixel((x, y), c + (a,))
    return out
def crystal_hole(im, a=0.55):
    """A missing crystal: the same shape as a brown silhouette (like an empty slot)."""
    out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            if im.getpixel((x, y))[3]: out.putpixel((x, y), (110, 78, 30, int(255 * a)))
    return out
SH_BIG_ON, SH_BIG_DIM = crystal_tint(SH_BIG), crystal_hole(SH_BIG, .45)
SH_SMALL, SH_SMALL_DIM = SHARD_ON, crystal_hole(SHARD_ON, .5)    # 7x10 pixel crystal for the rows
def tint(im, rgb):
    out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            if a:
                l = (r + g + b) / 765
                out.putpixel((x, y), tuple(int(c * (0.35 + 0.65 * (1 - l))) for c in rgb) + (a,))
    return out
WDIG = {d: tint(sprite(3, 0x05 + d), (96, 58, 14)) for d in range(10)}   # menu digits, in the notes' brown
FILE_T = {k: sprite(3, 0x1D + k) for k in range(3)}              # brown 'File1/2/3'
STAGE_PLATE = {k: sprite(3, 0x87 + k) for k in range(4)}         # coloured '1-4 Stage'
BOSS_NAME = {0: 0x108, 1: 0x10A, 2: 0x10B, 3: 0x10C, 4: 0x10D, 5: 0x10F, 6: 0x110}
BOSS_NAME = {w: sprite(3, i) for w, i in BOSS_NAME.items()}
BOSS_STAGE = {0: 3, 1: 4, 2: 4, 3: 4, 4: 4, 5: 3}                # stage index of each world's boss
STAGES = {w: (3 if w in (0, 5) else 4) for w in range(6)}

NOTE_X = [20, 110, 200]
def build_note(k, W, H, C=14):
    """A bigger copy of note k of the Select File board: corners (with the pins), edges and paper."""
    x0 = NOTE_X[k]
    n = board.crop((x0, 49, x0 + 80, 207)); nw, nh = n.size
    T = Image.new('RGBA', (W, H))
    paper = n.crop((C, C + 6, C + 40, C + 66))
    for y in range(C, H - C, paper.height):
        for x in range(C, W - C, paper.width):
            T.paste(paper.crop((0, 0, min(paper.width, W - C - x), min(paper.height, H - C - y))), (x, y))
    top, bot = n.crop((C + 6, 0, C + 16, C)), n.crop((C + 6, nh - C, C + 16, nh))
    for x in range(C, W - C, 10):
        cw = min(10, W - C - x)
        T.paste(top.crop((0, 0, cw, C)), (x, 0)); T.paste(bot.crop((0, 0, cw, C)), (x, H - C))
    lef, rig = n.crop((0, C + 6, C, C + 26)), n.crop((nw - C, C + 6, nw, C + 26))
    for y in range(C, H - C, 20):
        ch = min(20, H - C - y)
        T.paste(lef.crop((0, 0, C, ch)), (0, y)); T.paste(rig.crop((0, 0, C, ch)), (W - C, y))
    T.paste(n.crop((0, 0, C, C)), (0, 0)); T.paste(n.crop((nw - C, 0, nw, C)), (W - C, 0))
    T.paste(n.crop((0, nh - C, C, nh)), (0, H - C)); T.paste(n.crop((nw - C, nh - C, nw, nh)), (W - C, H - C))
    if k == 2:                                                   # the green note's middle pin
        T.paste(n.crop((36, 0, 48, C)), (W // 2 - 6, 0))
    return T

NOTE_POS, NOTE_W, NOTE_H = (6, 5), 236, 189
ROW_Y0, ROW_H, GRP_X, GRP_W = 46, 22, 134, 22
def row_y(w): return ROW_Y0 + w * ROW_H
def note_template(k, filled):
    T = build_note(k, NOTE_W, NOTE_H)
    T.alpha_composite(FILE_T[k], (14, 12))
    if filled:
        T.alpha_composite(SH_BIG_ON, (112, 9))
        T.alpha_composite(tint(PCT, (96, 58, 14)), (NOTE_W - 30, 16))
        for w in range(6):
            y = row_y(w)
            T.alpha_composite(SH_SMALL_DIM, (8, y + 5))              # boss crystal
            wn = world_name[w].crop(world_name[w].getbbox())
            T.alpha_composite(wn, (19, y + 1))
            for s in range(STAGES[w]):
                for j in range(3):
                    T.alpha_composite(SH_SMALL_DIM, (GRP_X + s * GRP_W + j * 6, y + 5))
    return T

# Stage select background: the HUD's wood stripes, the world strip and a white box for crystals
# Stage select: a page of the game's sketchbook (the 3D notebook of the stage select), rebuilt
# flat from its own textures: grass (bank 3 tex 0x207), cardboard (0x21A), paper (0x20A), page
# stack edge (0x217). The crystals sit on the green paper strip the game uses, as purple outlines
# for missing ones (like the game) and the blue crystal for collected ones.
def raw_ci4(index):
    """A raw 4-bit texture of bank 3 followed by its 16-colour palette (stage select textures)."""
    h = struct.unpack('>8I', rom[v2r(BANKS[3]):v2r(BANKS[3]) + 32])
    tb = v2r(h[2])
    a, pa = h[3] + u32(tb + 4 * index), h[3] + u32(tb + 4 * (index + 1))
    sz = pa - a
    pal = [rgba16(struct.unpack('>H', rom[pa + 2 * i:pa + 2 * i + 2])[0]) for i in range(16)]
    w = {0x80: 16, 0x100: 32, 0x200: 32, 0x400: 64, 0x800: 64}[sz]
    px = []
    for b in rom[a:a + sz]: px += [pal[b >> 4], pal[b & 15]]
    im = Image.new('RGBA', (w, sz * 2 // w)); im.putdata(px); return im
TEX_GRASS, TEX_PAPER, TEX_EDGE, TEX_CARD = raw_ci4(0x207), raw_ci4(0x20A), raw_ci4(0x217), raw_ci4(0x21A)
def tile(T, tex, box):
    x0, y0, x1, y1 = box
    for y in range(y0, y1, tex.height):
        for x in range(x0, x1, tex.width):
            T.paste(tex.crop((0, 0, min(tex.width, x1 - x), min(tex.height, y1 - y))), (x, y))
def outline_of(im, rgb, th=1):
    a = im.getchannel('A'); out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            if not a.getpixel((x, y)): continue
            edge = any(not (0 <= x + dx < im.width and 0 <= y + dy < im.height and a.getpixel((x + dx, y + dy)))
                       for dx in range(-th, th + 1) for dy in range(-th, th + 1))
            if edge: out.putpixel((x, y), rgb + (255,))
    return out
SH_BIG_HOLE = outline_of(SH_BIG, (96, 70, 210), 2)
def chalk_grass(w, h, seed=21):
    """The green behind the notebook, redrawn as chalk: diagonal strokes in the greens of the game's
    grass texture (0x207), with gaps where a lighter ground shows through."""
    rnd = random.Random(seed)
    greens = sorted({TEX_GRASS.getpixel((x, y))[:3] for y in range(0, 64, 3) for x in range(0, 64, 3)},
                    key=lambda c: sum(c))
    greens = greens[len(greens) // 6: -max(1, len(greens) // 6)] or greens
    out = Image.new('RGBA', (w, h), (196, 232, 150, 255))                  # light ground in the gaps
    for _ in range(w * h // 4):
        x, y = rnd.randrange(-6, w), rnd.randrange(0, h + 6)
        col = rnd.choice(greens); n = rnd.randint(3, 8)
        for k in range(n):
            px, py = x + k, y - k
            if 0 <= px < w and 0 <= py < h and rnd.random() > .15:
                out.putpixel((px, py), col + (255,))
    return out
def crayon_strip(w, h, seed, shade=1.0):
    """A green strip drawn in chalk: diagonal strokes of slightly different greens, gaps where the
    paper shows through, ragged edges and a heavier rim, like the game's hand-drawn strip."""
    rnd = random.Random(seed)
    base = [(150, 214, 158), (136, 204, 146), (166, 224, 172), (122, 192, 134)]
    base = [tuple(int(c * shade) for c in col) for col in base]
    out = Image.new('RGBA', (w, h))
    left = [rnd.choice((0, 1, 1, 2, 3)) for _ in range(h)]; right = [rnd.choice((0, 1, 1, 2, 3)) for _ in range(h)]
    top = [rnd.choice((0, 1, 1, 2, 3)) for _ in range(w)]; bot = [rnd.choice((0, 1, 1, 2, 3)) for _ in range(w)]
    inside = lambda x, y: not (x < left[y] or x >= w - right[y] or y < top[x] or y >= h - bot[x])
    # strokes: short diagonal lines going up-right, overlapping, each in one green
    for _ in range(w * h // 5):
        x, y = rnd.randrange(-4, w), rnd.randrange(0, h + 4)
        col = rnd.choice(base); n = rnd.randint(3, 7)
        for k in range(n):
            px, py = x + k, y - k
            if 0 <= px < w and 0 <= py < h and inside(px, py) and rnd.random() > .12:
                out.putpixel((px, py), col + (255,))
    # rim: heavier chalk along the ragged edge
    for y in range(h):
        for x in range(w):
            if not inside(x, y): continue
            edge = x <= left[y] + 1 or x >= w - right[y] - 2 or y <= top[x] + 1 or y >= h - bot[x] - 2
            if edge and rnd.random() > .2:
                r, g, b = rnd.choice(base); out.putpixel((x, y), (int(r * .72), int(g * .78), int(b * .72), 255))
    return out              # purple outline, like the game's strip
STRIP = (150, 214, 158, 255); STRIP_DARK = (104, 170, 112, 255)
def stage_select_bg(boss):
    T = Image.new('RGBA', (IW, IH))
    T.paste(chalk_grass(IW, IH), (0, 0))                                       # grass, drawn in chalk
    ox, oy = -IX, -IY
    tile(T, TEX_CARD, (ox + 12, oy + 10, ox + 240, oy + 196))                  # cardboard back
    for k, (dx, dy) in enumerate(((5, 6), (2, 3))):                            # page stack
        tile(T, TEX_EDGE, (ox + 8 + dx, oy + 14 + dy, ox + 234 + dx, oy + 192 + dy))
    page = Image.new('RGBA', (226, 178)); tile(page, TEX_PAPER, (0, 0, 226, 178))
    for x in range(0, 226, 12):                                                # torn top edge
        for y in range(0, 4 if (x // 12) % 2 else 2):
            for xx in range(x, min(x + 12, 226)): page.putpixel((xx, y), (0, 0, 0, 0))
    T.alpha_composite(page, (ox + 8, oy + 14))
    d = ImageDraw.Draw(T)
    for x in range(ox + 22, ox + 228, 18):                                     # spiral: hole + red wire
        d.ellipse((x, oy + 19, x + 5, oy + 22), fill=(150, 150, 150, 255))
        d.arc((x - 1, oy + 9, x + 6, oy + 22), 180, 360, fill=(220, 40, 30, 255), width=2)
    T.alpha_composite(level_word, (ox + X0 + 132, oy + 32))
    if boss:                                                                   # strip behind the boss name
        rounded(d, ox + 80, oy + 70, 88, 21, (60, 120, 70, 255))
    rounded(d, ox + 44, oy + 114, 160, 50, STRIP_DARK)                          # green strip
    rounded(d, ox + 45, oy + 115, 158, 48, STRIP)
    for x in ([SS_SH_X[1]] if boss else SS_SH_X):
        T.alpha_composite(SH_BIG_HOLE, (ox + x, oy + 125))
    return T
SS_SH_X = [70, 110, 150]

files_extra = {
    "icons/shard_small.png": SH_SMALL, "icons/shard_big.png": SH_BIG_ON,
    "images/ss_bg.png": stage_select_bg(False), "images/ss_bg_boss.png": stage_select_bg(True),
}
for k in range(3):
    files_extra["images/note_%d.png" % k] = note_template(k, True)
    files_extra["images/note_%d_empty.png" % k] = note_template(k, False)
for d_, im in WDIG.items(): files_extra["wdigits/%d.png" % d_] = im
for k, im in STAGE_PLATE.items(): files_extra["images/stage_plate_%d.png" % k] = im
for w, im in BOSS_NAME.items(): files_extra["images/boss_%d.png" % w] = im

# --- values ---
EMPTY = str(0x99999999)
def gate(name, src, on="is_files"):
    values[name] = {"type": "select", "index": on, "options": ["zero", src]}
values.update({
    "cursor": {"type": "u32", "addr": "0x800D6B88"},
    "f_world": {"type": "u32", "chain": ["0x800ECA08", {"value": "cursor", "times": 0x58}]},
    "f_empty": {"type": "lookup", "value": "f_world", "default": 0, "table": {EMPTY: 1}},
    "f_full": {"type": "lookup", "value": "f_world", "default": 1, "table": {EMPTY: 0}},
    "f_pct": {"type": "u8", "chain": ["0x800ECA08", {"value": "cursor", "times": 0x58}, "0x10"]},
    "is_ssel": {"type": "lookup", "value": "scene", "default": 0, "table": {"12": 1}},
    "ss_world": {"type": "u32", "addr": "0x800D6B98"},
    "ss_stage": {"type": "u32", "addr": "0x800D6B9C"},
    "ss_world_no": {"type": "u32", "addr": "0x800D6B98", "add": 1},
    "ss_ws": {"type": "sum", "terms": [{"value": "ss_world", "times": 10}, "ss_stage"]},
    "ss_boss": {"type": "lookup", "value": "ss_ws", "default": 0,
                "table": {str(w * 10 + s): 1 for w, s in BOSS_STAGE.items()}},
    "ss_notboss": {"type": "lookup", "value": "ss_ws", "default": 1,
                   "table": {str(w * 10 + s): 0 for w, s in BOSS_STAGE.items()}},
    "ss_bossflag": {"type": "flags", "mode": "any", "bits": [0], "chain": ["0x800D6BC0", {"value": "ss_world", "times": 1}]},
})
gate("fs_full", "f_full"); gate("fs_empty", "f_empty")
for w in range(6):
    values["f_b%d" % w] = {"type": "flags", "mode": "any", "bits": [0],
                           "chain": ["0x800ECA08", {"value": "cursor", "times": 0x58}, hex(0x34 + w)]}
    gate("fs_b%d" % w, "f_b%d" % w)
    for s in range(STAGES[w]):
        for j in range(3):
            values["f_%d_%d_%d" % (w, s, j)] = {"type": "flags", "mode": "any", "bits": [j],
                "chain": ["0x800ECA08", {"value": "cursor", "times": 0x58}, hex(0x3C + w * 4 + s)]}
            gate("fs_%d_%d_%d" % (w, s, j), "f_%d_%d_%d" % (w, s, j))
gate("ssg_normal", "ss_notboss", "is_ssel"); gate("ssg_boss", "ss_boss", "is_ssel")
values["ss_boss_got"] = {"type": "select", "index": "ss_boss", "options": ["zero", "ss_bossflag"]}
gate("ssg_boss_got", "ss_boss_got", "is_ssel")
for j in range(3):
    values["ss_sh%d" % j] = {"type": "flags", "mode": "any", "bits": [j],
                             "chain": ["0x800D6BC8", {"value": "ss_world", "times": 4}, {"value": "ss_stage", "times": 1}]}
    values["ss_shn%d" % j] = {"type": "select", "index": "ss_notboss", "options": ["zero", "ss_sh%d" % j]}
    gate("ssg_sh%d" % j, "ss_shn%d" % j, "is_ssel")

# --- layers (inserted right after the cork board, before the fades) ---
ML = []
nx, ny = NOTE_POS
ML.append({"pick": "cursor", "show": "fs_full", "x": nx, "y": ny, "images": {str(k): "images/note_%d.png" % k for k in range(3)}})
ML.append({"pick": "cursor", "show": "fs_empty", "x": nx, "y": ny, "images": {str(k): "images/note_%d_empty.png" % k for k in range(3)}})
ML.append({"number": "f_pct", "show": "fs_full", "glyphs": "wdigits/{c}.png", "advance": 16, "align": "right",
           "x": nx + NOTE_W - 32, "y": ny + 11})
for w in range(6):
    y = ny + row_y(w)
    ML.append({"image": "icons/shard_small.png", "x": nx + 8, "y": y + 5, "show": "fs_b%d" % w, "hide": "f_empty"})
    for s in range(STAGES[w]):
        for j in range(3):
            ML.append({"image": "icons/shard_small.png", "x": nx + GRP_X + s * GRP_W + j * 6, "y": y + 5,
                       "show": "fs_%d_%d_%d" % (w, s, j), "hide": "f_empty"})
# stage select
ML.append({"image": "images/ss_bg.png", "x": IX, "y": IY, "show": "ssg_normal"})
ML.append({"image": "images/ss_bg_boss.png", "x": IX, "y": IY, "show": "ssg_boss"})
ML.append({"pick": "ss_world", "show": "is_ssel", "x": X0 + 8, "y": 29, "images": {str(w): "images/world_%d.png" % w for w in range(7)}})
ML.append({"pick": "ss_world_no", "show": "is_ssel", "x": X0 + 178, "y": 32, "images": {str(n): "images/level_%d.png" % n for n in range(1, 8)}})
ML.append({"pick": "ss_stage", "show": "ssg_normal", "anchor": "center", "x": 124, "y": 80,
           "images": {str(k): "images/stage_plate_%d.png" % k for k in range(4)}})
ML.append({"pick": "ss_world", "show": "ssg_boss", "anchor": "center", "x": 124, "y": 80,
           "images": {str(w): "images/boss_%d.png" % w for w in range(7)}})
for j in range(3):
    ML.append({"image": "icons/shard_big.png", "x": SS_SH_X[j], "y": 125, "show": "ssg_sh%d" % j})
ML.append({"image": "icons/shard_big.png", "x": SS_SH_X[1], "y": 125, "show": "ssg_boss_got"})

# ---------------------------------------------------------------------------------------------
# World select (state 11): the blue space of that screen, from its own textures (bank 3 i4
# textures the game tints: star field 0xA9B268, galaxy swirl 0xA9AC68), with 'Level N', the
# world name, and the selected world's crystals per stage + its boss, from the loaded save.
# ---------------------------------------------------------------------------------------------
def i4_tex(off, w, h):
    px = []
    for b in rom[off:off + w * h // 2]: px += [b >> 4, b & 15]
    im = Image.new('L', (w, h)); im.putdata([v * 17 for v in px[:w * h]]); return im
STARFIELD, SWIRL = i4_tex(0xA9B268, 64, 64), i4_tex(0xA9AC68, 32, 32)
def space_bg():
    T = Image.new('RGBA', (IW, IH)); d = ImageDraw.Draw(T)
    for y in range(IH):                                               # deep blue, lighter below
        k = y / IH; d.line((0, y, IW, y), fill=(int(12 + 18 * k), int(24 + 40 * k), int(120 + 60 * k), 255))
    rnd = random.Random(7)
    for ty in range(0, IH, 64):                                       # the game's star field, tinted
        for tx in range(0, IW, 64):
            for y in range(64):
                for x in range(64):
                    v = STARFIELD.getpixel((x, y))
                    if v > 40 and 0 <= tx + x < IW and 0 <= ty + y < IH:
                        c = (250, 214, 90) if (x * 7 + y * 13 + tx) % 3 == 0 else (255, 255, 240)
                        T.putpixel((tx + x, ty + y), c + (255,))
    sw = SWIRL.resize((96, 96), Image.BILINEAR)                       # galaxy swirl, lilac
    g = Image.new('RGBA', sw.size, (176, 168, 240, 0)); g.putalpha(sw.point(lambda v: int(v * .75)))
    T.alpha_composite(g, (-IX + 168, -IY - 20))
    return T
SH_2X, SH_2X_DIM = SHARD_ON.resize((14, 20), Image.NEAREST), crystal_hole(SHARD_ON.resize((14, 20), Image.NEAREST), .6)
WS_CX = [49, 99, 149, 199]; WS_Y = 104
def ws_dims(n):
    T = Image.new('RGBA', (GW, GH))
    for s in range(n):
        T.alpha_composite(small[s + 1], (WS_CX[s] - 5, WS_Y - 18))
        for j in range(3): T.alpha_composite(SH_2X_DIM, (WS_CX[s] - 21 + j * 14, WS_Y))
    d = ImageDraw.Draw(T)
    rounded(d, 70, 150, 80, 20, (20, 30, 90, 255))
    T.alpha_composite(SH_2X_DIM, (160, 150))
    return T
files_extra.update({"images/ws_bg.png": space_bg(), "images/ws_dim3.png": ws_dims(3),
                    "images/ws_dim4.png": ws_dims(4), "icons/shard_2x.png": SH_2X})
values.update({
    "is_wsel": {"type": "lookup", "value": "scene", "default": 0, "table": {"11": 1}},
    "ws_n3": {"type": "lookup", "value": "ss_world", "default": 0, "table": {"0": 1, "5": 1}},
    "ws_n4": {"type": "lookup", "value": "ss_world", "default": 0, "table": {"1": 1, "2": 1, "3": 1, "4": 1}},
    "ws_has4": {"type": "lookup", "value": "ss_world", "default": 1, "table": {"0": 0, "5": 0, "6": 0}},
    "ws_real": {"type": "lookup", "value": "ss_world", "default": 1, "table": {"6": 0}},
})
gate("wsg_n3", "ws_n3", "is_wsel"); gate("wsg_n4", "ws_n4", "is_wsel"); gate("wsg_boss", "ss_bossflag", "is_wsel")
for s in range(4):
    for j in range(3):
        values["ws_%d_%d" % (s, j)] = {"type": "flags", "mode": "any", "bits": [j],
                                       "chain": ["0x800D6BC8", {"value": "ss_world", "times": 4}, str(s)]}
        values["wsk_%d_%d" % (s, j)] = {"type": "select", "index": "ws_has4" if s == 3 else "ws_real",
                                        "options": ["zero", "ws_%d_%d" % (s, j)]}
        gate("wsg_%d_%d" % (s, j), "wsk_%d_%d" % (s, j), "is_wsel")
# only the background: the top screen already shows the level and world
WL = [{"image": "images/ws_bg.png", "x": IX, "y": IY, "show": "is_wsel"}]
ML += WL

# ---------------------------------------------------------------------------------------------
# Main-menu screens (ovl5) and the three mini-games.
#   22-28: Theater, Options and the other main-menu screens: the menu paper (bank 3 #0x45, the
#          left half of the paper, mirrored).
#   23:    Mini-Games menu: the selected game's picture and name, its Best Score from the save and
#          the difficulties unlocked. The cursor is D_8018EDE1 (0 Hop, 1 Bumper, 2 Checker).
#   29/30/31: 100-Yard Hop / Checkerboard Chase / Bumper Crop Bump, on a notebook page:
#          the game, its Best Score and, live, each player's time (Hop: frames at D_8018E468,
#          30 per second) or score (Bumper: bytes at D_8018E1E0).
# Records live in the save at +0x18 (Hop, frames), +0x1A (Bumper, points), +0x1C (Checker,
# frames); unlocked difficulty at D_800D6BB9 (Hop), D_800D6BBA (Bumper), D_800D6BBB (Checker).
# ---------------------------------------------------------------------------------------------
def tint_light(im, rgb):
    out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            if a:
                l = (r + g + b) / 765
                out.putpixel((x, y), tuple(int(rgb[k] * (0.45 + 0.55 * l)) for k in range(3)) + (a,))
    return out
def x2(im): return im.resize((im.width * 2, im.height * 2), Image.NEAREST)

half = sprite(3, 0x45)                                               # 150x220
def paper_bg():
    Lh = Image.new('RGBA', (124, GH))
    Lh.paste(half.crop((0, 0, 124, 100)), (0, 0)); Lh.paste(half.crop((0, 220 - 99, 124, 220)), (0, 100))
    T = Image.new('RGBA', (IW, IH), half.getpixel((2, 110))[:3] + (255,))
    T.paste(Lh, (-IX, -IY)); T.paste(ImageOps.mirror(Lh), (-IX + 124, -IY))
    return T
def notebook_bg():
    """The stage select's sketchbook page, without its title and crystal strip."""
    T = Image.new('RGBA', (IW, IH))
    T.paste(chalk_grass(IW, IH, 33), (0, 0))
    ox, oy = -IX, -IY
    tile(T, TEX_CARD, (ox + 12, oy + 10, ox + 240, oy + 196))
    for dx, dy in ((5, 6), (2, 3)):
        tile(T, TEX_EDGE, (ox + 8 + dx, oy + 14 + dy, ox + 234 + dx, oy + 192 + dy))
    page = Image.new('RGBA', (226, 178)); tile(page, TEX_PAPER, (0, 0, 226, 178))
    for x in range(0, 226, 12):
        for y in range(0, 4 if (x // 12) % 2 else 2):
            for xx in range(x, min(x + 12, 226)): page.putpixel((xx, y), (0, 0, 0, 0))
    T.alpha_composite(page, (ox + 8, oy + 14))
    d = ImageDraw.Draw(T)
    for x in range(ox + 22, ox + 228, 18):
        d.ellipse((x, oy + 19, x + 5, oy + 22), fill=(150, 150, 150, 255))
        d.arc((x - 1, oy + 9, x + 6, oy + 22), 180, 360, fill=(220, 40, 30, 255), width=2)
    return T

MG_THUMB = {g: sprite(3, 0x49 + g) for g in range(3)}               # 64x64 pictures
MG_NAME = {g: sprite(3, 0x4C + g) for g in range(3)}                 # 64x46 names
BEST = sprite(3, 0x2F0)                                              # 'Best Score'
DIFF = [sprite(3, 0x8B + k) for k in range(4)]                       # Easy .. Intense!
CROWN = sprite(3, 0x389)
PLATE = [sprite(3, 0x317 + p) for p in range(4)]                     # Bumper players' plates
PNAME = [sprite(3, 0x374 + p) for p in range(4)]                     # 1P..4P
CLOCK = sprite(3, 0x379)
BROWN, PCOL = (96, 58, 14), [(240, 110, 140), (240, 170, 60), (110, 200, 90), (90, 140, 235)]
MGD = {str(d): sprite(3, 0x341 + d) for d in range(10)}; MGD["colon"] = sprite(3, 0x340).crop((0, 2, 4, 12))   # same height as the digits
def glyph(im, rgb):
    """These digits are intensity images (grey = coverage): one colour, coverage as alpha."""
    out = Image.new('RGBA', im.size)
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = im.getpixel((x, y))
            out.putpixel((x, y), rgb + (min(a, r),))
    return out
for name, im in MGD.items():
    files_extra["mgd/%s.png" % name] = x2(glyph(im, BROWN))          # brown, 2x (records)
    files_extra["mgw/%s.png" % name] = x2(glyph(im, (255, 255, 255)))  # white, 2x (live)
def diff_strip(unl):
    """The four difficulties in two rows; unlocked ones in gold, the crown when all are."""
    T = Image.new('RGBA', (180, 40))
    for k in range(4):
        dd = DIFF[k].crop(DIFF[k].getbbox())
        T.alpha_composite(tint_light(dd, (220, 150, 40)) if k <= unl else dd,
                          ((0 if k % 2 == 0 else 86), (0 if k < 2 else 20)))
    if unl >= 3: T.alpha_composite(CROWN, (152, 8))
    return T
for u in range(4): files_extra["images/mg_diff_%d.png" % u] = diff_strip(u)
for g in range(3):
    files_extra["images/mg_thumb_%d.png" % g] = MG_THUMB[g]
    files_extra["images/mg_name_%d.png" % g] = MG_NAME[g]
files_extra["images/mg_best.png"] = BEST
files_extra["images/paper_bg.png"] = paper_bg()
files_extra["images/notebook_bg.png"] = notebook_bg()
hop_rows = Image.new('RGBA', (GW, GH)); d = ImageDraw.Draw(hop_rows)
HOP_Y = [96 + 22 * p for p in range(4)]
for p in range(4):
    rounded(d, 40, HOP_Y[p], 168, 19, PCOL[p] + (255,))
    hop_rows.alpha_composite(PNAME[p], (46, HOP_Y[p] + 4)); hop_rows.alpha_composite(CLOCK, (76, HOP_Y[p] + 2))
files_extra["images/mg_hop_rows.png"] = hop_rows
bump = Image.new('RGBA', (GW, GH))
BUMP_X = [26 + 50 * p for p in range(4)]
for p in range(4): bump.alpha_composite(x2(PLATE[p]), (BUMP_X[p], 104))
files_extra["images/mg_bump_plates.png"] = bump

def frames_txt(f):
    if f >= 0x464F: return "9:59:99"
    return "%d:%02d:%02d" % (f // 30 // 60, f // 30 % 60, f % 30 * 3)
REC_TABLE = {str(f): frames_txt(f) for f in range(9000)}             # up to 5 minutes
LIVE_TABLE = {str(f): frames_txt(f) for f in range(3600)}            # up to 2 minutes
SAVE = ["0x800ECA08", {"value": "cursor", "times": 0x58}]
values.update({
    "is_menu": {"type": "lookup", "value": "scene", "default": 0, "table": {str(s): 1 for s in range(22, 29)}},
    "is_mgmenu": {"type": "lookup", "value": "scene", "default": 0, "table": {"23": 1}},
    "is_mg": {"type": "lookup", "value": "scene", "default": 0, "table": {"29": 1, "30": 1, "31": 1}},
    "is_hop": {"type": "lookup", "value": "scene", "default": 0, "table": {"29": 1}},
    "is_bump": {"type": "lookup", "value": "scene", "default": 0, "table": {"31": 1}},
    "is_chk": {"type": "lookup", "value": "scene", "default": 0, "table": {"30": 1}},
    "mg_game": {"type": "lookup", "value": "scene", "default": 0, "table": {"29": 0, "31": 1, "30": 2}},
    "mg_sel": {"type": "u8", "addr": "0x8018EDE1"},
    "rec_hop_f": {"type": "u16", "chain": SAVE + ["0x18"]},
    "rec_bump": {"type": "u16", "chain": SAVE + ["0x1A"]},
    "rec_chk_f": {"type": "u16", "chain": SAVE + ["0x1C"]},
    "rec_hop": {"type": "lookup", "value": "rec_hop_f", "default": "", "table": REC_TABLE},
    "rec_chk": {"type": "lookup", "value": "rec_chk_f", "default": "", "table": REC_TABLE},
    "unl_hop": {"type": "u8", "addr": "0x800D6BB9"},
    "unl_bump": {"type": "u8", "addr": "0x800D6BBA"},
    "unl_chk": {"type": "u8", "addr": "0x800D6BBB"},
    "mgm_rec": {"type": "select", "index": "mg_sel", "options": ["rec_hop", "rec_bump", "rec_chk"]},
    "mgm_unl": {"type": "select", "index": "mg_sel", "options": ["unl_hop", "unl_bump", "unl_chk"]},
    "mg_rec": {"type": "select", "index": "mg_game", "options": ["rec_hop", "rec_bump", "rec_chk"]},
    "mg_unl": {"type": "select", "index": "mg_game", "options": ["unl_hop", "unl_bump", "unl_chk"]},
})
for p in range(4):
    values["hop_f%d" % p] = {"type": "u32", "addr": hex(0x8018E468 + 4 * p)}
    values["hop_t%d" % p] = {"type": "lookup", "value": "hop_f%d" % p, "default": "", "table": LIVE_TABLE}
    values["bump_s%d" % p] = {"type": "u8", "addr": hex(0x8018E1E0 + p)}

GL = [{"image": "images/paper_bg.png", "x": IX, "y": IY, "show": "is_menu"}]
# Mini-Games menu, everything inside the paper's light area (x 22-222, y 22-180)
GL.append({"pick": "mg_sel", "show": "is_mgmenu", "x": 32, "y": 26, "images": {str(g): "images/mg_thumb_%d.png" % g for g in range(3)}})
GL.append({"pick": "mg_sel", "show": "is_mgmenu", "x": 112, "y": 34, "images": {str(g): "images/mg_name_%d.png" % g for g in range(3)}})
GL.append({"image": "images/mg_best.png", "x": 32, "y": 96, "show": "is_mgmenu"})
GL.append({"number": "mgm_rec", "glyphs": "mgd/{c}.png", "x": 40, "y": 114, "show": "is_mgmenu"})
GL.append({"pick": "mgm_unl", "show": "is_mgmenu", "x": 36, "y": 138, "images": {str(u): "images/mg_diff_%d.png" % u for u in range(4)}})
# the mini-games themselves
GL.append({"image": "images/notebook_bg.png", "x": IX, "y": IY, "show": "is_mg"})
GL.append({"pick": "mg_game", "show": "is_mg", "x": 24, "y": 32, "images": {str(g): "images/mg_name_%d.png" % g for g in range(3)}})
GL.append({"image": "images/mg_best.png", "x": 100, "y": 36, "show": "is_mg"})
GL.append({"number": "mg_rec", "glyphs": "mgd/{c}.png", "x": 108, "y": 56, "show": "is_mg"})
GL.append({"pick": "mg_unl", "show": "is_chk", "x": 36, "y": 110, "images": {str(u): "images/mg_diff_%d.png" % u for u in range(4)}})
GL.append({"image": "images/mg_hop_rows.png", "x": 0, "y": 0, "show": "is_hop"})
for p in range(4):
    GL.append({"number": "hop_t%d" % p, "glyphs": "mgw/{c}.png", "x": 96, "y": HOP_Y[p] - 1, "show": "is_hop"})
GL.append({"image": "images/mg_bump_plates.png", "x": 0, "y": 0, "show": "is_bump"})
for p in range(4):
    GL.append({"number": "bump_s%d" % p, "glyphs": "mgw/{c}.png", "pad": 2, "align": "center",
               "x": BUMP_X[p] + 30, "y": 112, "show": "is_bump"})
ML += GL

idx = next(i for i, l in enumerate(L) if l.get("image") == "images/intro_files.png")
L[idx + 1:idx + 1] = ML

md5 = hashlib.md5(rom).hexdigest()
manifest = {
    "format": 1,
    "id": "kirby64-usa",
    "name": "Kirby 64 – The Crystal Shards",
    "game": "Kirby 64: The Crystal Shards (USA)",
    "version": "1.0",
    "author": "Hydriostatic",
    "match": {"header": "KIRBY64", "country": "E"},
    "theme": {"background": "#9C7318"},
    "screen": {"title": "Kirby 64"},
    "pixel_screen": {"size": [GW, GH], "fill": "#000000", "layers": L},
    "values": values,
}

files = {
    "images/black.png": Image.new('RGBA', (IW, IH), (0, 0, 0, 255)),
    **files_extra,
    "images/intro_files.png": intro_files,
    **fade_img,
    "images/intro_white.png": intro_white, "images/intro_title.png": intro_title,
    "images/bg.png": bg, "images/cell.png": cell, "images/star.png": star, "images/ring.png": ring,
    "images/stage4.png": stage_box(4), "icons/shard.png": SHARD_ON,
}
for w, im in world_name.items(): files["images/world_%d.png" % w] = im
for n, im in level_num.items(): files["images/level_%d.png" % n] = im
for i, im in icon.items(): files["icons/ab_%d.png" % i] = im
for n, im in digit.items(): files["digits/%d.png" % n] = im

def png(im):
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    for path, im in files.items(): z.writestr(path, png(im))
print('wrote', OUT, '(%d files)' % (len(files) + 1))

# ---------------------------------------------------------------------------------------------
# Optional preview: draws the pixel_screen the way the emulator does, with sample values
# ---------------------------------------------------------------------------------------------
if PREVIEW:
    sample = {"lives": 2, "hp": 4, "stars": 17, "ability": 14, "world": 1, "stage": 1, "world_no": 2,
              "shards": 23, "is_dark": 0, "has4": 1}
    sample["ability_l"], sample["ability_r"] = AB_L[sample["ability"]], AB_R[sample["ability"]]
    shard_bits = {0: 7, 1: 5, 2: 0, 3: 0}
    for k in range(4):
        sample["cur%d" % k] = 1 if sample["stage"] == k else 0
        for j in range(3): sample["s%d_%d" % (k, j)] = (shard_bits[k] >> j) & 1
    canvas = Image.new('RGBA', (GW, GH))
    def put(path, x, y, center=False):
        im = files[path]
        if center: x, y = x - im.width // 2, y - im.height // 2
        canvas.alpha_composite(im, (int(x), int(y)))
    for ly in L:
        if 'show' in ly and not sample.get(ly['show']): continue
        if 'hide' in ly and sample.get(ly['hide']): continue
        c = ly.get('anchor') == 'center'
        if 'image' in ly: put(ly['image'], ly['x'], ly['y'], c)
        elif 'repeat' in ly:
            for i in range(max(0, min(ly['max'], sample[ly['count']]))): put(ly['repeat'], ly['x'] + i * ly.get('dx', 0), ly['y'] + i * ly.get('dy', 0), c)
        elif 'pick' in ly:
            p = ly['images'].get(str(sample[ly['pick']]))
            if p: put(p, ly['x'], ly['y'], c)
        elif 'number' in ly:
            s = str(sample[ly['number']]).rjust(ly.get('pad', 0), '0')
            tot = ly['advance'] * len(s)
            x = ly['x'] - tot if ly.get('align') == 'right' else ly['x']
            for ch in s: put(ly['glyphs'].replace('{c}', ch), x, ly['y']); x += ly['advance']
    canvas.resize((GW * 5, GH * 5), Image.NEAREST).save(PREVIEW)
    print('preview', PREVIEW, '(ability %d = icons %d + %d)' % (sample["ability"], sample["ability_l"], sample["ability_r"]))
