"""Серверное хранилище шаблонов рекламной сетки."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import GRID_TEMPLATES_DIR


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name.strip().lower(), flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:48] or "template"


def _template_path(template_id: str) -> Path:
    if ".." in template_id or "/" in template_id or "\\" in template_id:
        raise ValueError("Некорректный идентификатор шаблона")
    return GRID_TEMPLATES_DIR / f"{template_id}.json"


def list_templates() -> list[dict[str, Any]]:
    GRID_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for path in sorted(GRID_TEMPLATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        slots = data.get("slots") or []
        pages = {int(s.get("page_index", 0)) for s in slots if isinstance(s, dict)}
        out.append({
            "id": path.stem,
            "name": data.get("name", path.stem),
            "slot_count": len(slots),
            "page_count": len(pages) or 1,
            "page_format": data.get("page_format", "a4"),
            "saved_at": data.get("saved_at", ""),
        })
    return out


def load_template(template_id: str) -> dict[str, Any] | None:
    path = _template_path(template_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["id"] = template_id
    return data


def save_template(name: str, slots: list[dict], page_format: str = "a4") -> dict[str, Any]:
    GRID_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    template_id = f"{_slug(name)}-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name.strip(),
        "slots": slots,
        "page_format": page_format,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    _template_path(template_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return {"id": template_id, **payload}


def delete_template(template_id: str) -> bool:
    path = _template_path(template_id)
    if not path.exists():
        return False
    path.unlink()
    return True
