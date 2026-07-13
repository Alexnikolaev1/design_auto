"""Ручные правки полосы: экспорт модели и применение overrides."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.config import MM_TO_PT


@dataclass
class FrameOverride:
    element_id: str
    page_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "page_index": self.page_index,
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
        }


def parse_overrides_json(raw: str | bytes | dict | list | None) -> list[FrameOverride]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get("overrides", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[FrameOverride] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("element_id"):
            continue
        try:
            out.append(FrameOverride(
                element_id=str(item["element_id"]),
                page_index=int(item.get("page_index", 0)),
                x_mm=float(item["x_mm"]),
                y_mm=float(item["y_mm"]),
                width_mm=float(item["width_mm"]),
                height_mm=float(item["height_mm"]),
            ))
        except (TypeError, ValueError):
            continue
    return out


def _pt_to_mm(v: float) -> float:
    return v / MM_TO_PT


def _mm_to_pt(v: float) -> float:
    return v * MM_TO_PT


def export_layout_model(plan, image_names: list[str] | None = None) -> dict[str, Any]:
    """JSON-модель для визуального редактора полосы."""
    profile = plan.profile
    m = profile.margins_pt()
    names = image_names or []
    pages_out = []
    for page in plan.pages:
        images = []
        for i, img in enumerate(page.images):
            eid = getattr(img, "element_id", None) or f"p{page.index}_img{i}"
            fname = ""
            if 0 <= img.image_index < len(names):
                fname = names[img.image_index]
            images.append({
                "element_id": eid,
                "image_index": img.image_index,
                "filename": fname,
                "role": img.image_role,
                "x_mm": round(_pt_to_mm(img.rect.x), 2),
                "y_mm": round(_pt_to_mm(img.rect.y), 2),
                "width_mm": round(_pt_to_mm(img.rect.w), 2),
                "height_mm": round(_pt_to_mm(img.rect.h), 2),
                "text_wrap": img.text_wrap,
            })
        columns = [
            {
                "index": ci,
                "x_mm": round(_pt_to_mm(c.rect.x), 2),
                "y_mm": round(_pt_to_mm(c.rect.y), 2),
                "width_mm": round(_pt_to_mm(c.rect.w), 2),
                "height_mm": round(_pt_to_mm(c.rect.h), 2),
            }
            for ci, c in enumerate(page.columns)
        ]
        pages_out.append({
            "index": page.index,
            "images": images,
            "columns": columns,
        })
    return {
        "page_width_mm": round(_pt_to_mm(plan.page_width_pt or profile.page_width_pt()), 2),
        "page_height_mm": round(_pt_to_mm(plan.page_height_pt or profile.page_height_pt()), 2),
        "margins_mm": {
            "top": profile.margin_top_mm,
            "bottom": profile.margin_bottom_mm,
            "left": profile.margin_left_mm,
            "right": profile.margin_right_mm,
        },
        "columns_count": plan.template.columns,
        "pages": pages_out,
    }


def assign_element_ids(plan) -> None:
    for page in plan.pages:
        for i, img in enumerate(page.images):
            if not getattr(img, "element_id", ""):
                img.element_id = f"p{page.index}_img{i}"


def apply_overrides(plan, overrides: list[FrameOverride]):
    from app.layout.engine import Rect
    if not overrides:
        assign_element_ids(plan)
        return plan
    assign_element_ids(plan)
    by_id = {o.element_id: o for o in overrides}
    for page in plan.pages:
        for img in page.images:
            o = by_id.get(img.element_id)
            if not o or o.page_index != page.index:
                continue
            img.rect = Rect(
                x=_mm_to_pt(o.x_mm),
                y=_mm_to_pt(o.y_mm),
                w=_mm_to_pt(o.width_mm),
                h=_mm_to_pt(o.height_mm),
            )
    return plan


def overrides_to_json(overrides: list[FrameOverride]) -> str:
    return json.dumps({"overrides": [o.to_dict() for o in overrides]}, ensure_ascii=False, indent=2)
