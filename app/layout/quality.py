"""Оценка качества макета (0–100) для сравнения вариантов."""
from __future__ import annotations

from app.layout.engine import LayoutPlan


def _grade(score: float) -> str:
    if score >= 92:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def compute_layout_quality(
    plan: LayoutPlan,
    smoke: dict | None = None,
    print_checklist: dict | None = None,
    reference_score: float | None = None,
    ad_slot_report: dict | None = None,
) -> dict:
    score = 100.0
    notes: list[str] = []

    if smoke and not smoke.get("passed"):
        score -= 25
        notes.append("INX smoke не пройден")
    elif smoke and smoke.get("warnings"):
        score -= min(15, len(smoke["warnings"]) * 3)
        notes.append(f"{len(smoke['warnings'])} предупреждений INX")

    if print_checklist:
        counts = print_checklist.get("counts") or {}
        score -= (counts.get("fail", 0) * 12)
        score -= (counts.get("warn", 0) * 4)
        if not print_checklist.get("ready_for_print"):
            notes.append("Авто-чеклист печати не пройден")

    if ad_slot_report and ad_slot_report.get("empty_slots", 0) > 0:
        score -= min(20, ad_slot_report["empty_slots"] * 8)
        notes.append(f"Пустых рекламных слотов: {ad_slot_report['empty_slots']}")

    if reference_score is not None:
        boost = (reference_score - 50) * 0.15
        score += max(-10, min(10, boost))

    profile = plan.profile
    if profile.hyphenation:
        score += 2
    if profile.bleed_mm >= 3:
        score += 2

    total_lines = sum(len(p.preview_lines) for p in plan.pages)
    if total_lines < 3 and plan.pages:
        score -= 10
        notes.append("Мало текста в макете")

    empty_pages = sum(1 for p in plan.pages if not p.preview_lines and not p.images)
    if empty_pages:
        score -= empty_pages * 5
        notes.append(f"Пустых полос: {empty_pages}")

    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "grade": _grade(score),
        "notes": notes[:6],
    }
