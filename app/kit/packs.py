"""
Действия помощника дизайнеру: понятные кнопки + что приложить.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignerPack:
    id: str
    # Короткая кнопка: «Создать узор»
    action: str
    name: str
    description: str
    # Что нужно от дизайнера (наглядно в UI)
    needs: str
    needs_hint: str  # короче для карточки
    elements: tuple[str, ...]
    ad_format_id: str | None = None
    icon: str = "◆"
    category: str = "mix"
    # Нужна ли подпись в поле до генерации
    wants_caption: bool = False
    # Нужно ли потом Place фото в CS3
    wants_photo_in_cs3: bool = False
    primary: bool = True  # показывать крупной кнопкой


DESIGNER_PACKS: list[DesignerPack] = [
    DesignerPack(
        id="pack_decor",
        action="Создать узор",
        name="Узор и орнамент",
        description="Уголки, волнистый бордюр, линии-разделители — векторный декор Околицы",
        needs="Ничего прикладывать не нужно. Подпись для бордюра — по желанию (например «В эти дни»).",
        needs_hint="Ничего не нужно · подпись по желанию",
        elements=("styles_pack", "decor_corners", "decor_wave_border", "decor_rule", "decor_divider"),
        icon="✦",
        category="decor",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_backdrop",
        action="Создать подложку",
        name="Красивая подложка",
        description="Цветная плашка-подложка с волнистой рамкой под врезку или цитату",
        needs="Ничего не нужно. По желанию — короткий текст на подложке.",
        needs_hint="Ничего не нужно · текст по желанию",
        elements=("styles_pack", "decor_wave_border", "decor_corners"),
        icon="◈",
        category="decor",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_banner_wide",
        action="Создать баннер",
        name="Рекламный баннер",
        description="Широкий слот с пометкой «Реклама» — пустая форма под макет рекламы",
        needs="Ничего не нужно. Макет рекламы (картинку/текст) вставите сами в CS3.",
        needs_hint="Ничего · рекламу вставите в CS3",
        elements=("styles_pack", "ad_module_wide", "folio_line"),
        ad_format_id="ad_banner_bottom",
        icon="▬",
        category="ads",
        wants_caption=False,
    ),
    DesignerPack(
        id="pack_banner_row",
        action="Создать ряд баннеров",
        name="Два рекламных модуля",
        description="Узкий + широкий слот в ряд (низ полосы)",
        needs="Ничего не нужно. Содержимое рекламы — в CS3 (Place / свой текст).",
        needs_hint="Ничего · контент в CS3",
        elements=("styles_pack", "decor_divider", "ad_module", "ad_module_wide", "folio_line"),
        ad_format_id="ad_row",
        icon="▭",
        category="ads",
    ),
    DesignerPack(
        id="pack_ad_quarter",
        action="Создать рекламу 1/4",
        name="Модуль ¼ полосы",
        description="Витринный рекламный прямоугольник под объявление",
        needs="Ничего не нужно. Готовый макет рекламы положите в фрейм в CS3.",
        needs_hint="Ничего · макет в CS3",
        elements=("styles_pack", "ad_module", "ad_module_wide", "folio_line"),
        ad_format_id="ad_1_4",
        icon="□",
        category="ads",
    ),
    DesignerPack(
        id="pack_masthead",
        action="Создать шапку",
        name="Шапка газеты",
        description="Фирменная плашка логотипа + слот номера/даты + линия рубрики",
        needs="По желанию: название / «№ … / дата». Иначе будут плейсхолдеры.",
        needs_hint="По желанию: название и дата",
        elements=("styles_pack", "masthead_logo", "masthead_issue", "masthead_rubric_line"),
        icon="▤",
        category="masthead",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_photo",
        action="Создать рамку фото",
        name="Рамка под иллюстрацию",
        description="Горизонтальный кадр с обводкой и text-wrap",
        needs="После открытия в CS3: File → Place — ваше фото (≥300 dpi, CMYK).",
        needs_hint="В CS3: Place своё фото",
        elements=("styles_pack", "article_photo_frame", "decor_corners"),
        icon="▣",
        category="frames",
        wants_photo_in_cs3=True,
    ),
    DesignerPack(
        id="pack_weather",
        action="Создать плашку погоды",
        name="Плашка «Прогноз погоды»",
        description="Бирюзовая шапка в духе полосы Околицы",
        needs="По желанию: текст прогноза. Иначе — «ПРОГНОЗ ПОГОДЫ».",
        needs_hint="По желанию: текст прогноза",
        elements=("styles_pack", "weather_badge"),
        icon="☁",
        category="news",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_shorts",
        action="Создать карточки новостей",
        name="Блок коротких новостей",
        description="Оранжевая шапка + 3 пустые карточки под ваш текст",
        needs="Текст писать не обязательно здесь — впишете в CS3. По желанию — заголовок блока.",
        needs_hint="Текст в CS3 · заголовок по желанию",
        elements=("styles_pack", "news_header", "news_card"),
        icon="☰",
        category="news",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_teasers",
        action="Создать тизеры обложки",
        name="Тизеры на обложку",
        description="Строки AdventureC «тема + Стр. N» с уголками",
        needs="По желанию: темы через запятую. Иначе — плейсхолдеры.",
        needs_hint="По желанию: темы через запятую",
        elements=("styles_pack", "masthead_logo", "cover_teaser", "decor_corners"),
        icon="✧",
        category="masthead",
        wants_caption=True,
    ),
    DesignerPack(
        id="pack_styles",
        action="Создать пакет стилей",
        name="Только стили",
        description="Paragraph / Character / Object styles без декоративных объектов",
        needs="Ничего не нужно.",
        needs_hint="Ничего не нужно",
        elements=("styles_pack",),
        icon="Aa",
        category="styles",
        primary=False,
    ),
]


def get_pack(pack_id: str) -> DesignerPack | None:
    for p in DESIGNER_PACKS:
        if p.id == pack_id:
            return p
    return None


def list_packs() -> list[dict]:
    return [
        {
            "id": p.id,
            "action": p.action,
            "name": p.name,
            "description": p.description,
            "needs": p.needs,
            "needs_hint": p.needs_hint,
            "elements": list(p.elements),
            "ad_format_id": p.ad_format_id,
            "icon": p.icon,
            "category": p.category,
            "wants_caption": p.wants_caption,
            "wants_photo_in_cs3": p.wants_photo_in_cs3,
            "primary": p.primary,
        }
        for p in DESIGNER_PACKS
    ]
