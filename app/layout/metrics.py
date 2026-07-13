"""Точные метрики глифов через fonttools (ближе к InDesign, чем PIL bbox)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PT_TO_UNITS = 1000.0 / 72.0  # приблизительно для большинства TTF (unitsPerEm зависит от шрифта)


@lru_cache(maxsize=48)
def _font_metrics(font_path: str) -> tuple[object, float] | None:
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(font_path)
        upem = font["head"].unitsPerEm
        return font, float(upem)
    except Exception:
        return None


def advance_width_pt(font_path: Path | None, text: str, size_pt: float) -> float | None:
    if not font_path or not text or not font_path.exists():
        return None
    cached = _font_metrics(str(font_path.resolve()))
    if cached is None:
        return None
    font, upem = cached
    try:
        cmap = font.getBestCmap() or {}
        glyf = font.get("glyf")
        hmtx = font.get("hmtx")
        if hmtx is None:
            return None
        default_advance = hmtx.metrics.get(".notdef", (upem // 2, 0))[0]
        total = 0.0
        for ch in text:
            gid = cmap.get(ord(ch))
            if gid is None:
                total += default_advance
                continue
            name = font.getGlyphName(gid)
            adv = hmtx.metrics.get(name, (default_advance, 0))[0]
            total += adv
        return (total / upem) * size_pt
    except Exception:
        return None
