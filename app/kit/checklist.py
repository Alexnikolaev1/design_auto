"""Чеклист печати для CS3 Element Kit (делегирует genius preflight)."""
from __future__ import annotations

from app.kit.brand import BRAND_SWATCHES, COLOR_PROFILE_DEFAULT, MAX_TOTAL_INK, validate_swatches_ink
from app.kit.preflight import PreflightReport, format_genius_checklist, run_kit_preflight


def format_kit_checklist(
    include: list[str],
    source: str = "rules",
    smoke_ok: bool | None = None,
    inx_bytes: bytes | None = None,
    scene_id: str | None = None,
    preflight: PreflightReport | None = None,
) -> str:
    """Genius-чеклист: если есть INX — полный префлайт; иначе упрощённый."""
    if preflight is None and inx_bytes is not None:
        preflight = run_kit_preflight(inx_bytes, include=include)
    if preflight is not None:
        return format_genius_checklist(include, source, preflight, scene_id=scene_id)

    ink_warns = validate_swatches_ink()
    lines = [
        "LAYOUTGENIUS — CS3 ELEMENT KIT — ЧЕКЛИСТ ТИПОГРАФИИ",
        "=" * 56,
        f"Профиль цвета: {COLOR_PROFILE_DEFAULT}",
        "Цветовая модель объектов: Process CMYK (без RGB-swatches)",
        f"Комплектация: {source}",
        f"Сцена: {scene_id or '—'}",
        f"Элементов в наборе: {len(include)}",
        "",
        "SWATCHES (C M Y K %):",
    ]
    for name, (c, m, y, k) in BRAND_SWATCHES.items():
        total = c + m + y + k
        flag = " OK" if total <= MAX_TOTAL_INK else " WARN total ink"
        lines.append(f"  {name:20s}  {c:5.1f} {m:5.1f} {y:5.1f} {k:5.1f}  Σ{total:5.1f}%{flag}")
    lines.append("")
    if ink_warns:
        lines.append("ПРЕДУПРЕЖДЕНИЯ TOTAL INK:")
        lines.extend(f"  - {w}" for w in ink_warns)
        lines.append("")
    else:
        lines.append(f"Total ink всех swatches ≤ {MAX_TOTAL_INK:.0f}% — OK")
        lines.append("")

    lines.extend([
        "АВТОПРОВЕРКИ:",
        f"  [{'x' if smoke_ok else ' '}] Smoke INX CS3 (DOMVersion 5.0 / AID PI)",
        "  [x] Space=CMYK у всех Color в ките",
        "",
        "РУЧНЫЕ ШАГИ В INDESIGN CS3:",
        "  1. File → Open → okolica_kit.inx (рядом Fonts/)",
        "  2. Установить HeliosCondC / SchoolBookC / AdventureC",
        "  3. Скопировать сцену/объекты на рабочую полосу",
        "  4. View → Overprint Preview",
        "  5. File → Export / Print → Coated FOGRA39, bleed 3 mm",
        "  6. Фото ≥ 300 dpi; реклама с пометкой «Реклама»",
        "",
        "СОСТАВ НАБОРА:",
    ])
    for eid in include:
        lines.append(f"  - {eid}")
    lines.append("")
    lines.append("Конец чеклиста.")
    return "\n".join(lines)
