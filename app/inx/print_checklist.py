"""Чеклист готовности к печати: автоматические проверки + ручные шаги InDesign CS3."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import TypographyProfile


@dataclass
class CheckItem:
    id: str
    category: str
    title: str
    status: str  # pass | warn | fail | manual
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class PrintChecklist:
    items: list[CheckItem] = field(default_factory=list)
    ready_for_print: bool = False

    def to_dict(self) -> dict:
        counts = {"pass": 0, "warn": 0, "fail": 0, "manual": 0}
        for it in self.items:
            counts[it.status] = counts.get(it.status, 0) + 1
        auto_fail = any(i.status == "fail" for i in self.items if i.category != "manual")
        return {
            "ready_for_print": self.ready_for_print and not auto_fail,
            "counts": counts,
            "items": [i.to_dict() for i in self.items],
        }


def _manual_cs3_steps() -> list[CheckItem]:
    return [
        CheckItem("m1", "manual", "Открыть layout.inx в InDesign CS3",
                  "manual", "File → Open, папки Links и Fonts рядом с INX"),
        CheckItem("m2", "manual", "Панель Links — без «missing»",
                  "manual", "Window → Links, все изображения Connected"),
        CheckItem("m3", "manual", "Preflight в InDesign",
                  "manual", "Window → Preflight, 0 ошибок для печати"),
        CheckItem("m4", "manual", "Проверить обтекание и рекламные модули",
                  "manual", "Текст не залезает под рекламу, пометка «Реклама» на месте"),
        CheckItem("m5", "manual", "Экспорт PDF High Quality Print",
                  "manual", "File → Adobe PDF Presets → High Quality Print, bleed включён"),
    ]


def build_print_checklist(
    profile: TypographyProfile,
    smoke: dict | None,
    inx_error: str | None,
    image_paths: list[Path],
    page_count: int,
    font_warnings: list[str],
    ad_slot_report: dict | None = None,
) -> PrintChecklist:
    items: list[CheckItem] = []

    if inx_error:
        items.append(CheckItem("inx_struct", "automated", "Структура INX", "fail", inx_error))
    elif smoke and smoke.get("passed"):
        items.append(CheckItem("inx_struct", "automated", "Структура INX (smoke CS3)", "pass",
                               f"{smoke.get('stats', {}).get('pages', '?')} полос"))
    elif smoke:
        items.append(CheckItem("inx_struct", "automated", "Структура INX", "fail",
                               "; ".join(smoke.get("errors") or [])))
    else:
        items.append(CheckItem("inx_struct", "automated", "Структура INX", "warn", "Smoke не выполнялся"))

    for w in (smoke or {}).get("warnings") or []:
        items.append(CheckItem(f"inx_w_{len(items)}", "automated", "INX предупреждение", "warn", w))

    items.append(CheckItem(
        "page_count", "automated", "Пагинация",
        "pass" if page_count >= 1 else "fail",
        f"{page_count} полос в макете",
    ))

    items.append(CheckItem(
        "bleed", "automated", "Вылеты (bleed)",
        "pass" if profile.bleed_mm >= 3 else "warn",
        f"{profile.bleed_mm} мм",
    ))

    low_dpi = []
    for p in image_paths:
        try:
            from PIL import Image as PILImage
            with PILImage.open(p) as im:
                dpi = im.info.get("dpi", (72, 72))
                if dpi[0] < 200:
                    low_dpi.append(p.name)
        except Exception:
            low_dpi.append(p.name)
    if not image_paths:
        items.append(CheckItem("images", "automated", "Изображения", "pass", "Нет связанных файлов"))
    elif low_dpi:
        items.append(CheckItem("images", "automated", "DPI изображений", "warn",
                               f"Низкое DPI: {', '.join(low_dpi[:5])}"))
    else:
        items.append(CheckItem("images", "automated", "DPI изображений", "pass",
                               f"{len(image_paths)} файлов ≥200 DPI"))

    if font_warnings:
        items.append(CheckItem("fonts", "automated", "Шрифты", "warn", "; ".join(font_warnings[:3])))
    else:
        items.append(CheckItem("fonts", "automated", "Шрифты", "pass", "Все PostScript-имена найдены"))

    if profile.hyphenation:
        items.append(CheckItem("hyphenation", "automated", "Переносы", "pass", profile.language))
    else:
        items.append(CheckItem("hyphenation", "automated", "Переносы", "warn", "Выключены — риск разрывов строк"))

    if ad_slot_report and ad_slot_report.get("total_slots"):
        empty = ad_slot_report.get("empty_slots", 0)
        st = "pass" if empty == 0 else "warn"
        items.append(CheckItem(
            "ad_slots", "automated", "Рекламная сетка",
            st, f"занято {ad_slot_report.get('used_slots', 0)}/{ad_slot_report.get('total_slots', 0)}",
        ))

    items.extend(_manual_cs3_steps())

    auto_fail = any(i.status == "fail" for i in items if i.category != "manual")
    checklist = PrintChecklist(items=items, ready_for_print=not auto_fail)
    return checklist


def format_checklist_text(checklist: PrintChecklist) -> str:
    lines = [
        "LAYOUTGENIUS — ЧЕКЛИСТ ПЕЧАТИ (InDesign CS3)",
        "=" * 48,
        f"Готовность (авто): {'ДА' if checklist.ready_for_print else 'НЕТ — исправьте FAIL'}",
        "",
    ]
    cur_cat = ""
    icons = {"pass": "[OK]", "warn": "[!!]", "fail": "[XX]", "manual": "[  ]"}
    for it in checklist.items:
        if it.category != cur_cat:
            cur_cat = it.category
            title = {"automated": "АВТОМАТИЧЕСКИЕ ПРОВЕРКИ",
                     "manual": "РУЧНЫЕ ШАГИ В INDESIGN CS3"}.get(cur_cat, cur_cat.upper())
            lines += ["", title, "-" * 40]
        lines.append(f"  {icons.get(it.status, '[?]')} {it.title}")
        if it.detail:
            lines.append(f"      {it.detail}")
    lines += [
        "",
        "После всех [  ] в InDesign — макет готов к сдаче в печать.",
    ]
    return "\n".join(lines)
