"""Turns the AI texture concept into a usable 16x16 Minecraft block texture, and renders
an isometric preview of the block model.

    python assets/build_texture.py

Inputs : assets/block_texture_concept.png  (AI-generated concept, 1024x1024, anti-aliased)
Outputs: assets/block_texture.png          (strict 16x16, 8-colour palette, game-ready)
         assets/block_texture_x32.png      (nearest-neighbour blow-up, for the README)
         assets/model_preview.png          (isometric render of block_model.json's shape)
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SIZE = 16
PALETTE_COLORS = 8


def clean() -> Image.Image:
    """Collapse the concept to a strict pixel grid: area-average down to 16x16, then
    quantise to 8 flat colours so nothing is anti-aliased or noisy."""
    src = Image.open(HERE / "block_texture_concept.png").convert("RGB")
    small = src.resize((SIZE, SIZE), Image.BOX)
    quant = small.quantize(colors=PALETTE_COLORS, method=Image.MEDIANCUT).convert("RGB")
    quant.save(HERE / "block_texture.png")
    quant.resize((SIZE * 32, SIZE * 32), Image.NEAREST).save(HERE / "block_texture_x32.png")
    return quant


def _paint_face(canvas, tex, origin, u_vec, v_vec, factor: float) -> None:
    """Paint the texture into the parallelogram origin + s*u + t*v (s,t in [0,1]).
    Inverts the 2x2 basis per pixel — exact, and 16x16 nearest-neighbour keeps pixels crisp.
    """
    (ox, oy), (ux, uy), (vx, vy) = origin, u_vec, v_vec
    det = ux * vy - uy * vx
    xs = [ox, ox + ux, ox + vx, ox + ux + vx]
    ys = [oy, oy + uy, oy + vy, oy + uy + vy]
    px = canvas.load()
    tpx = tex.load()
    for x in range(int(min(xs)), int(max(xs)) + 1):
        for y in range(int(min(ys)), int(max(ys)) + 1):
            dx, dy = x - ox, y - oy
            s = (dx * vy - dy * vx) / det
            t = (ux * dy - uy * dx) / det
            if 0 <= s < 1 and 0 <= t < 1:
                r, g, b = tpx[min(SIZE - 1, int(s * SIZE)), min(SIZE - 1, int(t * SIZE))]
                px[x, y] = (min(255, int(r * factor)), min(255, int(g * factor)), min(255, int(b * factor)))


def preview(tex: Image.Image, cell: int = 14) -> None:
    """Cheap isometric cube render: top / left / right faces of the block.
    ponytail: no 3D engine involved. Ceiling: shows the cube silhouette and texture mapping
    only — it does not render the raised iron-strap element of block_model.json."""
    w = SIZE * cell
    canvas = Image.new("RGB", (w * 2 + 40, w * 2 + 80), (11, 15, 22))
    ox, oy = 20, 20
    left_top, mid_top, right_top = (ox, oy + w // 2), (ox + w, oy + w), (ox + 2 * w, oy + w // 2)

    _paint_face(canvas, tex, left_top, (w, -w // 2), (w, w // 2), 1.15)          # up
    _paint_face(canvas, tex, left_top, (w, w // 2), (0, w), 0.60)                # west
    _paint_face(canvas, tex, mid_top, (w, -w // 2), (0, w), 0.85)                # south

    draw = ImageDraw.Draw(canvas)
    draw.text((22, canvas.height - 28), "Anchored Coral Block - 16x16, 8 colours", fill=(148, 163, 184))
    canvas.save(HERE / "model_preview.png")


if __name__ == "__main__":
    preview(clean())
    print("wrote block_texture.png, block_texture_x32.png, model_preview.png")
