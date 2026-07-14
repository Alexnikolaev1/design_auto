"""Газетная логика «Сибирская околица»: роли фото, размеры кадров, шапка."""
from __future__ import annotations

import re
from pathlib import Path

from app.config import MM_TO_PT
from app.layout.image_roles import image_aspect
from app.layout.templates import TemplateSpec

MASTHEAD_HEIGHT_MM = 12.0
LEAD_MAX_HEIGHT_MM = 78.0
LEAD_MIN_HEIGHT_MM = 48.0
COL_PHOTO_MIN_HEIGHT_MM = 42.0

LEAD_NAME_RE = re.compile(
    r"(?:lead|hero|main|cover|облож|главн|hero[_-]?img)",
    re.IGNORECASE,
)
PORTRAIT_NAME_RE = re.compile(
    r"(?:portrait|портрет|лицо|face|avatar|автор)",
    re.IGNORECASE,
)


def is_newspaper_template(template: TemplateSpec) -> bool:
    return template.id == "okolica-news" or template.font_role == "newspaper"


def refine_photo_role(
    role: str,
    path: Path | None,
    filename: str = "",
    *,
    first_after_heading: bool = False,
) -> str:
    """Уточняет роль: lead | portrait | photo | (banner/ad/logo без изменений)."""
    if role in ("banner", "ad", "logo", "lead", "portrait", "mid"):
        return role
    name = filename or (path.name if path else "")
    if LEAD_NAME_RE.search(name) or first_after_heading:
        return "lead"
    if PORTRAIT_NAME_RE.search(name):
        return "portrait"
    if path and path.exists():
        asp = image_aspect(path)
        if asp < 0.85:
            return "portrait"
    return "photo"


def newspaper_image_rect(
    *,
    content_x: float,
    content_w: float,
    y: float,
    col_w: float,
    gutter_pt: float,
    n_cols: int,
    role: str,
    img_path: Path | None,
    page_height_pt: float,
    col_x: float | None = None,
) -> tuple[float, float, float, float]:
    """Возвращает (x, y, w, h) в pt."""
    asp = image_aspect(img_path) if img_path and img_path.exists() else 1.45
    cx = col_x if col_x is not None else content_x

    if role == "lead":
        if n_cols >= 3:
            x = content_x + col_w + gutter_pt
            w = 2 * col_w + gutter_pt
        else:
            x, w = content_x, content_w
        h = w / max(asp, 0.5)
        h = min(h, LEAD_MAX_HEIGHT_MM * MM_TO_PT, page_height_pt * 0.30)
        h = max(h, LEAD_MIN_HEIGHT_MM * MM_TO_PT)
        return x, y, w, h

    if role == "portrait":
        w = col_w
        h = w / max(asp, 0.55)
        h = min(h, page_height_pt * 0.28)
        h = max(h, COL_PHOTO_MIN_HEIGHT_MM * MM_TO_PT)
        return cx, y, w, h

    if role == "mid" or (role == "photo" and asp >= 1.5 and n_cols >= 2):
        w = min(content_w, 2 * col_w + gutter_pt)
        h = w / max(asp, 0.5)
        h = min(h, LEAD_MAX_HEIGHT_MM * MM_TO_PT * 0.85, page_height_pt * 0.24)
        h = max(h, COL_PHOTO_MIN_HEIGHT_MM * MM_TO_PT)
        return content_x, y, w, h

    w = col_w
    h = w / max(asp, 0.5)
    h = min(h, page_height_pt * 0.26)
    h = max(h, COL_PHOTO_MIN_HEIGHT_MM * MM_TO_PT)
    return cx, y, w, h


def stroke_pt_for_role(role: str) -> float:
    if role == "logo":
        return 0.0
    if role in ("ad", "banner"):
        return 0.5 if role == "ad" else 0.0
    if role in ("lead", "photo", "portrait", "mid"):
        return 0.5
    return 0.0


def masthead_reserve_pt() -> float:
    return MASTHEAD_HEIGHT_MM * MM_TO_PT
