"""
Smoke-тест INX для Adobe InDesign CS3 (DOMVersion 5.0).

Имитирует проверки, которые выполняет InDesign при открытии Interchange:
структура XML, ссылки между Story/TextFrame/Link, геометрия полос, уникальность ID.
Не заменяет ручной smoke-тест в CS3, но отлавливает типичные причины отказа открытия.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from app.inx.schema import InxValidationError, validate_inx


AID_PI_RE = re.compile(
    br'<\?aid\s+style="33"\s+type="document"[^?]*DOMVersion="5\.0"[^?]*'
    br'readerVersion="5\.0"',
    re.IGNORECASE,
)


@dataclass
class SmokeResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "stats": self.stats,
        }


def _parse_inx_root(content: bytes) -> etree.Element:
    """Парсит INX, пропуская XML declaration и Adobe AID processing instruction."""
    start = content.find(b"<")
    if start < 0:
        raise InxValidationError("Пустой или невалидный INX")
    return etree.fromstring(content[start:])


def smoke_test_inx(
    content: bytes,
    expected_page_w: float | None = None,
    expected_page_h: float | None = None,
) -> SmokeResult:
    result = SmokeResult(passed=True)

    if not content.strip():
        result.passed = False
        result.errors.append("Пустой файл INX")
        return result

    if not content.startswith(b"<?xml"):
        result.warnings.append("Отсутствует XML declaration — InDesign обычно добавляет сам")
    if not AID_PI_RE.search(content[:512]):
        result.warnings.append(
            "Отсутствует Adobe AID processing instruction (readerVersion 5.0) — "
            "рекомендуется для InDesign CS3"
        )

    try:
        base_warnings = validate_inx(content)
        result.warnings.extend(base_warnings)
    except InxValidationError as exc:
        result.passed = False
        result.errors.append(str(exc))
        return result

    try:
        root = _parse_inx_root(content)
    except etree.XMLSyntaxError as exc:
        result.passed = False
        result.errors.append(f"Синтаксис XML: {exc}")
        return result

    dom_ver = root.get("DOMVersion", "")
    if dom_ver != "5.0":
        result.warnings.append(f"DOMVersion={dom_ver!r}, ожидается '5.0' для CS3")

    self_ids: dict[str, str] = {}
    for el in root.iter():
        sid = el.get("Self")
        if not sid:
            continue
        if sid in self_ids:
            result.passed = False
            result.errors.append(f"Дублирующийся Self={sid!r}")
        self_ids[sid] = etree.QName(el).localname

    stories = {el.get("Self") for el in root.iter() if etree.QName(el).localname == "Story"}
    story_parents: set[str] = set()
    for tf in root.iter():
        if etree.QName(tf).localname != "TextFrame":
            continue
        parent = tf.get("ParentStory", "")
        if not parent:
            result.passed = False
            result.errors.append("TextFrame без ParentStory")
        elif parent not in stories:
            result.passed = False
            result.errors.append(f"TextFrame ссылается на несуществующую Story: {parent}")
        else:
            story_parents.add(parent)

    orphan_stories = stories - story_parents
    if orphan_stories:
        result.warnings.append(
            f"Story без TextFrame ({len(orphan_stories)}): возможны неиспользованные потоки"
        )

    links_ok = links_bad = 0
    for link in root.iter():
        if etree.QName(link).localname != "Link":
            continue
        uri = link.get("LinkResourceURI", "")
        if not uri:
            result.warnings.append("Link без LinkResourceURI")
            links_bad += 1
        elif ".." in uri or uri.startswith("/"):
            result.warnings.append(f"Подозрительный путь Link: {uri}")
            links_bad += 1
        else:
            links_ok += 1

    doc_pref = next(
        (el for el in root.iter() if etree.QName(el).localname == "DocumentPreference"),
        None,
    )
    if doc_pref is not None:
        try:
            pw = float(doc_pref.get("PageWidth", "0"))
            ph = float(doc_pref.get("PageHeight", "0"))
            if pw < 100 or ph < 100:
                result.warnings.append(f"Подозрительный размер полосы: {pw}×{ph} pt")
            if expected_page_w and abs(pw - expected_page_w) > 2:
                result.warnings.append(
                    f"PageWidth {pw} pt ≠ ожидаемому {expected_page_w:.1f} pt"
                )
            if expected_page_h and abs(ph - expected_page_h) > 2:
                result.warnings.append(
                    f"PageHeight {ph} pt ≠ ожидаемому {expected_page_h:.1f} pt"
                )
        except ValueError:
            result.warnings.append("Нечисловые PageWidth/PageHeight в DocumentPreference")

    spread_count = 0
    page_count = 0
    for spread in root.iter():
        if etree.QName(spread).localname != "Spread":
            continue
        spread_count += 1
        pages = [el for el in spread if etree.QName(el).localname == "Page"]
        page_count += len(pages)
        facing = doc_pref.get("FacingPages", "false") if doc_pref is not None else "false"
        if facing == "true" and len(pages) == 2:
            bounds = [p.get("GeometricBounds", "") for p in pages]
            if len(bounds) == 2:
                try:
                    left = [float(x) for x in bounds[0].split()]
                    right = [float(x) for x in bounds[1].split()]
                    if len(left) == 4 and len(right) == 4 and right[1] <= left[3]:
                        result.warnings.append(
                            "Разворот: правая полоса может перекрывать левую по координатам"
                        )
                except ValueError:
                    pass

    images_linked = 0
    images_orphan = 0
    for rect in root.iter():
        if etree.QName(rect).localname != "Rectangle":
            continue
        has_image = any(etree.QName(c).localname == "Image" for c in rect)
        if has_image:
            link_child = None
            for c in rect.iter():
                if etree.QName(c).localname == "Link":
                    link_child = c
                    break
            if link_child is not None and link_child.get("LinkResourceURI"):
                images_linked += 1
            else:
                images_orphan += 1
    if images_orphan:
        result.warnings.append(f"Изображений без Link: {images_orphan}")

    pstyle_ids = {
        el.get("Self") for el in root.iter()
        if etree.QName(el).localname == "ParagraphStyle"
    }
    for psr in root.iter():
        if etree.QName(psr).localname != "ParagraphStyleRange":
            continue
        ref = psr.get("AppliedParagraphStyle", "")
        if ref and ref not in pstyle_ids and not ref.startswith("ParagraphStyle/"):
            result.warnings.append(f"Неизвестный стиль абзаца: {ref}")

    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        result.warnings.append("INX не в UTF-8 — возможны проблемы с кириллицей в CS3")

    result.stats = {
        "stories": len(stories),
        "text_frames": sum(1 for el in root.iter() if etree.QName(el).localname == "TextFrame"),
        "spreads": spread_count,
        "pages": page_count,
        "links": links_ok,
        "images_linked": images_linked,
        "unique_ids": len(self_ids),
    }

    if result.errors:
        result.passed = False
    return result
