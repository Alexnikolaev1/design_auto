"""Тесты векторного PDF, CMYK, мульти-статьи и смарт-кадрирования."""
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import TypographyProfile
from app.export.color_convert import use_cmyk_output, rgb_to_cmyk_percent
from app.export.pdf_export import export_print_pdf, pdf_page_count, pdf_has_selectable_text
from app.layout.engine import build_layout
from app.layout.smart_crop import smart_crop_cover, _focal_point
from app.layout.templates import TEMPLATES
from app.parser.docx_parser import ParsedDocument, Block, Run
from app.parser.multi_merge import merge_parsed_documents, collect_article_paths


def test_rgb_to_cmyk():
    c, m, y, k = rgb_to_cmyk_percent(255, 255, 255)
    assert k == 0.0
    c, m, y, k = rgb_to_cmyk_percent(0, 0, 0)
    assert k == 100.0


def test_use_cmyk_for_print_profile():
    assert use_cmyk_output(TypographyProfile(color_profile="Coated FOGRA39"))
    assert not use_cmyk_output(TypographyProfile(color_profile="sRGB IEC61966-2.1 (для digital)"))


def test_vector_pdf_has_text():
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="Векторный PDF")]),
        Block(kind="body", runs=[Run(text=" ".join(["текст"] * 60))]),
    ]
    parsed = ParsedDocument(blocks=blocks, images=[])
    profile = TypographyProfile(pdf_vector_export=True, color_profile="Coated FOGRA39")
    plan = build_layout(parsed, TEMPLATES[0], profile)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "vector.pdf"
        info: dict = {}
        export_print_pdf(plan, [], out, dpi=150, export_info=info)
        assert out.exists()
        assert pdf_page_count(out) == len(plan.pages)
        assert info.get("text_verified") or pdf_has_selectable_text(out)


def test_merge_two_articles():
    doc1 = ParsedDocument(
        blocks=[Block(kind="heading", level=1, runs=[Run(text="Статья 1")]),
                Block(kind="body", runs=[Run(text="Текст первой")])],
        images=[],
    )
    doc2 = ParsedDocument(
        blocks=[Block(kind="heading", level=1, runs=[Run(text="Статья 2")]),
                Block(kind="body", runs=[Run(text="Текст второй")])],
        images=[],
    )
    merged = merge_parsed_documents([("Статья 1", doc1), ("Статья 2", doc2)])
    kinds = [b.kind for b in merged.blocks]
    assert "page_break" in kinds
    assert merged.full_text.count("Текст") == 2
    h1_count = sum(1 for b in merged.blocks if b.kind == "heading" and b.level == 1)
    assert h1_count == 2


def test_merge_skips_duplicate_h1():
    doc1 = ParsedDocument(blocks=[Block(kind="body", runs=[Run(text="A")])], images=[])
    doc2 = ParsedDocument(
        blocks=[
            Block(kind="heading", level=1, runs=[Run(text="Уже есть H1")]),
            Block(kind="body", runs=[Run(text="B")]),
        ],
        images=[],
    )
    merged = merge_parsed_documents([("X", doc1), ("Уже есть H1", doc2)])
    h1_texts = [b.text for b in merged.blocks if b.kind == "heading" and b.level == 1]
    assert h1_texts.count("Уже есть H1") == 1


def test_collect_article_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sources = root / "sources"
        sources.mkdir()
        (sources / "article_00.docx").write_bytes(b"x")
        (sources / "article_01.docx").write_bytes(b"y")
        paths = collect_article_paths(root)
        assert len(paths) == 2
        assert paths[0].name == "article_00.docx"


def test_cleanup_old_jobs():
    from app.tasks.cleanup import cleanup_old_jobs
    removed = cleanup_old_jobs(max_age_hours=0.001)
    assert removed >= 0


def test_smart_crop_focal_not_center():
    img = Image.new("RGB", (400, 200), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([320, 60, 380, 140], fill=(20, 20, 20))
    fx, fy = _focal_point(img)
    assert fx > 0.55
    cropped = smart_crop_cover(img, 100, 100)
    assert cropped.size == (100, 100)
