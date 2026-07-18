"""
Измеренная геометрия «Сибирская околица» (выпуск 027, полосы 001–003).

Источник: examples/_analysis/report.txt (PyMuPDF).
Все размеры в мм, если не указано иное.
"""
from __future__ import annotations

from dataclasses import dataclass

# Полоса (exact)
PAGE_W = 221.58
PAGE_H = 288.58

# Поля — медиана 002 (exact из report)
MARGIN_L = 18.29
MARGIN_R = 15.68
MARGIN_T = 13.55
MARGIN_B = 14.01
BLEED = 3.0

# Сетка стр.2: сайдбар + 2 текстовые (exact col left-edges [18.49, 87.67, 148.15])
SIDEBAR_W = 61.07
SIDEBAR_GUTTER = 8.11  # 87.67 - 18.49 - 61.07
COL_W = 56.99
COL_GUTTER = 3.49      # 148.15 - 87.67 - 56.99
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# Шапка (002: Times italic «Сибирская» y≈13.6, sz 16.4)
LOGO_W = 52.0
LOGO_H = 11.5
LOGO_SIZE_PT = 16.4
ISSUE_SIZE_PT = 11.0
RUBRIC_SIZE_PT = 14.0
RUBRIC_RULE_W = 0.6
# 001 cover teasers AdventureC 24pt
COVER_TEASER_SIZE_PT = 24.0

# Короткие новости (002: «Короткие» 23.9pt SchoolBook)
NEWS_HEADER_H = 16.0
NEWS_HEADER_SIZE_PT = 23.9
NEWS_CARD_H = 28.0
NEWS_CARD_GAP = 2.5
NEWS_STROKE = 0.75
NEWS_CARDS = 3

# Статья / lead (002: H1 36.9pt at x≈86–92)
LEAD_PHOTO_W = 114.0
LEAD_PHOTO_H = 62.0
PHOTO_STROKE = 0.5
H1_SIZE = 36.9
LEAD_SIZE = 11.0
BODY_SIZE = 9.0
BODY_LEADING = 10.8

# Погода (003: Calibri-Bold «ПРОГНОЗ ПОГОДЫ» ~25.9pt)
WEATHER_HEADER_SIZE_PT = 25.9
WEATHER_BADGE_H = 12.0

# Реклама низ
AD_ROW_H = 42.0
AD_NARROW_W = 55.0
AD_WIDE_W = 120.0
AD_GAP = 3.5

# Декор
WAVE_BORDER_STROKE = 1.25
CORNER_ARM = 6.0


@dataclass(frozen=True)
class RectMm:
    x: float
    y: float
    w: float
    h: float


def content_origin() -> tuple[float, float]:
    return MARGIN_L, MARGIN_T


def sidebar_rect(y: float, h: float) -> RectMm:
    return RectMm(MARGIN_L, y, SIDEBAR_W, h)


def main_cols_x() -> float:
    return MARGIN_L + SIDEBAR_W + SIDEBAR_GUTTER


def two_col_width() -> float:
    return 2 * COL_W + COL_GUTTER


def col2_x() -> float:
    return main_cols_x() + COL_W + COL_GUTTER
