"""Тесты размеров рекламных модулей."""
from app.layout.ad_units import (
    dimensions_from_area_cm2,
    resolve_ad_size_mm,
    parse_ad_marker,
    parse_dimensions_from_filename,
)


def test_50cm2_square():
    w, h = dimensions_from_area_cm2(50, 1.0)
    assert abs(w * h / 100 - 50) < 0.5  # площадь ~50 см²


def test_filename_mm():
    assert parse_dimensions_from_filename("reklama_70x50mm.jpg") == (70.0, 50.0)


def test_resolve_from_area_filename():
    w, h = resolve_ad_size_mm(None, filename="ad_50cm2.png")
    assert w > 0 and h > 0


def test_ad_marker():
    hits = parse_ad_marker("[РЕКЛАМА: shop.jpg 80x60mm]")
    assert len(hits) == 1
    assert hits[0][0] == "shop.jpg"
    assert hits[0][1] == 80.0
    assert hits[0][2] == 60.0
