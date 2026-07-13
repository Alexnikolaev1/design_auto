"""Переносы слов для типографики (ru-RU, en-US, de-DE, fr-FR)."""
from __future__ import annotations

import re

_HYPHENATORS: dict[str, object] = {}
_WORD_RE = re.compile(r"[\w\u0400-\u04FF]+", re.UNICODE)

_LANG_MAP = {
    "ru-RU": "ru_RU",
    "ru": "ru_RU",
    "en-US": "en_US",
    "en": "en_US",
    "de-DE": "de_DE",
    "de": "de_DE",
    "fr-FR": "fr_FR",
    "fr": "fr_FR",
}


def _get_hyphenator(language: str):
    key = _LANG_MAP.get(language, _LANG_MAP.get(language.split("-")[0], "en_US"))
    if key in _HYPHENATORS:
        return _HYPHENATORS[key]
    try:
        import pyphen
        dic = pyphen.Pyphen(lang=key)
        _HYPHENATORS[key] = dic
        return dic
    except Exception:
        _HYPHENATORS[key] = None
        return None


def syllables(word: str, language: str) -> list[str]:
    """Разбивает слово на слоги (границы переноса). Без переноса — одно слово."""
    if len(word) < 4:
        return [word]
    dic = _get_hyphenator(language)
    if dic is None:
        return [word]
    try:
        hyph = dic.inserted(word)
        parts = [p for p in hyph.split("\u00ad") if p]
        return parts if len(parts) > 1 else [word]
    except Exception:
        return [word]


def can_hyphenate(word: str, language: str) -> bool:
    return len(syllables(word, language)) > 1


def split_for_line(word: str, language: str, max_width: float, measure) -> tuple[str, str] | None:
    """
  Подбирает разрыв слова: (часть на строке + дефис, остаток).
  measure(fragment) -> ширина в pt.
    """
    parts = syllables(word, language)
    if len(parts) < 2:
        return None
    for i in range(len(parts) - 1, 0, -1):
        head = "".join(parts[:i]) + "-"
        if measure(head) <= max_width:
            tail = "".join(parts[i:])
            if tail:
                return head, tail
    return None
