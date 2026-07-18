"""Комплектация кита по брифу: сцены + rule-based + Gemini (тексты fillable_keys)."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.kit.brand import ELEMENT_CATALOG, default_include_ids, list_element_ids
from app.kit.scenes import SCENES, get_scene, list_scenes

# Бесплатный tier: https://aistudio.google.com/apikey
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Текстовые ключи, не являющиеся id элементов каталога
_TEXT_KEYS_EXTRA = {
    "news_card_1", "news_card_2", "news_card_3",
    "ad_body_narrow", "ad_body_wide",
    "cover_teaser_1", "cover_teaser_2", "cover_teaser_3",
    "wave_caption", "folio_left", "folio_page",
    "weather_body",
}


def _guess_scene_id(brief: str) -> str | None:
    text = (brief or "").lower()
    if not text.strip():
        return None
    no_ads = any(w in text for w in ("без реклам", "no ad", "без объявлен"))
    rules = (
        ("scene_weather_strip", ("погод", "прогноз", "weather")),
        ("scene_shorts_sidebar", ("только коротк", "сайдбар коротк", "лента коротк")),
        ("scene_cover_teasers", ("обложк", "тизер", "cover")),
        ("scene_feature_decor", ("фичер", "в эти дни", "орнамент")),
        ("scene_news_page", ("полоса новост", "новостн полос", "статья на полос",
                             "материал полос", "главный материал", "новостн")),
        ("scene_ads_bottom", ("низ с реклам", "рекламный блок", "рекламная полоса",
                              "сцена реклам", "баннер низ")),
    )
    for sid, keys in rules:
        if sid == "scene_ads_bottom" and no_ads:
            continue
        if any(k in text for k in keys):
            return sid
    return None


def _rule_based(brief: str, scene_id: str | None = None) -> dict[str, Any]:
    """Подбор элементов / сцены по ключевым словам брифа."""
    text = (brief or "").lower()
    resolved_scene = scene_id or _guess_scene_id(brief)
    scene = get_scene(resolved_scene) if resolved_scene else None

    if scene is not None:
        include = list(scene.elements)
        texts = dict(scene.default_texts)
        # date from brief
        m = re.search(r"(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[./]\d{1,2}[./]\d{2,4})", brief or "", re.I)
        if m and "masthead_issue" in texts:
            texts["masthead_issue"] = m.group(1)
        return {
            "include": include,
            "texts": texts,
            "source": "rules",
            "scene_id": scene.id,
        }

    include = set(default_include_ids())
    texts: dict[str, str] = {
        "masthead_logo": "Сибирская околица",
        "masthead_issue": "№ — / дата",
        "news_header": "Короткие новости",
        "article_kicker": "Рубрика",
        "article_headline": "Заголовок материала",
        "article_lead": "Лид: краткое введение в материал на две колонки.",
        "ad_module": "Реклама",
        "folio_left": "Сибирская околица",
        "folio_page": "Стр. —",
    }

    include.discard("weather_badge")
    if any(w in text for w in ("погод", "прогноз", "weather")):
        include.add("weather_badge")
        texts["weather_badge"] = "Прогноз погоды"

    if any(w in text for w in ("без коротк", "без новост", "no short")):
        include.discard("news_header")
        include.discard("news_card")

    if any(w in text for w in ("много коротк", "лента", "сайдбар")):
        include.add("news_header")
        include.add("news_card")

    if any(w in text for w in ("без реклам", "no ad", "без объявлен")):
        include.discard("ad_module")
        include.discard("ad_module_wide")

    if any(w in text for w in ("только стил", "styles only", "пакет стил")):
        include = {"styles_pack"}

    if any(w in text for w in ("только декор", "ornament", "узор")):
        include = {e.id for e in ELEMENT_CATALOG if e.category == "decor"}
        include.add("styles_pack")

    if any(w in text for w in ("тизер", "обложк")):
        include.add("cover_teaser")

    m = re.search(r"(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[./]\d{1,2}[./]\d{2,4})", brief or "", re.I)
    if m:
        texts["masthead_issue"] = m.group(1)

    valid = set(list_element_ids())
    include = sorted(include & valid)
    return {"include": include, "texts": texts, "source": "rules", "scene_id": None}


def _gemini_api_key() -> str:
    from app.config import GEMINI_API_KEY
    return (
        GEMINI_API_KEY
        or os.environ.get("LG_AI_API_KEY")
        or ""
    ).strip()


def _gemini_model() -> str:
    from app.config import GEMINI_MODEL
    return (os.environ.get("LG_AI_MODEL") or GEMINI_MODEL or DEFAULT_GEMINI_MODEL).strip()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _allowed_text_keys() -> set[str]:
    return set(list_element_ids()) | _TEXT_KEYS_EXTRA | {
        k for s in SCENES for k in s.default_texts
    }


def _normalize_ai_payload(data: dict[str, Any], scene_id: str | None = None) -> dict[str, Any] | None:
    allowed_el = set(list_element_ids())
    allowed_txt = _allowed_text_keys()
    scene = get_scene(scene_id) if scene_id else None
    if scene is None:
        sid = data.get("scene_id")
        if isinstance(sid, str) and get_scene(sid):
            scene = get_scene(sid)
            scene_id = sid

    if scene is not None:
        include = list(scene.elements)
    else:
        include = [i for i in data.get("include", []) if i in allowed_el]
        if not include:
            return None

    raw_texts = data.get("texts") or {}
    texts = {k: str(v) for k, v in raw_texts.items() if k in allowed_txt and str(v).strip()}
    return {
        "include": include,
        "texts": texts,
        "source": "gemini",
        "scene_id": scene.id if scene else scene_id,
    }


def _call_gemini(prompt: str) -> dict[str, Any] | None:
    api_key = _gemini_api_key()
    if not api_key:
        return None
    model = _gemini_model()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model, safe='.-_')}:generateContent"
        f"?key={urllib.parse.quote(api_key, safe='')}"
    )
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        parts = (raw.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return _extract_json_object(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def _ai_compose_gemini(brief: str, scene_id: str | None = None) -> dict[str, Any] | None:
    api_key = _gemini_api_key()
    if not api_key or not (brief or "").strip():
        return None

    scene = get_scene(scene_id) if scene_id else None
    if scene is None:
        guessed = _guess_scene_id(brief)
        scene = get_scene(guessed) if guessed else None

    if scene is not None:
        keys = list(scene.fillable_keys)
        prompt = (
            "Ты редактор районной газеты «Сибирская околица» (Новосибирская обл.).\n"
            "Стиль: коротко, по делу, без канцелярита и кликбейта. Заголовки — живые, не клише.\n"
            "Заполни тексты для сцены вёрстки InDesign CS3.\n"
            "Верни ТОЛЬКО JSON: "
            '{"scene_id":"' + scene.id + '","texts":{...}}.\n'
            f"Ключи texts (все обязательны): {json.dumps(keys, ensure_ascii=False)}\n"
            "Правила:\n"
            "- article_headline: 4–10 слов, в духе SchoolBook-заголовка\n"
            "- article_lead: 2–3 предложения\n"
            "- article_column: 3–5 предложений связного текста\n"
            "- news_card_*: 1–2 предложения, факты района\n"
            "- cover_teaser_*: «• Тема  Стр. N»\n"
            "- masthead_issue: формат «№ N / ДД месяца ГГГГ г.» если есть дата в брифе\n"
            "- weather_body: кратко температура/условия\n"
            "Не выдумывай другие ключи. Пиши по-русски.\n\n"
            f"Бриф выпуска: {brief}\n"
            f"Сцена: {scene.name} — {scene.description}\n"
            f"Плейсхолдеры: {json.dumps(scene.default_texts, ensure_ascii=False)}"
        )
        data = _call_gemini(prompt)
        if not data:
            return None
        data["scene_id"] = scene.id
        data["include"] = list(scene.elements)
        return _normalize_ai_payload(data, scene_id=scene.id)

    catalog = [
        {"id": e.id, "name": e.name, "category": e.category, "description": e.description}
        for e in ELEMENT_CATALOG
    ]
    scenes_meta = list_scenes()
    prompt = (
        "Ты комплектатор библиотеки элементов газеты для InDesign CS3.\n"
        'Верни ТОЛЬКО JSON: {"scene_id":"id|null","include":["id",...],'
        '"texts":{"key":"подпись"}}.\n'
        "Если подходит сцена из списка — укажи scene_id и texts для её fillable_keys.\n"
        "Иначе include — только id из каталога. Не выдумывай новые id.\n\n"
        f"Бриф: {brief}\n"
        f"Сцены: {json.dumps(scenes_meta, ensure_ascii=False)}\n"
        f"Элементы: {json.dumps(catalog, ensure_ascii=False)}"
    )
    data = _call_gemini(prompt)
    if not data:
        return None
    return _normalize_ai_payload(data)


def compose_kit_selection(
    brief: str = "",
    use_ai: bool = True,
    scene_id: str | None = None,
) -> dict[str, Any]:
    """
    Возвращает {include, texts, source, scene_id}.
    При use_ai и GEMINI_API_KEY — Gemini заполняет тексты сцены / комплектацию.
    """
    base = _rule_based(brief, scene_id=scene_id)
    if use_ai:
        ai = _ai_compose_gemini(brief, scene_id=base.get("scene_id") or scene_id)
        if ai:
            merged_texts = {**base["texts"], **ai.get("texts", {})}
            sid = ai.get("scene_id") or base.get("scene_id")
            include = ai["include"] if ai.get("include") else base["include"]
            if sid and get_scene(sid):
                include = list(get_scene(sid).elements)
            return {
                "include": include,
                "texts": merged_texts,
                "source": ai.get("source", "gemini"),
                "scene_id": sid,
            }
    return base
