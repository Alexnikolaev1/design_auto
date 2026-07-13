"""
Смарт-кадрирование: фокус по контрасту + эвристика горизонта.
Без OpenCV — только Pillow.
"""
from __future__ import annotations

from PIL import Image, ImageFilter


def _focal_point(img: Image.Image) -> tuple[float, float]:
    """Нормализованная точка интереса (0..1, 0..1)."""
    gray = img.convert("L")
    w, h = gray.size
    small = gray.resize((max(32, min(96, w // 8)), max(32, min(96, h // 8))))
    edges = small.filter(ImageFilter.FIND_EDGES)
    pixels = edges.load()
    sw, sh = small.size
    total_x = total_y = total_w = 0.0
    top_w = bottom_w = 0.0
    mid = sh // 2
    for y in range(sh):
        for x in range(sw):
            wgt = float(pixels[x, y])
            total_x += x * wgt
            total_y += y * wgt
            total_w += wgt
            if y < mid:
                top_w += wgt
            else:
                bottom_w += wgt
    if total_w < 1.0:
        return 0.5, 0.38
    fx = total_x / total_w / sw
    fy = total_y / total_w / sh
    # Горизонт: больше деталей внизу (земля) → сдвигаем фокус вверх
    if bottom_w > top_w * 1.35 and img.width > img.height * 1.1:
        fy = min(fy, 0.42)
    elif top_w > bottom_w * 1.5:
        fy = max(fy, 0.55)
    return max(0.08, min(0.92, fx)), max(0.08, min(0.92, fy))


def smart_crop_cover(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Cover-crop с привязкой к фокусу (лица/контраст/горизонт)."""
    if target_w < 1 or target_h < 1:
        return img
    iw, ih = img.size
    if iw < 2 or ih < 2:
        return img.resize((max(1, target_w), max(1, target_h)))
    src_ratio = iw / ih
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        new_h = ih
        new_w = int(ih * tgt_ratio)
    else:
        new_w = iw
        new_h = int(iw / tgt_ratio)
    fx, fy = _focal_point(img)
    cx = int(fx * iw)
    cy = int(fy * ih)
    left = max(0, min(iw - new_w, cx - new_w // 2))
    top = max(0, min(ih - new_h, cy - new_h // 2))
    cropped = img.crop((left, top, left + new_w, top + new_h))
    if cropped.size != (target_w, target_h):
        cropped = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return cropped
