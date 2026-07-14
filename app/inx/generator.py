"""
Генератор INX-документа для Adobe InDesign CS3 (DOMVersion 5.0).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from lxml import etree

from app.config import TypographyProfile, MM_TO_PT
from app.layout.engine import LayoutPlan
from app.layout import fonts as font_manager
from app.layout.templates import TemplateSpec
from app.parser.docx_parser import ParsedDocument, Block, Run


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _rgb_to_cmyk(rgb: tuple[int, int, int]) -> tuple[float, float, float, float]:
    r, g, b = [c / 255.0 for c in rgb]
    k = 1 - max(r, g, b)
    if k >= 1.0:
        return (0.0, 0.0, 0.0, 100.0)
    c = (1 - r - k) / (1 - k)
    m = (1 - g - k) / (1 - k)
    y = (1 - b - k) / (1 - k)
    return (round(c * 100, 2), round(m * 100, 2), round(y * 100, 2), round(k * 100, 2))


STYLE_MAP = {
    "h1": "Заголовок 1", "h2": "Заголовок 2", "h3": "Заголовок 3",
    "h4": "Заголовок 4", "body": "Основной текст", "list": "Список",
    "caption": "Основной текст", "footnote": "Сноска",
    "table_row": "Таблица", "table_header": "Таблица",
}


def _build_story_from_preview_lines(
    doc: etree.Element,
    lines: list,
    template: TemplateSpec,
    font_family_map: dict,
    color_black: str,
    color_accent: str,
) -> str:
    """Создаёт Story с точным содержимым колонки (как в preview_lines)."""
    story_id = f"Story/u{_uid()}"
    story_el = etree.SubElement(doc, "Story")
    story_el.set("Self", story_id)
    story_el.set("AppliedTOCStyle", "n")
    story_el.set("TrackChanges", "false")

    if not lines:
        psr = etree.SubElement(story_el, "ParagraphStyleRange")
        psr.set("AppliedParagraphStyle", "ParagraphStyle/Основной текст")
        _append_runs_to_paragraph(psr, [Run(text="")], template, "body",
                                   font_family_map, color_black, color_accent)
        etree.SubElement(psr, "Br")
        return story_id

    for line in lines:
        style_key = line.style if line.style != "caption" else "caption"
        if style_key.startswith("h"):
            style_name = STYLE_MAP.get(style_key, "Основной текст")
        elif style_key == "list":
            style_name = "Список"
        elif style_key in ("footnote", "table_row", "table_header"):
            style_name = STYLE_MAP.get(style_key, "Основной текст")
        else:
            style_name = "Основной текст"
        psr = etree.SubElement(story_el, "ParagraphStyleRange")
        psr.set("AppliedParagraphStyle", f"ParagraphStyle/{style_name}")
        x_off = getattr(line, "x_offset", 0.0) or 0.0
        if x_off > 0.5:
            psr.set("LeftIndent", str(round(x_off, 2)))
        _append_runs_to_paragraph(psr, line.runs, template, style_key,
                                   font_family_map, color_black, color_accent)
        etree.SubElement(psr, "Br")
    return story_id


def _append_runs_to_paragraph(psr, runs: list[Run], template: TemplateSpec, style_key: str,
                              font_family_map: dict, color_black: str, color_accent: str):
    """Добавляет CharacterStyleRange с учётом bold/italic."""
    is_heading = style_key.startswith("h")
    base_ps = template.heading_font_bold if is_heading else template.body_font

    segments: list[tuple[str, bool, bool]] = []
    for run in runs:
        if run.text:
            segments.append((run.text, run.bold, run.italic))

    if not segments:
        segments = [("", False, False)]

    for text, bold, italic in segments:
        csr = etree.SubElement(psr, "CharacterStyleRange")
        ps_font = base_ps
        if not is_heading:
            if bold and italic:
                ps_font = template.body_font_bold
            elif bold:
                ps_font = template.body_font_bold
            elif italic:
                ps_font = template.body_font_italic

        resolved = font_manager.resolve_variant(ps_font, bold=bold and not is_heading,
                                                 italic=italic and not is_heading)
        family, fstyle = font_family_map.get(ps_font, (resolved.family, resolved.style))
        csr.set("AppliedFont", family)
        csr.set("FontStyle", fstyle)
        if is_heading:
            csr.set("FillColor", color_accent)
        else:
            csr.set("FillColor", color_black)
        if bold and not is_heading:
            csr.set("FontStyle", "Bold" if not italic else "Bold Italic")
        elif italic and not is_heading:
            csr.set("FontStyle", "Italic")

        content = etree.SubElement(csr, "Content")
        content.text = text


def _bounds(top: float, left: float, bottom: float, right: float) -> str:
    return f"{round(top, 3)} {round(left, 3)} {round(bottom, 3)} {round(right, 3)}"


def _page_spread_groups(pages: list, facing: bool) -> list[list]:
    if not facing or len(pages) <= 1:
        return [[p] for p in pages]
    groups: list[list] = []
    i = 0
    while i < len(pages):
        if i + 1 < len(pages):
            groups.append([pages[i], pages[i + 1]])
            i += 2
        else:
            groups.append([pages[i]])
            i += 1
    return groups


def _emit_page_on_spread(
    spread: etree.Element,
    doc: etree.Element,
    page,
    offset_x: float,
    page_w: float,
    page_h: float,
    template: TemplateSpec,
    profile: TypographyProfile,
    font_family_map: dict,
    color_black: str,
    color_accent: str,
    color_tint: str,
    image_paths: list[Path],
    links_dirname: str,
) -> None:
    page_el = etree.SubElement(spread, "Page")
    page_el.set("Self", f"Page/u{_uid()}")
    page_el.set("Name", str(page.index + 1))
    page_el.set("AppliedMaster", "MasterSpread/A-Master")
    page_el.set("GeometricBounds", _bounds(0, offset_x, page_h, offset_x + page_w))

    if page.drop_cap and template.accent_style == "tint_block":
        tint_rect = etree.SubElement(spread, "Rectangle")
        tint_rect.set("Self", f"Rectangle/u{_uid()}")
        col0 = page.columns[0].rect
        tint_rect.set("GeometricBounds", _bounds(
            col0.y, col0.x + offset_x, col0.y + 40, col0.x + col0.w + offset_x,
        ))
        tint_rect.set("FillColor", color_tint)
        tint_rect.set("StrokeWeight", "0")

    for col_idx, col in enumerate(page.columns):
        col_lines = [ln for ln in page.preview_lines if ln.column_index == col_idx]
        col_story_id = _build_story_from_preview_lines(
            doc, col_lines, template, font_family_map, color_black, color_accent,
        )
        tf = etree.SubElement(spread, "TextFrame")
        tf.set("Self", f"TextFrame/u{_uid()}")
        tf.set("ParentStory", col_story_id)
        gx0, gy0 = col.rect.x + offset_x, col.rect.y
        gx1, gy1 = col.rect.x + col.rect.w + offset_x, col.rect.y + col.rect.h
        tf.set("GeometricBounds", _bounds(gy0, gx0, gy1, gx1))
        tfp = etree.SubElement(tf, "TextFramePreference")
        tfp.set("TextColumnCount", "1")
        tfp.set("VerticalJustification", "TopAlign")
        tfp.set("InsetSpacing", "0 0 0 0")

    for img_frame in page.images:
        if img_frame.image_index >= len(image_paths):
            continue
        img_path = image_paths[img_frame.image_index]

        if getattr(img_frame, "show_ad_label", False):
            from app.layout.ad_units import AD_LABEL_TEXT, AD_LABEL_HEIGHT_MM
            label_h = AD_LABEL_HEIGHT_MM * MM_TO_PT
            label_story_id = f"Story/u{_uid()}"
            ls = etree.SubElement(doc, "Story")
            ls.set("Self", label_story_id)
            ls.set("AppliedTOCStyle", "n")
            psr = etree.SubElement(ls, "ParagraphStyleRange")
            psr.set("AppliedParagraphStyle", "ParagraphStyle/Основной текст")
            csr = etree.SubElement(psr, "CharacterStyleRange")
            fam, fst = font_family_map.get(template.body_font_italic, ("Arial", "Italic"))
            csr.set("AppliedFont", fam)
            csr.set("FontStyle", fst)
            csr.set("PointSize", "7")
            csr.set("FillColor", color_black)
            content = etree.SubElement(csr, "Content")
            content.text = AD_LABEL_TEXT
            etree.SubElement(psr, "Br")
            ltf = etree.SubElement(spread, "TextFrame")
            ltf.set("Self", f"TextFrame/u{_uid()}")
            ltf.set("ParentStory", label_story_id)
            gx0 = img_frame.rect.x + offset_x
            gy1 = img_frame.rect.y
            gy0 = gy1 - label_h
            gx1 = img_frame.rect.x + img_frame.rect.w + offset_x
            ltf.set("GeometricBounds", _bounds(gy0, gx0, gy1, gx1))

        rect_el = etree.SubElement(spread, "Rectangle")
        rect_el.set("Self", f"Rectangle/u{_uid()}")
        gx0 = img_frame.rect.x + offset_x
        gy0 = img_frame.rect.y
        gx1 = img_frame.rect.x + img_frame.rect.w + offset_x
        gy1 = img_frame.rect.y + img_frame.rect.h
        rect_el.set("GeometricBounds", _bounds(gy0, gx0, gy1, gx1))
        if getattr(img_frame, "image_role", "") == "ad":
            rect_el.set("StrokeWeight", "0.5")
            rect_el.set("StrokeColor", color_black)
        else:
            stroke = getattr(img_frame, "stroke_pt", 0) or 0
            if stroke > 0:
                rect_el.set("StrokeWeight", f"{stroke:.2f}")
                rect_el.set("StrokeColor", color_black)
            else:
                rect_el.set("StrokeWeight", "0")

        if getattr(img_frame, "text_wrap", False):
            twp = etree.SubElement(rect_el, "TextWrapPreference")
            twp.set("TextWrapMode", "BoundingBoxTextWrap")
            side = getattr(img_frame, "wrap_side", "both")
            wrap_map = {"left": "Left", "right": "Right", "both": "BothSides"}
            twp.set("TextWrapSide", wrap_map.get(side, "BothSides"))
            twp.set("TextWrapOffset", "4 4 4 4")

        image_el = etree.SubElement(rect_el, "Image")
        image_el.set("Self", f"Image/u{_uid()}")
        image_el.set("ImageTypeName", "Linked")
        link_el = etree.SubElement(image_el, "Link")
        link_el.set("Self", f"Link/u{_uid()}")
        link_el.set("LinkResourceURI", f"{links_dirname}/{img_path.name}")
        link_el.set("LinkResourceFormat", "$ID/Image")


def build_inx(parsed: ParsedDocument, plan: LayoutPlan,
              image_paths: list[Path], links_dirname: str = "Links") -> bytes:
    profile = plan.profile
    template = plan.template
    lang = profile.indesign_language()
    page_w = plan.page_width_pt or profile.page_width_pt()
    page_h = plan.page_height_pt or profile.page_height_pt()

    doc = etree.Element("Document")
    doc.set("DOMVersion", "5.0")
    doc.set("Self", f"d{_uid()}")

    colors_el = etree.SubElement(doc, "RootColorGroup")
    accent_c, accent_m, accent_y, accent_k = _rgb_to_cmyk(plan.dominant_accent_rgb)

    def add_color(name: str, model: str, c=0.0, m=0.0, y=0.0, k=0.0) -> str:
        cid = f"Color/{name}"
        col = etree.SubElement(colors_el, "Color")
        col.set("Self", cid)
        col.set("Name", name)
        col.set("Model", model)
        col.set("Space", "CMYK")
        col.set("ColorValue", f"{c} {m} {y} {k}")
        return cid

    color_black = add_color("Black", "Process", 0, 0, 0, 100)
    add_color("Paper", "Process", 0, 0, 0, 0)
    color_accent = add_color("Accent", "Process", accent_c, accent_m, accent_y, accent_k)
    tint_c, tint_m, tint_y, tint_k = accent_c * 0.15, accent_m * 0.15, accent_y * 0.15, accent_k * 0.15
    color_tint = add_color("AccentTint", "Process", tint_c, tint_m, tint_y, tint_k)

    fonts_el = etree.SubElement(doc, "RootFontGroup")
    used_font_names = {
        template.body_font, template.body_font_bold, template.body_font_italic,
        template.heading_font, template.heading_font_bold,
    }
    if getattr(template, "rubric_font", ""):
        used_font_names.add(template.rubric_font)
    font_family_map: dict[str, tuple[str, str]] = {}
    registered_fonts: set[str] = set()
    for ps_name in used_font_names:
        for bold, italic in ((False, False), (True, False), (False, True)):
            resolved = font_manager.resolve_variant(ps_name, bold=bold, italic=italic)
            key = f"{resolved.family}\t{resolved.style}"
            if key not in registered_fonts:
                registered_fonts.add(key)
                f_el = etree.SubElement(fonts_el, "Font")
                f_el.set("Self", f"Font/{key}")
                f_el.set("FontFamily", resolved.family)
                f_el.set("FontStyleName", resolved.style)
                f_el.set("PostScriptName", resolved.postscript_name)
            if not bold and not italic:
                font_family_map[ps_name] = (resolved.family, resolved.style)
    for ps_name in used_font_names:
        if ps_name not in font_family_map:
            resolved = font_manager.resolve_variant(ps_name)
            font_family_map[ps_name] = (resolved.family, resolved.style)

    pstyles_el = etree.SubElement(doc, "RootParagraphStyleGroup")
    cstyles_el = etree.SubElement(doc, "RootCharacterStyleGroup")

    style_defs = {
        "Заголовок 1": (template.heading_font_bold, template.h_size_pt.get(1, 22)),
        "Заголовок 2": (template.heading_font_bold, template.h_size_pt.get(2, 17)),
        "Заголовок 3": (
            getattr(template, "rubric_font", None) or template.heading_font_bold,
            template.h_size_pt.get(3, 13),
        ),
        "Заголовок 4": (template.heading_font_bold, template.h_size_pt.get(4, 11)),
        "Лид": (template.body_font_bold, round(template.body_size_pt * 1.15, 1)),
        "Основной текст": (template.body_font, template.body_size_pt),
        "Список": (template.body_font, template.body_size_pt),
        "Сноска": (template.body_font_italic, max(7.5, template.body_size_pt * 0.88)),
        "Таблица": (template.body_font, max(8.0, template.body_size_pt * 0.92)),
    }
    for style_name, (ps_font, size_pt) in style_defs.items():
        family, fstyle = font_family_map.get(ps_font, (ps_font, "Regular"))
        leading = round(size_pt * 1.32, 2) if "Заголовок" in style_name else template.body_leading_pt
        p_el = etree.SubElement(pstyles_el, "ParagraphStyle")
        p_el.set("Self", f"ParagraphStyle/{style_name}")
        p_el.set("Name", style_name)
        p_el.set("AppliedFont", family)
        p_el.set("FontStyle", fstyle)
        p_el.set("PointSize", str(size_pt))
        p_el.set("Leading", str(leading))
        p_el.set("Language", lang)
        p_el.set("Hyphenation", "true" if profile.hyphenation and style_name in ("Основной текст", "Список") else "false")
        p_el.set("FillColor", color_accent if "Заголовок" in style_name else color_black)
        if style_name == "Список":
            p_el.set("BulletsAndNumberingListType", "BulletList")
            p_el.set("LeftIndent", "14")
            p_el.set("FirstLineIndent", "-14")
        if style_name == "Сноска":
            p_el.set("LeftIndent", "8")
            p_el.set("SpaceBefore", "2")
        if style_name == "Таблица":
            p_el.set("LeftIndent", "0")
            p_el.set("TabList", "0 36:left,72:left,108:left,144:left")
        if style_name == "Основной текст":
            p_el.set("SpaceAfter", "4")
        c_el = etree.SubElement(cstyles_el, "CharacterStyle")
        c_el.set("Self", f"CharacterStyle/{style_name}")
        c_el.set("Name", style_name)
        c_el.set("AppliedFont", family)
        c_el.set("FontStyle", fstyle)
        c_el.set("PointSize", str(size_pt))

    for variant in ("Bold", "Italic", "Bold Italic"):
        c_el = etree.SubElement(cstyles_el, "CharacterStyle")
        c_el.set("Self", f"CharacterStyle/Основной текст {variant}")
        c_el.set("Name", f"Основной текст {variant}")
        fam, fst = font_family_map.get(template.body_font_bold if "Bold" in variant else template.body_font_italic,
                                        font_family_map.get(template.body_font, ("", "Regular")))
        c_el.set("AppliedFont", fam)
        c_el.set("FontStyle", variant)

    master = etree.SubElement(doc, "MasterSpread")
    master.set("Self", "MasterSpread/A-Master")
    master.set("Name", "A-Master")
    master_page = etree.SubElement(master, "Page")
    master_page.set("Self", "Page/uMaster1")
    master_page.set("Name", "A")
    margin_pref = etree.SubElement(master_page, "MarginPreference")
    m = profile.margins_pt(0)
    margin_pref.set("Top", str(round(m["top"], 3)))
    margin_pref.set("Bottom", str(round(m["bottom"], 3)))
    margin_pref.set("Left", str(round(m["left"], 3)))
    margin_pref.set("Right", str(round(m["right"], 3)))
    margin_pref.set("ColumnCount", str(template.columns))
    margin_pref.set("ColumnGutter", str(round(template.gutter_mm * 72.0 / 25.4, 3)))

    doc_pref = etree.SubElement(doc, "DocumentPreference")
    doc_pref.set("PageWidth", str(round(page_w, 3)))
    doc_pref.set("PageHeight", str(round(page_h, 3)))
    doc_pref.set("FacingPages", "true" if profile.facing_pages else "false")
    doc_pref.set("DocumentBleedTopOffset", str(round(profile.bleed_pt(), 3)))
    doc_pref.set("DocumentBleedBottomOffset", str(round(profile.bleed_pt(), 3)))
    doc_pref.set("DocumentBleedInsideOrLeftOffset", str(round(profile.bleed_pt(), 3)))
    doc_pref.set("DocumentBleedOutsideOrRightOffset", str(round(profile.bleed_pt(), 3)))

    if profile.print_marks:
        marks = etree.SubElement(doc, "PrintMarksPreference")
        marks.set("CropMarks", "true")
        marks.set("RegistrationMarks", "true")
        marks.set("ColorBars", "true")
        marks.set("PageInformationMarks", "true")
        marks.set("BleedMarkOffset", str(round(profile.bleed_pt(), 3)))

    bleed_pref = etree.SubElement(doc, "DocumentBleedAndSlugPreference")
    bleed_pref.set("BleedTop", str(round(profile.bleed_pt(), 3)))
    bleed_pref.set("BleedBottom", str(round(profile.bleed_pt(), 3)))
    bleed_pref.set("BleedInside", str(round(profile.bleed_pt(), 3)))
    bleed_pref.set("BleedOutside", str(round(profile.bleed_pt(), 3)))

    spread_groups = _page_spread_groups(plan.pages, profile.facing_pages)
    for group in spread_groups:
        spread = etree.SubElement(doc, "Spread")
        spread.set("Self", f"Spread/u{_uid()}")
        spread.set("PageCount", str(len(group)))
        spread.set("BindingLocation", "1" if len(group) == 2 else "0")

        for spread_idx, page in enumerate(group):
            offset_x = spread_idx * page_w if profile.facing_pages and len(group) > 1 else 0.0
            _emit_page_on_spread(
                spread, doc, page, offset_x, page_w, page_h,
                template, profile, font_family_map,
                color_black, color_accent, color_tint,
                image_paths, links_dirname,
            )

    body_bytes = etree.tostring(doc, pretty_print=True, encoding="UTF-8")
    xml_declaration = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    aid_pi = (b'<?aid style="50" type="document" readerVersion="5.0" '
              b'featureSet="257" product="5.0(370)" ?>\n')
    return xml_declaration + aid_pi + body_bytes
