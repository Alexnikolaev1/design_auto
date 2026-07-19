"""
Super Genius печатный префлайт кита + чеклист открытия в InDesign CS3.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from app.kit.brand import BRAND_SWATCHES, COLOR_PROFILE_DEFAULT, MAX_TOTAL_INK, total_ink
from app.inx.smoke import smoke_test_inx, _parse_inx_root


@dataclass
class PreflightItem:
    id: str
    severity: str  # pass | warn | fail
    title: str
    detail: str = ""


@dataclass
class PreflightReport:
    items: list[PreflightItem] = field(default_factory=list)
    passed: bool = True

    def add(self, item: PreflightItem) -> None:
        self.items.append(item)
        if item.severity == "fail":
            self.passed = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "items": [i.__dict__ for i in self.items],
            "fail_count": sum(1 for i in self.items if i.severity == "fail"),
            "warn_count": sum(1 for i in self.items if i.severity == "warn"),
        }


def run_kit_preflight(inx_bytes: bytes, include: list[str] | None = None) -> PreflightReport:
    report = PreflightReport()
    include = include or []

    smoke = smoke_test_inx(inx_bytes)
    if smoke.passed:
        report.add(PreflightItem("smoke_cs3", "pass", "Smoke INX CS3 (DOM 5.0 / AID)",
                                 f"warnings={len(smoke.warnings)}"))
    else:
        report.add(PreflightItem("smoke_cs3", "fail", "Smoke INX CS3 провален",
                                 "; ".join(smoke.errors[:5])))

    try:
        root = _parse_inx_root(inx_bytes)
    except Exception as exc:
        report.add(PreflightItem("parse", "fail", "INX не разобран", str(exc)))
        return report

    rgb_hits = 0
    cmyk_count = 0
    for col in root.iter():
        if etree.QName(col).localname != "Color":
            continue
        space = (col.get("Space") or "").upper()
        if space == "CMYK":
            cmyk_count += 1
        elif space:
            rgb_hits += 1
    if rgb_hits:
        report.add(PreflightItem("cmyk_only", "fail", "Найдены не-CMYK цвета",
                                 f"non_cmyk={rgb_hits}"))
    else:
        report.add(PreflightItem("cmyk_only", "pass", "Все Color = Process CMYK",
                                 f"swatches_in_file={cmyk_count}"))

    ink_warns = []
    for name, (c, m, y, k) in BRAND_SWATCHES.items():
        t = total_ink(c, m, y, k)
        if t > MAX_TOTAL_INK:
            ink_warns.append(f"{name} Σ{t:.0f}%")
        if name != "Paper" and k >= 100 and (c + m + y) > 5:
            ink_warns.append(f"{name}: rich black риск")
    if ink_warns:
        report.add(PreflightItem("total_ink", "warn", "Total ink / rich black",
                                 "; ".join(ink_warns)))
    else:
        report.add(PreflightItem("total_ink", "pass",
                                 f"Total ink ≤ {MAX_TOTAL_INK:.0f}%",
                                 COLOR_PROFILE_DEFAULT))

    c, m, y, k = BRAND_SWATCHES["Black"]
    if (c, m, y, k) == (0.0, 0.0, 0.0, 100.0):
        report.add(PreflightItem("pure_black", "pass", "Black = 0/0/0/100 (текст)", ""))
    else:
        report.add(PreflightItem("pure_black", "warn", "Black не чистый K",
                                 f"{c}/{m}/{y}/{k}"))

    xml = inx_bytes.decode("utf-8", errors="replace")
    for needed in ("OkolicaRed", "OkolicaOrange", "OkolicaPurple", "Black", "Paper"):
        if needed not in xml:
            report.add(PreflightItem(f"swatch_{needed}", "fail", f"Нет swatch {needed}", ""))
        else:
            report.add(PreflightItem(f"swatch_{needed}", "pass", f"Swatch {needed}", ""))

    if "DocumentBleed" in xml or "BleedTop" in xml:
        report.add(PreflightItem("bleed", "pass", "Bleed задан (3 мм эталон)", ""))
    else:
        report.add(PreflightItem("bleed", "warn", "Bleed не найден в INX", ""))

    # Super Genius structure checks
    layer_count = sum(1 for el in root.iter() if etree.QName(el).localname == "Layer")
    group_count = sum(1 for el in root.iter() if etree.QName(el).localname == "Group")
    named = sum(1 for el in root.iter() if el.get("Name") and etree.QName(el).localname in (
        "TextFrame", "Rectangle", "GraphicLine", "Group",
    ))
    overprint = xml.count('OverprintFill="true"') + xml.count('OverprintStroke="true"')
    threaded = 'NextTextFrame="TextFrame/' in xml or "kit_article_col2" in xml

    # Layers намеренно не используем (CS3-safe)
    if layer_count == 0 and "ItemLayer=" not in xml:
        report.add(PreflightItem("layers", "pass", "CS3-safe: без кастомных Layers",
                                 "дефолтный слой InDesign"))
    elif layer_count >= 1:
        report.add(PreflightItem("layers", "warn", f"Layers: {layer_count}",
                                 "кастомные Layers могут мешать открытию в CS3"))
    else:
        report.add(PreflightItem("layers", "warn", "ItemLayer без RootLayerGroup", ""))

    if group_count >= 1:
        report.add(PreflightItem("groups", "pass", f"Groups: {group_count}",
                                 "Copy/Paste по модулю или сцене"))
    else:
        report.add(PreflightItem("groups", "warn", "Нет Group — сложный multi-select", ""))

    if "ObjectStyle/" in xml or "AppliedObjectStyle=" in xml:
        report.add(PreflightItem("object_styles", "warn", "Object styles в INX",
                                 "CS3-safe профиль их не использует"))
    else:
        report.add(PreflightItem("object_styles", "pass", "Без Object styles (CS3-safe)", ""))

    if named >= 5:
        report.add(PreflightItem("named_objects", "pass", f"Named objects: {named}",
                                 "стабильные Name для Layers panel"))
    else:
        report.add(PreflightItem("named_objects", "warn", f"Named objects: {named}", ""))

    if overprint >= 3:
        report.add(PreflightItem("overprint", "pass", f"Overprint attrs: {overprint}",
                                 "Black text/stroke OverprintFill/Stroke"))
    else:
        report.add(PreflightItem("overprint", "warn", f"Overprint attrs: {overprint}",
                                 "Рекомендуется Overprint на K=100"))

    if "article_column" in include or not include:
        if threaded:
            report.add(PreflightItem("threaded_cols", "pass",
                                     "Связанные 2 колонки (NextTextFrame)", ""))
        else:
            report.add(PreflightItem("threaded_cols", "warn",
                                     "Нет связи колонок статьи", ""))

    markers = [
        ("kit_masthead_logo", "masthead_logo" in include or not include),
        ("kit_article_photo_frame", "article_photo_frame" in include or not include),
        ("ParagraphStyle/Основной текст", "styles_pack" in include or not include),
    ]
    for marker, check in markers:
        if not check:
            continue
        if marker in xml:
            report.add(PreflightItem(f"marker_{marker[:24]}", "pass",
                                     f"Маркер: {marker}", ""))
        else:
            report.add(PreflightItem(f"marker_{marker[:24]}", "warn",
                                     f"Не найден {marker}", ""))

    if any(x in include for x in ("ad_module", "ad_module_wide")):
        report.add(PreflightItem("ad_mark", "pass", "Рекламные модули в наборе",
                                 "Проверьте пометку «Реклама»"))

    return report


def format_genius_checklist(
    include: list[str],
    source: str,
    preflight: PreflightReport,
    scene_id: str | None = None,
) -> str:
    lines = [
        "LAYOUTGENIUS — CS3 ELEMENT KIT — SUPER GENIUS PREFLIGHT",
        "=" * 64,
        f"Профиль: {COLOR_PROFILE_DEFAULT}",
        f"Комплектация: {source}",
        f"Сцена: {scene_id or '—'}",
        f"Элементов: {len(include)}",
        f"Префлайт: {'PASS' if preflight.passed else 'FAIL'} "
        f"(fail={preflight.to_dict()['fail_count']}, warn={preflight.to_dict()['warn_count']})",
        "",
        "АВТОПРОВЕРКИ:",
    ]
    for it in preflight.items:
        mark = {"pass": "[x]", "warn": "[!]", "fail": "[ ]"}.get(it.severity, "[?]")
        lines.append(f"  {mark} {it.title}" + (f" — {it.detail}" if it.detail else ""))

    lines.extend([
        "",
        "SWATCHES CMYK %:",
    ])
    for name, (c, m, y, k) in BRAND_SWATCHES.items():
        lines.append(f"  {name:20s}  {c:5.1f} {m:5.1f} {y:5.1f} {k:5.1f}  Σ{c+m+y+k:5.1f}%")

    lines.extend([
        "",
        "SUPER GENIUS — ОТКРЫТИЕ В INDESIGN CS3:",
        "  1. File → Open → okolica_kit.inx (рядом Fonts/)",
        "  2. Установить HeliosCondC / SchoolBookC / AdventureC",
        "  3. Window → Layers — слои Masthead / Article / News / Ads / Decor",
        "  4. Выделить Group сцены или модуля → Edit → Copy → Paste на полосу",
        "  5. Window → Object Styles — Photo Frame / News Card / Ad Module",
        "  6. View → Overprint Preview (Black текст с OverprintFill)",
        "  7. Статья: 2 связанные колонки — текст перетекает (цепочка фреймов)",
        "  8. File → Export/Print → Coated FOGRA39, bleed 3 mm, marks",
        "  9. Фото ≥ 300 dpi CMYK; реклама с пометкой «Реклама»",
        "",
        "СОСТАВ:",
    ])
    for eid in include:
        lines.append(f"  - {eid}")
    lines.append("")
    lines.append("Конец чеклиста.")
    return "\n".join(lines)
