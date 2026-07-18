"""
Эталонный профиль газеты «Сибирская околица» по PDF-образцам в examples/.

Источник: выпуск №27 (1313) от 15 июля 2026.
Измерено по полосам 001–008, 025–032 (PyMuPDF + визуальный разбор).

Источник: выпуски №26–27 (PDF в examples/, в т.ч. Okolica_026.pdf — 17 полос/разворотов).
Шрифты лежат в fonts/ (HeliosCondC, SchoolBookC, AdventureC).

Замечания по 026:
- обложка 205×272 мм; внутренние развороты 410×272 (= 2 полосы);
- фото: 60–125 мм ширина, lead ~100–120 мм; рамка тонкая;
- шаблон MVP использует полосу 221.6×288.6 мм (выпуск 027 постранично).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- Геометрия полосы ---
PAGE_WIDTH_MM = 221.58
PAGE_HEIGHT_MM = 288.58
PAGE_FORMAT_ID = "okolica"

# Поля (медиана по текстовым полосам 002 — examples/_analysis/report.txt)
MARGIN_TOP_MM = 13.55
MARGIN_BOTTOM_MM = 14.01
MARGIN_INSIDE_MM = 18.29
MARGIN_OUTSIDE_MM = 15.68
BLEED_MM = 3.0

# Базовая сетка внутренней полосы (стр. 2: col left-edges 18.49 / 87.67 / 148.15)
COLUMNS_COUNT = 3
COLUMN_GUTTER_MM = 3.49
SIDEBAR_WIDTH_MM = 61.07
SIDEBAR_GUTTER_MM = 8.11
TEXT_COLUMN_WIDTH_MM = 56.99

# --- Типографика (факт из PDF) ---
BODY_SIZE_PT = 9.0
BODY_LEADING_PT = 10.8
H1_SIZE_PT = 36.9          # главный заголовок полосы (красный SchoolBook, 002)
H2_SIZE_PT = 26.0          # вторичный / блочный заголовок
H3_SIZE_PT = 14.0          # рубрика / kicker (Adventure / cursive)
LEAD_SIZE_PT = 11.0        # лид (жирный, на ширину 2 кол.)
NEWS_HEADER_SIZE_PT = 23.9
LOGO_SIZE_PT = 16.4
WEATHER_HEADER_SIZE_PT = 25.9
COVER_TEASER_SIZE_PT = 24.0

# Цвета акцентов (RGB приближённо с полосы)
ACCENT_HEADLINE_RGB = (196, 30, 30)   # красный заголовок
ACCENT_SIDEBAR_RGB = (230, 120, 40)   # оранж «Короткие новости»
ACCENT_LOGO_RGB = (140, 40, 140)      # фиолетовый логотип
ACCENT_WEATHER_RGB = (40, 160, 170)   # бирюза погоды

# --- Роли шрифтов (файлы в fonts/) ---
FONT_BODY = "HeliosCondC"              # основной текст, ~90% объёма
FONT_BODY_BOLD = "HeliosCondC-Bold"
FONT_BODY_ITALIC = "HeliosCondC-Italic"
FONT_HEADLINE = "SchoolBookC-Bold"     # H1/H2 красные заголовки
FONT_HEADLINE_REGULAR = "SchoolBookC"
FONT_RUBRIC = "AdventureC"             # рубрики, тизеры на обложке
FONT_LOGO = "TimesNewRomanPS-BoldItalicMT"  # «Сибирская» в шапке (системный fallback)
FONT_DISPLAY_BLACK = "HeliosCondBlackC"
FONT_UI_BOLD = "Calibri-Bold"          # плашки вроде «ПРОГНОЗ ПОГОДЫ»

# Запасные, если фирменный файл отсутствует
FONT_FALLBACK = {
    "HeliosCondC": "PTSans-Regular",
    "HeliosCondC-Bold": "PTSans-Bold",
    "HeliosCondC-Italic": "PTSans-Regular",
    "SchoolBookC": "PTSerif-Regular",
    "SchoolBookC-Bold": "PTSerif-Bold",
    "SchoolBookC-Italic": "PTSerif-Italic",
    "SchoolBookC-BoldItalic": "PTSerif-Bold",
    "AdventureC": "PTSerif-Italic",
    "GaramondC": "PTSerif-Regular",
    "Calibri-Bold": "PTSans-Bold",
    "HeliosCondBlackC": "Montserrat-Bold",
}


@dataclass
class PageZone:
    """Зона макета на внутренней полосе."""
    id: str
    name: str
    description: str


# Типовые зоны (не координаты каждого выпуска, а роли)
PAGE_ZONES: list[PageZone] = [
    PageZone("masthead", "Шапка", "Логотип слева, номер/дата по центру, рубрика справа"),
    PageZone("sidebar", "Лента коротких", "«Короткие новости» — оранжевая шапка + карточки"),
    PageZone("kicker", "Рубрика", "Курсив/скрипт над заголовком (AdventureC ~14 pt)"),
    PageZone("headline", "Заголовок", "Крупный красный SchoolBook Bold 26–38 pt"),
    PageZone("lead_photo", "Главное фото", "Горизонтальный кадр под/рядом с заголовком"),
    PageZone("lead", "Лид", "Жирный абзац на ширину 1–2 колонок"),
    PageZone("body", "Текст", "Helios Cond 9/10.8, выключка, переносы"),
    PageZone("ads_row", "Рекламный ряд", "Низ полосы: 1–3 модуля"),
    PageZone("folio", "Колонтитул", "Номер страницы + юр. строка внизу"),
]


COVER_ZONES: list[PageZone] = [
    PageZone("cover_photo", "Фото обложки", "Full-bleed фото на всю полосу"),
    PageZone("cover_logo", "Логотип", "Скриптовый логотип сверху"),
    PageZone("cover_teasers", "Тизеры", "AdventureC: тема + «Стр. N»"),
    PageZone("cover_issue", "Выходные данные", "Вертикально: № выпуска / дата"),
]


@dataclass
class OkolicaProfile:
    """Готовый пакет для TypographyProfile + TemplateSpec."""
    name: str = "Сибирская околица"
    page_width_mm: float = PAGE_WIDTH_MM
    page_height_mm: float = PAGE_HEIGHT_MM
    margin_top_mm: float = MARGIN_TOP_MM
    margin_bottom_mm: float = MARGIN_BOTTOM_MM
    margin_inside_mm: float = MARGIN_INSIDE_MM
    margin_outside_mm: float = MARGIN_OUTSIDE_MM
    columns_count: int = COLUMNS_COUNT
    column_gutter_mm: float = COLUMN_GUTTER_MM
    body_size_pt: float = BODY_SIZE_PT
    body_leading_pt: float = BODY_LEADING_PT
    h_size_pt: dict[int, float] = field(default_factory=lambda: {
        1: H1_SIZE_PT, 2: H2_SIZE_PT, 3: H3_SIZE_PT, 4: 11.0,
    })
    preferred_template_id: str = "okolica-news"
    source_issue: str = "№27 (1313) / 15 июля 2026"
    source_dir: str = "examples/"


def to_typography_defaults() -> dict:
    """Словарь для TypographyProfile(**...)."""
    return {
        "page_format": PAGE_FORMAT_ID,
        "custom_page_width_mm": PAGE_WIDTH_MM,
        "custom_page_height_mm": PAGE_HEIGHT_MM,
        "margin_top_mm": MARGIN_TOP_MM,
        "margin_bottom_mm": MARGIN_BOTTOM_MM,
        "margin_inside_mm": MARGIN_INSIDE_MM,
        "margin_outside_mm": MARGIN_OUTSIDE_MM,
        "bleed_mm": BLEED_MM,
        "columns_count": COLUMNS_COUNT,
        "column_gutter_mm": COLUMN_GUTTER_MM,
        "body_size_override_pt": 0.0,  # кегль задан в шаблоне okolica-news
        "font_serif": FONT_HEADLINE_REGULAR,
        "font_sans": FONT_BODY,
        "font_display": FONT_RUBRIC,
        "language": "ru-RU",
        "hyphenation": True,
        "facing_pages": False,
        "heading_starts_new_page": True,
        "jump_lines": True,
        "mark_advertising": True,
    }
