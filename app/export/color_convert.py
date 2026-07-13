"""Конвертация цветов для печатного PDF (CMYK / RGB)."""
from __future__ import annotations

from app.config import TypographyProfile


def use_cmyk_output(profile: TypographyProfile) -> bool:
    """True для полиграфических профилей (не digital/sRGB)."""
    cp = (profile.color_profile or "").lower()
    if "digital" in cp or "srgb" in cp:
        return False
    return True


def rgb_to_cmyk_percent(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    """RGB 0-255 → CMYK 0-100%."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    k = 1.0 - max(r, g, b)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 100.0
    c = (1.0 - r - k) / (1.0 - k) * 100.0
    m = (1.0 - g - k) / (1.0 - k) * 100.0
    y = (1.0 - b - k) / (1.0 - k) * 100.0
    return round(c, 2), round(m, 2), round(y, 2), round(k * 100.0, 2)


def rgb_to_cmyk_unit(r: int, g: int, b: int) -> tuple[float, float, float, float]:
    c, m, y, k = rgb_to_cmyk_percent(r, g, b)
    return c / 100.0, m / 100.0, y / 100.0, k / 100.0


def rgb_to_rgb_unit(r: int, g: int, b: int) -> tuple[float, float, float]:
    return r / 255.0, g / 255.0, b / 255.0


def style_text_color(style: str, accent_rgb: tuple[int, int, int],
                     use_cmyk: bool) -> tuple:
    if style.startswith("h"):
        r, g, b = accent_rgb
    elif style in ("caption", "footnote", "jump_line"):
        r, g, b = 90, 90, 90
    elif style == "ad_label":
        r, g, b = 60, 60, 60
    else:
        r, g, b = 25, 25, 25
    if use_cmyk:
        return rgb_to_cmyk_unit(r, g, b)
    return rgb_to_rgb_unit(r, g, b)


def prepare_image_bytes(path, use_cmyk: bool) -> tuple[bytes, str]:
    """Готовит JPEG-поток для вставки в PDF."""
    import io
    from PIL import Image

    img = Image.open(path)
    if img.mode not in ("RGB", "L", "CMYK"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    if use_cmyk:
        if img.mode != "CMYK":
            img = img.convert("CMYK")
        img.save(buf, format="JPEG", quality=92, dpi=img.info.get("dpi", (300, 300)))
        return buf.getvalue(), "jpeg"
    if img.mode == "CMYK":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), "jpeg"
