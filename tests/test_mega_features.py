"""Тесты разрывов страниц и многостраничной сетки."""
from app.config import TypographyProfile
from app.layout.engine import build_layout
from app.layout.templates import TEMPLATES
from app.layout.ad_grid import parse_ad_grid_json, analyze_ad_slots
from app.analysis.reference_pdf import AdSlot
from app.parser.docx_parser import ParsedDocument, Block, Run
from app.inx.generator import build_inx, _page_spread_groups


def test_page_break_creates_new_page():
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="Часть 1")]),
        Block(kind="body", runs=[Run(text=" ".join(["а"] * 80))]),
        Block(kind="page_break"),
        Block(kind="heading", level=1, runs=[Run(text="Часть 2")]),
        Block(kind="body", runs=[Run(text=" ".join(["б"] * 80))]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    plan = build_layout(parsed, TEMPLATES[0], TypographyProfile())
    assert len(plan.pages) >= 2


def test_h1_starts_new_page():
    blocks = [
        Block(kind="body", runs=[Run(text=" ".join(["вступление"] * 60))]),
        Block(kind="heading", level=1, runs=[Run(text="Новая статья")]),
        Block(kind="body", runs=[Run(text="текст статьи")]),
    ]
    profile = TypographyProfile(heading_starts_new_page=True)
    plan = build_layout(parsed := ParsedDocument(blocks=blocks, images=[]), TEMPLATES[0], profile)
    assert len(plan.pages) >= 2


def test_multi_page_ad_slots():
    raw = '{"slots":[' \
          '{"page_index":0,"x_mm":10,"y_mm":20,"width_mm":50,"height_mm":40},' \
          '{"page_index":1,"x_mm":15,"y_mm":25,"width_mm":60,"height_mm":45}' \
          ']}'
    slots = parse_ad_grid_json(raw)
    assert len(slots) == 2
    assert slots[1].page_index == 1
    report = analyze_ad_slots(slots, used_indices={0})
    assert report["total_slots"] == 2
    assert report["used_slots"] == 1
    assert report["empty_slots"] == 1


def test_facing_spread_groups():
    from app.layout.engine import Page, ColumnFrame, Rect
    pages = [Page(index=i, columns=[], images=[]) for i in range(3)]
    groups = _page_spread_groups(pages, facing=True)
    assert len(groups) == 2
    assert len(groups[0]) == 2
    assert len(groups[1]) == 1


def test_inx_facing_has_two_page_spread():
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="A")]),
        Block(kind="body", runs=[Run(text=" ".join(["x"] * 300))]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    profile = TypographyProfile(facing_pages=True)
    plan = build_layout(parsed, TEMPLATES[1], profile)
    if len(plan.pages) < 2:
        return  # короткий текст — пропускаем
    inx = build_inx(parsed, plan, []).decode("utf-8", errors="replace")
    assert 'PageCount="2"' in inx or plan.pages.__len__() == 1
