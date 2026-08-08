"""Deterministic hard QA for Purrden pixel sprites.

No LLM/VLM. Exit semantics for CLI: 0 pass, 1 fail.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Core palette from art/style-bible.yaml (hex, lowercase). Transparent handled separately.
CORE_PALETTE = {
    "#1a1c2c",
    "#5d275d",
    "#b13e53",
    "#ef7d57",
    "#ffcd75",
    "#a7f070",
    "#38b764",
    "#257179",
    "#29366f",
    "#3b5dc9",
    "#41a6f6",
    "#73eff7",
    "#f4f4f4",
    "#94b0c2",
    "#566c86",
    "#333c57",
    "#ea90b4",
    "#f4d35e",
    "#f9e6c5",
    "#8b5e34",
    "#5a3a1a",
    "#9b6b9e",
    "#4a3f6b",
}


@dataclass
class QaCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class QaReport:
    path: str
    passed: bool
    checks: list[QaCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "passed": self.passed,
            "checks": [asdict(c) for c in self.checks],
        }


def _hex_rgb(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def qa_png(
    path: Path,
    *,
    expect_w: int = 32,
    expect_h: int = 32,
    max_colors: int = 9,
    baseline_y: int = 29,
    palette: set[str] | None = None,
) -> QaReport:
    """Run hard QA on a PNG file. Requires Pillow when images exist."""
    report = QaReport(path=str(path), passed=True)
    palette = palette or CORE_PALETTE

    if not path.is_file():
        report.checks.append(QaCheck("exists", False, "file not found"))
        report.passed = False
        return report

    try:
        from PIL import Image
    except ImportError:
        report.checks.append(
            QaCheck("pillow", False, "Pillow not installed; run: pip install Pillow")
        )
        report.passed = False
        return report

    try:
        im = Image.open(path)
        im.load()
    except Exception as e:  # noqa: BLE001 — surface any decode error
        report.checks.append(QaCheck("decode", False, str(e)))
        report.passed = False
        return report

    report.checks.append(
        QaCheck("format", im.format == "PNG", f"format={im.format!r}")
    )

    w, h = im.size
    report.checks.append(
        QaCheck("dimensions", (w, h) == (expect_w, expect_h), f"{w}x{h}")
    )

    rgba = im.convert("RGBA")
    pixels = list(rgba.getdata())
    opaque_colors: set[str] = set()
    non_binary_alpha = 0
    off_palette = 0
    for r, g, b, a in pixels:
        if a not in (0, 255):
            non_binary_alpha += 1
        if a == 0:
            continue
        hx = _hex_rgb(r, g, b)
        opaque_colors.add(hx)
        if hx not in palette:
            off_palette += 1

    report.checks.append(
        QaCheck(
            "binary_alpha",
            non_binary_alpha == 0,
            f"non_binary_pixels={non_binary_alpha}",
        )
    )
    report.checks.append(
        QaCheck(
            "color_budget",
            len(opaque_colors) <= max_colors,
            f"opaque_colors={len(opaque_colors)} max={max_colors}",
        )
    )
    report.checks.append(
        QaCheck(
            "palette_membership",
            off_palette == 0,
            f"off_palette_pixels={off_palette} unique={sorted(opaque_colors)}",
        )
    )

    # Bounding box / empty check
    opaque_coords = [
        (i % w, i // w) for i, (_r, _g, _b, a) in enumerate(pixels) if a == 255
    ]
    if not opaque_coords:
        report.checks.append(QaCheck("non_empty", False, "fully transparent"))
    else:
        xs = [x for x, _ in opaque_coords]
        ys = [y for _, y in opaque_coords]
        report.checks.append(
            QaCheck(
                "non_empty",
                True,
                f"bbox=({min(xs)},{min(ys)})-({max(xs)},{max(ys)})",
            )
        )
        # Soft baseline hint: feet should reach near baseline_y
        max_y = max(ys)
        report.checks.append(
            QaCheck(
                "baseline_near",
                abs(max_y - baseline_y) <= 2,
                f"max_y={max_y} baseline_y={baseline_y}",
            )
        )

    report.passed = all(c.ok for c in report.checks)
    return report


def report_json(report: QaReport) -> str:
    return json.dumps(report.to_dict(), indent=2)
