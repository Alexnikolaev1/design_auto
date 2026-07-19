"""PNG-превью каталога / сцены CS3 Kit (геометрия Околицы)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import MM_TO_PT
from app.kit import geometry as geo
from app.kit.brand import BRAND_SWATCHES
from app.kit.scenes import get_scene
from app.layout import fonts as font_manager
from app.layout.okolica_profile import FONT_BODY, FONT_HEADLINE, FONT_RUBRIC


def _cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    c, m, y, k = c / 100.0, m / 100.0, y / 100.0, k / 100.0
    r = 255 * (1 - c) * (1 - k)
    g = 255 * (1 - m) * (1 - k)
    b = 255 * (1 - y) * (1 - k)
    return int(r), int(g), int(b)


def _font(ps: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_manager.scan_fonts()
    r = font_manager.resolve(ps)
    if r.path:
        try:
            return ImageFont.truetype(str(r.path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def render_kit_preview_png(
    include: list[str],
    texts: dict[str, str],
    out_path: Path,
    scale: float = 2.0,
    scene_id: str | None = None,
    pack_id: str | None = None,
) -> Path:
    """Рисует упрощённый каталог/сцену (RGB-превью; в INX цвета CMYK)."""
    scene = get_scene(scene_id) if scene_id else None
    if scene is not None:
        want = set(scene.elements)
        texts = {**scene.default_texts, **(texts or {})}
    else:
        want = set(include)

    # Явный pack_id важнее эвристики — иначе снова «один бордюр + Стили:»
    if pack_id:
        kind_map = {
            "pack_decor": "ornament",
            "pack_backdrop": "backdrop",
            "pack_masthead": "masthead",
            "pack_photo": "photo",
            "pack_weather": "weather",
            "pack_shorts": "shorts",
            "pack_teasers": "teasers",
            "pack_styles": "styles",
        }
        forced = kind_map.get(pack_id)
    else:
        forced = None

    pw = int(geo.PAGE_W * MM_TO_PT * scale)
    ph = int(geo.PAGE_H * MM_TO_PT * scale)
    img = Image.new("RGB", (pw, ph), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    def rgb(name: str) -> tuple[int, int, int]:
        return _cmyk_to_rgb(*BRAND_SWATCHES[name])

    def mm(v: float) -> float:
        return v * MM_TO_PT * scale

    mx, my = mm(geo.MARGIN_L), mm(geo.MARGIN_T)
    small = _font(FONT_BODY, max(8, int(7 * scale)))
    body_f = _font(FONT_BODY, max(9, int(9 * scale)))
    head_f = _font(FONT_HEADLINE, max(14, int(18 * scale)))
    rub_f = _font(FONT_RUBRIC, max(10, int(11 * scale)))

    decor = {"decor_rule", "decor_corners", "decor_wave_border", "decor_divider"}
    core = want - {"styles_pack", "folio_line"}
    is_ornament = forced == "ornament" or (
        forced is None and bool(core) and core <= decor and len(core & decor) >= 3
    )
    is_backdrop = forced == "backdrop" or (
        forced is None and core == {"decor_wave_border", "decor_corners"}
    )
    mast = {"masthead_logo", "masthead_issue", "masthead_rubric_line"}
    is_masthead = forced == "masthead" or (
        forced is None and bool(core) and core <= mast and "masthead_logo" in core
    )
    is_photo = forced == "photo" or (
        forced is None and core in ({"article_photo_frame", "decor_corners"}, {"article_photo_frame"})
    )
    is_weather = forced == "weather" or (forced is None and core == {"weather_badge"})
    is_shorts = forced == "shorts" or (forced is None and core == {"news_header", "news_card"})
    is_teasers = forced == "teasers" or (forced is None and "cover_teaser" in core)
    is_styles = forced == "styles" or (forced is None and not core)

    if is_ornament or is_backdrop:
        return _render_ornament_preview(
            img, draw, mx, my, pw, ph, mm, scale, rgb, small, rub_f, texts or {},
            backdrop=is_backdrop, out_path=out_path,
        )

    if is_masthead or is_photo or is_weather or is_shorts or is_teasers or is_styles:
        return _render_gallery_preview(
            img, draw, mx, my, pw, ph, mm, scale, rgb, small, rub_f, body_f, head_f,
            texts or {}, want, out_path=out_path,
            kind=("masthead" if is_masthead else "photo" if is_photo else
                  "weather" if is_weather else "shorts" if is_shorts else
                  "teasers" if is_teasers else "styles"),
        )

    title = "Сцена: " + scene.name if scene else "Околица CS3 Kit · Process CMYK · превью"
    draw.text((mx, mm(3)), title, font=small, fill=rgb("OkolicaGray"))

    y = my
    if "masthead_logo" in want:
        draw.rounded_rectangle(
            [mx, y, mx + mm(geo.LOGO_W), y + mm(geo.LOGO_H)],
            radius=4, fill=rgb("OkolicaPurple"),
        )
        draw.text((mx + mm(8), y + mm(2)), texts.get("masthead_logo", "Сибирская околица"),
                  font=rub_f, fill=(255, 255, 255))
    if "masthead_issue" in want:
        draw.text((mx + mm(geo.LOGO_W + 3), y + mm(3)),
                  texts.get("masthead_issue", "№ — / дата"),
                  font=small, fill=rgb("OkolicaGray"))
    if "masthead_rubric_line" in want:
        rx = mx + mm(geo.LOGO_W + 54)
        draw.text((rx, y + mm(2)), texts.get("masthead_rubric_line", "Рубрика"),
                  font=rub_f, fill=(20, 20, 20))
        draw.line([rx, y + mm(9), rx + mm(50), y + mm(9)], fill=(20, 20, 20), width=1)
    y += mm(geo.LOGO_H + 4)

    if "news_header" in want or "news_card" in want:
        sb = mm(geo.SIDEBAR_W)
        ny = y
        if "news_header" in want:
            draw.rectangle([mx, ny, mx + sb, ny + mm(geo.NEWS_HEADER_H)], fill=rgb("OkolicaOrange"))
            draw.text((mx + mm(2), ny + mm(1)), texts.get("news_header", "Короткие новости"),
                      font=body_f, fill=(255, 255, 255))
            ny += mm(geo.NEWS_HEADER_H + 2)
        if "news_card" in want:
            for i in range(geo.NEWS_CARDS):
                cy = ny + i * mm(geo.NEWS_CARD_H + geo.NEWS_CARD_GAP)
                draw.rectangle(
                    [mx, cy, mx + sb, cy + mm(geo.NEWS_CARD_H)],
                    fill=rgb("OkolicaOrangeTint"), outline=rgb("OkolicaOrange"), width=2,
                )
                t = texts.get(f"news_card_{i+1}", f"Новость {i+1}")[:48]
                draw.text((mx + mm(2), cy + mm(2)), t, font=small, fill=(20, 20, 20))

    ax = mm(geo.main_cols_x())
    ay = my + mm(18) if scene and scene.id == "scene_news_page" else y
    if scene and scene.id == "scene_feature_decor":
        ax, ay = mx, my + mm(20)
    if "article_kicker" in want:
        draw.text((ax, ay), texts.get("article_kicker", "Рубрика"), font=rub_f, fill=(20, 20, 20))
        ay += mm(7)
    if "article_headline" in want:
        draw.text((ax, ay), texts.get("article_headline", "Заголовок")[:40],
                  font=head_f, fill=rgb("OkolicaRed"))
        ay += mm(16)
    if "article_photo_frame" in want:
        box = [ax, ay, ax + mm(geo.LEAD_PHOTO_W), ay + mm(geo.LEAD_PHOTO_H)]
        draw.rectangle(box, outline=(30, 30, 30), width=max(1, int(scale)))
        draw.text((ax + mm(30), ay + mm(geo.LEAD_PHOTO_H / 2)), "[Фото]",
                  font=small, fill=rgb("OkolicaGray"))
        ay += mm(geo.LEAD_PHOTO_H + 4)
    if "article_lead" in want:
        draw.text((ax, ay), texts.get("article_lead", "Лид…")[:70], font=body_f, fill=(20, 20, 20))
        ay += mm(12)

    if "cover_teaser" in want:
        ty = y + mm(8)
        for i in range(3):
            draw.text((mx, ty + i * mm(10)),
                      texts.get(f"cover_teaser_{i+1}", f"• Тема {i+1}"),
                      font=rub_f, fill=rgb("OkolicaPurple"))

    if "weather_badge" in want:
        wx, wy = mx + mm(geo.SIDEBAR_W + 4), my + mm(20)
        draw.rectangle([wx, wy, wx + mm(70), wy + mm(10)], fill=rgb("OkolicaTeal"))
        draw.text((wx + mm(2), wy + mm(2)), texts.get("weather_badge", "Прогноз погоды"),
                  font=body_f, fill=(255, 255, 255))

    dy = ph - mm(60)
    if "decor_rule" in want:
        draw.line([mx, dy, mx + mm(80), dy], fill=(0, 0, 0), width=1)
    if "decor_wave_border" in want:
        draw.rectangle([mx + mm(100), dy, mx + mm(155), dy + mm(30)],
                       outline=rgb("OkolicaPurple"), width=2)
        draw.text((mx + mm(110), dy + mm(12)), texts.get("wave_caption", "В эти дни"),
                  font=rub_f, fill=rgb("OkolicaPurple"))
    if "decor_corners" in want:
        arm = mm(geo.CORNER_ARM)
        cx0, cy0 = mx + mm(90), dy
        for a, b in (
            ((cx0, cy0 + arm), (cx0, cy0)), ((cx0, cy0), (cx0 + arm, cy0)),
            ((cx0 + mm(24) - arm, cy0), (cx0 + mm(24), cy0)),
            ((cx0 + mm(24), cy0), (cx0 + mm(24), cy0 + arm)),
        ):
            draw.line([*a, *b], fill=rgb("OkolicaPurple"), width=2)

    ad_y = ph - mm(geo.MARGIN_B + geo.AD_ROW_H)
    if "ad_module" in want:
        draw.rectangle([mx, ad_y, mx + mm(geo.AD_NARROW_W), ad_y + mm(geo.AD_ROW_H)],
                       outline=(0, 0, 0), width=1)
        draw.text((mx + mm(2), ad_y + mm(2)), "Реклама", font=small, fill=rgb("OkolicaGray"))
        draw.text((mx + mm(2), ad_y + mm(10)),
                  texts.get("ad_body_narrow", "")[:28], font=small, fill=(20, 20, 20))
    if "ad_module_wide" in want:
        ax0 = mx + mm(geo.AD_NARROW_W + geo.AD_GAP) if "ad_module" in want else mx
        draw.rectangle([ax0, ad_y, ax0 + mm(geo.AD_WIDE_W), ad_y + mm(geo.AD_ROW_H)],
                       outline=(0, 0, 0), width=1)
        draw.text((ax0 + mm(4), ad_y + mm(10)),
                  texts.get("ad_body_wide", "Реклама широкая")[:40],
                  font=small, fill=rgb("OkolicaGray"))

    if "folio_line" in want:
        fy = ph - mm(geo.MARGIN_B - 2)
        draw.line([mx, fy - mm(3), pw - mm(geo.MARGIN_R), fy - mm(3)],
                  fill=rgb("OkolicaGray"), width=1)
        draw.text((mx, fy), texts.get("folio_left", "Сибирская околица"),
                  font=small, fill=rgb("OkolicaGray"))

    if "styles_pack" in want:
        draw.text((mx, ph - mm(8)),
                  "Стили: Заголовок 1–2 · Рубрика · Лид · Основной · Подпись · Реклама · Folio",
                  font=small, fill=rgb("OkolicaGray"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _render_ornament_preview(
    img, draw, mx, my, pw, ph, mm, scale, rgb, small, rub_f, texts, *,
    backdrop: bool, out_path: Path,
) -> Path:
    import math
    purple = rgb("OkolicaPurple")
    orange = rgb("OkolicaOrange")
    teal = rgb("OkolicaTeal")
    red = rgb("OkolicaRed")
    gray = rgb("OkolicaGray")
    caption = texts.get("wave_caption", "В эти дни")
    cw = pw - mx - mm(geo.MARGIN_R)

    title = "Подложки" if backdrop else "Полоса узоров Околицы"
    draw.text((mx, mm(4)), title, font=small, fill=gray)

    def wave(x, y, w, amp=None, periods=6, color=purple, width=2):
        amp = amp if amp is not None else mm(2.2)
        pts = []
        segs = 40
        for i in range(segs + 1):
            t = i / segs
            pts.append((x + w * t, y + amp * math.sin(t * math.pi * 2 * periods)))
        draw.line(pts, fill=color, width=width)

    def scallop(x, y, w, n=10):
        step = w / n
        for i in range(n):
            cx = x + step * (i + 0.5)
            r = step * 0.4
            bbox = [cx - r, y - r, cx + r, y + r]
            draw.arc(bbox, 180, 360, fill=purple, width=2)

    def diamonds(x, y, w, n=10):
        step = w / n
        s = step * 0.25
        for i in range(n):
            cx = x + step * (i + 0.5)
            col = red if i % 2 == 0 else purple
            draw.polygon([(cx, y - s), (cx + s, y), (cx, y + s), (cx - s, y)], outline=col)

    def rosette(cx, cy, r, petals=8):
        for i in range(petals):
            ang = 2 * math.pi * i / petals
            draw.line(
                [cx + r * 0.2 * math.cos(ang), cy + r * 0.2 * math.sin(ang),
                 cx + r * math.cos(ang), cy + r * math.sin(ang)],
                fill=purple, width=2,
            )
        draw.ellipse([cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2], outline=orange, width=2)

    caption = texts.get("wave_caption", "В эти дни")
    if backdrop:
        y = my + mm(8)
        draw.rectangle([mx, y, mx + cw, y + mm(42)], outline=purple, width=3)
        draw.rectangle([mx + mm(8), y + mm(6), mx + cw - mm(8), y + mm(10)], fill=purple)
        for i in range(12):
            col = purple if i % 2 == 0 else orange
            draw.rectangle([mx + mm(10) + i * mm(12), y + mm(12), mx + mm(20) + i * mm(12), y + mm(16)], fill=col)
        draw.text((mx + mm(20), y + mm(22)), caption, font=rub_f, fill=purple)
        y += mm(50)
        bw = (cw - mm(4)) / 2
        draw.rectangle([mx, y, mx + bw, y + mm(36)], fill=rgb("OkolicaOrangeTint"), outline=orange, width=2)
        draw.text((mx + mm(8), y + mm(12)), caption, font=rub_f, fill=orange)
        draw.rectangle([mx + bw + mm(4), y, mx + cw, y + mm(36)], outline=teal, width=2)
        draw.text((mx + bw + mm(12), y + mm(12)), caption, font=rub_f, fill=teal)
        y += mm(44)
        draw.rectangle([mx, y, mx + cw, y + mm(32)], outline=purple, width=2)
        draw.text((mx + mm(16), y + mm(10)), caption, font=rub_f, fill=purple)
        y += mm(38)
        draw.rectangle([mx, y, mx + cw, y + mm(28)], outline=red, width=2)
        draw.rectangle([mx, y, mx + mm(5), y + mm(28)], fill=red)
        draw.text((mx + mm(12), y + mm(8)), caption, font=rub_f, fill=(30, 30, 30))
        y += mm(34)
        draw.rectangle([mx, y, mx + cw, y + mm(14)], fill=purple)
        draw.text((mx + mm(8), y + mm(2)), caption, font=rub_f, fill=(255, 255, 255))
        y += mm(20)
        draw.rectangle([mx, y, mx + cw, y + mm(30)], outline=purple, width=1)
        for i in range(10):
            col = purple if i % 2 == 0 else rgb("OkolicaOrangeTint")
            draw.rectangle([mx + mm(8) + i * mm(14), y + mm(5), mx + mm(20) + i * mm(14), y + mm(10)], fill=col)
        draw.text((mx + mm(20), y + mm(14)), caption, font=rub_f, fill=purple)
    else:
        y = my + mm(4)
        draw.rectangle([mx, y, mx + cw, y + mm(9)], fill=purple)
        draw.rectangle([mx, y + mm(9), mx + cw, y + mm(11.5)], fill=orange)
        draw.text((mx + mm(4), y + mm(2)), "Сибирская околица · фирменный бордюр",
                  font=rub_f, fill=(255, 255, 255))
        y += mm(16)
        draw.text((mx, y), "1. Линейки", font=small, fill=gray)
        draw.rectangle([mx, y + mm(4), mx + cw, y + mm(5.5)], fill=(0, 0, 0))
        draw.rectangle([mx, y + mm(6.5), mx + cw, y + mm(7.2)], fill=(0, 0, 0))
        y += mm(12)
        draw.text((mx, y), "2. Шахматный бордюр", font=small, fill=gray)
        for i in range(16):
            col = purple if i % 2 == 0 else rgb("OkolicaOrangeTint")
            draw.rectangle([mx + i * (cw / 16), y + mm(4), mx + (i + 1) * (cw / 16), y + mm(10)], fill=col)
        y += mm(14)
        draw.text((mx, y), "3. Цветные плашки", font=small, fill=gray)
        cols = [purple, orange, teal, red, purple, orange, teal, red]
        tw = cw / 8
        for i, col in enumerate(cols):
            draw.rectangle([mx + i * tw + 1, y + mm(4), mx + (i + 1) * tw - 1, y + mm(12)], fill=col)
        y += mm(16)
        draw.text((mx, y), "4. Рамка с уголками", font=small, fill=gray)
        draw.rectangle([mx, y + mm(4), mx + cw, y + mm(26)], outline=purple, width=2)
        draw.text((mx + mm(12), y + mm(10)), caption, font=rub_f, fill=purple)
        y += mm(30)
        draw.text((mx, y), "5. Три модуля", font=small, fill=gray)
        cw3 = (cw - mm(6)) / 3
        for i, (fill, stroke) in enumerate((
            (rgb("OkolicaOrangeTint"), orange), (None, teal), (None, purple),
        )):
            x = mx + i * (cw3 + mm(3))
            if fill:
                draw.rectangle([x, y + mm(4), x + cw3, y + mm(30)], fill=fill, outline=stroke, width=2)
            else:
                draw.rectangle([x, y + mm(4), x + cw3, y + mm(30)], outline=stroke, width=2)
            draw.text((x + mm(4), y + mm(12)), caption, font=small, fill=stroke)
        y += mm(36)
        draw.text((mx, y), "6. Большая врезка", font=small, fill=gray)
        draw.rectangle([mx, y + mm(4), mx + cw, y + mm(36)], outline=purple, width=3)
        draw.rectangle([mx + mm(8), y + mm(8), mx + cw - mm(8), y + mm(11)], fill=purple)
        draw.text((mx + mm(16), y + mm(16)), caption, font=rub_f, fill=purple)
        y += mm(42)
        draw.text((mx, y), "7. Комбо-бордюр", font=small, fill=gray)
        draw.rectangle([mx, y + mm(4), mx + cw, y + mm(7)], fill=purple)
        draw.rectangle([mx, y + mm(7.5), mx + cw, y + mm(9)], fill=orange)
        draw.rectangle([mx, y + mm(9.5), mx + cw, y + mm(11)], fill=teal)
        for i in range(14):
            col = purple if i % 2 == 0 else rgb("OkolicaOrangeTint")
            draw.rectangle([mx + i * (cw / 14), y + mm(13), mx + (i + 1) * (cw / 14), y + mm(18)], fill=col)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path



def _render_gallery_preview(
    img, draw, mx, my, pw, ph, mm, scale, rgb, small, rub_f, body_f, head_f, texts, want, *,
    kind: str, out_path: Path,
) -> Path:
    purple = rgb("OkolicaPurple")
    orange = rgb("OkolicaOrange")
    teal = rgb("OkolicaTeal")
    gray = rgb("OkolicaGray")
    cw = pw - mx - mm(geo.MARGIN_R)
    titles = {
        "masthead": "Шапка — варианты плашки",
        "photo": "Рамки фото — Place в CS3",
        "weather": "Плашки погоды",
        "shorts": "Короткие новости",
        "teasers": "Тизеры обложки",
        "styles": "Образцы стилей",
    }
    draw.text((mx, mm(4)), titles.get(kind, kind), font=small, fill=gray)
    y = my + mm(6)
    if kind == "masthead":
        draw.rounded_rectangle([mx, y, mx + mm(100), y + mm(18)], radius=3, fill=purple)
        draw.text((mx + mm(8), y + mm(4)), texts.get("masthead_logo", "Сибирская околица"),
                  font=rub_f, fill=(255, 255, 255))
        y += mm(28)
        draw.rounded_rectangle([mx, y, mx + mm(70), y + mm(14)], radius=2, fill=purple)
        draw.text((mx + mm(74), y + mm(3)), texts.get("masthead_issue", "№ — / дата"),
                  font=small, fill=gray)
        y += mm(24)
        draw.rectangle([mx, y, mx + cw, y + mm(8)], fill=purple)
        draw.text((mx + mm(6), y + mm(1)), texts.get("masthead_rubric_line", "Актуально"),
                  font=rub_f, fill=(255, 255, 255))
    elif kind == "photo":
        for label, w, h in (("широкий", cw, mm(48)), ("квадрат", mm(65), mm(65))):
            draw.rectangle([mx, y, mx + w, y + h], outline=(0, 0, 0), width=2)
            draw.text((mx + mm(6), y + h / 2), f"[Place · {label}]", font=small, fill=gray)
            y += h + mm(10)
    elif kind == "weather":
        for fill, w in ((teal, mm(90)), (purple, mm(110)), (teal, cw)):
            draw.rectangle([mx, y, mx + w, y + mm(14)], fill=fill)
            draw.text((mx + mm(4), y + mm(3)), texts.get("weather_badge", "ПРОГНОЗ ПОГОДЫ"),
                      font=rub_f, fill=(255, 255, 255))
            y += mm(22)
    elif kind == "shorts":
        draw.rectangle([mx, y, mx + mm(geo.SIDEBAR_W), y + mm(12)], fill=orange)
        draw.text((mx + mm(3), y + mm(2)), "Коротко", font=rub_f, fill=(255, 255, 255))
        y += mm(16)
        for i in range(3):
            draw.rectangle([mx, y, mx + mm(geo.SIDEBAR_W), y + mm(22)],
                           fill=rgb("OkolicaOrangeTint"), outline=orange, width=1)
            y += mm(26)
    elif kind == "teasers":
        draw.rounded_rectangle([mx, y, mx + mm(80), y + mm(14)], radius=2, fill=purple)
        y += mm(22)
        for i in range(3):
            draw.text((mx, y), texts.get(f"cover_teaser_{i+1}", f"• Тема {i+1}  Стр. {i+3}"),
                      font=rub_f, fill=purple)
            y += mm(12)
        draw.rectangle([mx, y, mx + cw, y + mm(28)], outline=purple, width=2)
        draw.text((mx + mm(12), y + mm(8)), texts.get("cover_teaser_1", "Тема номера"),
                  font=rub_f, fill=purple)
    else:  # styles
        for sample, size in (
            ("Заголовок первого уровня", head_f),
            ("Рубрика / кикер", rub_f),
            ("Основной текст полосы", body_f),
            ("Подпись к фото", small),
        ):
            draw.text((mx, y), sample, font=size, fill=(30, 30, 30) if size != head_f else rgb("OkolicaRed"))
            y += mm(14)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
