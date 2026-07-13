"""Тесты переносов, overrides и чеклиста печати."""
from app.config import TypographyProfile
from app.layout.hyphenation import syllables, can_hyphenate
from app.layout.overrides import (
    FrameOverride, apply_overrides, export_layout_model, parse_overrides_json,
)
from app.layout.engine import build_layout, Rect, ImageFrame, Page, ColumnFrame, LayoutPlan
from app.layout.templates import TEMPLATES
from app.inx.print_checklist import build_print_checklist
from app.parser.docx_parser import ParsedDocument, Block, Run


def test_russian_hyphenation():
    parts = syllables("типографика", "ru-RU")
    assert can_hyphenate("типографика", "ru-RU") or len(parts) >= 1


def test_apply_layout_override():
    plan = LayoutPlan(
        template=TEMPLATES[0],
        profile=TypographyProfile(),
        pages=[Page(
            index=0,
            columns=[ColumnFrame(rect=Rect(0, 0, 200, 700), chain_index=0)],
            images=[ImageFrame(
                rect=Rect(50, 50, 100, 80), image_index=0, element_id="p0_img0",
            )],
        )],
        dominant_accent_rgb=(0, 0, 0),
        keywords=[],
        page_width_pt=595,
        page_height_pt=842,
    )
    overrides = [FrameOverride("p0_img0", 0, 20.0, 30.0, 60.0, 45.0)]
    apply_overrides(plan, overrides)
    img = plan.pages[0].images[0]
    assert abs(img.rect.x - 20 * 72 / 25.4) < 2


def test_export_layout_model():
    parsed = ParsedDocument(
        blocks=[Block(kind="body", runs=[Run(text="test")])], images=[],
    )
    plan = build_layout(parsed, TEMPLATES[0], TypographyProfile())
    model = export_layout_model(plan)
    assert model["page_width_mm"] > 100
    assert "pages" in model


def test_print_checklist_passes_clean_smoke():
    cl = build_print_checklist(
        TypographyProfile(),
        {"passed": True, "stats": {"pages": 1}, "warnings": []},
        None,
        [],
        1,
        [],
    )
    assert cl.ready_for_print
    assert any(i.category == "manual" for i in cl.items)


def test_parse_overrides_json():
    raw = '{"overrides":[{"element_id":"p0_img0","page_index":0,"x_mm":10,"y_mm":20,"width_mm":50,"height_mm":40}]}'
    o = parse_overrides_json(raw)
    assert len(o) == 1
    assert o[0].element_id == "p0_img0"
