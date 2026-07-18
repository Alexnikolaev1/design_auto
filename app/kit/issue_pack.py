"""
Сборка выпуска (Issue Pack): несколько сцен в одном ZIP из брифа / текста DOCX.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.kit.compose import compose_kit_selection
from app.kit.scenes import get_scene


DEFAULT_ISSUE_SCENES = (
    "scene_news_page",
    "scene_shorts_sidebar",
    "scene_ads_bottom",
)


@dataclass
class IssueScenePlan:
    scene_id: str
    texts: dict[str, str] = field(default_factory=dict)
    source: str = "rules"


@dataclass
class IssuePackPlan:
    scenes: list[IssueScenePlan]
    brief: str = ""
    source_text_excerpt: str = ""
    media_slots: list[dict[str, str]] = field(default_factory=list)
    mode: str = "issue"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "brief": self.brief,
            "scene_ids": [s.scene_id for s in self.scenes],
            "scenes": [
                {"scene_id": s.scene_id, "texts": s.texts, "source": s.source}
                for s in self.scenes
            ],
            "media_slots": self.media_slots,
            "source_text_excerpt": self.source_text_excerpt[:500],
        }


def _split_articles(source_text: str) -> list[dict[str, str]]:
    """Грубое деление текста выпуска на материалы по заголовкам."""
    text = (source_text or "").strip()
    if not text:
        return []
    parts = re.split(r"\n{2,}", text)
    articles: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for part in parts:
        line = part.strip()
        if not line:
            continue
        first = line.split("\n", 1)[0].strip()
        rest = line.split("\n", 1)[1].strip() if "\n" in line else ""
        # короткий первый ряд без точки → заголовок
        is_heading = len(first) <= 80 and not first.endswith(".") and (
            first.isupper() or len(first.split()) <= 12 or first.startswith("#")
        )
        if is_heading and (rest or len(first.split()) <= 10):
            if current:
                articles.append(current)
            current = {
                "headline": first.lstrip("#").strip(),
                "body": rest,
                "lead": rest.split(".")[0] + "." if rest else "",
            }
        elif current is None:
            current = {
                "headline": first[:70],
                "body": line,
                "lead": (line.split(".")[0] + ".") if "." in line else line[:120],
            }
        else:
            current["body"] = (current.get("body", "") + "\n" + line).strip()
            if not current.get("lead"):
                current["lead"] = (line.split(".")[0] + ".") if "." in line else line[:120]
    if current:
        articles.append(current)
    return articles[:6]


def _shorts_from_text(source_text: str, n: int = 3) -> list[str]:
    lines = [ln.strip() for ln in (source_text or "").splitlines() if ln.strip()]
    shorts = [ln for ln in lines if 20 <= len(ln) <= 160]
    if len(shorts) < n:
        arts = _split_articles(source_text)
        for a in arts:
            bit = (a.get("lead") or a.get("headline") or "").strip()
            if bit and bit not in shorts:
                shorts.append(bit)
    while len(shorts) < n:
        shorts.append(f"Краткая новость района {len(shorts)+1}.")
    return shorts[:n]


def _media_slots_for_scenes(scene_ids: list[str]) -> list[dict[str, str]]:
    slots = []
    if "scene_news_page" in scene_ids or "scene_feature_decor" in scene_ids:
        slots.append({
            "id": "lead_photo",
            "frame": "kit_article_photo_frame",
            "hint": "Положите CMYK JPEG/TIFF ≥300 dpi в Links/, имя: lead_photo.jpg",
            "caption_key": "photo_caption",
        })
    if "scene_cover_teasers" in scene_ids:
        slots.append({
            "id": "cover_visual",
            "frame": "kit_masthead_logo",
            "hint": "Обложка: при необходимости замените плашку лого на фирменный знак",
            "caption_key": "",
        })
    return slots


def choose_issue_scene_ids(
    brief: str = "",
    source_text: str = "",
    explicit: list[str] | None = None,
) -> list[str]:
    if explicit:
        out = []
        for sid in explicit:
            if get_scene(sid) and sid not in out:
                out.append(sid)
        return out or list(DEFAULT_ISSUE_SCENES)

    text = f"{brief}\n{source_text}".lower()
    chosen: list[str] = ["scene_news_page"]

    if any(w in text for w in ("погод", "прогноз", "weather")):
        chosen.append("scene_weather_strip")
    else:
        chosen.append("scene_shorts_sidebar")

    if any(w in text for w in ("обложк", "тизер", "cover")):
        chosen.append("scene_cover_teasers")

    if any(w in text for w in ("фичер", "в эти дни")):
        chosen.append("scene_feature_decor")

    if not any(w in text for w in ("без реклам", "no ad")):
        chosen.append("scene_ads_bottom")

    # dedupe keep order
    seen = set()
    ordered = []
    for sid in chosen:
        if sid not in seen and get_scene(sid):
            seen.add(sid)
            ordered.append(sid)
    return ordered[:5] or list(DEFAULT_ISSUE_SCENES)


def fill_scene_texts_from_source(
    scene_id: str,
    brief: str,
    source_text: str,
    articles: list[dict[str, str]],
    base_texts: dict[str, str],
) -> dict[str, str]:
    texts = dict(base_texts)
    scene = get_scene(scene_id)
    if not scene:
        return texts

    m = re.search(
        r"(№\s*\d+[^\n]{0,40}|\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        f"{brief}\n{source_text}",
        re.I,
    )
    if m and "masthead_issue" in scene.default_texts:
        texts["masthead_issue"] = m.group(1).strip()

    if scene_id == "scene_news_page" and articles:
        a = articles[0]
        texts["article_headline"] = a.get("headline") or texts.get("article_headline", "")
        texts["article_lead"] = (a.get("lead") or "")[:280] or texts.get("article_lead", "")
        body = (a.get("body") or "")[:900]
        if body:
            texts["article_column"] = body
        texts["article_kicker"] = texts.get("article_kicker") or "Актуально"
        shorts = _shorts_from_text(source_text or "\n".join(
            x.get("lead", "") for x in articles[1:]
        ))
        for i, s in enumerate(shorts[:3], 1):
            texts[f"news_card_{i}"] = s

    elif scene_id in ("scene_shorts_sidebar", "scene_weather_strip"):
        shorts = _shorts_from_text(source_text)
        for i, s in enumerate(shorts[:3], 1):
            texts[f"news_card_{i}"] = s
        if scene_id == "scene_weather_strip" and any(
            w in (source_text + brief).lower() for w in ("°", "градус", "погод", "+")
        ):
            for ln in (source_text or brief).splitlines():
                if any(w in ln.lower() for w in ("погод", "°", "градус", "ясно", "дожд")):
                    texts["weather_body"] = ln.strip()[:120]
                    break

    elif scene_id == "scene_cover_teasers" and articles:
        for i, a in enumerate(articles[:3], 1):
            page = 2 + i
            texts[f"cover_teaser_{i}"] = f"• {a.get('headline', 'Тема')[:40]}  Стр. {page}"

    elif scene_id == "scene_feature_decor" and articles:
        a = articles[0] if len(articles) == 1 else (articles[1] if len(articles) > 1 else articles[0])
        texts["article_headline"] = a.get("headline") or texts.get("article_headline", "")
        texts["article_lead"] = (a.get("lead") or "")[:200]
        texts["wave_caption"] = "В эти дни"

    elif scene_id == "scene_ads_bottom":
        texts.setdefault("ad_body_narrow", "Рекламодатель · телефон")
        texts.setdefault("ad_body_wide", "Услуги · адрес · телефон")

    texts.setdefault("photo_caption", "Фото: пресс-служба / архив редакции")
    return texts


def plan_issue_pack(
    brief: str = "",
    source_text: str = "",
    use_ai: bool = True,
    scene_ids: list[str] | None = None,
    texts_overrides: dict[str, dict[str, str]] | None = None,
) -> IssuePackPlan:
    """
    texts_overrides: {scene_id: {key: value}} — правки из UI.
    """
    ids = choose_issue_scene_ids(brief, source_text, scene_ids)
    articles = _split_articles(source_text)
    overrides = texts_overrides or {}
    plans: list[IssueScenePlan] = []

    for sid in ids:
        sel = compose_kit_selection(
            brief or source_text[:500],
            use_ai=use_ai,
            scene_id=sid,
        )
        texts = fill_scene_texts_from_source(
            sid, brief, source_text, articles, sel.get("texts") or {},
        )
        # UI overrides for this scene (flat keys also accepted under "")
        if sid in overrides:
            texts.update({k: str(v) for k, v in overrides[sid].items() if str(v).strip()})
        plans.append(IssueScenePlan(scene_id=sid, texts=texts, source=sel.get("source", "rules")))

    return IssuePackPlan(
        scenes=plans,
        brief=brief,
        source_text_excerpt=(source_text or "")[:800],
        media_slots=_media_slots_for_scenes(ids),
    )


def format_media_manifest(slots: list[dict[str, str]]) -> str:
    lines = [
        "LAYOUTGENIUS — MEDIA MANIFEST (текст ↔ фото)",
        "=" * 50,
        "Положите файлы в папку Links/ рядом с INX.",
        "В CS3: File → Place в именованный фрейм.",
        "",
    ]
    if not slots:
        lines.append("(Нет обязательных фотослотов для этого набора сцен.)")
    for s in slots:
        lines.append(f"[{s['id']}]")
        lines.append(f"  frame: {s.get('frame', '')}")
        lines.append(f"  {s.get('hint', '')}")
        if s.get("caption_key"):
            lines.append(f"  caption key: {s['caption_key']}")
        lines.append("")
    return "\n".join(lines)
