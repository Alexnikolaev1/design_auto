"""Форматы печатных полос (газета, таблоид, A4)."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import MM_TO_PT


@dataclass(frozen=True)
class PageFormat:
    id: str
    name: str
    width_mm: float
    height_mm: float
    description: str = ""

    @property
    def width_pt(self) -> float:
        return self.width_mm * MM_TO_PT

    @property
    def height_pt(self) -> float:
        return self.height_mm * MM_TO_PT


PAGE_FORMATS: dict[str, PageFormat] = {
    "okolica": PageFormat(
        id="okolica",
        name="Околица (221.6×288.6 мм)",
        width_mm=221.58,
        height_mm=288.58,
        description="Полоса «Сибирская околица» (выпуск 027); разворот 026 ≈ 2×205×272",
    ),
    "a4": PageFormat(
        id="a4",
        name="A4 (210×297 мм)",
        width_mm=210.0,
        height_mm=297.0,
        description="Стандартный офисный лист, брошюры",
    ),
    "tabloid": PageFormat(
        id="tabloid",
        name="Таблоид (280×430 мм)",
        width_mm=280.0,
        height_mm=430.0,
        description="Газетный таблоид, полоса выпуска",
    ),
    "newspaper_broadsheet": PageFormat(
        id="newspaper_broadsheet",
        name="Газета широкий (315×470 мм)",
        width_mm=315.0,
        height_mm=470.0,
        description="Половина широкоформатной газетной полосы",
    ),
    "custom": PageFormat(
        id="custom",
        name="Свой формат",
        width_mm=221.58,
        height_mm=288.58,
        description="Произвольный размер полосы в миллиметрах",
    ),
}


def get_page_format(fmt_id: str) -> PageFormat:
    return PAGE_FORMATS.get(fmt_id, PAGE_FORMATS["a4"])


def detect_format_from_mm(width_mm: float, height_mm: float, tolerance: float = 25.0) -> str:
    """Подбирает ближайший формат по размерам страницы PDF."""
    best_id = "a4"
    best_diff = float("inf")
    for pf in PAGE_FORMATS.values():
        diff = abs(pf.width_mm - width_mm) + abs(pf.height_mm - height_mm)
        if diff < best_diff:
            best_diff = diff
            best_id = pf.id
    if best_diff > tolerance * 2:
        return "a4"
    return best_id
