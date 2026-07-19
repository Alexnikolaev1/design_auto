"""Тесты Issue Pack, рекламных форматов, CS3 Open Guarantee."""
from __future__ import annotations

from app.config import APP_VERSION
from app.inx.kit_generator import build_kit_inx
from app.inx.smoke import smoke_test_inx
from app.kit.ads import AD_FORMATS, get_ad_format, format_ad_rate_card, list_ad_formats
from app.kit.cs3_guarantee import format_open_guarantee, run_cs3_open_guarantee
from app.kit.issue_pack import (
    choose_issue_scene_ids, plan_issue_pack, _split_articles, format_media_manifest,
)


def test_version_3_3():
    assert APP_VERSION >= "4.0.0"


def test_split_articles():
    text = (
        "Ремонт школы на улице Ленина\n\n"
        "В районе начался капитальный ремонт. Работы продлятся до осени.\n\n"
        "Ярмарка выходного дня\n\n"
        "В субботу на площади пройдёт ярмарка местных производителей."
    )
    arts = _split_articles(text)
    assert len(arts) >= 2
    assert "школ" in arts[0]["headline"].lower() or "Ремонт" in arts[0]["headline"]


def test_plan_issue_pack_basic():
    plan = plan_issue_pack(
        brief="№ 28 / 22 июля 2026, полоса новости и погода",
        source_text=(
            "Кто здесь самый главный патриот?\n\n"
            "В Новосибирском доме творчества подвели итоги фестиваля. "
            "Участниками стали методисты учреждений культуры."
        ),
        use_ai=False,
    )
    assert len(plan.scenes) >= 2
    ids = [s.scene_id for s in plan.scenes]
    assert "scene_news_page" in ids
    assert "scene_weather_strip" in ids or "scene_shorts_sidebar" in ids
    news = next(s for s in plan.scenes if s.scene_id == "scene_news_page")
    assert news.texts.get("article_headline")
    assert plan.media_slots


def test_choose_scenes_no_ads():
    ids = choose_issue_scene_ids("выпуск без рекламы", "")
    assert "scene_ads_bottom" not in ids


def test_ad_formats_catalog():
    assert len(AD_FORMATS) >= 5
    assert get_ad_format("ad_1_4") is not None
    card = format_ad_rate_card()
    assert "см²" in card or "см" in card
    assert list_ad_formats()[0]["price_hint_rub"] > 0


def test_ad_format_inx_smoke_guarantee():
    fmt = get_ad_format("ad_banner_bottom")
    raw = build_kit_inx(ad_format_id=fmt.id, texts={"ad_body_wide": "Тест рекламы"})
    assert smoke_test_inx(raw).passed
    g = run_cs3_open_guarantee(raw, include=list(fmt.elements), label=fmt.id)
    assert g.passed, [i for i in g.items if not i.ok]
    assert "Group/" in raw.decode("utf-8")


def test_issue_scenes_inx_guarantee():
    plan = plan_issue_pack(
        brief="новости района",
        source_text="Заголовок материала\n\nЛид. Текст колонки про события района.",
        use_ai=False,
        scene_ids=["scene_news_page", "scene_ads_bottom"],
    )
    reports = []
    for sp in plan.scenes:
        raw = build_kit_inx(scene_id=sp.scene_id, texts=sp.texts)
        assert smoke_test_inx(raw).passed, sp.scene_id
        g = run_cs3_open_guarantee(raw, include=list(
            __import__("app.kit.scenes", fromlist=["get_scene"]).get_scene(sp.scene_id).elements
        ), label=sp.scene_id)
        reports.append(g)
        assert g.passed, (sp.scene_id, [i for i in g.items if not i.ok])
    text = format_open_guarantee(reports, pack_label="test")
    assert "CS3_OPEN_GUARANTEE_PASS" in text
    assert "MEDIA" in format_media_manifest(plan.media_slots).upper() or "Links" in format_media_manifest(plan.media_slots)
