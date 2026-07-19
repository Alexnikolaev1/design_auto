"""Тесты паков-действий дизайнера."""
from __future__ import annotations

from app.config import APP_VERSION
from app.inx.kit_generator import build_kit_inx
from app.inx.smoke import smoke_test_inx
from app.kit.cs3_guarantee import run_cs3_open_guarantee
from app.kit.packs import DESIGNER_PACKS, get_pack, list_packs


def test_version_4():
    assert APP_VERSION.startswith("4.")


def test_packs_have_actions_and_needs():
    assert len(DESIGNER_PACKS) >= 8
    for p in DESIGNER_PACKS:
        assert p.action.startswith("Создать"), p.id
        assert p.needs_hint
        assert p.needs
    data = list_packs()
    assert data[0]["action"]
    assert "needs_hint" in data[0]


def test_decor_and_backdrop():
    for pid in ("pack_decor", "pack_backdrop"):
        pack = get_pack(pid)
        assert pack is not None
        raw = build_kit_inx(
            include=list(pack.elements),
            texts={"wave_caption": "В эти дни"},
            pack_id=pid,
        )
        assert smoke_test_inx(raw).passed
        assert run_cs3_open_guarantee(raw, include=list(pack.elements)).passed
        xml = raw.decode("utf-8")
        assert "Group/" in xml
        assert "RootLayerGroup" not in xml
        # полоса должна быть плотной, не «один бордюр внизу»
        assert xml.count("<Group ") >= 6
        assert xml.count("<Rectangle") >= 40
        assert "Стили: Заголовок" not in xml


def test_banner_action():
    pack = get_pack("pack_banner_wide")
    raw = build_kit_inx(ad_format_id=pack.ad_format_id, texts={"ad_body_wide": "Реклама"})
    assert smoke_test_inx(raw).passed
