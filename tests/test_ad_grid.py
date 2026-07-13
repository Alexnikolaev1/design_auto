"""Тесты рекламной сетки и своего формата."""
from app.config import TypographyProfile
from app.layout.ad_grid import parse_ad_grid_json, resolve_ad_slots, scale_preset
from app.analysis.reference_pdf import AdSlot, ReferenceStyleProfile


def test_parse_ad_grid():
    raw = '{"slots":[{"x_mm":10,"y_mm":20,"width_mm":70,"height_mm":50}]}'
    slots = parse_ad_grid_json(raw)
    assert len(slots) == 1
    assert slots[0].width_mm == 70


def test_user_grid_over_pdf():
    ref = ReferenceStyleProfile(ad_slots=[AdSlot(0, 0, 0, 50, 50)])
    user = '{"slots":[{"x_mm":5,"y_mm":5,"width_mm":80,"height_mm":60}]}'
    slots = resolve_ad_slots(user, ref)
    assert len(slots) == 1
    assert slots[0].width_mm == 80


def test_custom_page_format():
    p = TypographyProfile(
        page_format="custom",
        custom_page_width_mm=260,
        custom_page_height_mm=400,
    )
    w, h = p.page_size_mm()
    assert abs(w - 260) < 0.1
    assert abs(h - 400) < 0.1


def test_scale_preset_tabloid():
    slots = scale_preset("grid_2x2", 280, 430, 18, 18, 20, 20)
    assert len(slots) == 4
    assert slots[0]["width_mm"] > 50
