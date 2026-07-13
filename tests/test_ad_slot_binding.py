"""Привязка рекламы к слотам по filename и slot_index."""
from app.analysis.reference_pdf import AdSlot
from app.layout.engine import _take_ad_slot
from app.layout.ad_grid import parse_ad_grid_json


def test_parse_grid_with_filename():
    raw = '{"slots":[{"x_mm":10,"y_mm":20,"width_mm":70,"height_mm":50,"filename":"shop.jpg"}]}'
    slots = parse_ad_grid_json(raw)
    assert slots[0].filename == "shop.jpg"


def test_take_slot_by_filename():
    slots = [
        AdSlot(0, 10, 20, 50, 50, filename=""),
        AdSlot(0, 80, 20, 50, 50, filename="reklama.jpg"),
    ]
    used: set[int] = set()
    s = _take_ad_slot(slots, used, 0, filename="reklama.jpg")
    assert s is not None
    assert s.filename == "reklama.jpg"
    assert 1 in used


def test_take_slot_by_index():
    slots = [AdSlot(0, 0, 0, 40, 40), AdSlot(0, 50, 0, 40, 40)]
    used: set[int] = set()
    s = _take_ad_slot(slots, used, 0, slot_index=1)
    assert s is slots[1]
