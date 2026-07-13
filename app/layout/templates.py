"""Библиотека шаблонов вёрстки с поддержкой пользовательских шрифтов."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from app.config import TypographyProfile
from app.layout import fonts as font_manager


@dataclass
class TemplateSpec:
    id: str
    name: str
    description: str
    columns: int
    gutter_mm: float
    body_font: str
    body_font_bold: str
    body_font_italic: str
    heading_font: str
    heading_font_bold: str
    body_size_pt: float
    body_leading_pt: float
    h_size_pt: dict[int, float]
    image_strategy: str
    accent_style: str
    font_role: str  # serif | sans | mixed


TEMPLATES: list[TemplateSpec] = [
    TemplateSpec(
        id="classic-book",
        name="Классическая книжная",
        description="Одна широкая колонка, антиква, спокойный ритм — "
                     "для длинного повествовательного текста и художественной прозы.",
        columns=1, gutter_mm=5,
        body_font="PTSerif-Regular", body_font_bold="PTSerif-Bold",
        body_font_italic="PTSerif-Italic",
        heading_font="PTSerif-Bold", heading_font_bold="PTSerif-Bold",
        body_size_pt=10.5, body_leading_pt=14.5,
        h_size_pt={1: 26, 2: 20, 3: 15, 4: 12.5},
        image_strategy="full_width", accent_style="rule", font_role="serif",
    ),
    TemplateSpec(
        id="editorial-two-col",
        name="Журнальная двухколоночная",
        description="Две колонки, гротеск в заголовках + антиква в тексте, "
                     "цветные плашки-акценты — для статей и лонгридов.",
        columns=2, gutter_mm=6,
        body_font="PTSerif-Regular", body_font_bold="PTSerif-Bold",
        body_font_italic="PTSerif-Italic",
        heading_font="PTSans-Bold", heading_font_bold="PTSans-Bold",
        body_size_pt=9.5, body_leading_pt=13,
        h_size_pt={1: 22, 2: 17, 3: 13, 4: 11},
        image_strategy="column_span", accent_style="tint_block", font_role="mixed",
    ),
    TemplateSpec(
        id="modern-grid",
        name="Модернистская сетка",
        description="Три узкие колонки, гротеск, много воздуха — "
                     "строгий швейцарский стиль для каталогов и брошюр.",
        columns=3, gutter_mm=5,
        body_font="PTSans-Regular", body_font_bold="PTSans-Bold",
        body_font_italic="PTSans-Regular",
        heading_font="Montserrat-Bold", heading_font_bold="Montserrat-Bold",
        body_size_pt=8.5, body_leading_pt=12,
        h_size_pt={1: 19, 2: 15, 3: 11.5, 4: 10},
        image_strategy="float_side", accent_style="rule", font_role="sans",
    ),
    TemplateSpec(
        id="report-formal",
        name="Деловой отчёт",
        description="Одна колонка с широкими полями, чёткая иерархия заголовков — "
                     "для официальных документов, отчётов и презентаций.",
        columns=1, gutter_mm=0,
        body_font="PTSans-Regular", body_font_bold="PTSans-Bold",
        body_font_italic="PTSans-Regular",
        heading_font="PTSans-Bold", heading_font_bold="PTSans-Bold",
        body_size_pt=10, body_leading_pt=14,
        h_size_pt={1: 20, 2: 16, 3: 12.5, 4: 11},
        image_strategy="full_width", accent_style="none", font_role="sans",
    ),
    TemplateSpec(
        id="magazine-mix",
        name="Смешанная журнальная",
        description="Две колонки с акцентными буквицами и крупными фото — "
                     "для контента с большим числом иллюстраций.",
        columns=2, gutter_mm=7,
        body_font="PTSerif-Regular", body_font_bold="PTSerif-Bold",
        body_font_italic="PTSerif-Italic",
        heading_font="Montserrat-Bold", heading_font_bold="Montserrat-Bold",
        body_size_pt=9.5, body_leading_pt=13.5,
        h_size_pt={1: 24, 2: 18, 3: 13.5, 4: 11},
        image_strategy="column_span", accent_style="tint_block", font_role="mixed",
    ),
    TemplateSpec(
        id="promo-ads",
        name="Рекламный буклет",
        description="Промо-полосы и баннеры на всю ширину страницы — "
                     "для брошюр, каталогов и рекламных вставок.",
        columns=1, gutter_mm=0,
        body_font="PTSans-Regular", body_font_bold="PTSans-Bold",
        body_font_italic="PTSans-Regular",
        heading_font="Montserrat-Bold", heading_font_bold="Montserrat-Bold",
        body_size_pt=10, body_leading_pt=13.5,
        h_size_pt={1: 22, 2: 17, 3: 13, 4: 11},
        image_strategy="banner_strip", accent_style="tint_block", font_role="sans",
    ),
]


def _bold_variant(ps: str) -> str:
    if "-Regular" in ps:
        return ps.replace("-Regular", "-Bold")
    if "-Italic" in ps:
        return ps.replace("-Italic", "-BoldItalic")
    base = ps.rsplit("-", 1)[0] if "-" in ps else ps
    resolved = font_manager.resolve_variant(base, bold=True)
    return resolved.postscript_name


def _italic_variant(ps: str) -> str:
    if "-Regular" in ps:
        return ps.replace("-Regular", "-Italic")
    base = ps.rsplit("-", 1)[0] if "-" in ps else ps
    resolved = font_manager.resolve_variant(base, italic=True)
    return resolved.postscript_name


def apply_profile_layout(template: TemplateSpec, profile: TypographyProfile) -> TemplateSpec:
    """Подставляет колонки и интервал из профиля (как в InDesign)."""
    t = copy.deepcopy(template)
    t.columns = profile.columns_count
    t.gutter_mm = profile.column_gutter_mm
    return t


def apply_user_fonts(template: TemplateSpec, profile: TypographyProfile) -> TemplateSpec:
    """Подставляет пользовательские шрифты в шаблон."""
    t = copy.deepcopy(template)
    serif = profile.font_serif
    sans = profile.font_sans
    display = profile.font_display

    if t.font_role == "serif":
        body = font_manager.pick_font_for_role("serif", serif, sans, display, t.body_font)
        t.body_font = body
        t.body_font_bold = _bold_variant(body)
        t.body_font_italic = _italic_variant(body)
        t.heading_font = t.body_font_bold
        t.heading_font_bold = t.body_font_bold
    elif t.font_role == "sans":
        body = font_manager.pick_font_for_role("sans", serif, sans, display, t.body_font)
        t.body_font = body
        t.body_font_bold = _bold_variant(body)
        t.body_font_italic = _italic_variant(body)
        t.heading_font = t.body_font_bold
        t.heading_font_bold = t.body_font_bold
    elif t.font_role == "mixed":
        body = font_manager.pick_font_for_role("serif", serif, sans, display, t.body_font)
        head = font_manager.pick_font_for_role("display", serif, sans, display, t.heading_font)
        t.body_font = body
        t.body_font_bold = _bold_variant(body)
        t.body_font_italic = _italic_variant(body)
        t.heading_font = head
        t.heading_font_bold = _bold_variant(head)
    else:
        body = font_manager.pick_font_for_role("sans", serif, sans, display, t.body_font)
        t.body_font = body
        t.body_font_bold = _bold_variant(body)

    if profile.body_size_override_pt > 0:
        ratio = profile.body_size_override_pt / t.body_size_pt
        t.body_size_pt = profile.body_size_override_pt
        t.body_leading_pt = round(t.body_leading_pt * ratio, 1)
        t.h_size_pt = {k: round(v * ratio, 1) for k, v in t.h_size_pt.items()}

    return t


def select_templates(word_count: int, image_count: int,
                     profile: TypographyProfile | None = None,
                     banner_count: int = 0) -> list[TemplateSpec]:
    picked = copy.deepcopy(TEMPLATES)

    # Всегда 5 вариантов: при наличии баннеров заменяем «Деловой отчёт» на «Рекламный буклет»
    if banner_count > 0:
        picked = [t for t in picked if t.id != "report-formal"]
        promo = next((t for t in TEMPLATES if t.id == "promo-ads"), None)
        if promo and not any(t.id == "promo-ads" for t in picked):
            picked.append(copy.deepcopy(promo))
    else:
        picked = [t for t in picked if t.id != "promo-ads"]

    picked = picked[:5]

    for t in picked:
        if word_count > 6000:
            t.body_size_pt = round(t.body_size_pt - 0.4, 1)
            t.body_leading_pt = round(t.body_leading_pt - 0.5, 1)
        elif word_count < 800:
            t.body_size_pt = round(t.body_size_pt + 0.6, 1)
            t.body_leading_pt = round(t.body_leading_pt + 0.8, 1)

        if image_count == 0 and t.image_strategy == "float_side":
            t.image_strategy = "full_width"

    if profile:
        return [apply_profile_layout(apply_user_fonts(t, profile), profile) for t in picked]
    return picked
