"""Общий рендер одной полосы в PIL (PNG-превью и PDF)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.layout.engine import LayoutPlan, Page
from app.layout import fonts as font_manager
from app.layout.smart_crop import smart_crop_cover
from app.parser.docx_parser import Run

DEFAULT_SCALE = 2.0
PRINT_SCALE = 300.0 / 72.0  # ~300 DPI относительно пунктов


def _font_cache(scale: float):
    cache: dict[tuple[str, int, bool, bool], ImageFont.FreeTypeFont] = {}

    def get(ps_name: str, size_pt: float, bold: bool = False, italic: bool = False):
        key = (ps_name, int(round(size_pt)), bold, italic)
        if key not in cache:
            resolved = font_manager.resolve_variant(ps_name, bold=bold, italic=italic)
            px = max(6, int(round(size_pt * scale)))
            try:
                cache[key] = (
                    ImageFont.truetype(str(resolved.path), px)
                    if resolved.path else ImageFont.load_default()
                )
            except Exception:
                cache[key] = ImageFont.load_default()
        return cache[key]

    return get


def _draw_runs(draw, x: float, y: float, runs: list[Run], style: str,
               template, plan: LayoutPlan, get_font, scale: float) -> float:
    is_heading = style.startswith("h")
    is_caption = style == "caption"
    if style == "h3" and getattr(template, "rubric_font", ""):
        size_pt = template.h_size_pt.get(3, 14)
        leading = size_pt * 1.15
        color = (20, 20, 20)
        base_ps = template.rubric_font
    elif is_heading:
        lvl = min(int(style[1]) if len(style) > 1 and style[1].isdigit() else 1, 4)
        size_pt = template.h_size_pt.get(lvl, 12)
        leading = size_pt * 1.15
        color = plan.dominant_accent_rgb
        base_ps = template.heading_font_bold
    elif style == "lead":
        size_pt = round(template.body_size_pt * 1.15, 1)
        leading = size_pt * 1.22
        color = (20, 20, 20)
        base_ps = template.body_font_bold
    elif is_caption:
        size_pt = template.body_size_pt * 0.85
        leading = size_pt * 1.2
        color = (90, 90, 90)
        base_ps = template.body_font_italic
    elif style == "footnote":
        size_pt = template.body_size_pt * 0.88
        leading = size_pt * 1.15
        color = (70, 70, 70)
        base_ps = template.body_font_italic
    elif style in ("table_row", "table_header"):
        size_pt = template.body_size_pt * (0.92 if style == "table_header" else 0.9)
        leading = size_pt * 1.2
        color = (30, 30, 30)
        base_ps = template.body_font_bold if style == "table_header" else template.body_font
    elif style == "jump_line":
        size_pt = template.body_size_pt * 0.82
        leading = size_pt * 1.2
        color = (100, 100, 100)
        base_ps = template.body_font_italic
    elif style == "ad_label":
        size_pt = 7.5
        leading = 10
        color = (60, 60, 60)
        base_ps = template.body_font_italic
    else:
        size_pt = template.body_size_pt
        leading = template.body_leading_pt
        color = (25, 25, 25)
        base_ps = template.body_font

    cx = x
    for run in runs:
        ps = base_ps
        if not is_heading and style not in ("jump_line", "caption", "ad_label"):
            if run.bold:
                ps = template.body_font_bold
            elif run.italic:
                ps = template.body_font_italic
        resolved = font_manager.resolve_variant(
            ps, bold=run.bold and not is_heading and style not in ("caption", "jump_line", "ad_label"),
            italic=(run.italic or style in ("caption", "jump_line", "ad_label")) and not is_heading,
        )
        adv = None
        if resolved.path:
            from app.layout.metrics import advance_width_pt
            adv = advance_width_pt(resolved.path, run.text, size_pt)
        f = get_font(ps, size_pt,
                     bold=run.bold and not is_heading and style not in ("caption", "jump_line", "ad_label"),
                     italic=(run.italic or style in ("caption", "jump_line", "ad_label")) and not is_heading)
        draw.text((cx, y), run.text, font=f, fill=color)
        if adv is not None and adv > 0:
            cx += adv * scale
        else:
            bbox = f.getbbox(run.text)
            cx += bbox[2] - bbox[0]
    return leading


def render_page_image(
    plan: LayoutPlan,
    page: Page,
    image_paths: list[Path],
    scale: float = DEFAULT_SCALE,
) -> Image.Image:
    template = plan.template
    accent = plan.dominant_accent_rgb
    tint = tuple(min(255, c + 200) for c in accent)
    get_font = _font_cache(scale)

    page_w = plan.page_width_pt or plan.profile.page_width_pt()
    page_h = plan.page_height_pt or plan.profile.page_height_pt()
    px_w = int(page_w * scale)
    px_h = int(page_h * scale)

    img = Image.new("RGB", (px_w, px_h), "white")
    draw = ImageDraw.Draw(img)

    from app.layout.newspaper import is_newspaper_template, masthead_reserve_pt
    from app.layout.okolica_profile import ACCENT_LOGO_RGB

    if is_newspaper_template(template):
        m = plan.profile.margins_pt(page.index)
        mh = masthead_reserve_pt()
        # фиолетовая «блямба» логотипа + название
        logo_x = m["left"] * scale
        logo_y = (m["top"] * 0.35) * scale
        logo_w = 78 * scale
        logo_h = min(mh * scale * 0.95, 28 * scale)
        draw.rounded_rectangle(
            [logo_x, logo_y, logo_x + logo_w, logo_y + logo_h],
            radius=max(2, int(4 * scale)), fill=ACCENT_LOGO_RGB,
        )
        logo_font = get_font(
            getattr(template, "rubric_font", "") or template.heading_font_bold,
            9, bold=False, italic=True,
        )
        draw.text(
            (logo_x + 4 * scale, logo_y + 2 * scale),
            "Сибирская околица",
            font=logo_font, fill=(255, 255, 255),
        )
        issue_font = get_font(template.body_font, 8, False, False)
        draw.text(
            (logo_x + logo_w + 8 * scale, logo_y + 4 * scale),
            "газета · образец вёрстки",
            font=issue_font, fill=(80, 80, 80),
        )

    if plan.profile.print_marks:
        bleed_px = plan.profile.bleed_pt() * scale
        draw.rectangle(
            [bleed_px, bleed_px, px_w - bleed_px, px_h - bleed_px],
            outline=(180, 180, 180), width=max(1, int(scale)),
        )

    if page.drop_cap and template.accent_style == "tint_block" and page.columns:
        col0 = page.columns[0].rect
        draw.rectangle(
            [col0.x * scale, col0.y * scale,
             (col0.x + col0.w) * scale, (col0.y + 40) * scale],
            fill=tint,
        )

    for img_frame in page.images:
        if img_frame.image_index >= len(image_paths):
            continue
        try:
            photo = Image.open(image_paths[img_frame.image_index]).convert("RGB")
            box = (
                int(img_frame.rect.x * scale), int(img_frame.rect.y * scale),
                int((img_frame.rect.x + img_frame.rect.w) * scale),
                int((img_frame.rect.y + img_frame.rect.h) * scale),
            )
            target_w, target_h = box[2] - box[0], box[3] - box[1]
            if getattr(plan.profile, "smart_crop", True):
                photo = smart_crop_cover(photo, max(1, target_w), max(1, target_h))
            else:
                photo_ratio = photo.width / photo.height
                target_ratio = target_w / max(target_h, 1)
                if photo_ratio > target_ratio:
                    new_h, new_w = target_h, int(target_h * photo_ratio)
                else:
                    new_w, new_h = target_w, int(target_w / photo_ratio)
                photo = photo.resize((max(new_w, 1), max(new_h, 1)))
                left = (photo.width - target_w) // 2
                top = (photo.height - target_h) // 2
                photo = photo.crop((left, top, left + target_w, top + target_h))
            img.paste(photo, (box[0], box[1]))
            stroke = getattr(img_frame, "stroke_pt", 0) or 0
            if stroke > 0 or getattr(img_frame, "image_role", "") == "ad":
                wline = max(1, int(scale * max(stroke, 0.5)))
                draw.rectangle(box, outline=(30, 30, 30), width=wline)
            if getattr(img_frame, "show_ad_label", False):
                from app.layout.ad_units import AD_LABEL_TEXT
                label_font = get_font(template.body_font_italic, 7.5, italic=True)
                label_y = box[1] - int(10 * scale)
                draw.text((box[0], max(0, label_y)), AD_LABEL_TEXT,
                          font=label_font, fill=(60, 60, 60))
        except Exception:
            draw.rectangle(
                [img_frame.rect.x * scale, img_frame.rect.y * scale,
                 (img_frame.rect.x + img_frame.rect.w) * scale,
                 (img_frame.rect.y + img_frame.rect.h) * scale],
                fill=(220, 220, 220),
            )

    for table_frame in getattr(page, "tables", []):
        tx0 = int(table_frame.rect.x * scale)
        ty0 = int(table_frame.rect.y * scale)
        tx1 = int((table_frame.rect.x + table_frame.rect.w) * scale)
        ty1 = int((table_frame.rect.y + table_frame.rect.h) * scale)
        draw.rectangle([tx0, ty0, tx1, ty1], outline=(120, 120, 120), width=max(1, int(scale * 0.5)))
        nrows = len(table_frame.rows)
        if nrows > 1:
            for ri in range(1, nrows):
                y = ty0 + int((ty1 - ty0) * ri / nrows)
                draw.line([tx0, y, tx1, y], fill=(180, 180, 180), width=1)
        ncols = max((len(r) for r in table_frame.rows), default=0)
        if ncols > 1:
            for ci in range(1, ncols):
                x = tx0 + int((tx1 - tx0) * ci / ncols)
                draw.line([x, ty0, x, ty1], fill=(180, 180, 180), width=1)

    col_cursors = {i: col.rect.y for i, col in enumerate(page.columns)}
    for line in page.preview_lines:
        col = page.columns[line.column_index]
        y = line.y_pt if line.y_pt is not None else col_cursors[line.column_index]
        x = col.rect.x + (line.x_offset or 0.0)
        leading = template.body_leading_pt
        if line.style.startswith("h"):
            lvl = min(int(line.style[1]) if len(line.style) > 1 else 1, 4)
            leading = template.h_size_pt.get(lvl, 12) * 1.15
        elif line.style == "caption":
            leading = template.body_size_pt * 0.85 * 1.2
        elif line.style == "footnote":
            leading = template.body_size_pt * 0.88 * 1.15
        elif line.style in ("table_row", "table_header"):
            leading = template.body_size_pt * 0.9 * 1.2
        elif line.style == "jump_line":
            leading = template.body_size_pt * 0.82 * 1.2
        elif line.style == "ad_label":
            leading = 10

        if y + leading > col.rect.y + col.rect.h + 40:
            continue

        _draw_runs(draw, x * scale, y * scale, line.runs, line.style, template, plan, get_font, scale)

        if line.style == "h1" and template.accent_style == "rule":
            line_w = line.width_pt or col.rect.w
            draw.line(
                [x * scale, (y + leading * 0.9) * scale,
                 (x + line_w) * scale, (y + leading * 0.9) * scale],
                fill=accent, width=max(1, int(scale)),
            )
        if line.y_pt is None:
            col_cursors[line.column_index] += leading
        else:
            col_cursors[line.column_index] = max(col_cursors[line.column_index], y + leading)

    return img
