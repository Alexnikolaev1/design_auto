"""
CS3 Open Guarantee — отчёт «откроется и скопируется в InDesign CS3».
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.inx.smoke import smoke_test_inx
from app.kit.preflight import PreflightReport, run_kit_preflight


REQUIRED_MARKERS = (
    'DOMVersion="5.0"',
    'readerVersion="5.0"',
    'Space="CMYK"',
    "Layer/",
    "Group/",
    "ObjectStyle/",
)


@dataclass
class GuaranteeItem:
    id: str
    ok: bool
    title: str
    detail: str = ""


@dataclass
class OpenGuaranteeReport:
    passed: bool = True
    items: list[GuaranteeItem] = field(default_factory=list)
    smoke: dict = field(default_factory=dict)
    preflight: dict = field(default_factory=dict)

    def add(self, item: GuaranteeItem) -> None:
        self.items.append(item)
        if not item.ok:
            self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "badge": "CS3_OPEN_GUARANTEE_PASS" if self.passed else "CS3_OPEN_GUARANTEE_FAIL",
            "items": [i.__dict__ for i in self.items],
            "smoke": self.smoke,
            "preflight": self.preflight,
        }


def run_cs3_open_guarantee(
    inx_bytes: bytes,
    include: list[str] | None = None,
    label: str = "kit",
) -> OpenGuaranteeReport:
    report = OpenGuaranteeReport()
    smoke = smoke_test_inx(inx_bytes)
    report.smoke = smoke.to_dict()
    report.add(GuaranteeItem(
        "smoke", smoke.passed,
        f"[{label}] Smoke DOM 5.0 / AID / structure",
        "; ".join(smoke.errors[:3]) if smoke.errors else f"warnings={len(smoke.warnings)}",
    ))

    pf = run_kit_preflight(inx_bytes, include=include)
    report.preflight = pf.to_dict()
    report.add(GuaranteeItem(
        "preflight", pf.passed,
        f"[{label}] Print preflight CMYK",
        f"fail={pf.to_dict()['fail_count']} warn={pf.to_dict()['warn_count']}",
    ))

    xml = inx_bytes.decode("utf-8", errors="replace")
    for marker in REQUIRED_MARKERS:
        report.add(GuaranteeItem(
            f"marker_{marker[:20]}",
            marker in xml,
            f"[{label}] Маркер {marker}",
            "ok" if marker in xml else "MISSING",
        ))

    # Copy/Paste readiness
    has_named_group = 'Name="' in xml and "Group/" in xml
    report.add(GuaranteeItem(
        "copy_paste_group", has_named_group,
        f"[{label}] Named Group для Copy/Paste",
        "Group+Name" if has_named_group else "нет именованной группы",
    ))

    if "article_column" in (include or []) or "kit_article_col1" in xml:
        threaded = "kit_article_col2" in xml and "NextTextFrame" in xml
        report.add(GuaranteeItem(
            "threaded_cols", threaded,
            f"[{label}] Связанные колонки статьи",
            "col1→col2" if threaded else "нет цепочки",
        ))

    return report


def format_open_guarantee(
    reports: list[OpenGuaranteeReport],
    pack_label: str = "Okolica Kit",
) -> str:
    all_pass = all(r.passed for r in reports) if reports else False
    lines = [
        "LAYOUTGENIUS — CS3 OPEN GUARANTEE",
        "=" * 56,
        f"Пакет: {pack_label}",
        f"Итог: {'PASS ✓' if all_pass else 'FAIL ✗'}",
        f"Файлов проверено: {len(reports)}",
        "",
        "Критерии гарантии открытия в Adobe InDesign CS3:",
        "  • DOMVersion 5.0 + Adobe AID processing instruction",
        "  • Только Process CMYK swatches",
        "  • Layers + Groups + Object Styles",
        "  • Smoke structure (Story↔TextFrame links)",
        "  • Named Group — один Copy/Paste на сцену",
        "",
        "РЕЗУЛЬТАТЫ:",
    ]
    for r in reports:
        badge = "PASS" if r.passed else "FAIL"
        lines.append(f"  --- {badge} ---")
        for it in r.items:
            mark = "[x]" if it.ok else "[ ]"
            lines.append(f"  {mark} {it.title}" + (f" — {it.detail}" if it.detail else ""))
        lines.append("")

    lines.extend([
        "РУЧНОЙ SMOKE (60 сек):",
        "  1. Установить Fonts/ из ZIP",
        "  2. File → Open каждый .inx",
        "  3. Layers видны, Swatches = CMYK",
        "  4. Выделить Group → Copy → Paste на новую полосу",
        "  5. View → Overprint Preview",
        "",
        f"BADGE: {'CS3_OPEN_GUARANTEE_PASS' if all_pass else 'CS3_OPEN_GUARANTEE_FAIL'}",
    ])
    return "\n".join(lines)
