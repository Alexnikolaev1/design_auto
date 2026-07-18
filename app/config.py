"""
Конфигурация LayoutGenius.

Все параметры читаются из переменных окружения (для Railway) с разумными
значениями по умолчанию для локального запуска.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "fonts"
JOBS_DIR = Path(os.environ.get("LG_JOBS_DIR", "/tmp/layoutgenius_jobs"))
JOBS_DIR.mkdir(parents=True, exist_ok=True)
GRID_TEMPLATES_DIR = Path(os.environ.get("LG_GRID_TEMPLATES_DIR", str(JOBS_DIR.parent / "grid_templates")))
GRID_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("LG_MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_IMAGES_PER_JOB = 12
MAX_ARTICLES_PER_JOB = 8
MAX_REFERENCE_PDFS = 3
MAX_PREVIEW_PAGES = int(os.environ.get("LG_MAX_PREVIEW_PAGES", "32"))
PDF_EXPORT_DPI = int(os.environ.get("LG_PDF_DPI", "300"))
JOB_TTL_HOURS = float(os.environ.get("LG_JOB_TTL_HOURS", "48"))

APP_VERSION = "3.3.0"

UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# Бесплатный Gemini: https://aistudio.google.com/apikey
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("LG_GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or ""
)
GEMINI_MODEL = os.environ.get("LG_GEMINI_MODEL", "gemini-2.5-flash")

MM_TO_PT = 72.0 / 25.4
A4_WIDTH_PT = 210 * MM_TO_PT
A4_HEIGHT_PT = 297 * MM_TO_PT

PAGE_FORMAT_IDS = ("okolica", "a4", "tabloid", "newspaper_broadsheet", "custom")

COLOR_PROFILES = [
    "Coated FOGRA39",
    "Uncoated FOGRA29",
    "US Web Coated SWOP v2",
    "Japan Color 2001 Coated",
    "sRGB IEC61966-2.1 (для digital)",
]

LANGUAGES = {
    "ru-RU": "Russian",
    "en-US": "English: USA",
    "de-DE": "German",
    "fr-FR": "French",
}


class TypographyProfile(BaseModel):
    """Профиль типографических настроек, задаваемый пользователем.

    Дефолт — газета «Сибирская околица» (полоса 221.6×288.6 мм, 3 кол., Helios/SchoolBook).
    """

    margin_top_mm: float = 14.0
    margin_bottom_mm: float = 14.0
    margin_inside_mm: float = 18.0
    margin_outside_mm: float = 16.0
    columns_count: int = Field(default=3, ge=1, le=12)
    column_gutter_mm: float = Field(default=3.5, ge=0.0, le=30.0)
    bleed_mm: float = 3.0
    color_profile: str = "Coated FOGRA39"
    print_marks: bool = False
    language: str = "ru-RU"
    hyphenation: bool = True
    auto_stock_images: bool = True
    mark_advertising: bool = True  # пометка «Реклама» у рекламных модулей (требование для СМИ)
    page_format: str = "okolica"  # okolica | a4 | tabloid | newspaper_broadsheet | custom
    facing_pages: bool = False
    heading_starts_new_page: bool = True  # H1 с новой полосы (газетные выпуски)
    jump_lines: bool = True  # «Продолжение на стр. N» при переносе на следующую полосу
    smart_crop: bool = True  # умное кадрирование фото (фокус / горизонт)
    pdf_vector_export: bool = True  # векторный PDF (редактируемый текст)
    # Формат полосы «Околицы» по умолчанию
    custom_page_width_mm: float = Field(default=221.58, ge=0.0, le=600.0)
    custom_page_height_mm: float = Field(default=288.58, ge=0.0, le=900.0)

    # Предпочтительные шрифты (PostScript-имена из каталога /fonts или загруженные)
    font_serif: str = "SchoolBookC"
    font_sans: str = "HeliosCondC"
    font_display: str = "AdventureC"

    # Опциональная корректировка базового кегля (0 = авто по шаблону; Околица уже 9 pt в шаблоне)
    body_size_override_pt: float = Field(default=0.0, ge=0.0, le=24.0)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_margins(cls, data):
        if isinstance(data, dict):
            if "margin_left_mm" in data and "margin_inside_mm" not in data:
                data["margin_inside_mm"] = data["margin_left_mm"]
            if "margin_right_mm" in data and "margin_outside_mm" not in data:
                data["margin_outside_mm"] = data["margin_right_mm"]
        return data

    def margins_pt(self, page_index: int = 0) -> dict[str, float]:
        """InDesign: Inside/Outside → Left/Right (с учётом разворота)."""
        inside = self.margin_inside_mm * MM_TO_PT
        outside = self.margin_outside_mm * MM_TO_PT
        if self.facing_pages and page_index % 2 == 1:
            left, right = outside, inside
        else:
            left, right = inside, outside
        return {
            "top": self.margin_top_mm * MM_TO_PT,
            "bottom": self.margin_bottom_mm * MM_TO_PT,
            "left": left,
            "right": right,
            "inside": inside,
            "outside": outside,
        }

    def margins_mm(self, page_index: int = 0) -> dict[str, float]:
        pt = self.margins_pt(page_index)
        inv = 1.0 / MM_TO_PT
        return {k: round(v * inv, 2) for k, v in pt.items()}

    def bleed_pt(self) -> float:
        return self.bleed_mm * MM_TO_PT

    def page_width_pt(self) -> float:
        from app.layout.page_formats import get_page_format
        if self.page_format == "custom" and self.custom_page_width_mm > 0:
            return self.custom_page_width_mm * MM_TO_PT
        return get_page_format(self.page_format).width_pt

    def page_height_pt(self) -> float:
        from app.layout.page_formats import get_page_format
        if self.page_format == "custom" and self.custom_page_height_mm > 0:
            return self.custom_page_height_mm * MM_TO_PT
        return get_page_format(self.page_format).height_pt

    def page_size_mm(self) -> tuple[float, float]:
        return self.page_width_pt() / MM_TO_PT, self.page_height_pt() / MM_TO_PT

    def indesign_language(self) -> str:
        return LANGUAGES.get(self.language, "Russian")


# Каталог ожидаемых имён файлов (обратная совместимость + Околица)
FONT_CATALOG: dict[str, str] = {
    # Сибирская околица (фирменные)
    "HeliosCondC": "HeliosCondC_0.otf",
    "HeliosCondC-Bold": "HeliosCondC-Bold.otf",
    "HeliosCondC-Italic": "HeliosCondC-Italic_0.otf",
    "HeliosCondC-BoldItalic": "HeliosCondC-BoldItalic_0.otf",
    "SchoolBookC": "SchoolBookC.otf",
    "SchoolBookC-Bold": "SchoolBookC-Bold.otf",
    "SchoolBookC-BoldItalic": "SchoolBookC-BoldItalic.otf",
    "AdventureC": "ADVENTUREC_0.OTF",
    # Свободные запасные
    "PTSerif-Regular": "PTSerif-Regular.ttf",
    "PTSerif-Bold": "PTSerif-Bold.ttf",
    "PTSerif-Italic": "PTSerif-Italic.ttf",
    "PTSans-Regular": "PTSans-Regular.ttf",
    "PTSans-Bold": "PTSans-Bold.ttf",
    "Montserrat-Regular": "Montserrat-Regular.ttf",
    "Montserrat-Bold": "Montserrat-Bold.ttf",
}

FONT_FALLBACK_SYSTEM_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
