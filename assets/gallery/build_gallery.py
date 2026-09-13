"""Build 10 Minecraft-style gallery assets: texture.png, model.json, preview.png.

    python assets/gallery/build_gallery.py

Does not touch assets/block_texture.png, block_model.json, or model_preview.png.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Pixel helpers
# ---------------------------------------------------------------------------

def px(size: int, paint) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    p = im.load()
    paint(p, size)
    return im


def fill_rect(p, x0, y0, x1, y1, c):
    for y in range(y0, y1):
        for x in range(x0, x1):
            p[x, y] = c


def dither_noise(p, size, colors, seed=0):
    """Sparse speckles from a color list for Minecraft grit."""
    n = len(colors)
    for y in range(size):
        for x in range(size):
            h = (x * 37 + y * 17 + seed * 91) & 255
            if h < 40:
                p[x, y] = colors[h % n]


def count_colors(im: Image.Image) -> int:
    return len({im.getpixel((x, y)) for y in range(im.height) for x in range(im.width)})


# ---------------------------------------------------------------------------
# Texture painters — each returns (Image, color_count_target_note)
# ---------------------------------------------------------------------------

def tex_ember_lantern(size=16):
    # warm metal frame + ember core — copper/bronze + orange/amber
    C = {
        "bg": (28, 18, 14),
        "frame": (120, 72, 38),
        "frame_hi": (168, 110, 58),
        "frame_lo": (72, 42, 22),
        "ember": (240, 120, 28),
        "ember_hi": (255, 200, 80),
        "ember_lo": (160, 48, 12),
        "glass": (60, 36, 24),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["bg"])
        # metal cage grid
        for i in range(s):
            p[i, 1] = C["frame_hi"]
            p[i, s - 2] = C["frame_lo"]
            p[1, i] = C["frame"]
            p[s - 2, i] = C["frame"]
        for y in range(3, s - 3):
            for x in range(3, s - 3):
                p[x, y] = C["glass"]
        # ember glow in centre
        for y in range(5, 11):
            for x in range(5, 11):
                d = abs(x - 7.5) + abs(y - 7.5)
                if d < 2:
                    p[x, y] = C["ember_hi"]
                elif d < 3.5:
                    p[x, y] = C["ember"]
                else:
                    p[x, y] = C["ember_lo"]
        # rivets
        for x, y in ((2, 2), (s - 3, 2), (2, s - 3), (s - 3, s - 3)):
            p[x, y] = C["frame_hi"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_slate_stair(size=16):
    C = {
        "base": (72, 78, 86),
        "mid": (96, 102, 112),
        "hi": (130, 138, 148),
        "lo": (48, 52, 58),
        "crack": (36, 38, 44),
        "moss": (58, 78, 52),
    }

    def paint(p, s):
        for y in range(s):
            for x in range(s):
                band = (x + y) % 5
                if band == 0:
                    p[x, y] = C["hi"]
                elif band == 1:
                    p[x, y] = C["mid"]
                elif band in (2, 3):
                    p[x, y] = C["base"]
                else:
                    p[x, y] = C["lo"]
        # cracks
        for x in range(2, 14):
            p[x, 7] = C["crack"]
        for y in range(3, 12):
            p[9, y] = C["crack"]
        p[4, 11] = C["moss"]
        p[5, 12] = C["moss"]
        p[11, 3] = C["moss"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_cedar_slab(size=16):
    C = {
        "plank": (140, 86, 48),
        "grain": (112, 64, 34),
        "hi": (176, 118, 70),
        "lo": (86, 50, 26),
        "knot": (58, 34, 18),
        "edge": (168, 108, 60),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["plank"])
        for y in range(s):
            shade = C["grain"] if (y // 4) % 2 == 0 else C["plank"]
            for x in range(s):
                p[x, y] = shade
                if (x + y * 3) % 7 == 0:
                    p[x, y] = C["lo"]
                if y % 4 == 0:
                    p[x, y] = C["edge"]
        # knots
        p[4, 5] = C["knot"]
        p[5, 5] = C["knot"]
        p[4, 6] = C["knot"]
        p[11, 10] = C["knot"]
        p[12, 10] = C["hi"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_brass_pipe(size=16):
    C = {
        "brass": (180, 140, 48),
        "brass_hi": (220, 190, 90),
        "brass_lo": (120, 90, 30),
        "bolt": (90, 70, 40),
        "shadow": (60, 48, 28),
        "oil": (40, 36, 28),
        "shine": (240, 220, 150),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["brass"])
        for y in range(s):
            for x in range(s):
                if x < 3 or x > s - 4:
                    p[x, y] = C["brass_lo"]
                elif x in (5, 6):
                    p[x, y] = C["shine"]
                elif x in (7, 8):
                    p[x, y] = C["brass_hi"]
                else:
                    p[x, y] = C["brass"]
        # flange rings
        for y in (2, 7, 12):
            for x in range(s):
                p[x, y] = C["bolt"] if x % 3 == 0 else C["brass_lo"]
        p[3, 4] = C["oil"]
        p[12, 10] = C["oil"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_prism_shard(size=16):
    C = {
        "void": (12, 8, 28),
        "core": (180, 120, 255),
        "mid": (120, 70, 220),
        "edge": (70, 40, 160),
        "hi": (230, 200, 255),
        "teal": (80, 200, 220),
        "deep": (40, 20, 90),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["void"])
        # crystalline facets — diagonal bands
        for y in range(s):
            for x in range(s):
                d = abs(x - 8) + abs(y - 8)
                if d > 9:
                    continue
                band = (x * 2 - y) % 6
                if band == 0:
                    p[x, y] = C["hi"]
                elif band == 1:
                    p[x, y] = C["core"]
                elif band == 2:
                    p[x, y] = C["teal"]
                elif band == 3:
                    p[x, y] = C["mid"]
                else:
                    p[x, y] = C["edge"]
                if d > 7:
                    p[x, y] = C["deep"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_wispfern(size=16):
    """RGBA plant sheet — air is transparent so cross-planes read as fronds."""
    C = {
        "stem": (40, 90, 48, 255),
        "leaf": (70, 160, 70, 255),
        "leaf_hi": (120, 210, 100, 255),
        "tip": (200, 240, 140, 255),
        "vein": (30, 60, 36, 255),
        "spore": (160, 220, 180, 255),
    }
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    p = im.load()
    for y in range(2, 15):
        p[7, y] = C["stem"]
        p[8, y] = C["stem"]
    for y, span in ((3, 4), (5, 5), (7, 6), (9, 5), (11, 4)):
        for dx in range(-span, span + 1):
            x = 7 + dx
            if 0 <= x < size:
                p[x, y] = C["leaf_hi"] if abs(dx) < 2 else C["leaf"]
                if abs(dx) == span:
                    p[x, y] = C["tip"]
        p[7, y] = C["vein"]
        p[8, y] = C["vein"]
    p[4, 4] = C["spore"]
    p[12, 8] = C["spore"]
    p[5, 10] = C["spore"]
    opaque = {(r, g, b) for (r, g, b, a) in im.getdata() if a > 0}
    return im, len(opaque)


def tex_terracotta_idol(size=16):
    C = {
        "clay": (168, 92, 58),
        "clay_hi": (198, 120, 78),
        "clay_lo": (120, 62, 38),
        "paint": (40, 28, 70),
        "paint_hi": (90, 60, 140),
        "eye": (220, 200, 160),
        "shadow": (80, 40, 28),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["clay"])
        for y in range(s):
            for x in range(s):
                if (x + y) % 4 == 0:
                    p[x, y] = C["clay_hi"]
                if y > 12:
                    p[x, y] = C["clay_lo"]
        # ceremonial stripes
        for y in (3, 4, 10, 11):
            for x in range(2, 14):
                p[x, y] = C["paint"] if y % 2 else C["paint_hi"]
        # eye marks
        p[5, 7] = C["eye"]
        p[6, 7] = C["paint"]
        p[10, 7] = C["eye"]
        p[9, 7] = C["paint"]
        p[7, 9] = C["shadow"]
        p[8, 9] = C["shadow"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_sandstone_ruin(size=16):
    C = {
        "sand": (196, 170, 110),
        "sand_hi": (220, 198, 140),
        "sand_lo": (150, 120, 70),
        "crack": (100, 78, 48),
        "moss": (78, 100, 52),
        "lichen": (120, 130, 70),
        "dark": (70, 55, 35),
    }

    def paint(p, s):
        for y in range(s):
            for x in range(s):
                row = y // 4
                p[x, y] = C["sand_hi"] if (x + row) % 3 == 0 else C["sand"]
                if (x * 5 + y * 3) % 11 == 0:
                    p[x, y] = C["sand_lo"]
        # weathered cracks
        for x in range(1, 15):
            p[x, 5] = C["crack"]
        for y in range(6, 14):
            p[8, y] = C["crack"]
        p[3, 9] = C["moss"]
        p[4, 10] = C["moss"]
        p[12, 3] = C["lichen"]
        p[13, 4] = C["lichen"]
        p[2, 14] = C["dark"]
        p[14, 12] = C["dark"]

    im = px(size, paint)
    return im, count_colors(im)


def tex_iron_war_pick(size=16):
    """RGBA item sheet — transparent air around haft + head."""
    C = {
        "iron": (160, 168, 178, 255),
        "iron_hi": (210, 218, 228, 255),
        "iron_lo": (100, 108, 118, 255),
        "haft": (96, 62, 32, 255),
        "haft_lo": (64, 40, 20, 255),
        "wrap": (48, 36, 24, 255),
        "rust": (120, 70, 40, 255),
    }
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    p = im.load()
    for i in range(12):
        x, y = 3 + i // 2, 14 - i
        if 0 <= x < size and 0 <= y < size:
            p[x, y] = C["haft"] if i % 3 else C["haft_lo"]
            if x + 1 < size:
                p[x + 1, y] = C["haft"]
    for x, y in ((6, 6), (7, 6), (6, 7), (7, 7)):
        p[x, y] = C["wrap"]
    for x in range(7, 14):
        p[x, 3] = C["iron"]
        p[x, 4] = C["iron_hi"]
    for y in range(2, 7):
        p[12, y] = C["iron_lo"]
        p[13, y] = C["iron"]
    p[8, 2] = C["iron_hi"]
    p[9, 2] = C["iron"]
    p[11, 5] = C["rust"]
    opaque = {(r, g, b) for (r, g, b, a) in im.getdata() if a > 0}
    return im, len(opaque)


def tex_honey_loaf(size=16):
    C = {
        "crust": (180, 110, 40),
        "crust_hi": (210, 150, 60),
        "crumb": (230, 190, 100),
        "crumb_lo": (200, 150, 70),
        "glaze": (255, 200, 80),
        "shadow": (120, 70, 28),
        "seed": (90, 55, 25),
    }

    def paint(p, s):
        fill_rect(p, 0, 0, s, s, C["crust"])
        for y in range(3, 13):
            for x in range(2, 14):
                p[x, y] = C["crumb"] if (x + y) % 2 == 0 else C["crumb_lo"]
        # top glaze
        for y in range(2, 5):
            for x in range(3, 13):
                p[x, y] = C["glaze"] if y == 2 else C["crust_hi"]
        # crust rim
        for x in range(2, 14):
            p[x, 12] = C["shadow"]
            p[x, 3] = C["crust_hi"]
        for y in range(3, 13):
            p[2, y] = C["shadow"]
            p[13, y] = C["crust"]
        # seeds
        for x, y in ((5, 4), (8, 3), (11, 5), (6, 6)):
            p[x, y] = C["seed"]

    im = px(size, paint)
    return im, count_colors(im)


# ---------------------------------------------------------------------------
# Model builders — Minecraft Java format elements
# ---------------------------------------------------------------------------

def face_all(tex="#0", uv=(0, 0, 16, 16)):
    u0, v0, u1, v1 = uv
    return {
        d: {"uv": [u0, v0, u1, v1], "texture": tex}
        for d in ("north", "east", "south", "west", "up", "down")
    }


def cuboid(name, frm, to, tex="#0", uv=(0, 0, 16, 16)):
    return {"name": name, "from": list(frm), "to": list(to), "faces": face_all(tex, uv)}


def model(elements, texture_key="0", particle=None, texture_size=(16, 16)):
    tex_path = f"craftify:block/gallery/{texture_key}"
    return {
        "credit": "Craftify gallery asset — portfolio only, not Part 4 submission",
        "texture_size": list(texture_size),
        "textures": {"0": tex_path, "particle": particle or tex_path},
        "elements": elements,
        "display": {
            "gui": {"rotation": [30, 225, 0], "translation": [0, 0, 0], "scale": [0.625, 0.625, 0.625]},
            "fixed": {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [0.5, 0.5, 0.5]},
            "thirdperson_righthand": {
                "rotation": [0, 90, 55],
                "translation": [0, 4, 2.5],
                "scale": [0.85, 0.85, 0.85],
            },
        },
    }


def m_ember_lantern():
    # base + cage posts + roof + flame
    return model([
        cuboid("base", (4, 0, 4), (12, 2, 12), uv=(0, 12, 16, 16)),
        cuboid("post_nw", (4, 2, 4), (5, 10, 5), uv=(0, 0, 4, 16)),
        cuboid("post_ne", (11, 2, 4), (12, 10, 5), uv=(0, 0, 4, 16)),
        cuboid("post_sw", (4, 2, 11), (5, 10, 12), uv=(0, 0, 4, 16)),
        cuboid("post_se", (11, 2, 11), (12, 10, 12), uv=(0, 0, 4, 16)),
        cuboid("flame", (6.5, 3, 6.5), (9.5, 8, 9.5), uv=(4, 4, 12, 12)),
        cuboid("roof", (3.5, 10, 3.5), (12.5, 12, 12.5), uv=(0, 0, 16, 8)),
        cuboid("hook", (7, 12, 7), (9, 16, 9), uv=(6, 0, 10, 8)),
    ], "ember_lantern")


def m_slate_stair():
    return model([
        cuboid("bottom", (0, 0, 0), (16, 8, 16), uv=(0, 8, 16, 16)),
        cuboid("step", (0, 8, 8), (16, 16, 16), uv=(0, 0, 16, 8)),
    ], "slate_stair")


def m_cedar_slab():
    return model([
        cuboid("slab", (0, 0, 0), (16, 8, 16), uv=(0, 0, 16, 16)),
    ], "cedar_slab")


def m_brass_pipe():
    return model([
        cuboid("shaft", (5, 0, 5), (11, 14, 11), uv=(4, 0, 12, 16)),
        cuboid("flange_bot", (3.5, 0, 3.5), (12.5, 2, 12.5), uv=(0, 12, 16, 16)),
        cuboid("flange_mid", (4, 6, 4), (12, 8, 12), uv=(0, 6, 16, 10)),
        cuboid("flange_top", (3.5, 14, 3.5), (12.5, 16, 12.5), uv=(0, 0, 16, 4)),
    ], "brass_pipe")


def m_prism_shard():
    return model([
        cuboid("base", (5, 0, 5), (11, 2, 11), uv=(4, 12, 12, 16)),
        cuboid("shard_a", (7, 2, 7), (9, 14, 9), uv=(6, 0, 10, 14)),
        cuboid("shard_b", (4, 2, 8), (6, 11, 10), uv=(2, 2, 6, 14)),
        cuboid("shard_c", (10, 2, 6), (12, 12, 8), uv=(10, 2, 14, 14)),
        cuboid("shard_d", (8, 2, 3), (10, 9, 5), uv=(8, 4, 12, 14)),
        cuboid("shard_e", (6, 2, 11), (8, 8, 13), uv=(4, 6, 8, 14)),
    ], "prism_shard")


def m_wispfern():
    # crossed thin planes (plant-like)
    return model([
        cuboid("plane_ns", (7.5, 0, 2), (8.5, 16, 14), uv=(0, 0, 16, 16)),
        cuboid("plane_ew", (2, 0, 7.5), (14, 16, 8.5), uv=(0, 0, 16, 16)),
        cuboid("pot", (5, 0, 5), (11, 2, 11), uv=(4, 12, 12, 16)),
    ], "wispfern")


def m_terracotta_idol():
    # small statue: plinth, torso, head, arms
    return model([
        cuboid("plinth", (3, 0, 3), (13, 2, 13), uv=(0, 12, 16, 16)),
        cuboid("legs", (6, 2, 7), (10, 6, 10), uv=(4, 8, 12, 14)),
        cuboid("torso", (5, 6, 6), (11, 11, 11), uv=(2, 2, 14, 12)),
        cuboid("head", (6, 11, 6.5), (10, 15, 10.5), uv=(4, 0, 12, 8)),
        cuboid("arm_l", (3, 7, 7), (5, 11, 9), uv=(0, 4, 4, 12)),
        cuboid("arm_r", (11, 7, 7), (13, 11, 9), uv=(12, 4, 16, 12)),
    ], "terracotta_idol")


def m_sandstone_ruin():
    # broken column stump + fallen block + rubble
    return model([
        cuboid("stump", (3, 0, 3), (10, 10, 10), uv=(0, 0, 16, 16)),
        cuboid("cap_broken", (2, 10, 2), (9, 12, 8), uv=(0, 0, 14, 8)),
        cuboid("fallen", (9, 0, 8), (15, 4, 14), uv=(0, 8, 16, 16)),
        cuboid("rubble_a", (1, 0, 11), (4, 2, 14), uv=(0, 12, 8, 16)),
        cuboid("rubble_b", (11, 0, 2), (14, 3, 5), uv=(8, 10, 16, 16)),
    ], "sandstone_ruin")


def m_iron_war_pick():
    # item-style: haft + pick head (laid diagonally-ish via cuboids)
    return model([
        cuboid("haft", (7, 1, 7), (9, 12, 9), uv=(4, 0, 8, 16)),
        cuboid("wrap", (6.5, 10, 6.5), (9.5, 12, 9.5), uv=(0, 0, 8, 8)),
        cuboid("head_bar", (2, 11, 6), (14, 14, 10), uv=(0, 4, 16, 12)),
        cuboid("spike_l", (1, 11.5, 7), (3, 13.5, 9), uv=(0, 4, 4, 10)),
        cuboid("spike_r", (13, 11.5, 7), (15, 13.5, 9), uv=(12, 4, 16, 10)),
    ], "iron_war_pick")


def m_honey_loaf():
    return model([
        cuboid("plate", (2, 0, 2), (14, 1, 14), uv=(0, 12, 16, 16)),
        cuboid("loaf", (4, 1, 5), (12, 6, 11), uv=(2, 4, 14, 14)),
        cuboid("glaze_top", (4.5, 6, 5.5), (11.5, 7, 10.5), uv=(4, 0, 12, 8)),
    ], "honey_loaf")


# ---------------------------------------------------------------------------
# Isometric multi-cuboid preview renderer
# ---------------------------------------------------------------------------

def project(x, y, z, ox, oy, sx, sy):
    """Minecraft coords → screen. Y up. View from south-east."""
    return (
        ox + (x - z) * sx,
        oy + (x + z) * sy - y * sx,
    )


def shade(rgb, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def sample_tex(tex: Image.Image, u, v, u0, v0, u1, v1):
    """u,v in [0,1] across the face UV rect. Returns RGBA (a=255 if RGB source)."""
    tw, th = tex.size
    uu = u0 + (u1 - u0) * u
    vv = v0 + (v1 - v0) * v
    px_ = min(tw - 1, max(0, int(uu / 16 * tw)))
    py_ = min(th - 1, max(0, int(vv / 16 * th)))
    pix = tex.getpixel((px_, py_))
    if len(pix) == 3:
        return (*pix, 255)
    return pix


def draw_quad(canvas, pts, tex, uv, factor, depth_buf, zkey):
    """Fill a convex quad by scan-converting the parallelogram approx via bounding box + barycentric-ish UV."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    # pts: origin, +u, +u+v, +v  — use origin, u_vec, v_vec
    ox, oy = x0, y0
    ux, uy = x1 - x0, y1 - y0
    vx, vy = x3 - x0, y3 - y0
    det = ux * vy - uy * vx
    if abs(det) < 1e-6:
        return
    xs = [x0, x1, x2, x3]
    ys = [y0, y1, y2, y3]
    xmin, xmax = int(min(xs)), int(max(xs)) + 1
    ymin, ymax = int(min(ys)), int(max(ys)) + 1
    w, h = canvas.size
    px = canvas.load()
    u0, v0, u1, v1 = uv
    for x in range(max(0, xmin), min(w, xmax)):
        for y in range(max(0, ymin), min(h, ymax)):
            dx, dy = x - ox, y - oy
            s = (dx * vy - dy * vx) / det
            t = (ux * dy - uy * dx) / det
            if 0 <= s < 1 and 0 <= t < 1:
                r, g, b, a = sample_tex(tex, s, t, u0, v0, u1, v1)
                if a < 16:
                    continue
                di = y * w + x
                if zkey >= depth_buf[di]:
                    depth_buf[di] = zkey
                    px[x, y] = shade((r, g, b), factor)


def render_preview(tex: Image.Image, elements: list, title: str, out: Path, cell: float = 10.0):
    """Isometric preview of model elements (visible top / west / south faces)."""
    sx = cell
    sy = cell * 0.5
    # canvas sized for a 16-unit cube plus margin
    W, H = 420, 460
    canvas = Image.new("RGB", (W, H), (14, 18, 26))
    depth_buf = [-1e9] * (W * H)
    ox, oy = W // 2, H // 2 + 30

    faces = []
    for el in elements:
        x0, y0, z0 = el["from"]
        x1, y1, z1 = el["to"]
        fc = el["faces"]
        # centre for depth
        cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2

        def corners(face):
            # return 4 MC corners for a face, then project
            if face == "up":
                return [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]
            if face == "down":
                return [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]
            if face == "west":
                return [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)]
            if face == "east":
                return [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)]
            if face == "north":
                return [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)]
            if face == "south":
                return [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            return []

        # visible set for SE isometric view: up, west, south
        for face, factor, bias in (("up", 1.12, 0.0), ("west", 0.58, -0.5), ("south", 0.82, 0.5)):
            info = fc.get(face)
            if not info:
                continue
            uv = info.get("uv", [0, 0, 16, 16])
            c = corners(face)
            pts = [project(x, y, z, ox, oy, sx, sy) for x, y, z in c]
            # depth key: larger = closer. Camera looks from +X+Z.
            zkey = (cx + cz) + cy * 0.01 + bias
            faces.append((zkey, pts, uv, factor))

    faces.sort(key=lambda t: t[0])  # painter's: far → near
    for zkey, pts, uv, factor in faces:
        draw_quad(canvas, pts, tex, uv, factor, depth_buf, zkey)

    draw = ImageDraw.Draw(canvas)
    draw.text((16, H - 28), title, fill=(148, 163, 184))
    canvas.save(out)


# ---------------------------------------------------------------------------
# Asset registry
# ---------------------------------------------------------------------------

ASSETS = [
    {
        "id": "01_ember_lantern",
        "name": "Ember Lantern",
        "concept": "A hanging brass cage lantern with a floating ember core — ceremonial light for dungeon halls.",
        "theme": "metal / ceremonial",
        "geometry": "multi-part assembly (base, posts, flame, roof, hook)",
        "tex": tex_ember_lantern,
        "model": m_ember_lantern,
        "ai_step": "AI-assisted silhouette and palette design; script-based flat pixel painting and multi-cuboid isometric preview.",
    },
    {
        "id": "02_slate_stair",
        "name": "Slate Stair",
        "concept": "A cracked grey slate stair block with a moss fleck — stone architecture, stepped geometry.",
        "theme": "stone",
        "geometry": "stairs (bottom slab + raised step)",
        "tex": tex_slate_stair,
        "model": m_slate_stair,
        "ai_step": "AI-assisted crack/moss motif planning; script quantized the texture to a deliberate 6-colour slate palette.",
    },
    {
        "id": "03_cedar_slab",
        "name": "Cedar Slab",
        "concept": "A half-height cedar plank slab with warm grain and dark knots — simple wood flooring piece.",
        "theme": "wood",
        "geometry": "slab (half-height cuboid)",
        "tex": tex_cedar_slab,
        "model": m_cedar_slab,
        "ai_step": "AI-assisted wood-grain direction choice; script painted plank bands and knots on a 16×16 grid.",
    },
    {
        "id": "04_brass_pipe_column",
        "name": "Brass Pipe Column",
        "concept": "A vertical industrial brass pipe with flange rings — mechanical column for steampunk builds.",
        "theme": "metal / mechanical",
        "geometry": "pillar/column with flange rings",
        "tex": tex_brass_pipe,
        "model": m_brass_pipe,
        "ai_step": "AI-assisted flange spacing and oil-stain accents; script rendered cylindrical shading bands.",
    },
    {
        "id": "05_prism_shard_cluster",
        "name": "Prism Shard Cluster",
        "concept": "A cluster of violet-teal crystal shards erupting from a dark base — vibrant crystal formation.",
        "theme": "crystal",
        "geometry": "multi-part (5 shards + base)",
        "tex": tex_prism_shard,
        "model": m_prism_shard,
        "ai_step": "Cursor image generation produced concept.png (violet/teal facets); script collapsed the motif into a flat 16×16 7-colour sheet and built the shard cuboids.",
    },
    {
        "id": "06_wispfern_frond",
        "name": "Wispfern Frond",
        "concept": "A glowing fern frond on crossed thin planes — plant-like item that reads from all angles.",
        "theme": "organic / plant",
        "geometry": "plant-like crossed thin planes + pot",
        "tex": tex_wispfern,
        "model": m_wispfern,
        "ai_step": "Cursor image generation produced concept.png (glowing frond motif); script redrew it as a transparent 16×16 cross-plane plant sheet.",
    },
    {
        "id": "07_terracotta_idol",
        "name": "Terracotta Idol",
        "concept": "A small painted clay idol with plinth, torso, head, and arms — ceremonial statue silhouette.",
        "theme": "ceremonial / decorative",
        "geometry": "statue (6 cuboids forming a figure)",
        "tex": tex_terracotta_idol,
        "model": m_terracotta_idol,
        "ai_step": "Cursor image generation produced concept.png (clay + ceremonial paint); script cleaned to a flat 16×16 palette and assembled the statue cuboids.",
    },
    {
        "id": "08_sandstone_ruin_cap",
        "name": "Sandstone Ruin Cap",
        "concept": "A broken sandstone column stump with fallen blocks and rubble — ancient desert ruins fragment.",
        "theme": "ruins / ancient",
        "geometry": "multi-part ruin assembly (stump, broken cap, fallen block, rubble)",
        "tex": tex_sandstone_ruin,
        "model": m_sandstone_ruin,
        "ai_step": "AI-assisted ruin composition; script weathered the sandstone palette and placed rubble cuboids.",
    },
    {
        "id": "09_iron_war_pick",
        "name": "Iron War Pick",
        "concept": "An item-style war pick with wrapped haft and double-spiked iron head — tool/weapon, not a block.",
        "theme": "metal / tool",
        "geometry": "tool (haft + wrap + head bar + spikes)",
        "tex": tex_iron_war_pick,
        "model": m_iron_war_pick,
        "ai_step": "AI-assisted tool silhouette; script painted iron/haft pixels and built the item-style cuboid assembly.",
    },
    {
        "id": "10_honey_loaf",
        "name": "Honey Loaf",
        "concept": "A glazed honey loaf resting on a flat plate — warm bakery food prop.",
        "theme": "food",
        "geometry": "multi-part (plate + loaf + glaze cap)",
        "tex": tex_honey_loaf,
        "model": m_honey_loaf,
        "ai_step": "AI-assisted crust/glaze palette; script painted crumb dither and stacked the plate/loaf/glaze cuboids.",
    },
]


def build_one(asset: dict) -> dict:
    folder = ROOT / asset["id"]
    folder.mkdir(parents=True, exist_ok=True)

    tex, n_colors = asset["tex"]()
    tex_path = folder / "texture.png"
    tex.save(tex_path)

    mdl = asset["model"]()
    (folder / "model.json").write_text(json.dumps(mdl, indent=2) + "\n", encoding="utf-8")

    n_el = len(mdl["elements"])
    title = f"{asset['name']} — 16x16, {n_colors} colours, {n_el} elems"
    render_preview(tex, mdl["elements"], title, folder / "preview.png")

    return {
        **asset,
        "colors": n_colors,
        "elements": n_el,
        "preview": f"{asset['id']}/preview.png",
        "texture": f"{asset['id']}/texture.png",
        "model_file": f"{asset['id']}/model.json",
    }


def write_readme(rows: list[dict]) -> None:
    lines = [
        "# Craftify Asset Gallery",
        "",
        "Portfolio extras — **not** part of the Part 4 submission. "
        "The official Anchored Coral Block remains untouched in `assets/` "
        "(`block_texture.png`, `block_model.json`, `model_preview.png`).",
        "",
        "Each entry includes a 16×16 texture, a Minecraft Java-format model, "
        "and an isometric preview rendered from that model’s elements.",
        "",
        "Rebuild: `python assets/gallery/build_gallery.py`",
        "",
        "| # | Name | Geometry | Theme | Colours | Elements |",
        "|---|------|----------|-------|---------|----------|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i:02d} | [{r['name']}](#{i:02d}-{r['name'].lower().replace(' ', '-')}) | "
            f"{r['geometry'].split('(')[0].strip()} | {r['theme']} | {r['colors']} | {r['elements']} |"
        )
    lines += ["", "---", ""]
    for r in rows:
        concept = ROOT / r["id"] / "concept.png"
        concept_line = (
            f"Concept source: [`concept.png`]({r['id']}/concept.png). "
            if concept.exists()
            else ""
        )
        lines += [
            f"## {r['id'][:2]}. {r['name']}",
            "",
            f"![{r['name']}]({r['preview']})",
            "",
            f"**Concept:** {r['concept']}",
            "",
            f"**Theme / geometry:** {r['theme']} — {r['geometry']}",
            "",
            f"**Texture:** [`texture.png`]({r['texture']}) — 16×16, **{r['colors']}** colours. "
            f"**Model:** [`model.json`]({r['model_file']}) — "
            f"{r['elements']} element{'s' if r['elements'] != 1 else ''}.",
            "",
            f"**AI-assisted step:** {concept_line}{r['ai_step']}",
            "",
            "---",
            "",
        ]
    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    rows = [build_one(a) for a in ASSETS]
    write_readme(rows)
    print(f"built {len(rows)} gallery assets -> {ROOT}")
    for r in rows:
        print(f"  {r['id']}: {r['colors']} colours, {r['elements']} elements")


if __name__ == "__main__":
    main()
