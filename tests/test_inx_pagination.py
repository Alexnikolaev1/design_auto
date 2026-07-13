"""INX должен отражать пагинацию из layout plan, а не весь текст в одном потоке."""
from pathlib import Path

from app.config import TypographyProfile
from app.layout.engine import build_layout
from app.layout.templates import TEMPLATES
from app.inx.generator import build_inx
from app.parser.docx_parser import ParsedDocument, Block, Run


def _sample_doc() -> ParsedDocument:
    blocks = [
        Block(kind="heading", level=1, runs=[Run(text="Заголовок статьи")]),
        Block(kind="body", runs=[Run(text=" ".join(["слово"] * 120))]),
        Block(kind="heading", level=2, runs=[Run(text="Вторая часть")]),
        Block(kind="body", runs=[Run(text=" ".join(["текст"] * 200))]),
    ]
    return ParsedDocument(blocks=blocks, images=[])


def test_inx_has_per_column_stories():
    parsed = _sample_doc()
    profile = TypographyProfile()
    tmpl = TEMPLATES[1]  # two-column
    plan = build_layout(parsed, tmpl, profile)
    inx = build_inx(parsed, plan, []).decode("utf-8", errors="replace")

    story_count = inx.count("<Story ")
    tf_count = inx.count("<TextFrame ")
    assert story_count >= len(plan.pages), "каждая страница должна иметь свои Story"
    assert tf_count >= len(plan.pages) * tmpl.columns
    assert "Заголовок статьи" in inx
