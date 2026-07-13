"""Рекламная сетка: парсинг, пресеты, слияние с PDF-референсом."""
from __future__ import annotations

import json
from typing import Any

from app.analysis.reference_pdf import AdSlot, ReferenceStyleProfile


def parse_ad_grid_json(raw: str | bytes | dict | list | None) -> list[AdSlot]:
    if not raw:
        return []
    try:
        if isinstance(raw, (str, bytes)):
            data = json.loads(raw)
        else:
            data = raw
    except (json.JSONDecodeError, TypeError):
        return []

    slots_raw: list[Any]
    if isinstance(data, dict):
        slots_raw = data.get("slots", [])
    elif isinstance(data, list):
        slots_raw = data
    else:
        return []

    out: list[AdSlot] = []
    for i, s in enumerate(slots_raw):
        if not isinstance(s, dict):
            continue
        try:
            w = float(s.get("width_mm", 0))
            h = float(s.get("height_mm", 0))
            if w < 5 or h < 5:
                continue
            out.append(AdSlot(
                page_index=int(s.get("page_index", 0)),
                x_mm=float(s.get("x_mm", 0)),
                y_mm=float(s.get("y_mm", 0)),
                width_mm=w,
                height_mm=h,
                area_cm2=(w * h) / 100.0,
                filename=str(s.get("filename", "") or ""),
            ))
        except (TypeError, ValueError):
            continue
    return out


def resolve_ad_slots(
    user_grid: str | bytes | dict | list | None,
    reference: ReferenceStyleProfile | None,
) -> list[AdSlot]:
    """Слоты из редактора сетки имеют приоритет над PDF-референсом."""
    user = parse_ad_grid_json(user_grid)
    if user:
        return user
    if reference and reference.ad_slots:
        return list(reference.ad_slots)
    return []


GRID_PRESETS: dict[str, dict] = {
    "right_column": {
        "name": "Правая колонка",
        "slots": [
            {"page_index": 0, "x_mm": 145, "y_mm": 35, "width_mm": 55, "height_mm": 220},
        ],
    },
    "top_banner": {
        "name": "Верхний баннер",
        "slots": [
            {"page_index": 0, "x_mm": 18, "y_mm": 22, "width_mm": 174, "height_mm": 45},
        ],
    },
    "three_bottom": {
        "name": "3 модуля внизу",
        "slots": [
            {"page_index": 0, "x_mm": 18, "y_mm": 230, "width_mm": 55, "height_mm": 50},
            {"page_index": 0, "x_mm": 78, "y_mm": 230, "width_mm": 55, "height_mm": 50},
            {"page_index": 0, "x_mm": 138, "y_mm": 230, "width_mm": 55, "height_mm": 50},
        ],
    },
    "grid_2x2": {
        "name": "Сетка 2×2",
        "slots": [
            {"page_index": 0, "x_mm": 18, "y_mm": 40, "width_mm": 85, "height_mm": 70},
            {"page_index": 0, "x_mm": 108, "y_mm": 40, "width_mm": 85, "height_mm": 70},
            {"page_index": 0, "x_mm": 18, "y_mm": 120, "width_mm": 85, "height_mm": 70},
            {"page_index": 0, "x_mm": 108, "y_mm": 120, "width_mm": 85, "height_mm": 70},
        ],
    },
    "newspaper_mix": {
        "name": "Газетный микс",
        "slots": [
            {"page_index": 0, "x_mm": 18, "y_mm": 25, "width_mm": 174, "height_mm": 35},
            {"page_index": 0, "x_mm": 145, "y_mm": 70, "width_mm": 48, "height_mm": 90},
            {"page_index": 0, "x_mm": 145, "y_mm": 168, "width_mm": 48, "height_mm": 90},
        ],
    },
    "issue_spread": {
        "name": "Выпуск: 2 полосы",
        "slots": [
            {"page_index": 0, "x_mm": 18, "y_mm": 25, "width_mm": 174, "height_mm": 40},
            {"page_index": 0, "x_mm": 145, "y_mm": 75, "width_mm": 48, "height_mm": 180},
            {"page_index": 1, "x_mm": 18, "y_mm": 25, "width_mm": 90, "height_mm": 120},
            {"page_index": 1, "x_mm": 115, "y_mm": 25, "width_mm": 78, "height_mm": 80},
            {"page_index": 1, "x_mm": 18, "y_mm": 230, "width_mm": 174, "height_mm": 45},
        ],
    },
}


def scale_preset(preset_id: str, page_w: float, page_h: float,
                 margin_l: float, margin_r: float,
                 margin_t: float, margin_b: float) -> list[dict]:
    """Масштабирует пресет (задан под A4) под текущий формат полосы."""
    base = GRID_PRESETS.get(preset_id)
    if not base:
        return []
    base_w, base_h = 210.0, 297.0
    base_ml, base_mr, base_mt, base_mb = 8.0, 10.0, 6.0, 7.0
    content_w = page_w - margin_l - margin_r
    content_h = page_h - margin_t - margin_b
    sx = content_w / (base_w - base_ml - base_mr)
    sy = content_h / (base_h - base_mt - base_mb)
    out = []
    for s in base["slots"]:
        x = margin_l + (s["x_mm"] - base_ml) * sx
        y = margin_t + (s["y_mm"] - base_mt) * sy
        w = s["width_mm"] * sx
        h = s["height_mm"] * sy
        out.append({
            "page_index": s.get("page_index", 0),
            "x_mm": round(x, 1),
            "y_mm": round(y, 1),
            "width_mm": round(w, 1),
            "height_mm": round(h, 1),
        })
    return out


def presets_catalog() -> list[dict]:
    return [{"id": k, "name": v["name"], "slot_count": len(v["slots"])} for k, v in GRID_PRESETS.items()]


def analyze_ad_slots(
    slots: list[AdSlot],
    used_indices: set[int] | None = None,
    placements: list[dict] | None = None,
) -> dict:
    """Отчёт по использованию рекламных слотов для preflight и API."""
    used = used_indices or set()
    assigned_names = {p.get("filename", "").lower() for p in (placements or []) if p.get("filename")}
    by_page: dict[int, list[dict]] = {}
    for i, s in enumerate(slots):
        pg = s.page_index
        by_page.setdefault(pg, []).append({
            "slot_index": i,
            "page_index": pg,
            "width_mm": s.width_mm,
            "height_mm": s.height_mm,
            "filename": s.filename,
            "used": i in used,
            "has_file_binding": bool(s.filename),
        })
    empty = [i for i, s in enumerate(slots) if i not in used]
    unbound_files = [
        p["filename"] for p in (placements or [])
        if p.get("image_role") == "ad" and p.get("filename", "").lower() not in
        {(slots[j].filename or "").lower() for j in used if j < len(slots)}
    ]
    return {
        "total_slots": len(slots),
        "used_slots": len(used),
        "empty_slots": len(empty),
        "pages_with_slots": sorted(by_page.keys()),
        "by_page": {str(k): v for k, v in sorted(by_page.items())},
        "unassigned_ads": unbound_files,
    }
