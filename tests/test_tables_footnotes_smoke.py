"""Тесты smoke INX, таблиц и сносок."""
from pathlib import Path

from app.config import TypographyProfile
from app.layout.engine import build_layout
from app.layout.templates import TEMPLATES
from app.inx.generator import build_inx
from app.inx.smoke import smoke_test_inx
from app.parser.docx_parser import ParsedDocument, Block, Run


def test_smoke_inx_passes_sample():
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="Тест smoke")]),
        Block(kind="body", runs=[Run(text=" ".join(["слово"] * 50))]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    profile = TypographyProfile()
    plan = build_layout(parsed, TEMPLATES[0], profile)
    inx_bytes = build_inx(parsed, plan, [])
    smoke = smoke_test_inx(inx_bytes, profile.page_width_pt(), profile.page_height_pt())
    assert smoke.passed, smoke.errors
    assert smoke.stats["stories"] >= 1
    assert smoke.stats["text_frames"] >= 1


def test_table_block_layout():
    table_rows = [
        [[Run(text="Колонка A", bold=True)], [Run(text="Колонка B", bold=True)]],
        [[Run(text="1")], [Run(text="2")]],
    ]
    blocks = [
        Block(kind="heading", level=2, runs=[Run(text="Таблица")]),
        Block(kind="table", table_rows=table_rows),
        Block(kind="body", runs=[Run(text="После таблицы")]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    plan = build_layout(parsed, TEMPLATES[0], TypographyProfile())
    has_table = any(p.tables for p in plan.pages)
    assert has_table
    table_styles = [ln.style for p in plan.pages for ln in p.preview_lines if "table" in ln.style]
    assert table_styles


def test_footnote_block_layout():
    blocks = [
        Block(kind="body", runs=[Run(text="Текст со сноской")]),
        Block(kind="heading", level=3, runs=[Run(text="Примечания", bold=True)]),
        Block(kind="footnote_block", runs=[Run(text="1. "), Run(text="Содержание сноски", italic=True)]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[], footnotes={1: [Run(text="Содержание сноски")]})
    plan = build_layout(parsed, TEMPLATES[0], TypographyProfile())
    fn_lines = [ln for p in plan.pages for ln in p.preview_lines if ln.style == "footnote"]
    assert fn_lines
    inx = build_inx(parsed, plan, []).decode("utf-8", errors="replace")
    assert "Сноска" in inx or "Содержание" in inx
