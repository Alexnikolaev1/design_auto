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
) -> Path:
    """Рисует упрощённый каталог/сцену (RGB-превью; в INX цвета CMYK)."""
    scene = get_scene(scene_id) if scene_id else None
    if scene is not None:
        want = set(scene.elements)
        texts = {**scene.default_texts, **(texts or {})}
    else:
        want = set(include)

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
