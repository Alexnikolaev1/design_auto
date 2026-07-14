"""
Анализ PDF-референсов (готовых макетов) для подбора типа вёрстки.

Пользователь загружает 1–3 PDF с примерами предыдущих работ — система
извлекает: число колонок, поля, кегль, плотность иллюстраций, баннеры
и подбирает ближайший шаблон + корректирует профиль типографики.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

from app.config import TypographyProfile, MM_TO_PT
from app.layout.templates import TEMPLATES, TemplateSpec
from app.layout.page_formats import detect_format_from_mm


@dataclass
class AdSlot:
    """Рекламный слот, извлечённый из PDF-референса или заданный в редакторе сетки."""
    page_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    area_cm2: float = 0.0
    filename: str = ""  # привязка к конкретному файлу рекламы

    def to_dict(self) -> dict:
        d = {
            "page_index": self.page_index,
            "x_mm": round(self.x_mm, 1),
            "y_mm": round(self.y_mm, 1),
            "width_mm": round(self.width_mm, 1),
            "height_mm": round(self.height_mm, 1),
            "area_cm2": round(self.area_cm2, 1),
        }
        if self.filename:
            d["filename"] = self.filename
        return d


@dataclass
class ReferenceStyleProfile:
    columns: int = 1
    margin_top_mm: float = 20.0
    margin_bottom_mm: float = 20.0
    margin_left_mm: float = 18.0
    margin_right_mm: float = 18.0
    body_size_pt: float = 10.0
    image_density: float = 0.0
    has_banners: bool = False
    preferred_template_id: str = "classic-book"
    template_scores: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    pages_analyzed: int = 0
    source_files: list[str] = field(default_factory=list)
    page_format_id: str = "a4"
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    ad_slots: list[AdSlot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "columns": self.columns,
            "margins_mm": {
                "top": round(self.margin_top_mm, 1),
                "bottom": round(self.margin_bottom_mm, 1),
                "left": round(self.margin_left_mm, 1),
                "right": round(self.margin_right_mm, 1),
            },
            "body_size_pt": round(self.body_size_pt, 1),
            "image_density": round(self.image_density, 2),
            "has_banners": self.has_banners,
            "preferred_template_id": self.preferred_template_id,
            "preferred_template_name": _template_name(self.preferred_template_id),
            "template_scores": {k: round(v, 2) for k, v in self.template_scores.items()},
            "summary": self.summary,
            "pages_analyzed": self.pages_analyzed,
            "source_files": self.source_files,
            "page_format_id": self.page_format_id,
            "page_format_name": _page_format_label(self.page_format_id),
            "page_size_mm": {
                "width": round(self.page_width_mm, 1),
                "height": round(self.page_height_mm, 1),
            },
            "ad_slots": [s.to_dict() for s in self.ad_slots],
            "ad_slot_count": len(self.ad_slots),
        }


def _template_name(tid: str) -> str:
    for t in TEMPLATES:
        if t.id == tid:
            return t.name
    return tid


def _page_format_label(fmt_id: str) -> str:
    from app.layout.page_formats import get_page_format
    return get_page_format(fmt_id).name


def _pt_to_mm(pt: float) -> float:
    return pt * 25.4 / 72.0


def _cluster_column_count(left_edges: list[float], page_width: float) -> int:
    if not left_edges:
        return 1
    edges = sorted(left_edges)
    clusters: list[float] = []
    for x in edges:
        if not clusters or x - clusters[-1] > page_width * 0.12:
            clusters.append(x)
    return min(max(len(clusters), 1), 3)


def _analyze_page(page) -> dict:
    rect = page.rect
    pw, ph = rect.width, rect.height

    text_blocks: list[tuple[float, float, float, float, float]] = []
    font_sizes: list[float] = []

    try:
        data = page.get_text("dict", flags=0)
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            x0, y0, x1, y1 = block["bbox"]
            bw = x1 - x0
            if bw < pw * 0.08:
                continue
            max_size = 0.0
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    sz = float(span.get("size", 0))
                    if 6 <= sz <= 28:
                        font_sizes.append(sz)
                        max_size = max(max_size, sz)
            text_blocks.append((x0, y0, x1, y1, max_size))
    except Exception:
        pass

    left_edges = [b[0] for b in text_blocks if (b[2] - b[0]) > pw * 0.12]
    columns = _cluster_column_count(left_edges, pw)

    body_sizes = [s for s in font_sizes if 7.5 <= s <= 13.5]
    body_size = statistics.median(body_sizes) if body_sizes else (
        statistics.median(font_sizes) if font_sizes else 10.0
    )

    if text_blocks:
        margin_left = min(b[0] for b in text_blocks)
        margin_right = pw - max(b[2] for b in text_blocks)
        margin_top = min(b[1] for b in text_blocks)
        margin_bottom = ph - max(b[3] for b in text_blocks)
    else:
        margin_left = margin_right = pw * 0.08
        margin_top = margin_bottom = ph * 0.07

    image_area = 0.0
    has_banner = False
    try:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                info = page.parent.extract_image(xref)
                iw, ih = info.get("width", 0), info.get("height", 0)
                if iw and ih:
                    image_area += iw * ih
                    if iw / max(ih, 1) >= 2.0 and iw > 600:
                        has_banner = True
            except Exception:
                continue
    except Exception:
        pass

    page_area = pw * ph
    text_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in text_blocks)
    density = min(1.0, image_area / max(page_area * 4, 1))

    ad_slots: list[AdSlot] = []
    try:
        data = page.get_text("dict", flags=0)
        for block in data.get("blocks", []):
            if block.get("type") != 1:
                continue
            x0, y0, x1, y1 = block["bbox"]
            w_mm = _pt_to_mm(x1 - x0)
            h_mm = _pt_to_mm(y1 - y0)
            area_cm2 = (w_mm * h_mm) / 100.0
            if area_cm2 < 12:
                continue
            if w_mm < pw * 0.08 and h_mm < ph * 0.05:
                continue
            ad_slots.append(AdSlot(
                page_index=0,
                x_mm=_pt_to_mm(x0),
                y_mm=_pt_to_mm(y0),
                width_mm=w_mm,
                height_mm=h_mm,
                area_cm2=area_cm2,
            ))
    except Exception:
        pass

    return {
        "columns": columns,
        "margin_top_mm": _pt_to_mm(margin_top),
        "margin_bottom_mm": _pt_to_mm(margin_bottom),
        "margin_left_mm": _pt_to_mm(margin_left),
        "margin_right_mm": _pt_to_mm(margin_right),
        "body_size_pt": body_size,
        "image_density": density,
        "has_banners": has_banner,
        "text_ratio": text_area / max(page_area, 1),
        "page_width_mm": _pt_to_mm(pw),
        "page_height_mm": _pt_to_mm(ph),
        "ad_slots": ad_slots,
    }


def analyze_references(paths: list[Path], max_pages_per_file: int = 3) -> ReferenceStyleProfile | None:
    if not paths:
        return None

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ReferenceStyleProfile(
            summary="PyMuPDF не установлен — анализ PDF-референсов недоступен.",
            source_files=[p.name for p in paths],
        )

    page_stats: list[dict] = []
    source_files: list[str] = []
    all_ad_slots: list[AdSlot] = []
    page_sizes: list[tuple[float, float]] = []

    for path in paths[:3]:
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        source_files.append(path.name)
        try:
            doc = fitz.open(str(path))
            n = min(len(doc), max_pages_per_file)
            for i in range(n):
                ps = _analyze_page(doc[i])
                ps["ad_slots"] = [
                    AdSlot(
                        page_index=i,
                        x_mm=s.x_mm, y_mm=s.y_mm,
                        width_mm=s.width_mm, height_mm=s.height_mm,
                        area_cm2=s.area_cm2,
                    )
                    for s in ps.get("ad_slots", [])
                ]
                page_stats.append(ps)
                all_ad_slots.extend(ps["ad_slots"])
                page_sizes.append((ps["page_width_mm"], ps["page_height_mm"]))
            doc.close()
        except Exception:
            continue

    if not page_stats:
        return ReferenceStyleProfile(
            summary="Не удалось прочитать PDF-референсы (повреждённый файл или скан без текста).",
            source_files=source_files,
        )

    columns = round(statistics.median([p["columns"] for p in page_stats]))
    columns = int(min(max(columns, 1), 3))

    if page_sizes:
        pw = statistics.median([s[0] for s in page_sizes])
        ph = statistics.median([s[1] for s in page_sizes])
        fmt_id = detect_format_from_mm(pw, ph)
    else:
        pw, ph, fmt_id = 210.0, 297.0, "a4"

    ref = ReferenceStyleProfile(
        columns=columns,
        margin_top_mm=statistics.median([p["margin_top_mm"] for p in page_stats]),
        margin_bottom_mm=statistics.median([p["margin_bottom_mm"] for p in page_stats]),
        margin_left_mm=statistics.median([p["margin_left_mm"] for p in page_stats]),
        margin_right_mm=statistics.median([p["margin_right_mm"] for p in page_stats]),
        body_size_pt=statistics.median([p["body_size_pt"] for p in page_stats]),
        image_density=statistics.median([p["image_density"] for p in page_stats]),
        has_banners=any(p["has_banners"] for p in page_stats),
        pages_analyzed=len(page_stats),
        source_files=source_files,
        page_format_id=fmt_id,
        page_width_mm=pw,
        page_height_mm=ph,
        ad_slots=all_ad_slots[:20],
    )

    ref.margin_top_mm = round(min(max(ref.margin_top_mm, 8), 45), 1)
    ref.margin_bottom_mm = round(min(max(ref.margin_bottom_mm, 8), 45), 1)
    ref.margin_left_mm = round(min(max(ref.margin_left_mm, 8), 40), 1)
    ref.margin_right_mm = round(min(max(ref.margin_right_mm, 8), 40), 1)
    ref.body_size_pt = round(min(max(ref.body_size_pt, 8), 14), 1)

    ref.template_scores = _score_templates(ref)
    ref.preferred_template_id = max(ref.template_scores, key=ref.template_scores.get)
    ref.summary = _build_summary(ref)
    return ref


def _score_templates(ref: ReferenceStyleProfile) -> dict[str, float]:
    scores: dict[str, float] = {}
    for t in TEMPLATES:
        score = 100.0
        score -= abs(t.columns - ref.columns) * 22
        score -= abs(t.body_size_pt - ref.body_size_pt) * 8
        score -= abs(t.body_leading_pt - ref.body_size_pt * 1.35) * 2

        if ref.image_density > 0.25 and t.image_strategy in ("column_span", "banner_strip", "full_width"):
            score += 12
        elif ref.image_density < 0.1 and t.image_strategy == "full_width" and t.columns == 1:
            score += 8

        if ref.has_banners and t.id in ("promo-ads", "magazine-mix"):
            score += 18
        if ref.has_banners and t.id == "report-formal":
            score -= 15

        if ref.columns == 1 and t.id == "classic-book":
            score += 5
        if ref.columns == 2 and t.id in ("editorial-two-col", "magazine-mix"):
            score += 8
        if ref.columns == 3 and t.id == "modern-grid":
            score += 10
        if ref.columns >= 3 and t.id == "okolica-news":
            score += 20
        if 8.5 <= ref.body_size_pt <= 9.5 and t.id == "okolica-news":
            score += 12

        scores[t.id] = max(score, 0.0)
    return scores


def _build_summary(ref: ReferenceStyleProfile) -> str:
    name = _template_name(ref.preferred_template_id)
    cols = {1: "одна колонка", 2: "две колонки", 3: "три колонки"}.get(ref.columns, f"{ref.columns} кол.")
    parts = [
        f"Проанализировано страниц: {ref.pages_analyzed}",
        f"Референс: {cols}, кегль ~{ref.body_size_pt} pt",
        f"Поля ~{ref.margin_top_mm}/{ref.margin_bottom_mm}/{ref.margin_left_mm}/{ref.margin_right_mm} мм",
    ]
    if ref.has_banners:
        parts.append("обнаружены широкие рекламные полосы")
    if ref.image_density > 0.2:
        parts.append("много иллюстраций")
    if ref.ad_slots:
        parts.append(f"найдено {len(ref.ad_slots)} рекламных слотов в PDF")
    if ref.page_format_id != "a4":
        parts.append(f"формат полосы ~{ref.page_width_mm:.0f}×{ref.page_height_mm:.0f} мм")
    parts.append(f"ближайший шаблон: «{name}»")
    return ". ".join(parts) + "."


def apply_reference_to_profile(
    profile: TypographyProfile,
    ref: ReferenceStyleProfile | None,
    use_reference_margins: bool = True,
) -> TypographyProfile:
    """Подстраивает профиль под референс (если пользователь не задал вручную)."""
    if ref is None or ref.pages_analyzed == 0:
        return profile

    p = profile.model_copy()
    if use_reference_margins:
        p.margin_top_mm = ref.margin_top_mm
        p.margin_bottom_mm = ref.margin_bottom_mm
        p.margin_inside_mm = ref.margin_left_mm
        p.margin_outside_mm = ref.margin_right_mm

    if p.body_size_override_pt <= 0:
        p.body_size_override_pt = ref.body_size_pt

    if ref.page_format_id and ref.page_format_id in ("a4", "tabloid", "newspaper_broadsheet", "okolica"):
        if p.page_format != "custom":
            p.page_format = ref.page_format_id

    return p


def reorder_templates_by_reference(
    templates: list[TemplateSpec],
    ref: ReferenceStyleProfile | None,
) -> list[TemplateSpec]:
    """Ставит на первое место шаблон, ближайший к референсу."""
    if ref is None or not ref.template_scores:
        return templates
    return sorted(templates, key=lambda t: ref.template_scores.get(t.id, 0), reverse=True)
