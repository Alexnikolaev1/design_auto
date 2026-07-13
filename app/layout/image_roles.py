"""Классификация иллюстраций: фото, рекламный баннер, логотип."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

BANNER_NAME_RE = re.compile(
    r"(?:banner|баннер|банер|rek|reklama|реклама|promo|промо|ad[_-]?|ads\b|афиш)",
    re.IGNORECASE,
)
LOGO_NAME_RE = re.compile(r"(?:logo|логотип|logotype|brand|бренд)", re.IGNORECASE)
BANNER_MARKER_ROLES = {"banner", "баннер", "реклама", "ad", "promo"}

# Широкий горизонтальный формат (типичный print/web баннер)
BANNER_ASPECT_MIN = 2.0
# Квадратный/вертикальный мини-формат логотипа
LOGO_MAX_SIDE = 480


def classify_image(path: Path, filename: str = "", forced_role: str = "") -> str:
    """
    Возвращает роль: photo | banner | logo | ad.
    """
    if forced_role in ("photo", "banner", "logo", "ad"):
        return forced_role

    name = (filename or path.name).lower()
    if LOGO_NAME_RE.search(name):
        return "logo"

    from app.layout.ad_units import parse_dimensions_from_filename, parse_area_cm2_from_filename
    if parse_dimensions_from_filename(name) or parse_area_cm2_from_filename(name):
        return "ad"
    if re.search(r"(?:reklama|реклама|^\s*ad[_-])", name, re.I):
        try:
            with Image.open(path) as im:
                if im.width / max(im.height, 1) >= BANNER_ASPECT_MIN:
                    return "banner"
        except Exception:
            pass
        return "ad"

    if BANNER_NAME_RE.search(name):
        return "banner"

    try:
        with Image.open(path) as im:
            w, h = im.width, max(im.height, 1)
            ratio = w / h
            if ratio >= BANNER_ASPECT_MIN:
                return "banner"
            if ratio >= 1.6 and h <= 400:
                return "banner"
    except Exception:
        pass
    return "photo"


def image_aspect(path: Path) -> float:
    try:
        with Image.open(path) as im:
            return im.width / max(im.height, 1)
    except Exception:
        return 1.6


def is_banner_role(role: str) -> bool:
    return role == "banner"


def is_ad_role(role: str) -> bool:
    return role == "ad"
