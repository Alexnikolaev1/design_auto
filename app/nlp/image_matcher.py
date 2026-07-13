"""
Интеллектуальная привязка иллюстраций к тексту.

Как система понимает, какая картинка к какому месту относится:

  1. Встроенные в DOCX — сохраняют позицию в потоке абзацев (inline).
  2. Маркеры в тексте — [IMAGE: file.jpg], {{image:file.jpg}}.
  3. Подписи — «Рисунок 1 — …» привязываются к предыдущей иллюстрации.
  4. Имя файла — 01_vvedenie_shema.jpg → раздел «Введение».
  5. mapping.json — явная карта {"file":"a.jpg","after_heading":"Глава 2"}.
  6. Семантика — пересечение слов имени файла с заголовком раздела.
  7. Порядок — картинки без подсказок распределяются по разделам H1/H2 по очереди.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.nlp.keywords import extract_keywords
from app.parser.docx_parser import Block, ExtractedImage, Run, ParsedDocument
from app.layout.image_roles import classify_image
from app.layout.ad_units import (
    parse_ad_marker, resolve_ad_size_mm, AD_MARKER_RE,
)

IMAGE_MARKER_RE = re.compile(
    r"\[(?:IMAGE|ИЛЛЮСТРАЦИЯ|РИСУНОК)\s*:\s*([^\]]+\.(?:jpg|jpeg|png|webp|gif|tif|tiff))\s*\]",
    re.IGNORECASE,
)
BANNER_MARKER_RE = re.compile(
    r"\[(?:BANNER|БАННЕР|РЕКЛАМА|AD)\s*:\s*([^\]]+\.(?:jpg|jpeg|png|webp|gif|tif|tiff))\s*\]",
    re.IGNORECASE,
)
IMAGE_MARKER_BRACE_RE = re.compile(
    r"\{\{(?:image|banner|баннер)\s*:\s*([^}]+\.(?:jpg|jpeg|png|webp|gif|tif|tiff))\s*\}\}",
    re.IGNORECASE,
)
CAPTION_RE = re.compile(
    r"^(?:Рис\.|Рисунок|Figure|Fig\.|Илл\.|Фото\.?|Illustration)\s*[\d.]+",
    re.IGNORECASE,
)
FILENAME_SECTION_RE = re.compile(
    r"^(?:\d{1,3}[_\-.])?(.+?)(?:[_\-.](?:img|pic|photo|image|рис|илл))?(?:\.\w+)?$",
    re.IGNORECASE,
)


@dataclass
class DocumentSection:
    title: str
    level: int
    start_block: int
    end_block: int
    text: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class ImagePlacement:
    image_index: int
    filename: str
    insert_after_block: int
    anchor_heading: str
    reason: str
    caption: str = ""
    image_role: str = "photo"
    width_mm: float | None = None
    height_mm: float | None = None
    slot_index: int | None = None


@dataclass
class ImageMatchResult:
    blocks: list[Block]
    images: list[ExtractedImage]
    placements: list[ImagePlacement]


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[а-яёa-z0-9]{3,}", text, flags=re.IGNORECASE)}


def _normalize_filename(name: str) -> str:
    return Path(name).name.lower()


def _build_sections(blocks: list[Block]) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    current_title = "(начало документа)"
    current_level = 0
    start = 0
    parts: list[str] = []

    for i, block in enumerate(blocks):
        if block.kind == "heading":
            if parts or i > 0:
                sections.append(DocumentSection(
                    title=current_title,
                    level=current_level,
                    start_block=start,
                    end_block=i - 1,
                    text=" ".join(parts),
                    keywords=extract_keywords(" ".join(parts), max_keywords=6),
                ))
            current_title = block.text.strip() or current_title
            current_level = block.level
            start = i
            parts = []
        elif block.kind in ("paragraph", "list_item") and block.kind != "image":
            parts.append(block.text)

    sections.append(DocumentSection(
        title=current_title,
        level=current_level,
        start_block=start,
        end_block=len(blocks) - 1,
        text=" ".join(parts),
        keywords=extract_keywords(" ".join(parts), max_keywords=6),
    ))
    return sections


def _score_image_to_section(filename: str, section: DocumentSection) -> float:
    stem = Path(filename).stem.lower()
    tokens = _tokenize(stem.replace("_", " ").replace("-", " "))
    if not tokens:
        return 0.0

    heading_tokens = _tokenize(section.title)
    section_tokens = heading_tokens | _tokenize(section.text) | set(section.keywords)
    overlap = len(tokens & section_tokens)
    score = overlap * 2.0

    m = re.match(r"^(\d{1,3})[_\-.]", stem)
    if m:
        idx = int(m.group(1)) - 1
        sec_idx = 0  # will be set by caller with section index bonus
        score += max(0, 3 - abs(idx - sec_idx))

    for t in tokens:
        if t in heading_tokens:
            score += 4.0
        elif any(t in kw for kw in section.keywords):
            score += 2.5

    return score


def _find_block_after_heading(blocks: list[Block], heading_text: str) -> int | None:
    target = heading_text.strip().lower()
    for i, b in enumerate(blocks):
        if b.kind == "heading" and target in b.text.strip().lower():
            return i
        if b.kind == "heading" and b.text.strip().lower() in target:
            return i
    for i, b in enumerate(blocks):
        if b.kind == "heading" and _tokenize(b.text) & _tokenize(heading_text):
            return i
    return None


def _insert_image_block(blocks: list[Block], after_index: int, image_index: int,
                        caption: str = "", image_role: str = "photo",
                        width_mm: float | None = None, height_mm: float | None = None,
                        slot_index: int | None = None) -> list[Block]:
    new_block = Block(
        kind="image", level=0, runs=[],
        image_index=image_index, caption=caption, image_role=image_role,
        width_mm=width_mm, height_mm=height_mm, slot_index=slot_index,
    )
    pos = min(after_index + 1, len(blocks))
    return blocks[:pos] + [new_block] + blocks[pos:]


def _attach_captions(blocks: list[Block]) -> list[Block]:
    """Помечает подписи «Рисунок N» и связывает с предыдущей картинкой."""
    out: list[Block] = []
    last_image_idx: int | None = None
    for block in blocks:
        if block.kind == "image":
            last_image_idx = block.image_index
            out.append(block)
            continue
        if block.kind in ("paragraph", "list_item") and CAPTION_RE.match(block.text.strip()):
            cap = block.text.strip()
            if last_image_idx is not None and out and out[-1].kind == "image":
                out[-1] = Block(
                    kind="image", level=0, runs=[],
                    image_index=out[-1].image_index, caption=cap,
                    image_role=out[-1].image_role,
                )
                continue
            out.append(Block(kind="caption", level=0, runs=block.runs, caption=cap))
            continue
        out.append(block)
    return out


def _extract_markers_from_blocks(blocks: list[Block], available_files: dict[str, Path],
                                  images: list[ExtractedImage],
                                  placements: list[ImagePlacement]) -> list[Block]:
    """Заменяет маркеры [IMAGE: file.jpg] в тексте на блоки-иллюстрации."""
    out: list[Block] = []
    for i, block in enumerate(blocks):
        if block.kind not in ("paragraph", "list_item", "heading"):
            out.append(block)
            continue
        text = block.text
        ad_markers = parse_ad_marker(text)
        banner_markers = BANNER_MARKER_RE.findall(text)
        markers = IMAGE_MARKER_RE.findall(text) + IMAGE_MARKER_BRACE_RE.findall(text)
        if not markers and not banner_markers and not ad_markers:
            out.append(block)
            continue

        clean_text = AD_MARKER_RE.sub("", text)
        clean_text = BANNER_MARKER_RE.sub("", clean_text)
        clean_text = IMAGE_MARKER_RE.sub("", clean_text)
        clean_text = IMAGE_MARKER_BRACE_RE.sub("", clean_text).strip()
        if clean_text:
            out.append(Block(kind=block.kind, level=block.level, runs=[Run(text=clean_text)]))

        for marker_file, w_mm, h_mm, area in ad_markers:
            key = _normalize_filename(marker_file)
            path = available_files.get(key)
            if not path:
                for k, p in available_files.items():
                    if k.endswith(key) or key.endswith(k):
                        path = p
                        break
            if not path:
                continue
            img_idx = _register_image(
                path, images, source="marker", forced_role="ad",
                width_mm=w_mm, height_mm=h_mm, area_cm2=area,
            )
            rw, rh = images[img_idx].width_mm, images[img_idx].height_mm
            placements.append(ImagePlacement(
                image_index=img_idx,
                filename=path.name,
                insert_after_block=len(out) - 1 if out else 0,
                anchor_heading=_nearest_heading(out),
                reason=f"рекламный модуль [{marker_file}] {rw}×{rh} мм",
                image_role="ad",
                width_mm=rw, height_mm=rh,
            ))
            out.append(Block(
                kind="image", level=0, runs=[], image_index=img_idx,
                image_role="ad", width_mm=rw, height_mm=rh,
            ))

        for marker_file in banner_markers:
            key = _normalize_filename(marker_file)
            path = available_files.get(key)
            if not path:
                for k, p in available_files.items():
                    if k.endswith(key) or key.endswith(k):
                        path = p
                        break
            if not path:
                continue
            img_idx = _register_image(path, images, source="marker", forced_role="banner")
            placements.append(ImagePlacement(
                image_index=img_idx,
                filename=path.name,
                insert_after_block=len(out) - 1 if out else 0,
                anchor_heading=_nearest_heading(out),
                reason=f"маркер баннера [{marker_file}]",
                image_role="banner",
            ))
            out.append(Block(kind="image", level=0, runs=[], image_index=img_idx, image_role="banner"))

        for marker_file in markers:
            key = _normalize_filename(marker_file)
            path = available_files.get(key)
            if not path:
                for k, p in available_files.items():
                    if k.endswith(key) or key.endswith(k):
                        path = p
                        key = k
                        break
            if not path:
                continue
            img_idx = _register_image(path, images, source="marker")
            role = images[img_idx].role
            placements.append(ImagePlacement(
                image_index=img_idx,
                filename=path.name,
                insert_after_block=len(out) - 1 if out else 0,
                anchor_heading=_nearest_heading(out),
                reason=f"маркер в тексте [{marker_file}]",
                image_role=role,
            ))
            out.append(Block(kind="image", level=0, runs=[], image_index=img_idx, image_role=role))
    return out


def _nearest_heading(blocks: list[Block]) -> str:
    for b in reversed(blocks):
        if b.kind == "heading":
            return b.text.strip()
    return ""


def _register_image(path: Path, images: list[ExtractedImage], source: str,
                    forced_role: str = "", width_mm: float | None = None,
                    height_mm: float | None = None, area_cm2: float | None = None) -> int:
    for i, img in enumerate(images):
        if img.path.resolve() == path.resolve():
            return i
    from PIL import Image as PILImage
    role = classify_image(path, path.name, forced_role=forced_role)
    if role == "ad":
        w_mm, h_mm = resolve_ad_size_mm(path, width_mm, height_mm, area_cm2, path.name)
    else:
        w_mm, h_mm = width_mm, height_mm
    try:
        with PILImage.open(path) as im:
            dpi = im.info.get("dpi", (96, 96))
            images.append(ExtractedImage(
                path=path,
                width_px=im.width,
                height_px=im.height,
                dpi=(int(dpi[0]), int(dpi[1])),
                source=source,
                original_name=path.name,
                role=role,
                width_mm=w_mm,
                height_mm=h_mm,
            ))
    except Exception:
        images.append(ExtractedImage(
            path=path, width_px=0, height_px=0, dpi=(96, 96),
            source=source, original_name=path.name, role=role,
            width_mm=w_mm, height_mm=h_mm,
        ))
    return len(images) - 1


def match_uploaded_images(
    parsed: ParsedDocument,
    uploaded_paths: list[Path],
    mapping_data: list[dict] | None = None,
) -> ImageMatchResult:
    """
    Встраивает загруженные иллюстрации в поток блоков документа.
    Возвращает обновлённые blocks, images и отчёт placements.
    """
    blocks = list(parsed.blocks)
    images = list(parsed.images)
    placements: list[ImagePlacement] = []
    blocks = _attach_captions(blocks)

    available: dict[str, Path] = {_normalize_filename(p.name): p for p in uploaded_paths}
    blocks = _extract_markers_from_blocks(blocks, available, images, placements)

    used_paths: set[Path] = {img.path.resolve() for img in images}
    pending = [p for p in uploaded_paths if p.resolve() not in used_paths]

    sections = _build_sections(blocks)

    if mapping_data:
        for entry in mapping_data:
            fname = entry.get("file") or entry.get("filename") or ""
            key = _normalize_filename(fname)
            path = available.get(key)
            if not path:
                continue
            if path.resolve() in used_paths:
                continue
            after = entry.get("after_heading") or entry.get("heading") or ""
            after_block = entry.get("after_block")
            if after_block is not None:
                insert_at = int(after_block)
            elif after:
                found = _find_block_after_heading(blocks, after)
                insert_at = found if found is not None else 0
            else:
                insert_at = 0
            forced = entry.get("role", "")
            area = entry.get("area_cm2")
            w_mm = entry.get("width_mm")
            h_mm = entry.get("height_mm")
            slot_idx = entry.get("slot_index")
            if slot_idx is not None:
                try:
                    slot_idx = int(slot_idx)
                except (TypeError, ValueError):
                    slot_idx = None
            img_idx = _register_image(
                path, images, source="mapping", forced_role=forced,
                width_mm=w_mm, height_mm=h_mm, area_cm2=area,
            )
            role = images[img_idx].role
            rw, rh = images[img_idx].width_mm, images[img_idx].height_mm
            used_paths.add(path.resolve())
            placements.append(ImagePlacement(
                image_index=img_idx,
                filename=path.name,
                insert_after_block=insert_at,
                anchor_heading=after or _section_at(sections, insert_at).title,
                reason="mapping.json",
                caption=entry.get("caption", ""),
                image_role=role,
                width_mm=rw, height_mm=rh,
                slot_index=slot_idx,
            ))
            blocks = _insert_image_block(
                blocks, insert_at, img_idx, entry.get("caption", ""), role, rw, rh,
                slot_index=slot_idx,
            )
        pending = [p for p in pending if p.resolve() not in used_paths]

    for path in pending:
        key = _normalize_filename(path.name)
        best_section: DocumentSection | None = None
        best_score = 0.0
        for si, section in enumerate(sections):
            score = _score_image_to_section(path.name, section)
            m = re.match(r"^(\d{1,3})[_\-.]", path.stem)
            if m:
                num = int(m.group(1))
                if num - 1 == si:
                    score += 5.0
            if score > best_score:
                best_score = score
                best_section = section

        if best_section and best_score >= 2.0:
            insert_at = best_section.start_block
            reason = f"имя файла -> раздел «{best_section.title}» (score={best_score:.1f})"
            anchor = best_section.title
        else:
            insert_at = _sequential_insert_point(blocks, len(placements))
            anchor = _section_at(sections, insert_at).title
            reason = "порядок загрузки → раздел по очереди"

        img_idx = _register_image(path, images, source="upload")
        role = images[img_idx].role
        rw, rh = images[img_idx].width_mm, images[img_idx].height_mm
        if role == "banner":
            reason = reason + " (рекламный баннер)"
        elif role == "ad":
            reason = reason + f" (реклама {rw}×{rh} мм)"
        used_paths.add(path.resolve())
        placements.append(ImagePlacement(
            image_index=img_idx,
            filename=path.name,
            insert_after_block=insert_at,
            anchor_heading=anchor,
            reason=reason,
            image_role=role,
            width_mm=rw, height_mm=rh,
        ))
        blocks = _insert_image_block(blocks, insert_at, img_idx, image_role=role, width_mm=rw, height_mm=rh)

    return ImageMatchResult(blocks=blocks, images=images, placements=placements)


def _section_at(sections: list[DocumentSection], block_index: int) -> DocumentSection:
    for s in sections:
        if s.start_block <= block_index <= s.end_block:
            return s
    return sections[0] if sections else DocumentSection("(документ)", 0, 0, 0, "")


def _sequential_insert_point(blocks: list[Block], placement_count: int) -> int:
    """Точка вставки по порядку: после N-го заголовка H1/H2."""
    headings = [i for i, b in enumerate(blocks) if b.kind == "heading" and b.level <= 2]
    if not headings:
        return max(0, len(blocks) - 1)
    idx = placement_count % len(headings)
    return headings[idx]


def parse_mapping_json(raw: bytes | str) -> list[dict]:
    try:
        data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "images" in data:
            return data["images"]
        return []
    except Exception:
        return []


def append_image_after_last_block(
    parsed: ParsedDocument, path: Path, source: str, reason: str, anchor: str = "",
) -> tuple[ParsedDocument, ImagePlacement]:
    """Добавляет иллюстрацию в конец потока (для стоковых фото)."""
    images = list(parsed.images)
    blocks = list(parsed.blocks)
    img_idx = _register_image(path, images, source)
    role = images[img_idx].role
    insert_at = max(0, len(blocks) - 1)
    blocks = _insert_image_block(blocks, insert_at, img_idx, image_role=role)
    placement = ImagePlacement(
        image_index=img_idx,
        filename=path.name,
        insert_after_block=insert_at,
        anchor_heading=anchor or _nearest_heading(blocks),
        reason=reason,
        image_role=role,
    )
    return ParsedDocument(blocks=blocks, images=images), placement
