"""Deterministic pixel repair pipeline for Purrden sprites.

semantic generation (hi-res)
  → crop / subject normalize
  → nearest-neighbor downsample to native size
  → palette quantization (core style bible)
  → binary alpha enforcement
  → optional hard QA

No generative models here — pure image processing (Pillow).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .qa import CORE_PALETTE, QaReport, qa_png

# RGB tuples for quantization (no alpha)
_PALETTE_RGB: list[tuple[int, int, int]] = []
for hx in sorted(CORE_PALETTE):
    _PALETTE_RGB.append((int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)))


@dataclass
class RepairResult:
    source: Path
    repaired: Path
    native_size: tuple[int, int]
    opaque_colors: int
    bbox: tuple[int, int, int, int] | None
    qa: QaReport | None = None


def _require_pil():
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Pillow is required for pixel repair. Install with: pip install Pillow"
        ) from e
    return Image


def subject_bbox(im, alpha_threshold: int = 16) -> tuple[int, int, int, int] | None:
    """Bounding box of non-transparent-ish pixels (left, upper, right, lower)."""
    rgba = im.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if pixels[x, y][3] > alpha_threshold:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x < 0:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


def crop_and_pad_square(im, margin_ratio: float = 0.08):
    """Crop to subject bbox, pad to square with transparency, keep composition room."""
    Image = _require_pil()
    rgba = im.convert("RGBA")
    box = subject_bbox(rgba)
    if box is None:
        return rgba
    left, upper, right, lower = box
    bw, bh = right - left, lower - upper
    pad = int(max(bw, bh) * margin_ratio)
    left = max(0, left - pad)
    upper = max(0, upper - pad)
    right = min(rgba.width, right + pad)
    lower = min(rgba.height, lower + pad)
    cropped = rgba.crop((left, upper, right, lower))
    side = max(cropped.width, cropped.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cropped.width) // 2
    oy = (side - cropped.height) // 2
    canvas.paste(cropped, (ox, oy), cropped)
    return canvas


def nearest_resize(im, size: tuple[int, int]):
    Image = _require_pil()
    # Pillow 9+: Resampling.NEAREST; older: Image.NEAREST
    try:
        resample = Image.Resampling.NEAREST
    except AttributeError:
        resample = Image.NEAREST
    return im.resize(size, resample=resample)


def quantize_to_palette(im, palette_rgb: Sequence[tuple[int, int, int]] = _PALETTE_RGB):
    """Map each opaque pixel to nearest palette colour (Euclidean RGB). Binary alpha."""
    Image = _require_pil()
    rgba = im.convert("RGBA")
    pixels = list(rgba.getdata())
    out = []
    for r, g, b, a in pixels:
        if a < 128:
            out.append((0, 0, 0, 0))
            continue
        best = palette_rgb[0]
        best_d = 1 << 30
        for pr, pg, pb in palette_rgb:
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if d < best_d:
                best_d = d
                best = (pr, pg, pb)
        out.append((best[0], best[1], best[2], 255))
    result = Image.new("RGBA", rgba.size)
    result.putdata(out)
    return result


def enforce_binary_alpha(im, threshold: int = 128):
    Image = _require_pil()
    rgba = im.convert("RGBA")
    out = []
    for r, g, b, a in rgba.getdata():
        out.append((r, g, b, 255) if a >= threshold else (0, 0, 0, 0))
    result = Image.new("RGBA", rgba.size)
    result.putdata(out)
    return result


def place_on_baseline(
    im,
    canvas_size: tuple[int, int] = (32, 32),
    baseline_y: int = 29,
):
    """Compose sprite onto native canvas with feet near baseline_y."""
    Image = _require_pil()
    src = im.convert("RGBA")
    box = subject_bbox(src)
    if box is None:
        return Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    subject = src.crop(box)
    cw, ch = canvas_size
    # Scale subject to fit width with 1px side margins if needed
    max_w = cw - 2
    max_h = baseline_y + 1  # rows 0..baseline_y inclusive
    sw, sh = subject.size
    scale = min(max_w / sw, max_h / sh, 1.0)
    if scale < 1.0:
        nw = max(1, int(sw * scale))
        nh = max(1, int(sh * scale))
        subject = nearest_resize(subject, (nw, nh))
        sw, sh = subject.size
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    x = (cw - sw) // 2
    y = baseline_y - sh + 1
    if y < 0:
        y = 0
    if y + sh > ch:
        y = ch - sh
    canvas.paste(subject, (x, y), subject)
    return canvas


def repair_to_sprite(
    source: Path,
    dest: Path,
    *,
    native: tuple[int, int] = (32, 32),
    baseline_y: int = 29,
    run_qa: bool = True,
) -> RepairResult:
    Image = _require_pil()
    im = Image.open(source)
    im.load()
    squared = crop_and_pad_square(im)
    # Downsample slightly larger than native first for cleaner silhouette, then compose
    intermediate = nearest_resize(squared, (native[0] * 2, native[1] * 2))
    quantized = quantize_to_palette(intermediate)
    binary = enforce_binary_alpha(quantized)
    final = place_on_baseline(binary, canvas_size=native, baseline_y=baseline_y)
    final = quantize_to_palette(final)
    final = enforce_binary_alpha(final)

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    final.save(dest, format="PNG", optimize=True)

    box = subject_bbox(final)
    opaque = {
        (r, g, b)
        for r, g, b, a in final.getdata()
        if a == 255
    }
    qa = qa_png(dest, expect_w=native[0], expect_h=native[1]) if run_qa else None
    return RepairResult(
        source=Path(source),
        repaired=dest,
        native_size=native,
        opaque_colors=len(opaque),
        bbox=box,
        qa=qa,
    )


def make_fixture_cat_png(dest: Path, *, size: int = 256) -> Path:
    """Synthetic hi-res 'cat-ish' blob for dry-run pipeline tests (no ComfyUI)."""
    Image = _require_pil()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = im.load()
    # body
    cx, cy, r = size // 2, int(size * 0.55), int(size * 0.22)
    for y in range(size):
        for x in range(size):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                px[x, y] = (148, 176, 194, 255)  # mist-ish
    # head
    hx, hy, hr = size // 2, int(size * 0.38), int(size * 0.16)
    for y in range(size):
        for x in range(size):
            if (x - hx) ** 2 + (y - hy) ** 2 <= hr * hr:
                px[x, y] = (148, 176, 194, 255)
    # ears
    for ear_x in (hx - hr // 2, hx + hr // 2):
        for y in range(hy - hr, hy - hr // 3):
            for x in range(ear_x - 8, ear_x + 8):
                if 0 <= x < size and 0 <= y < size:
                    if abs(x - ear_x) < (hy - hr // 3 - y) // 2 + 2:
                        px[x, y] = (86, 108, 134, 255)  # slate-ish
    # eyes
    for ex in (hx - 12, hx + 12):
        for y in range(hy - 4, hy + 4):
            for x in range(ex - 3, ex + 3):
                if 0 <= x < size and 0 <= y < size:
                    px[x, y] = (26, 28, 44, 255)  # ink
    im.save(dest, format="PNG")
    return dest
