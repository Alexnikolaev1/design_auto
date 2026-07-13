"""Размеры рекламных модулей: мм, см², разбор из маркеров и имён файлов."""
from __future__ import annotations

import math
import re
from pathlib import Path

from app.layout.image_roles import image_aspect

SIZE_MM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*mm",
    re.IGNORECASE,
)
AREA_CM2_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:cm2|см2|sq\s*cm|кв\.?\s*см)",
    re.IGNORECASE,
)
AD_MARKER_RE = re.compile(
    r"\[(?:РЕКЛАМА|REKLAMA|AD|ADS)\s*:\s*"
    r"([^\]\s]+\.(?:jpg|jpeg|png|webp|gif|tif|tiff))"
    r"(?:\s+(\d+(?:[.,]\d+)?)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*mm)?"
    r"(?:\s+(\d+(?:[.,]\d+)?)\s*(?:cm2|см2|кв\.?\s*см)?)?"
    r"\s*\]",
    re.IGNORECASE,
)

DEFAULT_AD_AREA_CM2 = 50.0
AD_LABEL_TEXT = "Реклама"
AD_LABEL_HEIGHT_MM = 4.5


def _fnum(s: str) -> float:
    return float(s.replace(",", "."))


def dimensions_from_area_cm2(area_cm2: float, aspect: float) -> tuple[float, float]:
    """Площадь в см² + пропорции картинки → (ширина_мм, высота_мм)."""
    area = max(area_cm2, 1.0)
    aspect = max(aspect, 0.2)
    h_cm = math.sqrt(area / aspect)
    w_cm = aspect * h_cm
    return round(w_cm * 10, 2), round(h_cm * 10, 2)


def parse_dimensions_from_filename(name: str) -> tuple[float, float] | None:
    stem = Path(name).stem
    m = SIZE_MM_RE.search(stem)
    if m:
        return _fnum(m.group(1)), _fnum(m.group(2))
    m = AREA_CM2_RE.search(stem)
    if m:
        return None  # caller resolves with aspect
    return None


def parse_area_cm2_from_filename(name: str) -> float | None:
    m = AREA_CM2_RE.search(Path(name).stem)
    if m:
        return _fnum(m.group(1))
    return None


def resolve_ad_size_mm(
    path: Path | None,
    width_mm: float | None = None,
    height_mm: float | None = None,
    area_cm2: float | None = None,
    filename: str = "",
) -> tuple[float, float]:
    """Итоговый размер рекламного модуля в миллиметрах."""
    if width_mm and height_mm and width_mm > 0 and height_mm > 0:
        return round(width_mm, 2), round(height_mm, 2)

    if not width_mm and not height_mm and filename:
        parsed = parse_dimensions_from_filename(filename)
        if parsed:
            return parsed
        area_cm2 = area_cm2 or parse_area_cm2_from_filename(filename)

    aspect = image_aspect(path) if path and path.exists() else 1.0
    area = area_cm2 or DEFAULT_AD_AREA_CM2
    return dimensions_from_area_cm2(area, aspect)


def parse_ad_marker(text: str) -> list[tuple[str, float | None, float | None, float | None]]:
    """
    Возвращает список (filename, width_mm|None, height_mm|None, area_cm2|None).
    """
    out: list[tuple[str, float | None, float | None, float | None]] = []
    for m in AD_MARKER_RE.finditer(text):
        fname = m.group(1).strip()
        w = _fnum(m.group(2)) if m.group(2) else None
        h = _fnum(m.group(3)) if m.group(3) else None
        area = _fnum(m.group(4)) if m.group(4) else None
        out.append((fname, w, h, area))
    return out
