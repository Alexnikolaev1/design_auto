"""
Экспорт print-ready PDF без InDesign.

По умолчанию — векторный PDF (редактируемый текст, линии, CMYK для печати).
При сбое векторного рендера — fallback на растровый 300 DPI.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import fitz

from app.config import TypographyProfile, FONTS_DIR
from app.export.color_convert import (
    use_cmyk_output, style_text_color, rgb_to_cmyk_unit,
)
from app.layout import fonts as font_manager
from app.layout.ad_units import AD_LABEL_TEXT
from app.layout.engine import LayoutPlan, Page
from app.layout.metrics import advance_width_pt
from app.layout.smart_crop import smart_crop_cover
from app.parser.docx_parser import Run
from app.preview.page_render import render_page_image, PRINT_SCALE

logger = logging.getLogger(__name__)


def _draw_crop_marks(page: fitz.Page, trim: fitz.Rect, mark_len: float = 12, offset: float = 3,
                     use_cmyk: bool = False) -> None:
    color = rgb_to_cmyk_unit(0, 0, 0) if use_cmyk else (0, 0, 0)
    corners = [
        (trim.x0, trim.y0), (trim.x1, trim.y0),
        (trim.x0, trim.y1), (trim.x1, trim.y1),
    ]
    for cx, cy in corners:
        hx = -1 if cx == trim.x0 else 1
        hy = -1 if cy == trim.y0 else 1
        page.draw_line(
            fitz.Point(cx, cy - hy * offset),
            fitz.Point(cx, cy - hy * (offset + mark_len)),
            color=color, width=0.25,
        )
        page.draw_line(
            fitz.Point(cx - hx * offset, cy),
            fitz.Point(cx - hx * (offset + mark_len), cy),
            color=color, width=0.25,
        )


def _line_typography(style: str, template, plan: LayoutPlan):
    is_heading = style.startswith("h")
    if is_heading:
        lvl = min(int(style[1]) if len(style) > 1 and style[1].isdigit() else 1, 4)
        size_pt = template.h_size_pt.get(lvl, 12)
        leading = size_pt * 1.15
        base_ps = template.heading_font_bold
    elif style == "caption":
        size_pt = template.body_size_pt * 0.85
        leading = size_pt * 1.2
        base_ps = template.body_font_italic
    elif style == "footnote":
        size_pt = template.body_size_pt * 0.88
        leading = size_pt * 1.15
        base_ps = template.body_font_italic
    elif style in ("table_row", "table_header"):
        size_pt = template.body_size_pt * (0.92 if style == "table_header" else 0.9)
        leading = size_pt * 1.2
        base_ps = template.body_font_bold if style == "table_header" else template.body_font
    elif style == "jump_line":
        size_pt = template.body_size_pt * 0.82
        leading = size_pt * 1.2
        base_ps = template.body_font_italic
    elif style == "ad_label":
        size_pt = 7.5
        leading = 10
        base_ps = template.body_font_italic
    else:
        size_pt = template.body_size_pt
        leading = template.body_leading_pt
        base_ps = template.body_font
    return size_pt, leading, base_ps, is_heading


class _FontCache:
    def __init__(self) -> None:
        self._fonts: dict[str, fitz.Font] = {}
        self._bundled: Path | None = None

    def _bundled_font(self) -> Path | None:
        if self._bundled is None:
            for candidate in sorted(FONTS_DIR.glob("*.ttf")):
                self._bundled = candidate
                break
        return self._bundled

    def get(self, resolved) -> fitz.Font | None:
        path = resolved.path if resolved else None
        if not path or not path.exists():
            path = self._bundled_font()
        if not path or not path.exists():
            return None
        key = str(path.resolve())
        if key not in self._fonts:
            self._fonts[key] = fitz.Font(fontfile=key)
        return self._fonts[key]


def _resolve_run_font(template, style: str, run: Run, is_heading: bool, base_ps: str):
    if is_heading or style in ("caption", "jump_line", "ad_label"):
        bold = False
        italic = style in ("caption", "jump_line", "ad_label")
        ps = base_ps
    else:
        bold = bool(run.bold)
        italic = bool(run.italic) or style == "footnote"
        ps = base_ps
        if bold:
            ps = template.body_font_bold
        elif italic:
            ps = template.body_font_italic
    return font_manager.resolve_variant(ps, bold=bold, italic=italic)


def _image_stream(path: Path, rect_w: float, rect_h: float, dpi: float,
                  smart_crop: bool, use_cmyk: bool) -> bytes:
    from PIL import Image

    scale = max(1.0, dpi / 72.0)
    tw = max(1, int(rect_w * scale))
    th = max(1, int(rect_h * scale))
    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if smart_crop:
        img = smart_crop_cover(img, tw, th)
    else:
        iw, ih = img.size
        pr = iw / max(ih, 1)
        tr = tw / max(th, 1)
        if pr > tr:
            nh, nw = th, int(th * pr)
        else:
            nw, nh = tw, int(tw / pr)
        img = img.resize((max(nw, 1), max(nh, 1)), Image.Resampling.LANCZOS)
        left = (img.width - tw) // 2
        top = (img.height - th) // 2
        img = img.crop((left, top, left + tw, top + th))
    buf = io.BytesIO()
    if use_cmyk:
        img = img.convert("CMYK")
        img.save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _draw_vector_page(
    pdf_page: fitz.Page,
    plan: LayoutPlan,
    page: Page,
    image_paths: list[Path],
    ox: float,
    oy: float,
    font_cache: _FontCache,
    use_cmyk: bool,
    smart_crop: bool,
    img_dpi: float,
) -> None:
    template = plan.template
    accent = plan.dominant_accent_rgb
    tint = tuple(min(255, c + 200) for c in accent)
    cs = fitz.csCMYK if use_cmyk else fitz.csRGB
    tw = fitz.TextWriter(pdf_page.rect, color=cs)

    if page.drop_cap and template.accent_style == "tint_block" and page.columns:
        col0 = page.columns[0].rect
        fill = rgb_to_cmyk_unit(*tint) if use_cmyk else tuple(c / 255 for c in tint)
        pdf_page.draw_rect(
            fitz.Rect(col0.x + ox, col0.y + oy, col0.x + col0.w + ox, col0.y + 40 + oy),
            color=fill, fill=fill,
        )

    for img_frame in page.images:
        if img_frame.image_index >= len(image_paths):
            continue
        ipath = image_paths[img_frame.image_index]
        rect = fitz.Rect(
            img_frame.rect.x + ox, img_frame.rect.y + oy,
            img_frame.rect.x + img_frame.rect.w + ox,
            img_frame.rect.y + img_frame.rect.h + oy,
        )
        try:
            stream = _image_stream(
                ipath, img_frame.rect.w, img_frame.rect.h,
                img_dpi, smart_crop, use_cmyk,
            )
            pdf_page.insert_image(rect, stream=stream)
            if getattr(img_frame, "image_role", "") == "ad":
                stroke = rgb_to_cmyk_unit(80, 80, 80) if use_cmyk else (80 / 255, 80 / 255, 80 / 255)
                pdf_page.draw_rect(rect, color=stroke, width=0.5)
            if getattr(img_frame, "show_ad_label", False):
                label_resolved = font_manager.resolve_variant(
                    template.body_font_italic, bold=False, italic=True,
                )
                label_font = font_cache.get(label_resolved)
                if label_font:
                    label_y = rect.y0 - 2
                    label_color = style_text_color("ad_label", accent, use_cmyk)
                    tw.append(
                        (rect.x0, label_y), AD_LABEL_TEXT,
                        font=label_font, fontsize=7.5,
                    )
        except Exception:
            fill = rgb_to_cmyk_unit(220, 220, 220) if use_cmyk else (220 / 255, 220 / 255, 220 / 255)
            pdf_page.draw_rect(rect, color=fill, fill=fill)

    for table_frame in getattr(page, "tables", []):
        tx0 = table_frame.rect.x + ox
        ty0 = table_frame.rect.y + oy
        tx1 = tx0 + table_frame.rect.w
        ty1 = ty0 + table_frame.rect.h
        stroke = rgb_to_cmyk_unit(120, 120, 120) if use_cmyk else (120 / 255, 120 / 255, 120 / 255)
        grid = rgb_to_cmyk_unit(180, 180, 180) if use_cmyk else (180 / 255, 180 / 255, 180 / 255)
        pdf_page.draw_rect(fitz.Rect(tx0, ty0, tx1, ty1), color=stroke, width=0.5)
        nrows = len(table_frame.rows)
        if nrows > 1:
            for ri in range(1, nrows):
                y = ty0 + (ty1 - ty0) * ri / nrows
                pdf_page.draw_line(fitz.Point(tx0, y), fitz.Point(tx1, y), color=grid, width=0.25)
        ncols = max((len(r) for r in table_frame.rows), default=0)
        if ncols > 1:
            for ci in range(1, ncols):
                x = tx0 + (tx1 - tx0) * ci / ncols
                pdf_page.draw_line(fitz.Point(x, ty0), fitz.Point(x, ty1), color=grid, width=0.25)

    col_cursors = {i: col.rect.y for i, col in enumerate(page.columns)}
    for line in page.preview_lines:
        col = page.columns[line.column_index]
        y = line.y_pt if line.y_pt is not None else col_cursors[line.column_index]
        x = col.rect.x + (line.x_offset or 0.0)
        size_pt, leading, base_ps, is_heading = _line_typography(line.style, template, plan)

        if y + leading > col.rect.y + col.rect.h + 40:
            continue

        cx = x + ox
        y_top = y + oy
        y_base = y_top + size_pt * 0.82

        for run in line.runs:
            if not run.text:
                continue
            resolved = _resolve_run_font(template, line.style, run, is_heading, base_ps)
            font = font_cache.get(resolved)
            if font is None:
                continue
            tw.append((cx, y_base), run.text, font=font, fontsize=size_pt)
            adv = advance_width_pt(resolved.path, run.text, size_pt) if resolved.path else 0.0
            cx += adv if adv and adv > 0 else size_pt * len(run.text) * 0.45

        if line.style == "h1" and template.accent_style == "rule":
            rule_y = y_top + leading * 0.9
            line_w = line.width_pt or col.rect.w
            rule_color = style_text_color("h1", accent, use_cmyk)
            pdf_page.draw_line(
                fitz.Point(x + ox, rule_y),
                fitz.Point(x + line_w + ox, rule_y),
                color=rule_color, width=1.0,
            )

        if line.y_pt is None:
            col_cursors[line.column_index] += leading
        else:
            col_cursors[line.column_index] = max(col_cursors[line.column_index], y + leading)

    tw.write_text(pdf_page)


def export_vector_pdf(
    plan: LayoutPlan,
    image_paths: list[Path],
    out_path: Path,
    dpi: float = 300.0,
) -> Path:
    profile = plan.profile
    use_cmyk = use_cmyk_output(profile)
    smart_crop = getattr(profile, "smart_crop", True)
    page_w = plan.page_width_pt or profile.page_width_pt()
    page_h = plan.page_height_pt or profile.page_height_pt()
    bleed = profile.bleed_pt() if profile.bleed_mm > 0 else 0.0
    media_w = page_w + 2 * bleed
    media_h = page_h + 2 * bleed
    font_cache = _FontCache()

    doc = fitz.open()
    try:
        for page in plan.pages:
            pdf_page = doc.new_page(width=media_w, height=media_h)
            _draw_vector_page(
                pdf_page, plan, page, image_paths,
                ox=bleed, oy=bleed, font_cache=font_cache,
                use_cmyk=use_cmyk, smart_crop=smart_crop, img_dpi=dpi,
            )
            if profile.print_marks and bleed > 0:
                trim = fitz.Rect(bleed, bleed, bleed + page_w, bleed + page_h)
                _draw_crop_marks(pdf_page, trim, use_cmyk=use_cmyk)
                stroke = rgb_to_cmyk_unit(128, 128, 128) if use_cmyk else (0.5, 0.5, 0.5)
                pdf_page.draw_rect(trim, color=stroke, width=0.25)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.set_metadata({
            "title": f"LayoutGenius {plan.template.id}",
            "creator": "LayoutGenius",
            "producer": "LayoutGenius Vector PDF",
            "format": profile.page_format,
        })
        doc.save(str(out_path), deflate=True, garbage=4)
    finally:
        doc.close()
    return out_path


def export_raster_pdf(
    plan: LayoutPlan,
    image_paths: list[Path],
    out_path: Path,
    dpi: float = 300.0,
) -> Path:
    profile = plan.profile
    page_w = plan.page_width_pt or profile.page_width_pt()
    page_h = plan.page_height_pt or profile.page_height_pt()
    bleed = profile.bleed_pt() if profile.bleed_mm > 0 else 0.0
    scale = dpi / 72.0
    media_w = page_w + 2 * bleed
    media_h = page_h + 2 * bleed

    doc = fitz.open()
    try:
        for page in plan.pages:
            pil_img = render_page_image(plan, page, image_paths, scale=scale)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG", optimize=True)
            pdf_page = doc.new_page(width=media_w, height=media_h)
            trim = fitz.Rect(bleed, bleed, bleed + page_w, bleed + page_h)
            pdf_page.insert_image(trim, stream=buf.getvalue())
            if profile.print_marks and bleed > 0:
                _draw_crop_marks(pdf_page, trim)
                pdf_page.draw_rect(trim, color=(0.5, 0.5, 0.5), width=0.25)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.set_metadata({
            "title": f"LayoutGenius {plan.template.id}",
            "creator": "LayoutGenius",
            "producer": "LayoutGenius Raster PDF",
            "format": profile.page_format,
        })
        doc.save(str(out_path), deflate=True, garbage=4)
    finally:
        doc.close()
    return out_path


def export_print_pdf(
    plan: LayoutPlan,
    image_paths: list[Path],
    out_path: Path,
    dpi: float = 300.0,
    export_info: dict | None = None,
) -> Path:
    """Векторный PDF; при ошибке — растровый fallback."""
    profile = plan.profile
    use_cmyk = use_cmyk_output(profile)
    vector_ok = False
    if getattr(profile, "pdf_vector_export", True):
        try:
            export_vector_pdf(plan, image_paths, out_path, dpi=dpi)
            vector_ok = (
                out_path.exists()
                and pdf_page_count(out_path) == len(plan.pages)
                and pdf_has_selectable_text(out_path)
            )
            if out_path.exists() and not vector_ok:
                logger.warning("Vector PDF missing text — raster fallback")
        except Exception as exc:
            logger.warning("Vector PDF failed, falling back to raster: %s", exc)
            vector_ok = False

    if not vector_ok:
        export_raster_pdf(plan, image_paths, out_path, dpi=dpi)

    if export_info is not None:
        export_info.update({
            "vector": vector_ok,
            "cmyk": use_cmyk and vector_ok,
            "dpi": dpi if not vector_ok else None,
            "image_dpi": dpi,
            "text_verified": vector_ok,
        })
    return out_path


def pdf_page_count(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    try:
        return doc.page_count
    finally:
        doc.close()


def pdf_has_selectable_text(pdf_path: Path) -> bool:
    """Проверка, что PDF содержит извлекаемый текст (векторный слой)."""
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(min(doc.page_count, 3)):
            if doc[i].get_text().strip():
                return True
        return False
    finally:
        doc.close()
