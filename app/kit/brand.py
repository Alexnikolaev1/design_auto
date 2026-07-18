"""
BrandKit «Сибирская околица»: Process CMYK swatches + каталог элементов.

Цвета зафиксированы в CMYK % для типографии (не выводятся из RGB в рантайме).
Геометрия ориентирована на полосу 221.6×288.6 мм (выпуск 027).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# Process CMYK 0–100 (именованные swatches для INX Space="CMYK")
BRAND_SWATCHES: dict[str, tuple[float, float, float, float]] = {
    "Black": (0.0, 0.0, 0.0, 100.0),
    "Paper": (0.0, 0.0, 0.0, 0.0),
    "OkolicaRed": (15.0, 95.0, 90.0, 5.0),       # заголовки
    "OkolicaOrange": (0.0, 55.0, 85.0, 0.0),     # короткие новости
    "OkolicaOrangeTint": (0.0, 12.0, 22.0, 0.0), # заливка карточек
    "OkolicaPurple": (45.0, 80.0, 0.0, 15.0),    # лого / шапка
    "OkolicaTeal": (75.0, 10.0, 25.0, 5.0),      # погода / плашки
    "OkolicaGray": (0.0, 0.0, 0.0, 45.0),        # подписи / folio
}

COLOR_PROFILE_DEFAULT = "Coated FOGRA39"
MAX_TOTAL_INK = 300.0  # % (FOGRA-ориентир для coated)


@dataclass(frozen=True)
class KitElement:
    id: str
    name: str
    category: str  # styles | masthead | news | article | decor | ads
    description: str
    default_include: bool = True
    tags: tuple[str, ...] = ()


ELEMENT_CATALOG: list[KitElement] = [
    KitElement("styles_pack", "Пакет стилей", "styles",
               "Заголовок 1–3, Лид, Основной, Рубрика, Подпись, Реклама",
               tags=("styles", "типографика")),
    KitElement("masthead_logo", "Шапка: логотип", "masthead",
               "Фиолетовая плашка «Сибирская околица»",
               tags=("шапка", "лого")),
    KitElement("masthead_issue", "Шапка: номер и дата", "masthead",
               "Слот № выпуска / дата",
               tags=("шапка", "дата")),
    KitElement("masthead_rubric_line", "Шапка: линия рубрики", "masthead",
               "Подчёркнутая рубрика справа",
               tags=("шапка", "рубрика")),
    KitElement("news_header", "Короткие новости: шапка", "news",
               "Оранжевая плашка с заголовком",
               tags=("новости", "сайдбар")),
    KitElement("news_card", "Короткие новости: карточка", "news",
               "Карточка с оранжевой обводкой (×3 в каталоге)",
               tags=("новости", "карточка")),
    KitElement("article_kicker", "Рубрика (kicker)", "article",
               "AdventureC над заголовком",
               tags=("рубрика", "статья")),
    KitElement("article_headline", "Заголовок H1", "article",
               "Красный SchoolBook плейсхолдер",
               tags=("заголовок", "статья")),
    KitElement("article_lead", "Лид", "article",
               "Жирный лид на 2 колонки",
               tags=("лид", "статья")),
    KitElement("article_photo_frame", "Рамка фото", "article",
               "Горизонтальный кадр 0.5 pt Black",
               tags=("фото", "рамка")),
    KitElement("article_column", "Колонка текста", "article",
               "Образец набора Helios Cond 9/10.8",
               tags=("текст", "колонка")),
    KitElement("decor_rule", "Разделитель (rule)", "decor",
               "Горизонтальная линия",
               tags=("декор", "линия")),
    KitElement("decor_corners", "Уголки", "decor",
               "Четыре угловых L-элемента",
               tags=("декор", "угол")),
    KitElement("decor_wave_border", "Волнистый бордюр", "decor",
               "Рамка в духе блока «В эти дни»",
               tags=("декор", "бордюр")),
    KitElement("decor_divider", "Разделитель блоков", "decor",
               "Двойная линия между материалами",
               tags=("декор", "разделитель")),
    KitElement("ad_module", "Рекламный модуль", "ads",
               "Слот с пометкой «Реклама»",
               tags=("реклама",)),
    KitElement("ad_module_wide", "Реклама широкая", "ads",
               "Широкий модуль нижней полосы",
               tags=("реклама", "баннер"),
               default_include=True),
    KitElement("weather_badge", "Плашка погоды", "news",
               "Бирюзовая шапка «Прогноз погоды»",
               tags=("погода",),
               default_include=False),
    KitElement("cover_teaser", "Тизеры обложки", "masthead",
               "Три строки AdventureC: тема + Стр. N",
               tags=("обложка", "тизер"),
               default_include=False),
    KitElement("folio_line", "Колонтитул / folio", "decor",
               "Номер полосы + юр. строка",
               tags=("folio", "низ"),
               default_include=True),
]


def list_element_ids() -> list[str]:
    return [e.id for e in ELEMENT_CATALOG]


def get_element(element_id: str) -> KitElement | None:
    for e in ELEMENT_CATALOG:
        if e.id == element_id:
            return e
    return None


def default_include_ids() -> list[str]:
    return [e.id for e in ELEMENT_CATALOG if e.default_include]


def catalog_as_dicts() -> list[dict]:
    return [
        {
            "id": e.id,
            "name": e.name,
            "category": e.category,
            "description": e.description,
            "default_include": e.default_include,
            "tags": list(e.tags),
        }
        for e in ELEMENT_CATALOG
    ]


def total_ink(c: float, m: float, y: float, k: float) -> float:
    return c + m + y + k


def validate_swatches_ink(limit: float = MAX_TOTAL_INK) -> list[str]:
    """Возвращает список предупреждений по total ink."""
    warns: list[str] = []
    for name, (c, m, y, k) in BRAND_SWATCHES.items():
        t = total_ink(c, m, y, k)
        if t > limit:
            warns.append(f"{name}: total ink {t:.0f}% > {limit:.0f}%")
    return warns
