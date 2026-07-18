"""
Рекламные форматы «Околицы»: площади, геометрия, прайс-ориентир.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.kit import geometry as geo


@dataclass(frozen=True)
class AdFormat:
    id: str
    name: str
    width_mm: float
    height_mm: float
    area_cm2: float
    price_hint_rub: int  # ориентир для менеджера (редакция правит)
    description: str
    elements: tuple[str, ...]  # kit element ids to include


def _area(w: float, h: float) -> float:
    return round((w * h) / 100.0, 1)


# Ориентиры площади относительно полосы ~221×289 ≈ 640 cm²
AD_FORMATS: list[AdFormat] = [
    AdFormat(
        id="ad_1_8",
        name="1/8 полосы",
        width_mm=geo.AD_NARROW_W,
        height_mm=geo.AD_ROW_H,
        area_cm2=_area(geo.AD_NARROW_W, geo.AD_ROW_H),
        price_hint_rub=2500,
        description="Узкий модуль нижней полосы",
        elements=("styles_pack", "ad_module", "folio_line"),
    ),
    AdFormat(
        id="ad_1_4",
        name="1/4 полосы",
        width_mm=90.0,
        height_mm=70.0,
        area_cm2=_area(90.0, 70.0),
        price_hint_rub=5500,
        description="Четверть полосы — витринный модуль",
        elements=("styles_pack", "ad_module", "ad_module_wide", "folio_line"),
    ),
    AdFormat(
        id="ad_1_2",
        name="1/2 полосы",
        width_mm=geo.CONTENT_W,
        height_mm=120.0,
        area_cm2=_area(geo.CONTENT_W, 120.0),
        price_hint_rub=11000,
        description="Половина полосы по ширине контента",
        elements=("styles_pack", "ad_module_wide", "decor_divider", "folio_line"),
    ),
    AdFormat(
        id="ad_full",
        name="Полоса (1/1)",
        width_mm=geo.CONTENT_W,
        height_mm=geo.PAGE_H - geo.MARGIN_T - geo.MARGIN_B - 10,
        area_cm2=_area(geo.CONTENT_W, geo.PAGE_H - geo.MARGIN_T - geo.MARGIN_B - 10),
        price_hint_rub=22000,
        description="Почти целая полоса под рекламу",
        elements=("styles_pack", "ad_module_wide", "folio_line"),
    ),
    AdFormat(
        id="ad_banner_bottom",
        name="Баннер низ",
        width_mm=geo.AD_WIDE_W,
        height_mm=geo.AD_ROW_H,
        area_cm2=_area(geo.AD_WIDE_W, geo.AD_ROW_H),
        price_hint_rub=4500,
        description="Широкий нижний баннер",
        elements=("styles_pack", "ad_module_wide", "folio_line"),
    ),
    AdFormat(
        id="ad_row",
        name="Ряд (узкий+широкий)",
        width_mm=geo.AD_NARROW_W + geo.AD_GAP + geo.AD_WIDE_W,
        height_mm=geo.AD_ROW_H,
        area_cm2=_area(geo.AD_NARROW_W + geo.AD_GAP + geo.AD_WIDE_W, geo.AD_ROW_H),
        price_hint_rub=7000,
        description="Как scene_ads_bottom — два модуля в ряд",
        elements=("styles_pack", "decor_divider", "ad_module", "ad_module_wide", "folio_line"),
    ),
]


def get_ad_format(fmt_id: str) -> AdFormat | None:
    for f in AD_FORMATS:
        if f.id == fmt_id:
            return f
    return None


def list_ad_formats() -> list[dict]:
    return [
        {
            "id": f.id,
            "name": f.name,
            "width_mm": f.width_mm,
            "height_mm": f.height_mm,
            "area_cm2": f.area_cm2,
            "price_hint_rub": f.price_hint_rub,
            "description": f.description,
            "elements": list(f.elements),
        }
        for f in AD_FORMATS
    ]


def format_ad_rate_card() -> str:
    lines = [
        "ОКОЛИЦА — РЕКЛАМНЫЕ ФОРМАТЫ (ориентир для менеджера)",
        "=" * 56,
        f"{'ID':20s} {'Название':22s} {'мм':14s} {'см²':7s} {'₽':>7s}",
        "-" * 56,
    ]
    for f in AD_FORMATS:
        size = f"{f.width_mm:.0f}×{f.height_mm:.0f}"
        lines.append(
            f"{f.id:20s} {f.name:22s} {size:14s} {f.area_cm2:6.1f} {f.price_hint_rub:7d}"
        )
    lines.extend([
        "",
        "Цены — ориентир; финальный прайс задаёт редакция.",
        "Все модули: пометка «Реклама», Process CMYK, без RGB.",
        "В INX: Object Style «Kit Ad Module», слой Ads.",
    ])
    return "\n".join(lines)
