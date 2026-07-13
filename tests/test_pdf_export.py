"""Тесты PDF-экспорта и оценки качества."""
import tempfile
from pathlib import Path

from app.config import TypographyProfile
from app.layout.engine import build_layout
from app.layout.templates import TEMPLATES
from app.layout.quality import compute_layout_quality
from app.export.pdf_export import export_print_pdf, pdf_page_count
from app.parser.docx_parser import ParsedDocument, Block, Run
from app.inx.smoke import smoke_test_inx
from app.inx.generator import build_inx


def test_export_print_pdf():
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="PDF тест")]),
        Block(kind="body", runs=[Run(text=" ".join(["слово"] * 80))]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    profile = TypographyProfile()
    plan = build_layout(parsed, TEMPLATES[0], profile)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.pdf"
        export_print_pdf(plan, [], out, dpi=72)
        assert out.exists()
        assert pdf_page_count(out) == len(plan.pages)


def test_layout_quality_score():
    parsed = ParsedDocument(
        blocks=[Block(kind="body", runs=[Run(text="текст")])], images=[],
    )
    plan = build_layout(parsed, TEMPLATES[0], TypographyProfile())
    inx = build_inx(parsed, plan, [])
    smoke = smoke_test_inx(inx).to_dict()
    q = compute_layout_quality(plan, smoke, {"ready_for_print": True, "counts": {}})
    assert 0 <= q["score"] <= 100
    assert q["grade"] in ("A+", "A", "B", "C", "D")
