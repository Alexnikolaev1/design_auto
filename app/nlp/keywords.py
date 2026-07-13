"""
Извлечение ключевых слов и подбор дополняющих стоковых изображений.

Упрощение относительно исходного ТЗ (см. README): вместо связки
spaCy(ru_core_news_sm) + YAKE используется только YAKE. Модель spaCy для
русского языка весит десятки/сотни МБ и требует скачивания во время
сборки образа — в текущем окружении сборки нет доступа к её источнику
(нет сети до нужных хостов), из-за чего сборка Docker-образа была бы
ненадёжной на Railway. YAKE — чистый Python, без внешних моделей,
и на практике неплохо справляется с ключевыми словами и для русского,
и для английского текста.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import requests
import yake

RU_STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а",
    "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же",
    "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от",
    "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже",
    "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был",
    "него", "до", "вас", "нибудь", "опять", "уж", "вам", "сказал",
    "этот", "эта", "это", "эти", "для", "тот", "чтобы", "кто", "мы",
}


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Извлекает ключевые словосочетания с помощью YAKE (без внешних моделей)."""
    text = text.strip()
    if not text:
        return []

    # YAKE неплохо работает мультиязычно с параметром lan="ru" (движок
    # использует статистику символов/частот, не словарь), но при
    # смешанном ru/en тексте иногда лучше поведение с dedupLim пониже.
    extractor = yake.KeywordExtractor(
        lan="ru", n=2, dedupLim=0.7, top=max_keywords * 3, windowsSize=2
    )
    try:
        raw = extractor.extract_keywords(text)
    except Exception:
        raw = []

    candidates = [kw for kw, _score in sorted(raw, key=lambda x: x[1])]

    cleaned: list[str] = []
    for kw in candidates:
        kw_clean = kw.strip().lower()
        words = [w for w in re.findall(r"[а-яёa-z0-9]+", kw_clean) if w not in RU_STOPWORDS]
        if not words:
            continue
        phrase = " ".join(words)
        if phrase not in cleaned and len(phrase) > 2:
            cleaned.append(phrase)
        if len(cleaned) >= max_keywords:
            break

    return cleaned


def fetch_stock_photo(keyword: str, dest_dir: Path, unsplash_key: str = "",
                       pexels_key: str = "") -> Optional[Path]:
    """
    Пытается найти одно стоковое фото по ключевому слову.

    Требует UNSPLASH_ACCESS_KEY или PEXELS_API_KEY в переменных окружения.
    Если ни один ключ не задан или сеть/API недоступны — возвращает None,
    и вызывающий код должен корректно обработать отсутствие изображения
    (а не падать).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    if unsplash_key:
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": keyword, "per_page": 1, "orientation": "portrait"},
                headers={"Authorization": f"Client-ID {unsplash_key}"},
                timeout=8,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                img_url = results[0]["urls"]["regular"]
                img_resp = requests.get(img_url, timeout=15)
                img_resp.raise_for_status()
                out_path = dest_dir / f"stock_{abs(hash(keyword)) % 10_000}.jpg"
                out_path.write_bytes(img_resp.content)
                return out_path
        except Exception:
            pass

    if pexels_key:
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "per_page": 1, "orientation": "portrait"},
                headers={"Authorization": pexels_key},
                timeout=8,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"]["large"]
                img_resp = requests.get(img_url, timeout=15)
                img_resp.raise_for_status()
                out_path = dest_dir / f"stock_{abs(hash(keyword)) % 10_000}.jpg"
                out_path.write_bytes(img_resp.content)
                return out_path
        except Exception:
            pass

    return None
