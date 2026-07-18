"""
Сцены-пресеты: готовые композиции «один Copy/Paste» под полосы Околицы.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KitScene:
    id: str
    name: str
    description: str
    elements: tuple[str, ...]
    default_texts: dict[str, str] = field(default_factory=dict)
    # ключи текстов, которые Gemini должен заполнить по брифу
    fillable_keys: tuple[str, ...] = ()


SCENES: list[KitScene] = [
    KitScene(
        id="scene_news_page",
        name="Полоса новости",
        description="Шапка + сайдбар коротких + H1/фото/лид/колонка — как стр. 2–3",
        elements=(
            "styles_pack",
            "masthead_logo", "masthead_issue", "masthead_rubric_line",
            "news_header", "news_card",
            "article_kicker", "article_headline", "article_photo_frame",
            "article_lead", "article_column",
            "decor_rule", "folio_line",
        ),
        default_texts={
            "masthead_logo": "Сибирская околица",
            "masthead_issue": "№ — / дата",
            "masthead_rubric_line": "Актуально",
            "news_header": "Короткие новости",
            "news_card_1": "Краткая новость района — первая карточка.",
            "news_card_2": "Вторая короткая новость для ленты.",
            "news_card_3": "Третья короткая новость.",
            "article_kicker": "Актуально",
            "article_headline": "Главный заголовок полосы",
            "article_lead": "Лид: два-три предложения о сути материала.",
            "article_column": (
                "Основной текст колонки. Helios Condensed 9/10.8, "
                "выключка, переносы. Замените на материал выпуска."
            ),
        },
        fillable_keys=(
            "masthead_issue", "masthead_rubric_line",
            "news_card_1", "news_card_2", "news_card_3",
            "article_kicker", "article_headline", "article_lead", "article_column",
        ),
    ),
    KitScene(
        id="scene_ads_bottom",
        name="Низ с рекламой",
        description="Разделитель + узкий и широкий рекламные модули с пометкой «Реклама»",
        elements=(
            "styles_pack",
            "decor_divider",
            "ad_module", "ad_module_wide",
            "folio_line",
        ),
        default_texts={
            "ad_module": "Реклама",
            "ad_module_wide": "Рекламный модуль — широкая полоса",
            "ad_body_narrow": "Текст / телефон рекламодателя",
            "ad_body_wide": "Услуги · телефон · адрес",
        },
        fillable_keys=("ad_body_narrow", "ad_body_wide"),
    ),
    KitScene(
        id="scene_shorts_sidebar",
        name="Сайдбар коротких",
        description="Только оранжевая лента «Короткие новости» + 3 карточки",
        elements=("styles_pack", "news_header", "news_card"),
        default_texts={
            "news_header": "Короткие новости",
            "news_card_1": "Новость 1",
            "news_card_2": "Новость 2",
            "news_card_3": "Новость 3",
        },
        fillable_keys=("news_card_1", "news_card_2", "news_card_3"),
    ),
    KitScene(
        id="scene_cover_teasers",
        name="Обложка: тизеры",
        description="Логотип + тизеры AdventureC (тема + «Стр. N») в духе обложки",
        elements=(
            "styles_pack",
            "masthead_logo", "masthead_issue",
            "cover_teaser",
            "decor_corners",
        ),
        default_texts={
            "masthead_logo": "Сибирская околица",
            "masthead_issue": "№ — / дата",
            "cover_teaser_1": "• Тема первая  Стр. 3",
            "cover_teaser_2": "• Тема вторая  Стр. 6–7",
            "cover_teaser_3": "• Тема третья  Стр. 12–13",
        },
        fillable_keys=(
            "masthead_issue",
            "cover_teaser_1", "cover_teaser_2", "cover_teaser_3",
        ),
    ),
    KitScene(
        id="scene_feature_decor",
        name="Фичер + декор",
        description="Рубрика, заголовок, волнистый бордюр «В эти дни», уголки",
        elements=(
            "styles_pack",
            "article_kicker", "article_headline", "article_lead",
            "decor_wave_border", "decor_corners", "decor_rule",
        ),
        default_texts={
            "article_kicker": "Ну и ну!",
            "article_headline": "Заголовок фичерного материала",
            "article_lead": "Короткий лид к фичеру.",
            "wave_caption": "В эти дни",
        },
        fillable_keys=("article_kicker", "article_headline", "article_lead", "wave_caption"),
    ),
    KitScene(
        id="scene_weather_strip",
        name="Полоса с погодой",
        description="Шапка + бирюзовый «ПРОГНОЗ ПОГОДЫ» + сайдбар коротких (как стр. 3)",
        elements=(
            "styles_pack",
            "masthead_logo", "masthead_issue",
            "weather_badge",
            "news_header", "news_card",
            "folio_line",
        ),
        default_texts={
            "masthead_logo": "Сибирская околица",
            "masthead_issue": "№ — / дата",
            "weather_badge": "ПРОГНОЗ ПОГОДЫ",
            "weather_body": "Район: ясно, +22…+24 °C. Ветер слабый.",
            "news_header": "Короткие\nновости",
            "news_card_1": "Краткая новость 1.",
            "news_card_2": "Краткая новость 2.",
            "news_card_3": "Краткая новость 3.",
        },
        fillable_keys=(
            "masthead_issue", "weather_body",
            "news_card_1", "news_card_2", "news_card_3",
        ),
    ),
]


def get_scene(scene_id: str) -> KitScene | None:
    for s in SCENES:
        if s.id == scene_id:
            return s
    return None


def list_scenes() -> list[dict]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "elements": list(s.elements),
            "fillable_keys": list(s.fillable_keys),
        }
        for s in SCENES
    ]


def scene_element_ids(scene_id: str) -> list[str]:
    s = get_scene(scene_id)
    return list(s.elements) if s else []
