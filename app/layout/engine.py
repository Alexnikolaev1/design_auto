"""
Движок компоновки: сетка, пагинация, обтекание, рекламные слоты из PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from app.config import TypographyProfile, MM_TO_PT
from app.layout import fonts as font_manager
from app.layout.templates import TemplateSpec
from app.parser.docx_parser import ParsedDocument, Block, Run
from app.nlp.keywords import extract_keywords
from app.layout.image_roles import image_aspect, is_banner_role, is_ad_role
from app.layout.ad_units import resolve_ad_size_mm, AD_LABEL_HEIGHT_MM
from app.layout.text_flow import (
    ColumnObstacle, flow_runs_into_lines, obstacle_bottom,
)
from app.analysis.reference_pdf import AdSlot
from app.layout.newspaper import (
    is_newspaper_template, refine_photo_role, newspaper_image_rect,
    stroke_pt_for_role, masthead_reserve_pt,
)


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float


@dataclass
class ImageFrame:
    rect: Rect
    image_index: int
    caption: str = ""
    anchor_heading: str = ""
    image_role: str = "photo"
    width_mm: float | None = None
    height_mm: float | None = None
    show_ad_label: bool = False
    text_wrap: bool = False
    wrap_side: str = "both"  # left | right | both
    element_id: str = ""
    stroke_pt: float = 0.0


@dataclass
class ColumnFrame:
    rect: Rect
    chain_index: int


@dataclass
class PreviewLine:
    runs: list[Run]
    style: str
    column_index: int
    x_offset: float = 0.0
    width_pt: float | None = None
    y_pt: float | None = None

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class TableFrame:
    rect: Rect
    rows: list[list[str]]
    header: bool = True


@dataclass
class Page:
    index: int
    columns: list[ColumnFrame]
    images: list[ImageFrame]
    preview_lines: list[PreviewLine] = field(default_factory=list)
    tables: list[TableFrame] = field(default_factory=list)
    drop_cap: bool = False


@dataclass
class LayoutPlan:
    template: TemplateSpec
    profile: TypographyProfile
    pages: list[Page]
    dominant_accent_rgb: tuple[int, int, int]
    keywords: list[str]
    page_width_pt: float = 0.0
    page_height_pt: float = 0.0
    used_ad_slot_indices: list[int] = field(default_factory=list)


def _content_area(profile: TypographyProfile, page_index: int = 0) -> Rect:
    m = profile.margins_pt(page_index)
    pw, ph = profile.page_width_pt(), profile.page_height_pt()
    return Rect(
        x=m["left"], y=m["top"],
        w=pw - m["left"] - m["right"],
        h=ph - m["top"] - m["bottom"],
    )


def _columns_for_page(content: Rect, template: TemplateSpec,
                       reserved_top: dict[int, float] | None = None) -> list[ColumnFrame]:
    reserved_top = reserved_top or {}
    gutter_pt = template.gutter_mm * (72.0 / 25.4)
    n = template.columns
    col_w = (content.w - gutter_pt * (n - 1)) / n
    cols = []
    for i in range(n):
        x = content.x + i * (col_w + gutter_pt)
        top_offset = reserved_top.get(i, 0.0)
        cols.append(ColumnFrame(
            rect=Rect(x=x, y=content.y + top_offset, w=col_w, h=content.h - top_offset),
            chain_index=0,
        ))
    return cols


def _pil_font_loader(postscript_name: str, px_size: int, bold: bool, italic: bool):
    resolved = font_manager.resolve_variant(postscript_name, bold=bold, italic=italic)
    if resolved.path is not None:
        try:
            return ImageFont.truetype(str(resolved.path), px_size)
        except Exception:
            pass
    return ImageFont.load_default()


def _pick_dominant_color(images: list) -> tuple[int, int, int]:
    if not images:
        return (0x1F, 0x3A, 0x5F)
    try:
        from PIL import Image
        img = Image.open(images[0].path).convert("RGB")
        img = img.resize((32, 32))
        pixels = list(img.getdata())
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        return (max(0, r - 30), max(0, g - 30), max(0, b - 30))
    except Exception:
        return (0x1F, 0x3A, 0x5F)


def _accent_for_template(template: TemplateSpec, parsed: ParsedDocument) -> tuple[int, int, int]:
    """Для «Околицы» — фирменный красный заголовок; иначе цвет с фото."""
    if template.id == "okolica-news":
        from app.layout.okolica_profile import ACCENT_HEADLINE_RGB
        return ACCENT_HEADLINE_RGB
    return _pick_dominant_color(parsed.images)


def _nearest_heading(blocks: list[Block], up_to: int) -> str:
    for i in range(min(up_to, len(blocks) - 1), -1, -1):
        if blocks[i].kind == "heading":
            return blocks[i].text.strip()
    return ""


def _image_rect_for_strategy(template: TemplateSpec, col_rect: Rect, img_index: int,
                              aspect: float = 0.65, role: str = "photo",
                              content: Rect | None = None, img_path: Path | None = None,
                              float_side: str = "left") -> Rect:
    if is_banner_role(role) and content is not None:
        real_aspect = image_aspect(img_path) if img_path and img_path.exists() else 3.0
        w = content.w
        h = min(w / real_aspect, content.h * 0.38)
        h = max(h, 45)
        return Rect(x=content.x, y=col_rect.y, w=w, h=h)
    if template.image_strategy == "banner_strip" and content is not None:
        w = content.w
        h = min(content.h * 0.2, 72)
        h = max(h, 40)
        return Rect(x=content.x, y=col_rect.y, w=w, h=h)
    if template.image_strategy == "column_span" and content is not None:
        w = content.w
        asp = image_aspect(img_path) if img_path and img_path.exists() else 1.35
        h = min(w / asp, content.h * 0.42)
        h = max(h, 50)
        return Rect(x=content.x, y=col_rect.y, w=w, h=h)
    if role == "logo" and content is not None:
        side = min(content.w * 0.35, 120)
        return Rect(x=content.x, y=col_rect.y, w=side, h=side * 0.6)
    if template.image_strategy == "float_side" or (template.columns >= 2 and role == "photo"):
        fw = col_rect.w * 0.44
        fh = fw * aspect
        if float_side == "right":
            return Rect(x=col_rect.x + col_rect.w - fw, y=col_rect.y, w=fw, h=fh)
        return Rect(x=col_rect.x, y=col_rect.y, w=fw, h=fh)
    if template.image_strategy == "full_width":
        h = col_rect.w * 0.55
        return Rect(x=col_rect.x, y=col_rect.y, w=col_rect.w, h=h)
    h = col_rect.w * aspect
    return Rect(x=col_rect.x, y=col_rect.y, w=col_rect.w, h=h)


def _should_float(role: str, template: TemplateSpec) -> bool:
    if is_ad_role(role) or is_banner_role(role):
        return False
    return template.image_strategy == "float_side" or (
        template.columns >= 2 and template.image_strategy != "column_span"
    )


def _take_ad_slot(
    slots: list[AdSlot],
    used: set[int],
    page_index: int,
    filename: str = "",
    slot_index: int | None = None,
) -> AdSlot | None:
    """Выбирает слот: по индексу → по имени файла → слот на этой полосе → глобальный (page 0)."""
    if slot_index is not None and 0 <= slot_index < len(slots) and slot_index not in used:
        used.add(slot_index)
        return slots[slot_index]
    norm = Path(filename).name.lower() if filename else ""
    if norm:
        for i, s in enumerate(slots):
            if i in used:
                continue
            sf = (s.filename or "").lower()
            if sf and (sf == norm or sf in norm or norm in sf):
                used.add(i)
                return s
    for i, s in enumerate(slots):
        if i in used:
            continue
        if s.page_index == page_index:
            used.add(i)
            return s
    for i, s in enumerate(slots):
        if i in used:
            continue
        if s.page_index == 0:
            used.add(i)
            return s
    return None


def _flow_to_preview(flow_lines) -> list[PreviewLine]:
    return [
        PreviewLine(
            runs=fl.runs, style=fl.style, column_index=fl.column_index,
            x_offset=fl.x_offset, width_pt=fl.width_pt, y_pt=fl.y_pt,
        )
        for fl in flow_lines
    ]


def build_layout(
    parsed: ParsedDocument,
    template: TemplateSpec,
    profile: TypographyProfile,
    ad_slots: list[AdSlot] | None = None,
) -> LayoutPlan:
    pw, ph = profile.page_width_pt(), profile.page_height_pt()
    blocks = parsed.blocks
    slot_queue = list(ad_slots or [])
    used_slot_indices: set[int] = set()

    pages: list[Page] = []
    chain_counter = 0
    page_idx = 0
    image_counter = 0
    column_obstacles: dict[int, list[ColumnObstacle]] = {}

    def content_for(page_index: int) -> Rect:
        return _content_area(profile, page_index)

    content = content_for(0)

    def new_page(drop_cap: bool = False) -> Page:
        nonlocal chain_counter, page_idx, column_obstacles
        column_obstacles = {}
        cols = _columns_for_page(content_for(page_idx), template)
        for c in cols:
            c.chain_index = chain_counter
            chain_counter += 1
        p = Page(index=page_idx, columns=cols, images=[], drop_cap=drop_cap)
        pages.append(p)
        page_idx += 1
        return p

    def sync_content() -> None:
        nonlocal content
        content = content_for(cur_page.index)

    cur_page = new_page(drop_cap=(template.accent_style == "tint_block" and not is_newspaper_template(template)))
    sync_content()
    col_i = 0
    newspaper = is_newspaper_template(template)
    gutter_pt = template.gutter_mm * MM_TO_PT

    def _base_y() -> float:
        y0 = cur_page.columns[0].rect.y
        if newspaper:
            return y0 + masthead_reserve_pt()
        return y0

    y_cursor = {i: _base_y() for i in range(len(cur_page.columns))}
    first_body_on_page = True
    awaiting_lead_photo = True
    awaiting_lead_para = False
    block_index = 0

    def col_bottom(i: int) -> float:
        return cur_page.columns[i].rect.y + cur_page.columns[i].rect.h

    def page_has_content() -> bool:
        if cur_page.images or cur_page.preview_lines:
            return True
        return any(y_cursor[i] > _base_y() + 2 for i in y_cursor)

    def _reset_cursors() -> dict[int, float]:
        return {i: _base_y() for i in range(len(cur_page.columns))}

    def goto_page(target: int) -> None:
        nonlocal cur_page, col_i, y_cursor, first_body_on_page
        while cur_page.index < target:
            cur_page = new_page()
            sync_content()
            col_i = 0
            first_body_on_page = True
            y_cursor = _reset_cursors()

    def force_new_page() -> None:
        nonlocal cur_page, col_i, y_cursor, first_body_on_page
        if not page_has_content():
            return
        cur_page = new_page()
        sync_content()
        col_i = 0
        first_body_on_page = True
        y_cursor = _reset_cursors()

    def _append_jump_line(from_page: Page, col_idx: int, target_human_page: int) -> None:
        if not profile.jump_lines or target_human_page < 2:
            return
        col = from_page.columns[col_idx]
        y = y_cursor.get(col_idx, col.rect.y)
        if y <= col.rect.y + 4:
            return
        from_page.preview_lines.append(PreviewLine(
            runs=[Run(text=f"Продолжение на стр. {target_human_page} »", italic=True)],
            style="jump_line",
            column_index=col_idx,
            y_pt=min(y + template.body_leading_pt * 0.3, col.rect.y + col.rect.h - 14),
        ))

    def ensure_space(needed: float) -> None:
        nonlocal cur_page, col_i, y_cursor, first_body_on_page
        col = cur_page.columns[col_i]
        remaining = col_bottom(col_i) - y_cursor[col_i]
        if 0 < remaining < template.body_leading_pt * 2.5 and needed > remaining:
            prev_page = cur_page
            prev_col = col_i
            col_i += 1
            if col_i >= len(cur_page.columns):
                if profile.jump_lines and page_has_content():
                    _append_jump_line(prev_page, prev_col, page_idx + 2)
                cur_page = new_page()
                sync_content()
                col_i = 0
                first_body_on_page = True
                y_cursor = _reset_cursors()
            return
        if y_cursor[col_i] + needed <= col_bottom(col_i):
            return
        prev_page = cur_page
        prev_col = col_i
        col_i += 1
        if col_i >= len(cur_page.columns):
            if profile.jump_lines and page_has_content():
                _append_jump_line(prev_page, prev_col, page_idx + 2)
            cur_page = new_page()
            sync_content()
            col_i = 0
            first_body_on_page = True
            y_cursor = _reset_cursors()

    def place_text_block(block: Block, style: str) -> None:
        nonlocal col_i, y_cursor, first_body_on_page, block_index
        col = cur_page.columns[col_i]
        obstacles = column_obstacles.get(col_i, [])

        if block.kind == "heading":
            ni = block_index + 1
            while ni < len(blocks) and blocks[ni].kind in ("caption", "image"):
                ni += 1
            if ni < len(blocks) and blocks[ni].kind in ("body", "list_item"):
                extra = template.body_leading_pt * 2
                ensure_space(template.body_leading_pt * 3 + extra)

        ensure_space(template.body_leading_pt * 2)
        col = cur_page.columns[col_i]
        obstacles = column_obstacles.get(col_i, [])

        flow_lines, end_y = flow_runs_into_lines(
            block.runs, style, template, col_i, col.rect.w,
            y_cursor[col_i], obstacles, _pil_font_loader,
            hyphenate=profile.hyphenation,
            language=profile.language,
        )
        cur_page.preview_lines.extend(_flow_to_preview(flow_lines))
        y_cursor[col_i] = end_y

        obs = column_obstacles.get(col_i, [])
        if obs:
            bottom = obstacle_bottom(obs)
            if y_cursor[col_i] < bottom + 8:
                y_cursor[col_i] = bottom + 8
            column_obstacles[col_i] = [o for o in obs if o.y_bottom > y_cursor[col_i]]

        if block.kind == "body":
            first_body_on_page = False

    def place_table_block(block: Block) -> None:
        nonlocal col_i, y_cursor
        if not block.table_rows:
            return
        ncols = max(len(row) for row in block.table_rows)
        col = cur_page.columns[col_i]
        row_h = template.body_leading_pt * 1.1
        table_h = row_h * len(block.table_rows) + 8
        ensure_space(table_h + 12)
        col = cur_page.columns[col_i]
        y0 = y_cursor[col_i]
        cell_w = col.rect.w / max(ncols, 1)
        row_texts: list[list[str]] = []
        for ri, row in enumerate(block.table_rows):
            cells = []
            for ci in range(ncols):
                if ci < len(row):
                    cells.append("".join(r.text for r in row[ci]).strip())
                else:
                    cells.append("")
            row_texts.append(cells)
            style = "table_header" if ri == 0 else "table_row"
            line_runs = [Run(text="  |  ".join(cells))]
            if ri == 0:
                line_runs = [Run(text="  |  ".join(cells), bold=True)]
            flow_lines, end_y = flow_runs_into_lines(
                line_runs, style, template, col_i, col.rect.w,
                y_cursor[col_i], column_obstacles.get(col_i, []), _pil_font_loader,
            )
            cur_page.preview_lines.extend(_flow_to_preview(flow_lines))
            y_cursor[col_i] = end_y
        cur_page.tables.append(TableFrame(
            rect=Rect(col.rect.x, y0, col.rect.w, y_cursor[col_i] - y0 + 4),
            rows=row_texts,
            header=True,
        ))
        y_cursor[col_i] += 10
        for i in range(len(cur_page.columns)):
            if i != col_i:
                y_cursor[i] = max(y_cursor[i], y_cursor[col_i])

    for block in blocks:
        if block.kind == "page_break":
            force_new_page()
            block_index += 1
            continue

        if block.kind == "heading" and block.level == 1 and profile.heading_starts_new_page:
            force_new_page()

        if block.kind == "heading" and block.level <= 2:
            awaiting_lead_photo = True
            awaiting_lead_para = True

        if block.kind == "image" and block.image_index is not None:
            role = block.image_role
            if block.image_index < len(parsed.images):
                role = parsed.images[block.image_index].role or role
            img_path = parsed.images[block.image_index].path if block.image_index < len(parsed.images) else None
            img_meta = parsed.images[block.image_index] if block.image_index < len(parsed.images) else None
            col = cur_page.columns[col_i]
            fname = (img_meta.original_name if img_meta else "") or (img_path.name if img_path else "")
            text_wrap = False
            wrap_side = "both"
            float_side = "left" if image_counter % 2 == 0 else "right"
            stroke = 0.0

            if newspaper and not is_ad_role(role) and not is_banner_role(role) and role != "logo":
                role = refine_photo_role(
                    role, img_path, fname,
                    first_after_heading=awaiting_lead_photo,
                )
                if role == "lead":
                    awaiting_lead_photo = False

            if is_ad_role(role):
                w_mm = block.width_mm or (img_meta.width_mm if img_meta else None)
                h_mm = block.height_mm or (img_meta.height_mm if img_meta else None)
                w_mm, h_mm = resolve_ad_size_mm(img_path, w_mm, h_mm, filename=fname)
                slot = _take_ad_slot(
                    slot_queue, used_slot_indices, cur_page.index,
                    filename=fname, slot_index=block.slot_index,
                ) if slot_queue else None
                label_h = AD_LABEL_HEIGHT_MM * MM_TO_PT if profile.mark_advertising else 0
                if slot:
                    if slot.page_index > cur_page.index:
                        goto_page(slot.page_index)
                    x = slot.x_mm * MM_TO_PT
                    y = slot.y_mm * MM_TO_PT
                    w_pt, h_pt = slot.width_mm * MM_TO_PT, slot.height_mm * MM_TO_PT
                    w_mm, h_mm = slot.width_mm, slot.height_mm
                else:
                    w_pt, h_pt = w_mm * MM_TO_PT, h_mm * MM_TO_PT
                    y = max(y_cursor.values())
                    ensure_space(label_h + h_pt + 12)
                    y = max(y_cursor.values()) + label_h
                    x = content.x + max(0.0, (content.w - w_pt) / 2)
                img_rect = Rect(x, y, w_pt, h_pt)
                gap = 12
                for i in y_cursor:
                    y_cursor[i] = max(y_cursor[i], img_rect.y + img_rect.h + gap)
                col_i = 0
                text_wrap = True
                wrap_side = "both"
                stroke = stroke_pt_for_role(role)
            elif is_banner_role(role):
                y = max(y_cursor.values())
                img_rect = _image_rect_for_strategy(
                    template, cur_page.columns[0].rect, image_counter,
                    role="banner", content=content, img_path=img_path,
                )
                img_rect = Rect(img_rect.x, y, img_rect.w, img_rect.h)
                gap = 14
                for i in y_cursor:
                    y_cursor[i] = img_rect.y + img_rect.h + gap
                col_i = 0
            elif newspaper:
                # Газетные размеры: lead на 2 кол., фото на всю колонку (не 44%)
                y = max(y_cursor.values()) if role in ("lead", "mid") else y_cursor[col_i]
                n_cols = len(cur_page.columns)
                col_w = cur_page.columns[0].rect.w
                x, y, w, h = newspaper_image_rect(
                    content_x=content.x, content_w=content.w, y=y,
                    col_w=col_w, gutter_pt=gutter_pt, n_cols=n_cols,
                    role=role, img_path=img_path, page_height_pt=ph,
                    col_x=col.rect.x,
                )
                if role not in ("lead", "mid"):
                    x = col.rect.x
                    y = y_cursor[col_i]
                img_rect = Rect(x, y, w, h)
                gap = 10
                if role in ("lead", "mid"):
                    for i in y_cursor:
                        y_cursor[i] = max(y_cursor[i], img_rect.y + img_rect.h + gap)
                    # текст основной статьи — с колонок под lead (1..n)
                    col_i = 1 if n_cols >= 3 else 0
                else:
                    y_cursor[col_i] = img_rect.y + img_rect.h + gap
                text_wrap = True
                wrap_side = "both"
                stroke = stroke_pt_for_role(role)
            elif template.image_strategy in ("column_span", "banner_strip") and content is not None:
                y = max(y_cursor.values())
                img_rect = _image_rect_for_strategy(
                    template, col.rect, image_counter, aspect=0.8,
                    role=role, content=content, img_path=img_path,
                )
                img_rect = Rect(img_rect.x, y, img_rect.w, img_rect.h)
                gap = 12
                for i in y_cursor:
                    y_cursor[i] = img_rect.y + img_rect.h + gap
                col_i = 0
                text_wrap = True
                wrap_side = "both"
            elif _should_float(role, template):
                aspect = 0.78 if image_counter % 2 == 0 else 0.92
                img_rect = _image_rect_for_strategy(
                    template, col.rect, image_counter, aspect,
                    role=role, content=content, img_path=img_path,
                    float_side=float_side,
                )
                img_rect = Rect(img_rect.x, y_cursor[col_i], img_rect.w, img_rect.h)
                column_obstacles.setdefault(col_i, []).append(ColumnObstacle(
                    y_top=img_rect.y,
                    y_bottom=img_rect.y + img_rect.h,
                    side=float_side,
                    float_width=img_rect.w,
                ))
                text_wrap = True
                wrap_side = float_side
                gap = 8
            else:
                aspect = 0.75 if image_counter % 2 == 0 else 0.95
                img_rect = _image_rect_for_strategy(
                    template, col.rect, image_counter, aspect,
                    role=role, content=content, img_path=img_path,
                )
                img_rect = Rect(img_rect.x, y_cursor[col_i], img_rect.w, img_rect.h)
                gap = 10
                y_cursor[col_i] += img_rect.h + gap
                text_wrap = True
                wrap_side = "both"

            anchor = _nearest_heading(blocks, block_index)
            ad_w = ad_h = None
            if is_ad_role(role) and img_path:
                ad_w, ad_h = resolve_ad_size_mm(
                    img_path, block.width_mm, block.height_mm, filename=fname,
                )
            cur_page.images.append(ImageFrame(
                rect=img_rect,
                image_index=block.image_index,
                caption=block.caption,
                anchor_heading=anchor,
                image_role=role,
                width_mm=ad_w,
                height_mm=ad_h,
                show_ad_label=profile.mark_advertising and is_ad_role(role),
                text_wrap=text_wrap,
                wrap_side=wrap_side,
                stroke_pt=stroke,
            ))
            if block.caption:
                cap_block = Block(kind="caption", runs=[Run(text=block.caption, italic=True)])
                place_text_block(cap_block, "caption")
            image_counter += 1
            block_index += 1
            continue

        if block.kind == "caption":
            place_text_block(block, "caption")
            block_index += 1
            continue

        if block.kind == "table":
            place_table_block(block)
            block_index += 1
            continue

        if block.kind == "footnote_block":
            place_text_block(block, "footnote")
            block_index += 1
            continue

        style = f"h{block.level}" if block.kind == "heading" else (
            "list" if block.kind == "list_item" else "body")
        if (
            newspaper
            and style == "body"
            and awaiting_lead_para
            and block.kind == "body"
        ):
            style = "lead"
            awaiting_lead_para = False
            # лид на ширину 2 колонок: временно расширяем
            if len(cur_page.columns) >= 2:
                col = cur_page.columns[col_i if col_i < len(cur_page.columns) else 0]
                # place across 2 cols by using wider measure
                wide_w = col.rect.w * 2 + gutter_pt
                ensure_space(template.body_leading_pt * 3)
                obstacles = column_obstacles.get(col_i, [])
                lead_runs = [Run(text=r.text, bold=True, italic=r.italic) for r in block.runs] or block.runs
                flow_lines, end_y = flow_runs_into_lines(
                    lead_runs, "lead", template, col_i, wide_w,
                    y_cursor[col_i], obstacles, _pil_font_loader,
                    hyphenate=profile.hyphenation,
                    language=profile.language,
                )
                cur_page.preview_lines.extend(_flow_to_preview(flow_lines))
                y_cursor[col_i] = end_y
                if col_i + 1 < len(cur_page.columns):
                    y_cursor[col_i + 1] = max(y_cursor[col_i + 1], end_y)
                first_body_on_page = False
                block_index += 1
                continue

        place_text_block(block, style)
        block_index += 1

    if not pages:
        pages.append(new_page())

    plan = LayoutPlan(
        template=template, profile=profile, pages=pages,
        dominant_accent_rgb=_accent_for_template(template, parsed),
        keywords=extract_keywords(parsed.full_text),
        page_width_pt=pw,
        page_height_pt=ph,
        used_ad_slot_indices=sorted(used_slot_indices),
    )
    for page in plan.pages:
        for i, img in enumerate(page.images):
            if not img.element_id:
                img.element_id = f"p{page.index}_img{i}"
    return plan
