"""Тесты CS3 Element Kit Super Genius: Groups, Layers, Overprint, сцены."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lxml import etree

from app.config import APP_VERSION
from app.inx.kit_generator import build_kit_inx
from app.inx.smoke import smoke_test_inx
from app.kit.brand import (
    BRAND_SWATCHES, ELEMENT_CATALOG, default_include_ids, validate_swatches_ink,
)
from app.kit.checklist import format_kit_checklist
from app.kit.compose import compose_kit_selection
from app.kit.geometry import MARGIN_L, MARGIN_T, PAGE_H, PAGE_W, SIDEBAR_W
from app.kit.preflight import run_kit_preflight
from app.kit.preview import render_kit_preview_png
from app.kit.scenes import SCENES, get_scene


def test_app_version_super_genius():
    assert APP_VERSION.startswith("4.") or APP_VERSION.startswith("3.")
    assert APP_VERSION >= "4.0.0"


def test_geometry_matches_analysis_002():
    """Поля и сайдбар — из examples/_analysis/report.txt (полоса 002)."""
    assert abs(PAGE_W - 221.58) < 0.01
    assert abs(PAGE_H - 288.58) < 0.01
    assert abs(MARGIN_L - 18.29) < 0.01
    assert abs(MARGIN_T - 13.55) < 0.01
    assert abs(SIDEBAR_W - 61.07) < 0.01


def test_swatches_are_cmyk_tuples():
    assert "OkolicaRed" in BRAND_SWATCHES
    for name, vals in BRAND_SWATCHES.items():
        assert len(vals) == 4, name
        assert all(0 <= v <= 100 for v in vals), name
    assert not validate_swatches_ink()


def test_compose_rules_weather():
    sel = compose_kit_selection("нужен прогноз погоды", use_ai=False)
    assert "weather_badge" in sel["include"]
    assert sel["source"] == "rules"
    assert sel.get("scene_id") == "scene_weather_strip"


def test_compose_rules_no_ads():
    sel = compose_kit_selection("без рекламы", use_ai=False)
    assert "ad_module" not in sel["include"]
    assert "ad_module_wide" not in sel["include"]


def test_compose_scene_from_brief():
    sel = compose_kit_selection("полоса новости про школу", use_ai=False)
    assert sel["scene_id"] == "scene_news_page"
    assert "article_headline" in sel["include"]


def test_compose_explicit_scene():
    sel = compose_kit_selection("выпуск 15.07.2026", use_ai=False, scene_id="scene_ads_bottom")
    assert sel["scene_id"] == "scene_ads_bottom"
    assert "ad_module" in sel["include"]


def test_extract_json_from_gemini_fence():
    from app.kit.compose import _extract_json_object, _normalize_ai_payload
    raw = '```json\n{"include":["styles_pack","decor_rule"],"texts":{"decor_rule":"линия"}}\n```'
    data = _extract_json_object(raw)
    assert data is not None
    norm = _normalize_ai_payload(data)
    assert norm is not None
    assert "styles_pack" in norm["include"]


def test_normalize_scene_texts_keys():
    from app.kit.compose import _normalize_ai_payload
    data = {
        "scene_id": "scene_shorts_sidebar",
        "texts": {"news_card_1": "Первая", "news_card_2": "Вторая",
                  "news_card_3": "Третья", "bogus": "nope"},
    }
    norm = _normalize_ai_payload(data, scene_id="scene_shorts_sidebar")
    assert norm is not None
    assert norm["texts"]["news_card_1"] == "Первая"
    assert "bogus" not in norm["texts"]


def test_ai_without_key_falls_back_to_rules(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LG_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LG_AI_API_KEY", raising=False)
    import app.config as cfg
    monkeypatch.setattr(cfg, "GEMINI_API_KEY", "")
    sel = compose_kit_selection("нужен прогноз погоды", use_ai=True)
    assert sel["source"] == "rules"
    assert "weather_badge" in sel["include"]


def test_kit_inx_super_genius_features():
    include = default_include_ids()
    texts = compose_kit_selection("", use_ai=False)["texts"]
    raw = build_kit_inx(include=include, texts=texts)
    assert b'DOMVersion="5.0"' in raw
    assert b'style="33"' in raw
    assert b'Space="CMYK"' in raw

    smoke = smoke_test_inx(raw)
    assert smoke.passed, smoke.errors

    xml = raw.decode("utf-8")
    assert "Group/" in xml
    assert "RootLayerGroup" not in xml
    assert "ItemLayer=" not in xml
    assert "ObjectStyle/" not in xml
    assert 'OverprintFill="true"' in xml or 'OverprintStroke="true"' in xml
    assert "kit_masthead_logo" in xml
    assert "kit_article_col1" in xml
    assert "kit_article_col2" in xml
    assert "NextTextFrame" in xml
    assert "ParagraphStyle/Заголовок 1" in xml
    assert "ParagraphStyle/Логотип" in xml

    from app.inx.smoke import _parse_inx_root
    root = _parse_inx_root(raw)
    for col in root.iter():
        if etree.QName(col).localname != "Color":
            continue
        assert col.get("Space") == "CMYK", col.get("Name")


def test_scene_inx_smoke_groups_preflight():
    for scene in SCENES:
        raw = build_kit_inx(scene_id=scene.id, texts=dict(scene.default_texts))
        smoke = smoke_test_inx(raw)
        assert smoke.passed, (scene.id, smoke.errors)
        pf = run_kit_preflight(raw, include=list(scene.elements))
        assert pf.passed, (scene.id, [i for i in pf.items if i.severity == "fail"])
        xml = raw.decode("utf-8")
        assert "Group/" in xml, scene.id
        assert "RootLayerGroup" not in xml, scene.id
        assert b'style="33"' in raw


def test_kit_preview_and_checklist():
    include = default_include_ids()
    texts = {"masthead_logo": "Сибирская околица"}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "catalog.png"
        render_kit_preview_png(include, texts, out)
        assert out.is_file() and out.stat().st_size > 1000
        scene_out = Path(tmp) / "scene.png"
        render_kit_preview_png([], {}, scene_out, scene_id="scene_news_page")
        assert scene_out.stat().st_size > 1000

    raw = build_kit_inx(include=include, texts=texts)
    text = format_kit_checklist(include, source="rules", smoke_ok=True, inx_bytes=raw)
    assert "FOGRA39" in text
    assert "SUPER GENIUS" in text


def test_element_catalog_and_scenes():
    assert len(ELEMENT_CATALOG) >= 10
    ids = {e.id for e in ELEMENT_CATALOG}
    assert "folio_line" in ids and "cover_teaser" in ids
    assert get_scene("scene_news_page") is not None
    assert get_scene("scene_weather_strip") is not None
    assert len(SCENES) >= 6
