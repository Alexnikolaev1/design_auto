"""
Генератор INX для Adobe InDesign CS3 (DOMVersion 5.0).

CS3-safe профиль (иначе File → Open: «may not support the file format»):
- AID PI: style="33" + DOMVersion="5.0" (как у реального CS3/CS4 Interchange)
- Без RootLayerGroup / ItemLayer (дефолтный слой CS3)
- Без Object Styles / AppliedObjectStyle
- Линии: тонкие Rectangle (H/V); диагонали — GraphicLine только с GeometricBounds
- Process CMYK, Named Groups для Copy/Paste, Overprint на K=100
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

    # --- Paragraph / Character styles (без Object Styles — CS3 часто рвёт INX) ---
    pstyles = etree.SubElement(doc, "RootParagraphStyleGroup")
    cstyles = etree.SubElement(doc, "RootCharacterStyleGroup")

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
        kind = _pack_gallery_kind(include_set)
        if kind == "ornament":
            _layout_ornament_page(ctx)
        elif kind == "backdrop":
            _layout_backdrop_page(ctx)
        elif kind == "masthead":
            _layout_masthead_gallery(ctx)
        elif kind == "photo":
            _layout_photo_gallery(ctx)
        elif kind == "weather":
            _layout_weather_gallery(ctx)
        elif kind == "shorts":
            _layout_shorts_gallery(ctx)
        elif kind == "teasers":
            _layout_teasers_gallery(ctx)
        elif kind == "styles":
            _layout_styles_page(ctx)
        else:
            _layout_catalog(ctx)

    body_bytes = etree.tostring(doc, pretty_print=True, encoding="UTF-8")
    xml_declaration = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    # Реальный Adobe INX: style="33" + DOMVersion в PI (style="50" CS3 отвергает)
    aid_pi = (
        b'<?aid style="33" type="document" DOMVersion="5.0" '
        b'readerVersion="5.0" featureSet="257" product="5.0(370)" ?>\n'
    )
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
        self.ctx.group_stack.append(grp)
        return grp

    def __exit__(self, *exc):
        self.ctx.group_stack.pop()


def _parent(ctx: _Ctx) -> etree.Element:
    return ctx.group_stack[-1] if ctx.group_stack else ctx.spread


def _set_layer(ctx: _Ctx, key: str) -> None:
    """No-op: CS3-safe INX не использует кастомные Layers."""
    return


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
    el.set("GeometricBounds", _bounds(y, x, y + h, x + w))
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
    """CS3-safe line: H/V → Rectangle; диагональ → GraphicLine только с GeometricBounds."""
    stroke = stroke or ctx.black
    eps = 0.05
    rid = self_id.replace("GraphicLine/", "Rectangle/") if self_id else ""

    if abs(y0 - y1) < eps:
        h = max(weight, 0.35)
        _rect(
            ctx, min(x0, x1), y0 - h / 2, max(abs(x1 - x0), 0.35), h,
            fill=stroke, stroke=None, stroke_w=0, self_id=rid, name=name,
        )
        return
    if abs(x0 - x1) < eps:
        w = max(weight, 0.35)
        _rect(
            ctx, x0 - w / 2, min(y0, y1), w, max(abs(y1 - y0), 0.35),
            fill=stroke, stroke=None, stroke_w=0, self_id=rid, name=name,
        )
        return

    # Диагональ: без PathPointType/PathGeometry — только bounds (угол→угол)
    el = etree.SubElement(_parent(ctx), "GraphicLine")
    el.set("Self", self_id or f"GraphicLine/u{_uid()}")
    if name:
        el.set("Name", name)
    el.set("GeometricBounds", _bounds(min(y0, y1), min(x0, x1), max(y0, y1), max(x0, x1)))
    el.set("StrokeWeight", str(weight))
    el.set("StrokeColor", stroke)
    if stroke == ctx.black:
        el.set("OverprintStroke", "true")


def _label(ctx: _Ctx, x: float, y: float, w: float, text: str) -> None:
    if ctx.scene_mode:
        return
    _text_frame(ctx, x, y, w, _mm(5), text, "Метка каталога", ctx.gray, name=f"label_{_uid()}")


def _logo_vector(ctx: _Ctx, x: float, y: float, w: float, h: float, *, tag: str = "") -> None:
    suffix = f"_{tag}" if tag else ""
    sid = f"Rectangle/kit_masthead_logo{suffix}"
    _rect(ctx, x, y, w, h, fill=ctx.purple, stroke=None, stroke_w=0,
          self_id=sid, name=f"kit_masthead_logo{suffix}")
    inset = _mm(1.2)
    _line(ctx, x + inset, y + _mm(1.5), x + w - inset, y + _mm(1.5),
          ctx.paper, 0.4, self_id=f"GraphicLine/kit_logo_rule_top{suffix}",
          name=f"kit_logo_rule_top{suffix}")
    _line(ctx, x + inset, y + h - _mm(1.5), x + w - inset, y + h - _mm(1.5),
          ctx.paper, 0.4, name=f"kit_logo_rule_bot{suffix}")
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
    _text_frame(
        ctx, x + _mm(8), y + _mm(1.5), w - _mm(10), h - _mm(2.5),
        logo_text, "Логотип", ctx.paper, fill_override=ctx.paper,
        self_story_tag=f"kit_masthead_logo_text{suffix}",
        name=f"kit_masthead_logo_text{suffix}",
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
    for x0, y0, x1, y1 in pts:
        _line(ctx, x0, y0, x1, y1, ctx.purple, 1.0)


def _polyline(ctx: _Ctx, pts: list[tuple[float, float]], stroke: str, weight: float = 0.6,
              self_id: str = "", name: str = "") -> None:
    for i in range(len(pts) - 1):
        sid = self_id if i == 0 else ""
        nm = name if i == 0 else ""
        _line(ctx, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
              stroke, weight, self_id=sid, name=nm)


def _orn_label(ctx: _Ctx, x: float, y: float, text: str) -> None:
    _text_frame(ctx, x, y, _mm(90), _mm(4), text, "Метка каталога", ctx.gray,
                name=f"orn_lbl_{_uid()}")


def _wave_line(ctx: _Ctx, x: float, y: float, w: float, *,
               amp: float | None = None, periods: float = 5, stroke: str | None = None,
               weight: float = 0.7, segs: int = 12) -> None:
    stroke = stroke or ctx.purple
    amp = amp if amp is not None else _mm(2.4)
    pts = []
    for i in range(segs + 1):
        t = i / segs
        pts.append((x + w * t, y + amp * math.sin(t * math.pi * 2 * periods)))
    _polyline(ctx, pts, stroke, weight)


def _double_wave(ctx: _Ctx, x: float, y: float, w: float) -> None:
    _wave_line(ctx, x, y, w, amp=_mm(2.8), periods=5, weight=0.85, segs=12)
    _wave_line(ctx, x, y + _mm(2.2), w, amp=_mm(2.0), periods=5, weight=0.55,
               stroke=ctx.orange, segs=12)


def _scallop_edge(ctx: _Ctx, x: float, y: float, w: float, n: int = 8) -> None:
    """Гирлянда-фестон (дуги из коротких хорд)."""
    step = w / n
    for i in range(n):
        cx = x + step * (i + 0.5)
        r = step * 0.42
        pts = []
        for k in range(5):
            ang = math.pi + (math.pi * k / 4)
            pts.append((cx + r * math.cos(ang), y + r * math.sin(ang)))
        _polyline(ctx, pts, ctx.purple, 0.65)


def _greek_key(ctx: _Ctx, x: float, y: float, w: float, cell: float | None = None) -> None:
    cell = cell or _mm(5.5)
    n = max(3, int(w / cell))
    h = cell * 0.85
    for i in range(n):
        ox = x + i * cell
        pts = [
            (ox, y + h), (ox, y), (ox + cell * 0.55, y),
            (ox + cell * 0.55, y + h * 0.55), (ox + cell * 0.25, y + h * 0.55),
            (ox + cell * 0.25, y + h * 0.28), (ox + cell * 0.75, y + h * 0.28),
            (ox + cell * 0.75, y + h), (ox + cell, y + h),
        ]
        _polyline(ctx, pts, ctx.purple, 0.7)


def _diamond_chain(ctx: _Ctx, x: float, y: float, w: float, n: int = 9) -> None:
    step = w / n
    s = step * 0.28
    for i in range(n):
        cx = x + step * (i + 0.5)
        pts = [(cx, y - s), (cx + s, y), (cx, y + s), (cx - s, y), (cx, y - s)]
        _polyline(ctx, pts, ctx.red if i % 2 == 0 else ctx.purple, 0.75)
        if i < n - 1:
            _line(ctx, cx + s, y, cx + step - s, y, ctx.gray, 0.4)


def _dot_row(ctx: _Ctx, x: float, y: float, w: float, n: int = 18,
             size: float | None = None, fill: str | None = None) -> None:
    """Ряд квадратных «бусин» — только Rectangle."""
    size = size or _mm(1.3)
    fill = fill or ctx.purple
    step = w / max(n, 1)
    for i in range(n):
        _rect(ctx, x + step * i + (step - size) / 2, y - size / 2, size, size,
              fill=fill, stroke=None, stroke_w=0)


def _triple_rule(ctx: _Ctx, x: float, y: float, w: float) -> None:
    _line(ctx, x, y, x + w, y, ctx.black, 1.1)
    _line(ctx, x, y + _mm(1.4), x + w, y + _mm(1.4), ctx.black, 0.4)
    _line(ctx, x, y + _mm(2.3), x + w, y + _mm(2.3), ctx.black, 0.4)


def _ribbon_bar(ctx: _Ctx, x: float, y: float, w: float, h: float, fill: str) -> None:
    """Плашка-лента с «засечками» по краям."""
    _rect(ctx, x, y, w, h, fill=fill, stroke=None, stroke_w=0)
    notch = h * 0.35
    _rect(ctx, x, y, _mm(1.2), h, fill=ctx.paper, stroke=None, stroke_w=0)
    _rect(ctx, x + w - _mm(1.2), y, _mm(1.2), h, fill=ctx.paper, stroke=None, stroke_w=0)
    _line(ctx, x + _mm(2), y + notch, x + _mm(2), y + h - notch, ctx.paper, 0.6)
    _line(ctx, x + w - _mm(2), y + notch, x + w - _mm(2), y + h - notch, ctx.paper, 0.6)


def _nested_frame(ctx: _Ctx, x: float, y: float, w: float, h: float,
                  outer: str, inner: str) -> None:
    _rect(ctx, x, y, w, h, fill=ctx.paper, stroke=outer, stroke_w=1.5)
    inset = _mm(2.5)
    _rect(ctx, x + inset, y + inset, w - 2 * inset, h - 2 * inset,
          fill=None, stroke=inner, stroke_w=0.55)
    _corners(ctx, x + _mm(1.5), y + _mm(1.5), w - _mm(3), h - _mm(3))


def _checker_band(ctx: _Ctx, x: float, y: float, w: float, h: float, n: int = 12) -> None:
    step = w / n
    for i in range(n):
        if i % 2 == 0:
            _rect(ctx, x + i * step, y, step, h, fill=ctx.purple, stroke=None, stroke_w=0)
        else:
            _rect(ctx, x + i * step, y, step, h, fill=ctx.orange_tint, stroke=None, stroke_w=0)


def _rosette(ctx: _Ctx, cx: float, cy: float, r: float, petals: int = 6) -> None:
    for i in range(petals):
        ang = (2 * math.pi * i) / petals
        _line(ctx, cx + r * 0.22 * math.cos(ang), cy + r * 0.22 * math.sin(ang),
              cx + r * math.cos(ang), cy + r * math.sin(ang), ctx.purple, 0.7)
    # центр — квадрат (без кольца из диагоналей)
    s = r * 0.18
    _rect(ctx, cx - s, cy - s, s * 2, s * 2, fill=None, stroke=ctx.orange, stroke_w=0.6)


def _flourish_corner(ctx: _Ctx, x: float, y: float, size: float, *,
                     flip_x: int = 1, flip_y: int = 1) -> None:
    """Угловой завиток — короткая полилиния."""
    s = size
    fx, fy = flip_x, flip_y
    pts = [
        (x, y),
        (x + fx * s * 0.2, y),
        (x + fx * s * 0.45, y + fy * s * 0.12),
        (x + fx * s * 0.65, y + fy * s * 0.08),
        (x + fx * s * 0.75, y + fy * s * 0.35),
        (x + fx * s * 0.4, y + fy * s * 0.55),
        (x + fx * s * 0.15, y + fy * s * 0.4),
        (x, y + fy * s * 0.55),
    ]
    _polyline(ctx, pts, ctx.purple, 0.8)


def _vine_strip(ctx: _Ctx, x: float, y: float, h: float, leaves: int = 5) -> None:
    _line(ctx, x, y, x, y + h, ctx.purple, 0.7)
    step = h / leaves
    for i in range(leaves):
        cy = y + step * (i + 0.5)
        side = 1 if i % 2 == 0 else -1
        # лист из H/V ромба
        s = _mm(2.8)
        _polyline(ctx, [
            (x, cy), (x + side * s, cy - s * 0.45),
            (x + side * s * 1.7, cy), (x + side * s, cy + s * 0.45), (x, cy),
        ], ctx.teal if i % 3 == 0 else ctx.purple, 0.55)


def _ornate_frame(ctx: _Ctx, x: float, y: float, w: float, h: float, caption: str,
                  *, tag: str = "main") -> None:
    _rect(ctx, x, y, w, h, fill=ctx.paper, stroke=ctx.purple, stroke_w=1.4,
          self_id=f"Rectangle/kit_decor_wave_{tag}", name=f"kit_decor_wave_{tag}")
    inset = _mm(3)
    _rect(ctx, x + inset, y + inset, w - 2 * inset, h - 2 * inset,
          fill=None, stroke=ctx.orange, stroke_w=0.6)
    _scallop_edge(ctx, x + _mm(4), y + _mm(2.5), w - _mm(8), n=7)
    _scallop_edge(ctx, x + _mm(4), y + h - _mm(2.5), w - _mm(8), n=7)
    fs = _mm(9)
    _flourish_corner(ctx, x + _mm(2), y + _mm(2), fs, flip_x=1, flip_y=1)
    _flourish_corner(ctx, x + w - _mm(2), y + _mm(2), fs, flip_x=-1, flip_y=1)
    _flourish_corner(ctx, x + _mm(2), y + h - _mm(2), fs, flip_x=1, flip_y=-1)
    _flourish_corner(ctx, x + w - _mm(2), y + h - _mm(2), fs, flip_x=-1, flip_y=-1)
    _text_frame(
        ctx, x + _mm(8), y + h / 2 - _mm(5), w - _mm(16), _mm(10),
        caption, "Рубрика", ctx.purple, fill_override=ctx.purple,
        self_story_tag=f"kit_wave_caption_{tag}", name=f"kit_wave_caption_{tag}", overprint=False,
    )


def _wave_border(ctx: _Ctx, x: float, y: float, w: float, h: float, caption: str) -> None:
    _ornate_frame(ctx, x, y, w, h, caption)


def _star_burst(ctx: _Ctx, cx: float, cy: float, r: float, rays: int = 8) -> None:
    for i in range(rays):
        ang = 2 * math.pi * i / rays
        r0 = r * (0.35 if i % 2 == 0 else 0.2)
        _line(ctx, cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
              cx + r * math.cos(ang), cy + r * math.sin(ang),
              ctx.orange if i % 2 else ctx.purple, 0.6)


def _is_ornament_pack(include_set: set[str] | None) -> bool:
    if not include_set:
        return False
    decor = {"decor_rule", "decor_corners", "decor_wave_border", "decor_divider"}
    core = include_set - {"styles_pack", "folio_line"}
    return bool(core) and core <= decor and len(core & decor) >= 3


def _is_backdrop_pack(include_set: set[str] | None) -> bool:
    if not include_set:
        return False
    core = include_set - {"styles_pack", "folio_line"}
    return core == {"decor_wave_border", "decor_corners"}


def _pack_gallery_kind(include_set: set[str] | None) -> str | None:
    """Какая витрина-полоса для кнопки (не каталог)."""
    if not include_set:
        return None
    if _is_ornament_pack(include_set):
        return "ornament"
    if _is_backdrop_pack(include_set):
        return "backdrop"
    core = include_set - {"styles_pack", "folio_line"}
    mast = {"masthead_logo", "masthead_issue", "masthead_rubric_line"}
    if core and core <= mast and "masthead_logo" in core:
        return "masthead"
    if core == {"article_photo_frame", "decor_corners"} or core == {"article_photo_frame"}:
        return "photo"
    if core == {"weather_badge"}:
        return "weather"
    if core == {"news_header", "news_card"}:
        return "shorts"
    if "cover_teaser" in core:
        return "teasers"
    if not core:
        return "styles"
    return None


def _layout_ornament_page(ctx: _Ctx) -> None:
    """Целая полоса разнообразных узоров — каждый блок отдельный Group."""
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    content_w = ctx.page_w - mx - _mm(geo.MARGIN_R)
    caption = ctx.texts.get("wave_caption", "В эти дни")

    _text_frame(
        ctx, mx, my - _mm(1), content_w, _mm(5),
        "Полоса узоров · Group → Copy/Paste · фирменные цвета Околицы",
        "Метка каталога", ctx.gray, name="kit_ornament_title",
    )
    y = my + _mm(6)

    with _group(ctx, "Узор · двойная волна", "orn_wave"):
        _orn_label(ctx, mx, y, "1. Двойная волна")
        _double_wave(ctx, mx, y + _mm(5), content_w)
        _dot_row(ctx, mx, y + _mm(11), content_w, n=22, fill=ctx.orange)
    y += _mm(15)

    with _group(ctx, "Узор · фестоны и бусины", "orn_scallop"):
        _orn_label(ctx, mx, y, "2. Фестон / гирлянда")
        _scallop_edge(ctx, mx, y + _mm(6), content_w, n=10)
        _line(ctx, mx, y + _mm(10), mx + content_w, y + _mm(10), ctx.gray, 0.35)
        _dot_row(ctx, mx, y + _mm(12.5), content_w, n=16, size=_mm(1.0), fill=ctx.purple)
    y += _mm(16)

    with _group(ctx, "Узор · меандр", "orn_greek"):
        _orn_label(ctx, mx, y, "3. Меандр (греческий ключ)")
        _greek_key(ctx, mx, y + _mm(4), content_w)
    y += _mm(14)

    with _group(ctx, "Узор · ромбы", "orn_diamonds"):
        _orn_label(ctx, mx, y, "4. Цепь ромбов")
        _diamond_chain(ctx, mx, y + _mm(7), content_w, n=9)
    y += _mm(14)

    with _group(ctx, "Узор · тройная линейка", "orn_rules"):
        _orn_label(ctx, mx, y, "5. Разделители / тройная линейка")
        _triple_rule(ctx, mx, y + _mm(5), content_w)
        mid = mx + content_w / 2
        _line(ctx, mx, y + _mm(12), mid - _mm(8), y + _mm(12), ctx.gray, 0.45,
              self_id="GraphicLine/kit_decor_rule", name="kit_decor_rule")
        _rosette(ctx, mid, y + _mm(12), _mm(5), petals=6)
        _line(ctx, mid + _mm(8), y + _mm(12), mx + content_w, y + _mm(12), ctx.gray, 0.45,
              self_id="GraphicLine/kit_decor_divider", name="kit_decor_divider")
    y += _mm(18)

    with _group(ctx, "Узор · розетки и звёзды", "orn_rosettes"):
        _orn_label(ctx, mx, y, "6. Розетки и звёзды")
        _rosette(ctx, mx + _mm(22), y + _mm(13), _mm(10), petals=6)
        _star_burst(ctx, mx + _mm(55), y + _mm(13), _mm(9), rays=8)
        _rosette(ctx, mx + _mm(90), y + _mm(13), _mm(8), petals=8)
        _star_burst(ctx, mx + _mm(125), y + _mm(13), _mm(8), rays=8)
        _rosette(ctx, mx + _mm(160), y + _mm(13), _mm(9), petals=6)
    y += _mm(28)

    with _group(ctx, "Узор · уголки и лоза", "orn_corners"):
        _orn_label(ctx, mx, y, "7. Уголки, завитки и лоза")
        _corners(ctx, mx, y + _mm(4), _mm(30), _mm(26))
        _flourish_corner(ctx, mx + _mm(38), y + _mm(4), _mm(12), flip_x=1, flip_y=1)
        _flourish_corner(ctx, mx + _mm(54), y + _mm(4), _mm(12), flip_x=-1, flip_y=1)
        _flourish_corner(ctx, mx + _mm(38), y + _mm(18), _mm(12), flip_x=1, flip_y=-1)
        _flourish_corner(ctx, mx + _mm(54), y + _mm(18), _mm(12), flip_x=-1, flip_y=-1)
        _vine_strip(ctx, mx + _mm(85), y + _mm(3), _mm(28), leaves=5)
        _vine_strip(ctx, mx + _mm(100), y + _mm(3), _mm(28), leaves=5)
        _checker_band(ctx, mx + _mm(120), y + _mm(8), _mm(55), _mm(6), n=10)
    y += _mm(34)

    with _group(ctx, "Узор · лента-шашка", "orn_ribbon"):
        _orn_label(ctx, mx, y, "8. Лента и шашечный бордюр")
        _ribbon_bar(ctx, mx, y + _mm(5), content_w, _mm(7), ctx.purple)
        _checker_band(ctx, mx, y + _mm(15), content_w, _mm(5), n=16)
    y += _mm(24)

    with _group(ctx, "Узор · рамка врезки", "orn_frame"):
        _orn_label(ctx, mx, y, "9. Рамка врезки / подложка")
        fw = min(content_w, _mm(175))
        _ornate_frame(ctx, mx, y + _mm(4), fw, _mm(36), caption)
    y += _mm(44)

    with _group(ctx, "Узор · бордюр-комбо", "orn_combo"):
        _orn_label(ctx, mx, y, "10. Бордюр-комбо (волна + ромбы + фестон)")
        _wave_line(ctx, mx, y + _mm(5), content_w, periods=5, weight=0.8, segs=12)
        _diamond_chain(ctx, mx, y + _mm(12), content_w, n=9)
        _scallop_edge(ctx, mx, y + _mm(19), content_w, n=10)
        _dot_row(ctx, mx, y + _mm(24), content_w, n=20, size=_mm(1.1), fill=ctx.teal)

    _folio(ctx)


def _layout_backdrop_page(ctx: _Ctx) -> None:
    """Полоса разнообразных подложек на всю страницу."""
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    content_w = ctx.page_w - mx - _mm(geo.MARGIN_R)
    caption = ctx.texts.get("wave_caption", "В эти дни")

    _text_frame(
        ctx, mx, my, content_w, _mm(5),
        "Подложки · выберите Group → Copy/Paste под врезку, цитату или анонс",
        "Метка каталога", ctx.gray, name="kit_backdrop_title",
    )
    y = my + _mm(8)

    with _group(ctx, "Подложка · орнамент", "backdrop_main"):
        _ornate_frame(ctx, mx, y, content_w, _mm(42), caption)
    y += _mm(48)

    with _group(ctx, "Подложка · оранжевая", "backdrop_orange"):
        _rect(ctx, mx, y, _mm(90), _mm(38), fill=ctx.orange_tint, stroke=ctx.orange, stroke_w=1.1)
        _scallop_edge(ctx, mx + _mm(4), y + _mm(3), _mm(82), n=8)
        _dot_row(ctx, mx + _mm(6), y + _mm(8), _mm(78), n=12, fill=ctx.orange)
        _text_frame(ctx, mx + _mm(6), y + _mm(14), _mm(78), _mm(14),
                    caption, "Рубрика", ctx.orange, fill_override=ctx.orange, overprint=False)

    with _group(ctx, "Подложка · бирюзовая", "backdrop_teal"):
        _rect(ctx, mx + _mm(98), y, content_w - _mm(98), _mm(38),
              fill=ctx.paper, stroke=ctx.teal, stroke_w=1.25)
        _double_wave(ctx, mx + _mm(104), y + _mm(6), content_w - _mm(110))
        _text_frame(ctx, mx + _mm(104), y + _mm(14), content_w - _mm(112), _mm(14),
                    caption, "Рубрика", ctx.teal, fill_override=ctx.teal, overprint=False)
    y += _mm(44)

    with _group(ctx, "Подложка · уголки", "backdrop_corners"):
        _nested_frame(ctx, mx, y, content_w, _mm(34), ctx.purple, ctx.orange)
        _text_frame(ctx, mx + _mm(16), y + _mm(10), content_w - _mm(32), _mm(12),
                    caption, "Рубрика", ctx.purple, fill_override=ctx.purple, overprint=False)
    y += _mm(40)

    with _group(ctx, "Подложка · цитата", "backdrop_quote"):
        _rect(ctx, mx, y, content_w, _mm(36), fill=ctx.paper, stroke=ctx.red, stroke_w=0.75)
        _rect(ctx, mx, y, _mm(4), _mm(36), fill=ctx.red, stroke=None, stroke_w=0)
        _triple_rule(ctx, mx + _mm(10), y + _mm(6), content_w - _mm(20))
        _text_frame(ctx, mx + _mm(12), y + _mm(14), content_w - _mm(24), _mm(14),
                    caption, "Лид", ctx.black, name="kit_backdrop_quote")
    y += _mm(42)

    with _group(ctx, "Подложка · лента", "backdrop_ribbon"):
        _ribbon_bar(ctx, mx, y, content_w, _mm(14), ctx.purple)
        _text_frame(ctx, mx + _mm(8), y + _mm(2), content_w - _mm(16), _mm(10),
                    caption, "Короткие шапка", ctx.paper, fill_override=ctx.paper,
                    overprint=False, name="kit_backdrop_ribbon_txt")
    y += _mm(20)

    with _group(ctx, "Подложка · виньетка", "backdrop_vignette"):
        _rect(ctx, mx, y, content_w, _mm(40), fill=ctx.paper, stroke=ctx.purple, stroke_w=0.5)
        _diamond_chain(ctx, mx + _mm(8), y + _mm(8), content_w - _mm(16), n=8)
        _corners(ctx, mx + _mm(6), y + _mm(6), content_w - _mm(12), _mm(28))
        _text_frame(ctx, mx + _mm(20), y + _mm(16), content_w - _mm(40), _mm(12),
                    caption, "Рубрика", ctx.purple, fill_override=ctx.purple, overprint=False)

    _folio(ctx)


def _layout_masthead_gallery(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    _text_frame(ctx, mx, my, cw, _mm(5),
                "Шапка · несколько вариантов плашки — Copy/Paste нужный Group",
                "Метка каталога", ctx.gray, name="kit_mh_gallery_title")
    y = my + _mm(10)
    with _group(ctx, "Шапка · полная", "mh_full"):
        _draw_masthead(ctx, mx, y)
    y += _mm(28)
    with _group(ctx, "Шапка · широкий логотип", "mh_wide"):
        _logo_vector(ctx, mx, y, min(cw, _mm(120)), _mm(geo.LOGO_H * 1.15), tag="wide")
    y += _mm(28)
    with _group(ctx, "Шапка · компакт", "mh_compact"):
        _logo_vector(ctx, mx, y, _mm(70), _mm(14), tag="compact")
        _text_frame(ctx, mx + _mm(74), y + _mm(2), _mm(50), _mm(8),
                    ctx.texts.get("masthead_issue", "№ — / дата"), "Выпуск", ctx.gray)
        _line(ctx, mx, y + _mm(16), mx + cw, y + _mm(16), ctx.purple, 0.7)
    y += _mm(28)
    with _group(ctx, "Шапка · только линейка рубрики", "mh_rubric"):
        _ribbon_bar(ctx, mx, y, cw, _mm(8), ctx.purple)
        _text_frame(ctx, mx + _mm(6), y + _mm(1), cw - _mm(12), _mm(6),
                    ctx.texts.get("masthead_rubric_line", "Актуально"),
                    "Короткие шапка", ctx.paper, fill_override=ctx.paper, overprint=False)
    _folio(ctx)


def _layout_photo_gallery(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    _text_frame(ctx, mx, my, cw, _mm(5),
                "Рамки фото · Place CMYK ≥300 dpi · Copy/Paste Group",
                "Метка каталога", ctx.gray, name="kit_photo_gallery_title")
    y = my + _mm(10)
    sizes = (
        ("Фото · широкий кадр", cw, _mm(55)),
        ("Фото · квадрат", _mm(70), _mm(70)),
        ("Фото · узкий", _mm(55), _mm(75)),
    )
    for i, (label, pw, ph) in enumerate(sizes):
        with _group(ctx, label, f"photo_var_{i}"):
            _orn_label(ctx, mx, y, label)
            photo = _rect(ctx, mx, y + _mm(5), pw, ph, fill=ctx.paper, stroke=ctx.black,
                          stroke_w=geo.PHOTO_STROKE, name=f"kit_photo_frame_{i}")
            tw = etree.SubElement(photo, "TextWrapPreference")
            tw.set("TextWrapMode", "BoundingBoxTextWrap")
            tw.set("TextWrapOffset", f"{_mm(2):.3f} {_mm(2):.3f} {_mm(2):.3f} {_mm(2):.3f}")
            _corners(ctx, mx + _mm(2), y + _mm(7), pw - _mm(4), ph - _mm(4))
            _text_frame(ctx, mx + _mm(4), y + _mm(5) + ph / 2 - _mm(3), pw - _mm(8), _mm(6),
                        "[Place фото]", "Подпись", ctx.gray)
        y += ph + _mm(14)
        if y > ctx.page_h - _mm(40):
            break
    _folio(ctx)


def _layout_weather_gallery(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    txt = ctx.texts.get("weather_badge", ctx.texts.get("wave_caption", "ПРОГНОЗ ПОГОДЫ"))
    _text_frame(ctx, mx, my, cw, _mm(5),
                "Плашки погоды · варианты ширины и цвета",
                "Метка каталога", ctx.gray)
    y = my + _mm(12)
    for i, (label, w, fill, stroke) in enumerate((
        ("Погода · бирюзовая", _mm(90), ctx.teal, ctx.teal),
        ("Погода · фиолетовая", _mm(110), ctx.purple, ctx.purple),
        ("Погода · на всю ширину", cw, ctx.teal, ctx.purple),
    )):
        with _group(ctx, label, f"weather_var_{i}"):
            _rect(ctx, mx, y, w, _mm(16), fill=fill, stroke=None, stroke_w=0,
                  name=f"kit_weather_{i}")
            _text_frame(ctx, mx + _mm(4), y + _mm(3), w - _mm(8), _mm(10),
                        txt, "Погода шапка", ctx.paper, fill_override=ctx.paper, overprint=False)
            _line(ctx, mx, y + _mm(16), mx + w, y + _mm(16), stroke, 0.8)
        y += _mm(28)
    _folio(ctx)


def _layout_shorts_gallery(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    _text_frame(ctx, mx, my, _mm(180), _mm(5),
                "Короткие новости · шапка + карточки — текст впишете в CS3",
                "Метка каталога", ctx.gray)
    _draw_news_sidebar(ctx, mx, my + _mm(10))
    # вторая колонка-вариант
    x2 = mx + _mm(geo.SIDEBAR_W + 10)
    with _group(ctx, "Карточки · широкий вариант", "shorts_wide"):
        _rect(ctx, x2, my + _mm(10), _mm(100), _mm(12), fill=ctx.orange, stroke=None, stroke_w=0)
        _text_frame(ctx, x2 + _mm(3), my + _mm(12), _mm(94), _mm(8),
                    ctx.texts.get("news_header", "Коротко"), "Короткие шапка",
                    ctx.paper, fill_override=ctx.paper, overprint=False)
        for i in range(3):
            cy = my + _mm(28) + i * _mm(28)
            _rect(ctx, x2, cy, _mm(100), _mm(24), fill=ctx.orange_tint, stroke=ctx.orange, stroke_w=0.75)
            _text_frame(ctx, x2 + _mm(3), cy + _mm(4), _mm(94), _mm(16),
                        ctx.texts.get(f"news_card_{i+1}", f"Новость {i+1}"),
                        "Основной текст", ctx.black)
    _folio(ctx)


def _layout_teasers_gallery(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    _text_frame(ctx, mx, my, cw, _mm(5),
                "Тизеры обложки · с уголками и без",
                "Метка каталога", ctx.gray)
    y = _draw_masthead(ctx, mx, my + _mm(8))
    y = _draw_cover_teasers(ctx, mx, y + _mm(6))
    with _group(ctx, "Тизер · крупный анонс", "teaser_hero"):
        _nested_frame(ctx, mx, y + _mm(8), cw, _mm(36), ctx.purple, ctx.orange)
        _text_frame(ctx, mx + _mm(12), y + _mm(18), cw - _mm(24), _mm(14),
                    ctx.texts.get("cover_teaser_1", "Тема номера · Стр. 1"),
                    "Тизер обложки", ctx.purple, fill_override=ctx.purple, overprint=False)
    _folio(ctx)


def _layout_styles_page(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    samples = [
        ("Заголовок 1", "Заголовок первого уровня", ctx.red),
        ("Заголовок 2", "Заголовок второго уровня", ctx.red),
        ("Рубрика", "РУБРИКА / КИКЕР", ctx.black),
        ("Лид", "Лид материала — чуть крупнее основного.", ctx.black),
        ("Основной текст", "Основной текст полосы. Переносы, выключка.", ctx.black),
        ("Подпись", "Подпись к фото или врезке.", ctx.gray),
        ("Реклама", "Пометка «Реклама»", ctx.gray),
        ("Folio", "Сибирская околица · folio", ctx.gray),
    ]
    _text_frame(ctx, mx, my, cw, _mm(5),
                "Пакет стилей · образец Paragraph Styles (Copy текста со стилем)",
                "Метка каталога", ctx.gray)
    y = my + _mm(10)
    with _group(ctx, "Образцы стилей", "styles_samples"):
        for style, sample, col in samples:
            _text_frame(ctx, mx, y, cw, _mm(10), sample, style, col,
                        fill_override=col if col != ctx.black else None,
                        overprint=(col == ctx.black))
            y += _mm(12)
    _folio(ctx)


def _folio(ctx: _Ctx) -> None:
    if not ctx.want("folio_line"):
        return
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
    """Полоса рекламного формата: основной слот + декоративные рамки."""
    from app.kit.ads import AdFormat
    fmt: AdFormat
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cw = ctx.page_w - mx - _mm(geo.MARGIN_R)
    _text_frame(
        ctx, mx, my, cw, _mm(7),
        f"Реклама: {fmt.name} · {fmt.width_mm:.0f}×{fmt.height_mm:.0f} мм · "
        f"{fmt.area_cm2} см² · ориентир {fmt.price_hint_rub} ₽",
        "Метка каталога", ctx.gray, name="kit_ad_format_label",
    )
    aw, ah = _mm(fmt.width_mm), _mm(fmt.height_mm)
    ax, ay = mx, my + _mm(12)
    max_w = ctx.page_w - mx - _mm(geo.MARGIN_R)
    max_h = ctx.page_h - ay - _mm(geo.MARGIN_B) - _mm(80)
    aw = min(aw, max_w)
    ah = min(ah, max_h)
    with _group(ctx, f"Ad {fmt.id}", f"kit_adfmt_{fmt.id}"):
        _rect(ctx, ax, ay, aw, ah, fill=ctx.paper, stroke=ctx.black, stroke_w=0.75,
              self_id=f"Rectangle/kit_ad_format_{fmt.id}", name=f"kit_ad_format_{fmt.id}")
        _text_frame(
            ctx, ax + _mm(2), ay + _mm(2), aw - _mm(4), _mm(5),
            "Реклама", "Реклама", ctx.gray, name="kit_ad_format_mark",
        )
        _text_frame(
            ctx, ax + _mm(2), ay + _mm(10), aw - _mm(4), max(ah - _mm(20), _mm(8)),
            ctx.texts.get("ad_body_wide") or ctx.texts.get("ad_body_narrow")
            or f"{fmt.name}\n{fmt.description}",
            "Основной текст", ctx.black, name="kit_ad_format_body",
        )
        if ctx.texts.get("ad_price"):
            _text_frame(
                ctx, ax + _mm(2), ay + ah - _mm(8), aw - _mm(4), _mm(6),
                ctx.texts["ad_price"], "Реклама", ctx.gray, name="kit_ad_format_price",
            )
    y2 = ay + ah + _mm(10)
    with _group(ctx, "Рамка · с уголками", "ad_frame_corners"):
        bw = min(cw * 0.55, _mm(110))
        bh = _mm(34)
        _rect(ctx, mx, y2, bw, bh, fill=ctx.paper, stroke=ctx.purple, stroke_w=0.75)
        _corners(ctx, mx + _mm(3), y2 + _mm(3), bw - _mm(6), bh - _mm(6))
        _text_frame(ctx, mx + _mm(8), y2 + _mm(10), bw - _mm(16), _mm(10),
                    "Вариант рамки под макет", "Реклама", ctx.gray)
    bx = mx + min(cw * 0.55, _mm(110)) + _mm(8)
    if bx + _mm(65) < ctx.page_w - _mm(geo.MARGIN_R):
        with _group(ctx, "Рамка · двойная", "ad_frame_double"):
            _nested_frame(ctx, bx, y2, min(_mm(70), cw - (bx - mx)), _mm(34), ctx.orange, ctx.purple)
            _text_frame(ctx, bx + _mm(6), y2 + _mm(10), _mm(55), _mm(10),
                        "Двойная", "Реклама", ctx.gray)
    _folio(ctx)


def _layout_catalog(ctx: _Ctx) -> None:
    mx = _mm(geo.MARGIN_L)
    my = _mm(geo.MARGIN_T)
    cursor_y = my

    _set_layer(ctx, "kit_guides")
    _text_frame(
        ctx, mx, cursor_y, ctx.page_w - mx - _mm(geo.MARGIN_R), _mm(8),
        f"Околица CS3 Kit · {COLOR_PROFILE_DEFAULT} · "
        f"{geo.PAGE_W:.2f}×{geo.PAGE_H:.2f} мм · Groups + Overprint",
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
