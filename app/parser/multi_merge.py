"""Слияние нескольких DOCX в один выпуск газеты."""
from __future__ import annotations

from pathlib import Path

from app.config import MAX_ARTICLES_PER_JOB
from app.parser.docx_parser import ParsedDocument, Block, Run, parse_docx, ExtractedImage
from app.parser.doc_converter import ensure_docx


def collect_article_paths(job_dir: Path) -> list[Path]:
    """Порядок статей: sources/article_XX → fallback source.docx."""
    sources = job_dir / "sources"
    if sources.is_dir():
        found: list[Path] = []
        for ext in (".docx", ".doc"):
            found.extend(sorted(sources.glob(f"article_*{ext}")))
        if found:
            return found[:MAX_ARTICLES_PER_JOB]
    for ext in (".docx", ".doc"):
        p = job_dir / f"source{ext}"
        if p.exists():
            return [p]
    return []


def _article_title_from_path(path: Path, parsed: ParsedDocument) -> str:
    for b in parsed.blocks:
        if b.kind == "heading" and b.text.strip():
            return b.text.strip()[:120]
    stem = path.stem.replace("article_", "").replace("_", " ")
    if stem.isdigit():
        return f"Материал {int(stem) + 1}"
    return stem or "Материал"


def merge_parsed_documents(parts: list[tuple[str, ParsedDocument]]) -> ParsedDocument:
    if not parts:
        raise ValueError("Нет документов для слияния")
    if len(parts) == 1:
        return parts[0][1]

    blocks: list[Block] = []
    images: list[ExtractedImage] = []
    footnotes: dict[int, list[Run]] = {}
    fn_offset = 0

    for i, (title, doc) in enumerate(parts):
        if i > 0:
            blocks.append(Block(kind="page_break", runs=[]))
            has_h1 = (
                doc.blocks
                and doc.blocks[0].kind == "heading"
                and doc.blocks[0].level == 1
            )
            if not has_h1:
                blocks.append(Block(
                    kind="heading", level=1,
                    runs=[Run(text=title, bold=True)],
                ))
        img_base = len(images)
        for b in doc.blocks:
            nb = Block(
                kind=b.kind, level=b.level,
                runs=list(b.runs), image_index=b.image_index,
                caption=b.caption, image_role=b.image_role,
                width_mm=b.width_mm, height_mm=b.height_mm,
                slot_index=b.slot_index,
                table_rows=b.table_rows,
                footnote_ids=[fid + fn_offset for fid in b.footnote_ids],
            )
            if nb.image_index is not None:
                nb.image_index += img_base
            blocks.append(nb)
        images.extend(doc.images)
        for fid, fruns in doc.footnotes.items():
            footnotes[fid + fn_offset] = list(fruns)
        if doc.footnotes:
            fn_offset = max(footnotes.keys(), default=0) + 1

    return ParsedDocument(blocks=blocks, images=images, footnotes=footnotes)


def parse_issue(
    article_paths: list[Path],
    images_root: Path,
    convert_root: Path,
) -> tuple[ParsedDocument, bool, list[str]]:
    """Парсит и объединяет статьи выпуска. Возвращает (parsed, was_converted, titles)."""
    parts: list[tuple[str, ParsedDocument]] = []
    was_converted = False
    titles: list[str] = []
    for i, path in enumerate(article_paths):
        art_img = images_root / f"art_{i:02d}"
        art_img.mkdir(parents=True, exist_ok=True)
        docx_path, conv = ensure_docx(path, convert_root / f"art_{i:02d}")
        was_converted = was_converted or conv
        parsed = parse_docx(docx_path, art_img)
        title = _article_title_from_path(path, parsed)
        titles.append(title)
        parts.append((title, parsed))
    merged = merge_parsed_documents(parts)
    return merged, was_converted, titles
