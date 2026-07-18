"""
Super Genius генератор INX для Adobe InDesign CS3 (DOMVersion 5.0).

- Process CMYK only
- Named Layers + Groups (один Copy/Paste на модуль/сцену)
- Object styles + OverprintFill на чистом Black
- Linked 2-col article body
- Геометрия из examples/_analysis
"""
from __future__ import annotations

import math
import uuid
from typing import Iterable

from lxml import etree

from app.config import MM_TO_PT
from app.kit import geometry as geo
from app.kit.brand import BRAND_SWATCHES, COLOR_PROFILE_DEFAULT
from app.kit.scenes import get_scene
from app.layout import fonts as font_manager
from app.layout.okolica_profile import (
    BODY_LEADING_PT, BODY_SIZE_PT, FONT_BODY, FONT_BODY_BOLD, FONT_BODY_ITALIC,
    FONT_HEADLINE, FONT_LOGO, FONT_RUBRIC, FONT_UI_BOLD,
    H1_SIZE_PT, H2_SIZE_PT, H3_SIZE_PT, LEAD_SIZE_PT,
    LOGO_SIZE_PT, NEWS_HEADER_SIZE_PT, WEATHER_HEADER_SIZE_PT, COVER_TEASER_SIZE_PT,
)


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _mm(v: float) -> float:
    return v * MM_TO_PT


def _bounds(y0: float, x0: float, y1: float, x1: float) -> str:
    return f"{y0:.3f} {x0:.3f} {y1:.3f} {x1:.3f}"


def build_kit_inx(
    include: Iterable[str] | None = None,
    texts: dict[str, str] | None = None,
    scene_id: str | None = None,
    ad_format_id: str | None = None,
) -> bytes:
    font_manager.scan_fonts()
    scene = get_scene(scene_id) if scene_id else None

    # Рекламный формат как отдельная «сцена»
    ad_fmt = None
    if ad_format_id:
        from app.kit.ads import get_ad_format
        ad_fmt = get_ad_format(ad_format_id)
        if ad_fmt is not None:
            include_set = set(ad_fmt.elements)
            merged_texts = {
                "ad_module": "Реклама",
                "ad_module_wide": "Реклама",
                "ad_body_narrow": texts.get("ad_body_narrow", f"{ad_fmt.name} · {ad_fmt.area_cm2} см²") if texts else f"{ad_fmt.name}",
                "ad_body_wide": (texts or {}).get("ad_body_wide", f"{ad_fmt.name} — {ad_fmt.width_mm:.0f}×{ad_fmt.height_mm:.0f} мм"),
                "ad_price": f"ориентир {ad_fmt.price_hint_rub} ₽",
                **(texts or {}),
            }
            scene = None
        else:
            ad_fmt = None

    if ad_fmt is None:
        if scene is not None:
            include_set = set(scene.elements)
            merged_texts = {**scene.default_texts, **(texts or {})}
        else:
            include_set = set(include) if include is not None else None
            merged_texts = texts or {}

    def want(eid: str) -> bool:
        return include_set is None or eid in include_set

    page_w = _mm(geo.PAGE_W)
    page_h = _mm(geo.PAGE_H)
    bleed = _mm(geo.BLEED)

    doc = etree.Element("Document")
    doc.set("DOMVersion", "5.0")
    doc.set("Self", f"d{_uid()}")

    # --- Layers ---
    layers_el = etree.SubElement(doc, "RootLayerGroup")
    layer_map: dict[str, str] = {}
    for i, (lid, lname) in enumerate((
        ("kit_guides", "0 · Guides / Labels"),
        ("kit_decor", "1 · Decor"),
        ("kit_ads", "2 · Ads"),
        ("kit_news", "3 · Short News"),
        ("kit_article", "4 · Article"),
        ("kit_masthead", "5 · Masthead"),
    )):
        layer = etree.SubElement(layers_el, "Layer")
        sid = f"Layer/{lid}"
        layer.set("Self", sid)
        layer.set("Name", lname)
        layer.set("Visible", "true")
        layer.set("Locked", "false")
        layer.set("IgnoreWrap", "false")
        layer.set("LayerColor", str(i + 1))
        layer_map[lid] = sid

    # --- CMYK swatches ---
    colors_el = etree.SubElement(doc, "RootColorGroup")
    color_ids: dict[str, str] = {}

    def add_cmyk(name: str, c: float, m: float, y: float, k: float) -> str:
        cid = f"Color/{name}"
        col = etree.SubElement(colors_el, "Color")
        col.set("Self", cid)
        col.set("Name", name)
        col.set("Model", "Process")
        col.set("Space", "CMYK")
        col.set("ColorValue", f"{c} {m} {y} {k}")
        color_ids[name] = cid
        return cid

    for name, vals in BRAND_SWATCHES.items():
        add_cmyk(name, *vals)

    black = color_ids["Black"]
    paper = color_ids["Paper"]
    red = color_ids["OkolicaRed"]
    orange = color_ids["OkolicaOrange"]
    orange_tint = color_ids["OkolicaOrangeTint"]
    purple = color_ids["OkolicaPurple"]
    teal = color_ids["OkolicaTeal"]
    gray = color_ids["OkolicaGray"]

    # --- Fonts ---
    fonts_el = etree.SubElement(doc, "RootFontGroup")
    used_ps = {
        FONT_BODY, FONT_BODY_BOLD, FONT_BODY_ITALIC, FONT_HEADLINE, FONT_RUBRIC,
        FONT_LOGO, FONT_UI_BOLD,
    }
    font_family_map: dict[str, tuple[str, str]] = {}
    registered: set[str] = set()
    for ps_name in used_ps:
        for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
            resolved = font_manager.resolve_variant(ps_name, bold=bold, italic=italic)
            key = f"{resolved.family}\t{resolved.style}"
            if key not in registered:
                registered.add(key)
                f_el = etree.SubElement(fonts_el, "Font")
                f_el.set("Self", f"Font/{key}")
                f_el.set("FontFamily", resolved.family)
                f_el.set("FontStyleName", resolved.style)
                f_el.set("PostScriptName", resolved.postscript_name)
            if not bold and not italic:
                font_family_map[ps_name] = (resolved.family, resolved.style)
    for ps_name in used_ps:
        if ps_name not in font_family_map:
            r = font_manager.resolve_variant(ps_name)
            font_family_map[ps_name] = (r.family, r.style)

    # --- Paragraph / Character / Object styles ---
    pstyles = etree.SubElement(doc, "RootParagraphStyleGroup")
    cstyles = etree.SubElement(doc, "RootCharacterStyleGroup")
    ostyles = etree.SubElement(doc, "RootObjectStyleGroup")

    style_defs = [
        ("Заголовок 1", FONT_HEADLINE, H1_SIZE_PT, red, H1_SIZE_PT * 1.12),
        ("Заголовок 2", FONT_HEADLINE, H2_SIZE_PT, red, H2_SIZE_PT * 1.15),
        ("Короткие шапка", FONT_HEADLINE, NEWS_HEADER_SIZE_PT, paper, NEWS_HEADER_SIZE_PT * 1.05),
        ("Рубрика", FONT_RUBRIC, H3_SIZE_PT, black, H3_SIZE_PT * 1.2),
        ("Логотип", FONT_LOGO, LOGO_SIZE_PT, paper, LOGO_SIZE_PT * 1.1),
        ("Лид", FONT_BODY_BOLD, LEAD_SIZE_PT, black, LEAD_SIZE_PT * 1.22),
        ("Основной текст", FONT_BODY, BODY_SIZE_PT, black, BODY_LEADING_PT),
        ("Подпись", FONT_BODY_ITALIC, BODY_SIZE_PT * 0.85, gray, BODY_SIZE_PT * 0.85 * 1.2),
        ("Реклама", FONT_BODY_BOLD, 8.0, gray, 10.0),
        ("Метка каталога", FONT_BODY, 7.0, gray, 9.0),
        ("Тизер обложки", FONT_RUBRIC, COVER_TEASER_SIZE_PT, purple, COVER_TEASER_SIZE_PT * 1.15),
        ("Folio", FONT_BODY, 7.5, gray, 9.0),
        ("Погода шапка", FONT_UI_BOLD, WEATHER_HEADER_SIZE_PT, paper, WEATHER_HEADER_SIZE_PT * 1.05),
        ("Выпуск", FONT_BODY, geo.ISSUE_SIZE_PT, gray, geo.ISSUE_SIZE_PT * 1.2),
    ]
    if want("styles_pack") or include_set is None:
        for name, ps, size, fill, leading in style_defs:
            fam, fst = font_family_map.get(ps, (ps, "Regular"))
            p_el = etree.SubElement(pstyles, "ParagraphStyle")
            p_el.set("Self", f"ParagraphStyle/{name}")
            p_el.set("Name", name)
            p_el.set("AppliedFont", fam)
            p_el.set("FontStyle", fst)
            p_el.set("PointSize", str(round(size, 2)))
            p_el.set("Leading", str(round(leading, 2)))
            p_el.set("Language", "Russian")
            p_el.set("Hyphenation", "true" if name == "Основной текст" else "false")
            p_el.set("FillColor", fill)
            if name == "Основной текст":
                p_el.set("Justification", "LeftJustified")
                p_el.set("SpaceAfter", "3")
                p_el.set("OverprintFill", "true")
            if fill == black:
                p_el.set("OverprintFill", "true")
            c_el = etree.SubElement(cstyles, "CharacterStyle")
            c_el.set("Self", f"CharacterStyle/{name}")
            c_el.set("Name", name)
            c_el.set("AppliedFont", fam)
            c_el.set("FontStyle", fst)
            c_el.set("PointSize", str(round(size, 2)))
            if fill == black:
                c_el.set("OverprintFill", "true")

        # Object styles
        for os_name, stroke, stroke_w, fill_c, extra in (
            ("Kit Photo Frame", black, geo.PHOTO_STROKE, paper, {}),
            ("Kit News Card", orange, geo.NEWS_STROKE, orange_tint, {}),
            ("Kit Ad Module", black, 0.75, paper, {}),
            ("Kit Logo Plate", None, 0, purple, {}),
            ("Kit Weather Badge", None, 0, teal, {}),
            ("Kit Wave Box", purple, geo.WAVE_BORDER_STROKE, paper, {}),
        ):
            o_el = etree.SubElement(ostyles, "ObjectStyle")
            o_el.set("Self", f"ObjectStyle/{os_name}")
            o_el.set("Name", os_name)
            o_el.set("EnableFill", "true")
            o_el.set("EnableStroke", "true")
            o_el.set("FillColor", fill_c)
            if stroke:
                o_el.set("StrokeColor", stroke)
                o_el.set("StrokeWeight", str(stroke_w))
                if stroke == black:
                    o_el.set("OverprintStroke", "true")
            else:
                o_el.set("StrokeWeight", "0")

    # --- Document prefs ---
    master = etree.SubElement(doc, "MasterSpread")
    master.set("Self", "MasterSpread/A-Master")
    master.set("Name", "A-Master")
    master_page = etree.SubElement(master, "Page")
    master_page.set("Self", "Page/uMaster1")
    master_page.set("Name", "A")
    mp = etree.SubElement(master_page, "MarginPreference")
    mp.set("Top", str(round(_mm(geo.MARGIN_T), 3)))
    mp.set("Bottom", str(round(_mm(geo.MARGIN_B), 3)))
    mp.set("Left", str(round(_mm(geo.MARGIN_L), 3)))
    mp.set("Right", str(round(_mm(geo.MARGIN_R), 3)))
    mp.set("ColumnCount", "3")
    mp.set("ColumnGutter", str(round(_mm(geo.COL_GUTTER), 3)))

    doc_pref = etree.SubElement(doc, "DocumentPreference")
    doc_pref.set("PageWidth", str(round(page_w, 3)))
    doc_pref.set("PageHeight", str(round(page_h, 3)))
    doc_pref.set("FacingPages", "false")
    doc_pref.set("DocumentBleedTopOffset", str(round(bleed, 3)))
    doc_pref.set("DocumentBleedBottomOffset", str(round(bleed, 3)))
    doc_pref.set("DocumentBleedInsideOrLeftOffset", str(round(bleed, 3)))
    doc_pref.set("DocumentBleedOutsideOrRightOffset", str(round(bleed, 3)))

    bleed_pref = etree.SubElement(doc, "DocumentBleedAndSlugPreference")
    bleed_pref.set("BleedTop", str(round(bleed, 3)))
    bleed_pref.set("BleedBottom", str(round(bleed, 3)))
    bleed_pref.set("BleedInside", str(round(bleed, 3)))
    bleed_pref.set("BleedOutside", str(round(bleed, 3)))
    bleed_pref.set("SlugBottom", "0")

    spread = etree.SubElement(doc, "Spread")
    spread.set("Self", f"Spread/u{_uid()}")
    spread.set("PageCount", "1")
    spread.set("BindingLocation", "0")

    page = etree.SubElement(spread, "Page")
    page.set("Self", f"Page/u{_uid()}")
    page.set("Name", "1")
    page.set("GeometricBounds", _bounds(0, 0, page_h, page_w))
    page.set("ItemTransform", "1 0 0 1 0 0")

    ctx = _Ctx(
        doc=doc, spread=spread,
        font_family_map=font_family_map,
        black=black, paper=paper, red=red, orange=orange,
        orange_tint=orange_tint, purple=purple, teal=teal, gray=gray,
        texts=merged_texts, want=want,
        page_w=page_w, page_h=page_h,
        scene_mode=scene is not None or ad_fmt is not None,
        scene_name=(
            scene.name if scene else (ad_fmt.name if ad_fmt else "")
        ),
        layer_map=layer_map,
        active_layer=layer_map["kit_guides"],
        group_stack=[],
        ad_format=ad_fmt,
    )

    if ad_fmt is not None:
        with _group(ctx, f"AD · {ad_fmt.name}", f"kit_ad_{ad_fmt.id}"):
            _layout_ad_format(ctx, ad_fmt)
    elif scene is not None:
        with _group(ctx, f"SCENE · {scene.name}", "kit_scene"):
            _layout_scene(ctx, scene.id)
    else:
        _layout_catalog(ctx)

    body_bytes = etree.tostring(doc, pretty_print=True, encoding="UTF-8")
    xml_declaration = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    aid_pi = (b'<?aid style="50" type="document" readerVersion="5.0" '
              b'featureSet="257" product="5.0(370)" ?>\n')
    return xml_declaration + aid_pi + body_bytes


class _Ctx:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _group:
    """Context manager: wraps subsequent spread children into a named Group."""

    def __init__(self, ctx: _Ctx, name: str, self_tag: str = ""):
        self.ctx = ctx
        self.name = name
        self.self_tag = self_tag or f"u{_uid()}"
        self._parent = None
        self._start_len = 0

    def __enter__(self):
        self._parent = self.ctx.group_stack[-1] if self.ctx.group_stack else self.ctx.spread
        self._start_len = len(self._parent)
        grp = etree.SubElement(self._parent, "Group")
        grp.set("Self", f"Group/{self.self_tag}")
        grp.set("Name", self.name)
        grp.set("ItemLayer", self.ctx.active_layer)
        self.ctx.group_stack.append(grp)
        return grp

    def __exit__(self, *exc):
        self.ctx.group_stack.pop()


def _parent(ctx: _Ctx) -> etree.Element:
    return ctx.group_stack[-1] if ctx.group_stack else ctx.spread


def _set_layer(ctx: _Ctx, key: str) -> None:
    ctx.active_layer = ctx.layer_map.get(key, ctx.layer_map["kit_guides"])


def _text_frame(
    ctx: _Ctx,
    x: float, y: float, w: float, h: float,
    text: str,
    style_name: str,
    fill_color: str,
    fill_override: str | None = None,
    self_story_tag: str = "",
    name: str = "",
    overprint: bool | None = None,
    next_tf: str | None = None,
    prev_tf: str | None = None,
    shared_story_id: str | None = None,
    create_story: bool = True,
) -> str:
    """Returns TextFrame Self id."""
    story_id = shared_story_id or (
        f"Story/{self_story_tag}" if self_story_tag else f"Story/u{_uid()}"
    )
    if create_story:
        story = etree.SubElement(ctx.doc, "Story")
        story.set("Self", story_id)
        story.set("AppliedTOCStyle", "n")
        story.set("TrackChanges", "false")
        psr = etree.SubElement(story, "ParagraphStyleRange")
        psr.set("AppliedParagraphStyle", f"ParagraphStyle/{style_name}")
        csr = etree.SubElement(psr, "CharacterStyleRange")
        csr.set("AppliedCharacterStyle", f"CharacterStyle/{style_name}")
        fill = fill_override or fill_color
        csr.set("FillColor", fill)
        use_op = overprint if overprint is not None else (fill == ctx.black)
        if use_op:
            csr.set("OverprintFill", "true")
        content = etree.SubElement(csr, "Content")
        content.text = text
        etree.SubElement(psr, "Br")

    tf_id = f"TextFrame/{name}" if name else f"TextFrame/u{_uid()}"
    tf = etree.SubElement(_parent(ctx), "TextFrame")
    tf.set("Self", tf_id)
    if name:
        tf.set("Name", name)
    tf.set("ParentStory", story_id)
    tf.set("ItemLayer", ctx.active_layer)
    tf.set("GeometricBounds", _bounds(y, x, y + h, x + w))
    tf.set("PreviousTextFrame", prev_tf or "n")
    tf.set("NextTextFrame", next_tf or "n")
    return tf_id


def _rect(
    ctx: _Ctx,
    x: float, y: float, w: float, h: float, *,
    fill: str | None = None, stroke: str | None = None,
    stroke_w: float = 0.5, self_id: str = "", name: str = "",
    object_style: str = "",
) -> etree.Element:
    el = etree.SubElement(_parent(ctx), "Rectangle")
    rid = self_id or f"Rectangle/u{_uid()}"
    el.set("Self", rid)
    if name:
        el.set("Name", name)
    el.set("ItemLayer", ctx.active_layer)
    el.set("GeometricBounds", _bounds(y, x, y + h, x + w))
    if object_style:
        el.set("AppliedObjectStyle", f"ObjectStyle/{object_style}")
    el.set("StrokeWeight", str(stroke_w if stroke else 0))
    if stroke:
        el.set("StrokeColor", stroke)
        if stroke == ctx.black:
            el.set("OverprintStroke", "true")
    else:
        el.set("StrokeWeight", "0")
    el.set("FillColor", fill or ctx.paper)
    return el


def _line(
    ctx: _Ctx,
    x0: float, y0: float, x1: float, y1: float,
    stroke: str | None = None, weight: float = 0.75,
    self_id: str = "", name: str = "",
) -> None:
    stroke = stroke or ctx.black
    el = etree.SubElement(_parent(ctx), "GraphicLine")
    el.set("Self", self_id or f"GraphicLine/u{_uid()}")
    if name:
        el.set("Name", name)
    el.set("ItemLayer", ctx.active_layer)
    el.set("GeometricBounds", _bounds(min(y0, y1), min(x0, x1), max(y0, y1), max(x0, x1)))
    el.set("StrokeWeight", str(weight))
    el.set("StrokeColor", stroke)
    if stroke == ctx.black:
        el.set("OverprintStroke", "true")
    path = etree.SubElement(el, "PathPointType")
    path.set("Anchor", f"{x0:.3f} {y0:.3f}")
    path2 = etree.SubElement(el, "PathPointType")
    path2.set("Anchor", f"{x1:.3f} {y1:.3f}")


def _label(ctx: _Ctx, x: float, y: float, w: float, text: str) -> None:
    if ctx.scene_mode:
        return
    prev = ctx.active_layer
    _set_layer(ctx, "kit_guides")
    _text_frame(ctx, x, y, w, _mm(5), text, "Метка каталога", ctx.gray, name=f"label_{_uid()}")
    ctx.active_layer = prev


def _logo_vector(ctx: _Ctx, x: float, y: float, w: float, h: float) -> None:
    _rect(ctx, x, y, w, h, fill=ctx.purple, stroke=None, stroke_w=0,
          self_id="Rectangle/kit_masthead_logo", name="kit_masthead_logo",
          object_style="Kit Logo Plate")
    inset = _mm(1.2)
    _line(ctx, x + inset, y + _mm(1.5), x + w - inset, y + _mm(1.5),
          ctx.paper, 0.4, self_id="GraphicLine/kit_logo_rule_top", name="kit_logo_rule_top")
    _line(ctx, x + inset, y + h - _mm(1.5), x + w - inset, y + h - _mm(1.5),
          ctx.paper, 0.4, name="kit_logo_rule_bot")
    cx, cy = x + _mm(4), y + h / 2
    arm = _mm(1.8)
    for a, b in (
        ((cx, cy - arm), (cx + arm, cy)),
        ((cx + arm, cy), (cx, cy + arm)),
        ((cx, cy + arm), (cx - arm, cy)),
        ((cx - arm, cy), (cx, cy - arm)),
    ):
        _line(ctx, a[0], a[1], b[0], b[1], ctx.paper, 0.7)
    logo_text = ctx.texts.get("masthead_logo", "Сибирская околица")
    # Real masthead uses Times Bold Italic for «Сибирская»
    _text_frame(
        ctx, x + _mm(8), y + _mm(1.5), w - _mm(10), h - _mm(2.5),
        logo_text, "Логотип", ctx.paper, fill_override=ctx.paper,
        self_story_tag="kit_masthead_logo_text", name="kit_masthead_logo_text",
        overprint=False,
    )


def _corners(ctx: _Ctx, x: float, y: float, box_w: float, box_h: float) -> None:
    arm = _mm(geo.CORNER_ARM)
    pts = [
        (x, y + arm, x, y), (x, y, x + arm, y),
        (x + box_w - arm, y, x + box_w, y), (x + box_w, y, x + box_w, y + arm),
        (x, y + box_h - arm, x, y + box_h), (x, y + box_h, x + arm, y + box_h),
        (x + box_w - arm, y + box_h, x + box_w, y + box_h),
        (x + box_w, y + box_h, x + box_w, y + box_h - arm),
    ]
    for i, (x0, y0, x1, y1) in enumerate(pts):
        sid = "GraphicLine/kit_decor_corners" if i == 0 else ""
        _line(ctx, x0, y0, x1, y1, ctx.purple, 1.0, self_id=sid,
              name="kit_decor_corners" if i == 0 else "")


def _wave_border(ctx: _Ctx, x: float, y: float, w: float, h: float, caption: str) -> None:
    _rect(ctx, x, y, w, h, fill=ctx.paper, stroke=ctx.purple,
          stroke_w=geo.WAVE_BORDER_STROKE, self_id="Rectangle/kit_decor_wave_border",
          name="kit_decor_wave_border", object_style="Kit Wave Box")
    segs = 10
    amp = _mm(2.2)
    for edge_y, flip in ((y + _mm(4), 1), (y + h - _mm(4), -1)):
        for i in range(segs):
            t0, t1 = i / segs, (i + 1) / segs
            x0 = x + _mm(3) + (w - _mm(6)) * t0
            x1 = x + _mm(3) + (w - _mm(6)) * t1
            y0 = edge_y + flip * amp * math.sin(t0 * math.pi * 4)
            y1 = edge_y + flip * amp * math.sin(t1 * math.pi * 4)
            _line(ctx, x0, y0, x1, y1, ctx.purple, 0.55)
    _text_frame(
        ctx, x + _mm(4), y + h / 2 - _mm(4), w - _mm(8), _mm(8),
        caption, "Рубрика", ctx.purple, fill_override=ctx.purple,
        self_story_tag="kit_wave_caption", name="kit_wave_caption", overprint=False,
    )


def _folio(ctx: _Ctx) -> None:
    if not ctx.want("folio_line"):
        return
    _set_layer(ctx, "kit_decor")
    with _group(ctx, "Folio", "kit_folio"):
        y = ctx.page_h - _mm(geo.MARGIN_B) + _mm(2)
        _line(ctx, _mm(geo.MARGIN_L), y - _mm(3),
              ctx.page_w - _mm(geo.MARGIN_R), y - _mm(3),
              ctx.gray, 0.35, self_id="GraphicLine/kit_folio_line", name="kit_folio_line")
        _text_frame(
            ctx, _mm(geo.MARGIN_L), y - _mm(1), _mm(80), _mm(5),
            ctx.texts.get("folio_left", "Сибирская околица"),
            "Folio", ctx.gray, name="kit_folio_left",
        )
        _text_frame(
            ctx, ctx.page_w - _mm(geo.MARGIN_R) - _mm(30), y - _mm(1), _mm(28), _mm(5),
            ctx.texts.get("folio_page", "Стр. —"),
            "Folio", ctx.gray, self_story_tag="kit_folio_page", name="kit_folio_page",
        )


def _draw_masthead(ctx: _Ctx, x: float, y: float) -> float:
    if not (ctx.want("masthead_logo") or ctx.want("masthead_issue") or ctx.want("masthead_rubric_line")):
        return y
    _set_layer(ctx, "kit_masthead")
    _label(ctx, x, y, _mm(80), "ШАПКА")
    y += _mm(5) if not ctx.scene_mode else 0
    logo_w, logo_h = _mm(geo.LOGO_W), _mm(geo.LOGO_H)
    with _group(ctx, "Masthead", "kit_masthead"):
        if ctx.want("masthead_logo"):
            _logo_vector(ctx, x, y, logo_w, logo_h)
        if ctx.want("masthead_issue"):
            _text_frame(
                ctx, x + logo_w + _mm(3), y + _mm(2), _mm(55), _mm(8),
                ctx.texts.get("masthead_issue", "№ — / дата"),
                "Выпуск", ctx.gray, self_story_tag="kit_masthead_issue",
                name="kit_masthead_issue",
            )
        if ctx.want("masthead_rubric_line"):
            rx = x + logo_w + _mm(60)
            rw = min(_mm(55), ctx.page_w - _mm(geo.MARGIN_R) - rx)
            _text_frame(
                ctx, rx, y + _mm(1), rw, _mm(6),
                ctx.texts.get("masthead_rubric_line", "Актуально"),
                "Рубрика", ctx.black, name="kit_masthead_rubric",
            )
            _line(ctx, rx, y + _mm(8), rx + rw, y + _mm(8), ctx.black, geo.RUBRIC_RULE_W,
                  self_id="GraphicLine/kit_masthead_rubric_line", name="kit_masthead_rubric_line")
    return y + logo_h + _mm(4)


def _draw_news_sidebar(ctx: _Ctx, x: float, y: float) -> float:
    if not (ctx.want("news_header") or ctx.want("news_card")):
        return y
    _set_layer(ctx, "kit_news")
    _label(ctx, x, y, _mm(60), "КОРОТКИЕ НОВОСТИ")
    if not ctx.scene_mode:
        y += _mm(5)
    col_w = _mm(geo.SIDEBAR_W)
    with _group(ctx, "Short News Sidebar", "kit_news"):
        if ctx.want("news_header"):
            _rect(ctx, x, y, col_w, _mm(geo.NEWS_HEADER_H), fill=ctx.orange,
                  self_id="Rectangle/kit_news_header", name="kit_news_header")
            _text_frame(
                ctx, x + _mm(2), y + _mm(2), col_w - _mm(4), _mm(geo.NEWS_HEADER_H - 3),
                ctx.texts.get("news_header", "Короткие\nновости"),
                "Короткие шапка", ctx.paper, fill_override=ctx.paper,
                name="kit_news_header_text", overprint=False,
            )
            y += _mm(geo.NEWS_HEADER_H) + _mm(2)
        if ctx.want("news_card"):
            for i in range(geo.NEWS_CARDS):
                cy = y + i * _mm(geo.NEWS_CARD_H + geo.NEWS_CARD_GAP)
                _rect(ctx, x, cy, col_w, _mm(geo.NEWS_CARD_H),
                      fill=ctx.orange_tint, stroke=ctx.orange, stroke_w=geo.NEWS_STROKE,
                      self_id=f"Rectangle/kit_news_card_{i+1}", name=f"kit_news_card_{i+1}",
                      object_style="Kit News Card")
                _text_frame(
                    ctx, x + _mm(2), cy + _mm(2), col_w - _mm(4), _mm(geo.NEWS_CARD_H - 4),
                    ctx.texts.get(f"news_card_{i+1}", f"Краткий текст новости {i+1}."),
                    "Основной текст", ctx.black,
                    self_story_tag=f"kit_news_card_{i+1}", name=f"kit_news_card_{i+1}_text",
                )
            y += geo.NEWS_CARDS * _mm(geo.NEWS_CARD_H + geo.NEWS_CARD_GAP)
    return y


def _draw_article(ctx: _Ctx, x: float, y: float) -> float:
    if not any(ctx.want(e) for e in (
        "article_kicker", "article_headline", "article_lead",
        "article_photo_frame", "article_column",
    )):
        return y
    _set_layer(ctx, "kit_article")
    _label(ctx, x, y - _mm(5), _mm(80), "СТАТЬЯ")
    ay = y
    col2 = _mm(geo.two_col_width())
    with _group(ctx, "Article Block", "kit_article"):
        if ctx.want("article_kicker"):
            _text_frame(
                ctx, x, ay, col2, _mm(6),
                ctx.texts.get("article_kicker", "Рубрика"),
                "Рубрика", ctx.black, name="kit_article_kicker",
            )
            ay += _mm(7)
        if ctx.want("article_headline"):
            _text_frame(
                ctx, x, ay, col2, _mm(20),
                ctx.texts.get("article_headline", "Заголовок материала"),
                "Заголовок 1", ctx.red, fill_override=ctx.red,
                self_story_tag="kit_article_headline", name="kit_article_headline",
                overprint=False,
            )
            ay += _mm(22)
        if ctx.want("article_photo_frame"):
            pw, ph = _mm(geo.LEAD_PHOTO_W), _mm(geo.LEAD_PHOTO_H)
            photo = _rect(ctx, x, ay, pw, ph, fill=ctx.paper, stroke=ctx.black,
                  stroke_w=geo.PHOTO_STROKE, self_id="Rectangle/kit_article_photo_frame",
                  name="kit_article_photo_frame", object_style="Kit Photo Frame")
            tw = etree.SubElement(photo, "TextWrapPreference")
            tw.set("TextWrapMode", "BoundingBoxTextWrap")
            tw.set("TextWrapOffset", f"{_mm(2):.3f} {_mm(2):.3f} {_mm(2):.3f} {_mm(2):.3f}")
            _text_frame(
                ctx, x + _mm(2), ay + ph / 2 - _mm(3), pw - _mm(4), _mm(6),
                ctx.texts.get("photo_caption", "[Фото ≥300 dpi CMYK]"),
                "Подпись", ctx.gray, name="kit_article_photo_label",
            )
            ay += ph + _mm(4)
        if ctx.want("article_lead"):
            _text_frame(
                ctx, x, ay, col2, _mm(14),
                ctx.texts.get("article_lead", "Лид: краткое введение в материал."),
                "Лид", ctx.black, self_story_tag="kit_article_lead", name="kit_article_lead",
            )
            ay += _mm(16)
        if ctx.want("article_column"):
            sample = ctx.texts.get(
                "article_column",
                "Образец основного текста Helios Condensed 9/10.8. "
                "Выключка по ширине, переносы включены. "
                "Две связанные колонки — текст перетекает автоматически.",
            )
            # Linked 2-column frames (same Story)
            story_id = "Story/kit_article_column"
            col_h = _mm(50)
            tf2 = f"TextFrame/kit_article_col2"
            tf1 = f"TextFrame/kit_article_col1"
            _text_frame(
                ctx, x, ay, _mm(geo.COL_W), col_h, sample, "Основной текст", ctx.black,
                self_story_tag="kit_article_column", name="kit_article_col1",
                shared_story_id=story_id, create_story=True,
                next_tf=tf2, prev_tf="n",
            )
            _text_frame(
                ctx, x + _mm(geo.COL_W + geo.COL_GUTTER), ay, _mm(geo.COL_W), col_h,
                "", "Основной текст", ctx.black,
                name="kit_article_col2",
                shared_story_id=story_id, create_story=False,
                next_tf="n", prev_tf=tf1,
            )
            ay += col_h + _mm(2)
    return ay


def _draw_ads(ctx: _Ctx, y: float | None = None) -> None:
    if not (ctx.want("ad_module") or ctx.want("ad_module_wide")):
        return
    _set_layer(ctx, "kit_ads")
    ad_y = y if y is not None else ctx.page_h - _mm(geo.MARGIN_B) - _mm(geo.AD_ROW_H)
    mx = _mm(geo.MARGIN_L)
    _label(ctx, mx, ad_y - _mm(6), _mm(60), "РЕКЛАМА")
    with _group(ctx, "Ads Row", "kit_ads"):
        if ctx.want("decor_divider") and y is not None:
            _line(ctx, mx, ad_y - _mm(4), mx + _mm(geo.CONTENT_W), ad_y - _mm(4), ctx.black, 0.4)
            _line(ctx, mx, ad_y - _mm(2.5), mx + _mm(geo.CONTENT_W), ad_y - _mm(2.5),
                  ctx.black, 0.4, self_id="GraphicLine/kit_decor_divider", name="kit_decor_divider")
        cur_x = mx
        if ctx.want("ad_module"):
            aw, ah = _mm(geo.AD_NARROW_W), _mm(geo.AD_ROW_H)
            _rect(ctx, cur_x, ad_y, aw, ah, fill=ctx.paper, stroke=ctx.black, stroke_w=0.75,
                  self_id="Rectangle/kit_ad_module", name="kit_ad_module",
                  object_style="Kit Ad Module")
            _text_frame(
                ctx, cur_x + _mm(2), ad_y + _mm(1), aw - _mm(4), _mm(5),
                ctx.texts.get("ad_module", "Реклама"),
                "Реклама", ctx.gray, name="kit_ad_label",
            )
            _text_frame(
                ctx, cur_x + _mm(2), ad_y + _mm(8), aw - _mm(4), ah - _mm(10),
                ctx.texts.get("ad_body_narrow", "Текст / телефон рекламодателя"),
                "Основной текст", ctx.black, name="kit_ad_body_narrow",
            )
            cur_x += aw + _mm(geo.AD_GAP)
        if ctx.want("ad_module_wide"):
            aw, ah = _mm(geo.AD_WIDE_W), _mm(geo.AD_ROW_H)
            _rect(ctx, cur_x, ad_y, aw, ah, fill=ctx.paper, stroke=ctx.black, stroke_w=0.75,
                  self_id="Rectangle/kit_ad_module_wide", name="kit_ad_module_wide",
                  object_style="Kit Ad Module")
            _text_frame(
                ctx, cur_x + _mm(2), ad_y + _mm(1), aw - _mm(4), _mm(5),
                ctx.texts.get("ad_module_wide", "Реклама"),
                "Реклама", ctx.gray, name="kit_ad_wide_label",
            )
            _text_frame(
                ctx, cur_x + _mm(2), ad_y + _mm(10), aw - _mm(4), _mm(12),
                ctx.texts.get("ad_body_wide", "Услуги · телефон · адрес"),
                "Основной текст", ctx.black, name="kit_ad_body_wide",
            )


def _draw_cover_teasers(ctx: _Ctx, x: float, y: float) -> float:
    if not ctx.want("cover_teaser"):
        return y
    _set_layer(ctx, "kit_masthead")
    with _group(ctx, "Cover Teasers", "kit_cover_teasers"):
        for i in range(3):
            ty = y + i * _mm(14)
            _text_frame(
                ctx, x, ty, _mm(160), _mm(12),
                ctx.texts.get(f"cover_teaser_{i+1}", f"• Тема {i+1}  Стр. {i+3}"),
                "Тизер обложки", ctx.purple, fill_override=ctx.purple,
                self_story_tag=f"kit_cover_teaser_{i+1}", name=f"kit_cover_teaser_{i+1}",
                overprint=False,
            )
    return y + _mm(44)


def _draw_weather(ctx: _Ctx, x: float, y: float) -> float:
    if not ctx.want("weather_badge"):
        return y
    _set_layer(ctx, "kit_news")
    with _group(ctx, "Weather Badge", "kit_weather"):
        ww = _mm(100)
        wh = _mm(geo.WEATHER_BADGE_H)
        _rect(ctx, x, y, ww, wh, fill=ctx.teal, self_id="Rectangle/kit_weather_badge",
              name="kit_weather_badge", object_style="Kit Weather Badge")
        _text_frame(
            ctx, x + _mm(3), y + _mm(1.5), ww - _mm(6), wh - _mm(2),
            ctx.texts.get("weather_badge", "ПРОГНОЗ ПОГОДЫ"),
            "Погода шапка", ctx.paper, fill_override=ctx.paper,
            name="kit_weather_text", overprint=False,
        )
        if ctx.texts.get("weather_body"):
            _text_frame(
                ctx, x, y + wh + _mm(2), ww, _mm(20),
                ctx.texts["weather_body"], "Основной текст", ctx.black,
                name="kit_weather_body",
            )
    return y + _mm(geo.WEATHER_BADGE_H + 24)


def _layout_ad_format(ctx: _Ctx, fmt) -> None:
    """Отдельная полоса-каталог одного рекламного формата."""
    from app.kit.ads import AdFormat
    fmt: AdFormat
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    _set_layer(ctx, "kit_guides")
    _text_frame(
        ctx, mx, my, _mm(180), _mm(8),
        f"Реклама: {fmt.name} · {fmt.width_mm:.0f}×{fmt.height_mm:.0f} мм · "
        f"{fmt.area_cm2} см² · ориентир {fmt.price_hint_rub} ₽",
        "Метка каталога", ctx.gray, name="kit_ad_format_label",
    )
    _set_layer(ctx, "kit_ads")
    aw, ah = _mm(fmt.width_mm), _mm(fmt.height_mm)
    ax = mx
    ay = my + _mm(14)
    # не выходим за поля
    max_w = ctx.page_w - mx - _mm(geo.MARGIN_R)
    max_h = ctx.page_h - ay - _mm(geo.MARGIN_B) - _mm(10)
    aw = min(aw, max_w)
    ah = min(ah, max_h)
    with _group(ctx, f"Ad {fmt.id}", f"kit_adfmt_{fmt.id}"):
        _rect(ctx, ax, ay, aw, ah, fill=ctx.paper, stroke=ctx.black, stroke_w=0.75,
              self_id=f"Rectangle/kit_ad_format_{fmt.id}", name=f"kit_ad_format_{fmt.id}",
              object_style="Kit Ad Module")
        _text_frame(
            ctx, ax + _mm(2), ay + _mm(2), aw - _mm(4), _mm(5),
            "Реклама", "Реклама", ctx.gray, name="kit_ad_format_mark",
        )
        _text_frame(
            ctx, ax + _mm(2), ay + _mm(10), aw - _mm(4), ah - _mm(14),
            ctx.texts.get("ad_body_wide") or ctx.texts.get("ad_body_narrow")
            or f"{fmt.name}\n{fmt.description}",
            "Основной текст", ctx.black, name="kit_ad_format_body",
        )
        if ctx.texts.get("ad_price"):
            _text_frame(
                ctx, ax + _mm(2), ay + ah - _mm(8), aw - _mm(4), _mm(6),
                ctx.texts["ad_price"], "Реклама", ctx.gray, name="kit_ad_format_price",
            )
    _folio(ctx)


def _layout_catalog(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cursor_y = my

    _set_layer(ctx, "kit_guides")
    _text_frame(
        ctx, mx, cursor_y, ctx.page_w - mx - _mm(geo.MARGIN_R), _mm(8),
        f"Околица CS3 Super Genius · {COLOR_PROFILE_DEFAULT} · "
        f"{geo.PAGE_W:.2f}×{geo.PAGE_H:.2f} мм · Groups+Layers+Overprint",
        "Метка каталога", ctx.gray, name="kit_catalog_title",
    )
    cursor_y += _mm(10)
    cursor_y = _draw_masthead(ctx, mx, cursor_y)

    art_x = _mm(geo.main_cols_x())
    art_y = my + _mm(18)
    if ctx.want("news_header") or ctx.want("news_card"):
        _draw_news_sidebar(ctx, mx, cursor_y)
    else:
        art_y = cursor_y

    if ctx.want("weather_badge"):
        _draw_weather(ctx, mx + _mm(geo.SIDEBAR_W + 4), my + _mm(20))

    _draw_article(ctx, art_x, art_y)

    if ctx.want("cover_teaser"):
        _draw_cover_teasers(ctx, mx, cursor_y + _mm(100))

    decor_y = ctx.page_h - _mm(geo.MARGIN_B) - _mm(55)
    _set_layer(ctx, "kit_decor")
    if any(ctx.want(e) for e in ("decor_rule", "decor_corners", "decor_wave_border", "decor_divider")):
        _label(ctx, mx, decor_y - _mm(6), _mm(60), "ДЕКОР")
        with _group(ctx, "Decor Pack", "kit_decor"):
            if ctx.want("decor_rule"):
                _line(ctx, mx, decor_y, mx + _mm(80), decor_y, ctx.black, 0.75,
                      self_id="GraphicLine/kit_decor_rule", name="kit_decor_rule")
            if ctx.want("decor_divider"):
                _line(ctx, mx, decor_y + _mm(4), mx + _mm(80), decor_y + _mm(4), ctx.black, 0.4)
                _line(ctx, mx, decor_y + _mm(5.5), mx + _mm(80), decor_y + _mm(5.5), ctx.black, 0.4,
                      self_id="GraphicLine/kit_decor_divider", name="kit_decor_divider")
            if ctx.want("decor_corners"):
                _corners(ctx, mx + _mm(90), decor_y, _mm(24), _mm(24))
            if ctx.want("decor_wave_border"):
                _wave_border(ctx, mx + _mm(120), decor_y, _mm(55), _mm(30),
                             ctx.texts.get("wave_caption", "В эти дни"))

    _draw_ads(ctx)
    _folio(ctx)


def _layout_scene(ctx: _Ctx, scene_id: str) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)

    _set_layer(ctx, "kit_guides")
    _text_frame(
        ctx, mx, _mm(2), ctx.page_w - mx * 2, _mm(4),
        f"Сцена: {ctx.scene_name} · выделите Group → Copy → Paste",
        "Метка каталога", ctx.gray, name="kit_scene_hint",
    )

    if scene_id == "scene_news_page":
        y = _draw_masthead(ctx, mx, my)
        _draw_news_sidebar(ctx, mx, y)
        _draw_article(ctx, _mm(geo.main_cols_x()), y)
        _set_layer(ctx, "kit_decor")
        if ctx.want("decor_rule"):
            with _group(ctx, "Decor", "kit_decor_rule_g"):
                _line(ctx, _mm(geo.main_cols_x()), ctx.page_h - _mm(40),
                      _mm(geo.main_cols_x()) + _mm(geo.two_col_width()),
                      ctx.page_h - _mm(40), ctx.black, 0.75,
                      self_id="GraphicLine/kit_decor_rule", name="kit_decor_rule")
        _folio(ctx)
        return

    if scene_id == "scene_shorts_sidebar":
        _draw_news_sidebar(ctx, mx, my + _mm(8))
        return

    if scene_id == "scene_ads_bottom":
        ad_y = ctx.page_h - _mm(geo.MARGIN_B) - _mm(geo.AD_ROW_H) - _mm(8)
        _draw_ads(ctx, y=ad_y)
        _folio(ctx)
        return

    if scene_id == "scene_cover_teasers":
        y = _draw_masthead(ctx, mx, my + _mm(10))
        y = _draw_cover_teasers(ctx, mx, y + _mm(8))
        _set_layer(ctx, "kit_decor")
        if ctx.want("decor_corners"):
            with _group(ctx, "Corners", "kit_corners"):
                _corners(ctx, mx, y + _mm(4), _mm(160), _mm(40))
        return

    if scene_id == "scene_feature_decor":
        _set_layer(ctx, "kit_article")
        ay = my + _mm(20)
        with _group(ctx, "Feature + Decor", "kit_feature"):
            if ctx.want("article_kicker"):
                _text_frame(ctx, mx, ay, _mm(160), _mm(6),
                            ctx.texts.get("article_kicker", "Ну и ну!"),
                            "Рубрика", ctx.black, name="kit_article_kicker")
                ay += _mm(8)
            if ctx.want("article_headline"):
                _text_frame(ctx, mx, ay, _mm(180), _mm(22),
                            ctx.texts.get("article_headline", "Заголовок фичера"),
                            "Заголовок 1", ctx.red, fill_override=ctx.red,
                            self_story_tag="kit_article_headline", name="kit_article_headline",
                            overprint=False)
                ay += _mm(24)
            if ctx.want("article_lead"):
                _text_frame(ctx, mx, ay, _mm(160), _mm(14),
                            ctx.texts.get("article_lead", "Лид"),
                            "Лид", ctx.black, name="kit_article_lead")
                ay += _mm(18)
            _set_layer(ctx, "kit_decor")
            if ctx.want("decor_wave_border"):
                _wave_border(ctx, mx, ay, _mm(100), _mm(36),
                             ctx.texts.get("wave_caption", "В эти дни"))
                ay += _mm(42)
            if ctx.want("decor_corners"):
                _corners(ctx, mx + _mm(110), my + _mm(20), _mm(60), _mm(80))
            if ctx.want("decor_rule"):
                _line(ctx, mx, ay, mx + _mm(160), ay, ctx.black, 0.75,
                      self_id="GraphicLine/kit_decor_rule", name="kit_decor_rule")
        return

    if scene_id == "scene_weather_strip":
        y = _draw_masthead(ctx, mx, my)
        _draw_weather(ctx, _mm(geo.main_cols_x()), y)
        _draw_news_sidebar(ctx, mx, y)
        _folio(ctx)
        return

    _layout_catalog(ctx)
