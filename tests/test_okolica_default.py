"""Шрифты и дефолт-профиль «Сибирская околица»."""
from app.config import TypographyProfile, FONT_CATALOG, FONTS_DIR
from app.layout import fonts as font_manager
from app.layout.okolica_profile import ACCENT_HEADLINE_RGB, FONT_BODY, FONT_HEADLINE_REGULAR, FONT_RUBRIC
from app.layout.templates import TEMPLATES, select_templates
from app.layout.engine import build_layout
from app.parser.docx_parser import ParsedDocument, Block, Run


def test_okolica_font_files_present():
    required = [
        "HeliosCondC", "HeliosCondC-Bold", "HeliosCondC-Italic",
        "SchoolBookC", "SchoolBookC-Bold", "AdventureC",
    ]
    for ps in required:
        fname = FONT_CATALOG[ps]
        assert (FONTS_DIR / fname).is_file(), f"missing {fname}"


def test_okolica_fonts_resolve():
    font_manager.scan_fonts(force=True)
    for ps in ("HeliosCondC", "SchoolBookC", "AdventureC", "HeliosCondC-Bold", "SchoolBookC-Bold"):
        r = font_manager.resolve(ps)
        assert r.path is not None and r.path.is_file(), ps
        assert not r.is_fallback, ps


def test_default_profile_is_okolica():
    p = TypographyProfile()
    assert p.page_format == "okolica"
    assert abs(p.custom_page_width_mm - 221.58) < 0.01
    assert abs(p.custom_page_height_mm - 288.58) < 0.01
    assert p.columns_count == 3
    assert p.font_sans == FONT_BODY
    assert p.font_serif == FONT_HEADLINE_REGULAR
    assert p.font_display == FONT_RUBRIC


def test_okolica_lead_photo_is_large():
    from PIL import Image
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        img_path = Path(tmp) / "lead.jpg"
        Image.new("RGB", (1200, 800), (100, 120, 140)).save(img_path)
        from app.parser.docx_parser import ExtractedImage
        parsed = ParsedDocument(
            blocks=[
                Block(kind="heading", level=1, runs=[Run(text="Главный материал")]),
                Block(kind="image", image_index=0, image_role="photo"),
                Block(kind="body", runs=[Run(text=" ".join(["слово"] * 100))]),
                Block(kind="body", runs=[Run(text=" ".join(["ещё"] * 80))]),
            ],
            images=[ExtractedImage(
                path=img_path, width_px=1200, height_px=800,
                dpi=(72, 72), role="photo",
            )],
        )
        tpl = select_templates(300, 1, TypographyProfile())[0]
        plan = build_layout(parsed, tpl, TypographyProfile())
        assert plan.pages
        frames = plan.pages[0].images
        assert frames
        lead = frames[0]
        assert lead.image_role == "lead"
        # lead ≈ 2 колонки, не миниатюра 44%
        page_w = plan.page_width_pt
        assert lead.rect.w > page_w * 0.40
        assert lead.stroke_pt >= 0.4
        # лид-абзац
        styles = {ln.style for ln in plan.pages[0].preview_lines}
        assert "lead" in styles or "body" in styles


def test_modern_grid_not_in_default_five():
    ids = [t.id for t in select_templates(1000, 2, TypographyProfile())]
    assert ids[0] == "okolica-news"
    assert "modern-grid" not in ids


def test_okolica_template_first():
    assert TEMPLATES[0].id == "okolica-news"
    picked = select_templates(1200, 2, TypographyProfile())
    assert picked[0].id == "okolica-news"
    assert picked[0].body_font.startswith("Helios")
    assert "SchoolBook" in picked[0].heading_font


def test_okolica_red_accent():
    parsed = ParsedDocument(
        blocks=[
            Block(kind="heading", level=1, runs=[Run(text="Тест")]),
            Block(kind="body", runs=[Run(text=" ".join(["слово"] * 80))]),
        ],
        images=[],
    )
    tpl = select_templates(200, 0, TypographyProfile())[0]
    plan = build_layout(parsed, tpl, TypographyProfile())
    assert plan.dominant_accent_rgb == ACCENT_HEADLINE_RGB
