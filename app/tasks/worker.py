"""Фоновая обработка задачи вёрстки."""
from __future__ import annotations

import json
import shutil
import traceback
import zipfile
from pathlib import Path

from app.config import (
    JOBS_DIR, TypographyProfile, UNSPLASH_ACCESS_KEY, PEXELS_API_KEY,
    MAX_IMAGES_PER_JOB, MAX_PREVIEW_PAGES, PDF_EXPORT_DPI,
)
from app.analysis.reference_pdf import (
    analyze_references, apply_reference_to_profile, reorder_templates_by_reference,
)
from app.parser.docx_parser import parse_docx, DocxParseError, ParsedDocument
from app.parser.doc_converter import ensure_docx
from app.parser.multi_merge import collect_article_paths, parse_issue
from app.nlp.keywords import extract_keywords, fetch_stock_photo
from app.nlp.image_matcher import match_uploaded_images, parse_mapping_json, ImagePlacement, append_image_after_last_block, _build_sections
from app.layout.templates import select_templates
from app.layout.engine import build_layout
from app.layout import fonts as font_manager
from app.inx.generator import build_inx
from app.inx.schema import validate_inx, InxValidationError
from app.inx.smoke import smoke_test_inx
from app.preview.renderer import render_preview_pages
from app.layout.ad_grid import resolve_ad_slots, analyze_ad_slots
from app.layout.overrides import (
    apply_overrides, export_layout_model, parse_overrides_json, overrides_to_json,
)
from app.inx.print_checklist import build_print_checklist, format_checklist_text, CheckItem
from app.export.pdf_export import export_print_pdf, pdf_page_count
from app.layout.quality import compute_layout_quality
from app.util.upload_files import (
    collect_uploaded_images, ingest_into_extracted, resolve_image_on_disk,
)


def _job_dir(job_id: str) -> Path:
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_status(job_id: str, status: str, **extra):
    d = _job_dir(job_id)
    payload = {"job_id": job_id, "status": status, **extra}
    (d / "status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def read_status(job_id: str) -> dict | None:
    f = JOBS_DIR / job_id / "status.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _placements_to_mapping(placements: list[dict]) -> list[dict]:
    """mapping.json для повторной загрузки или правки привязок."""
    out = []
    for p in placements:
        entry: dict = {
            "filename": p["filename"],
            "anchor_heading": p.get("anchor_heading", ""),
            "role": p.get("image_role", "photo"),
        }
        if p.get("caption"):
            entry["caption"] = p["caption"]
        if p.get("width_mm"):
            entry["width_mm"] = p["width_mm"]
        if p.get("height_mm"):
            entry["height_mm"] = p["height_mm"]
        if p.get("slot_index") is not None:
            entry["slot_index"] = p["slot_index"]
        out.append(entry)
    return out


def _placement_to_dict(p: ImagePlacement) -> dict:
    return {
        "filename": p.filename,
        "anchor_heading": p.anchor_heading,
        "reason": p.reason,
        "caption": p.caption,
        "image_role": p.image_role,
        "width_mm": p.width_mm,
        "height_mm": p.height_mm,
        "slot_index": p.slot_index,
    }


def _document_outline(parsed: ParsedDocument) -> list[dict]:
    return [
        {"title": s.title, "level": s.level, "word_estimate": len(s.text.split())}
        for s in _build_sections(parsed.blocks)
        if s.title != "(начало документа)" or s.text.strip()
    ]


def _extract_headings(parsed: ParsedDocument) -> list[str]:
    return [item["title"] for item in _document_outline(parsed) if item["title"]]


def process_job(job_id: str, source_path: Path, profile_dict: dict,
                extra_image_paths: list[Path] | None = None,
                job_fonts_dir: Path | None = None,
                mapping_data: list[dict] | None = None,
                reference_pdf_paths: list[Path] | None = None,
                use_reference_style: bool = True,
                ad_grid_json: str | None = None) -> None:
    d = _job_dir(job_id)
    (d / "job_meta.json").write_text(json.dumps({
        "profile": profile_dict,
        "use_reference_style": use_reference_style,
        "ad_grid": ad_grid_json or "",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    article_paths = collect_article_paths(d)
    if not article_paths and source_path and source_path.exists():
        article_paths = [source_path]
    if not article_paths:
        _write_status(job_id, "error", message="Исходные документы не найдены")
        return
    _execute_pipeline(
        job_id, article_paths, profile_dict, extra_image_paths, job_fonts_dir,
        mapping_data, reference_pdf_paths, use_reference_style, ad_grid_json,
    )


def rebuild_job(job_id: str, mapping_data: list[dict] | None = None,
                ad_grid_json: str | None = None,
                layout_overrides_json: str | None = None) -> None:
    """Пересборка макета с новыми привязками / рекламной сеткой (без повторной загрузки)."""
    d = _job_dir(job_id)
    meta_path = d / "job_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("Метаданные задачи не найдены")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    profile_dict = meta["profile"]
    use_reference_style = meta.get("use_reference_style", True)
    grid = ad_grid_json if ad_grid_json is not None else meta.get("ad_grid", "")

    source_path = None
    article_paths = collect_article_paths(d)
    if not article_paths:
        for ext in (".docx", ".doc"):
            p = d / f"source{ext}"
            if p.exists():
                article_paths = [p]
                source_path = p
                break
    elif article_paths:
        source_path = article_paths[0]
    if not article_paths:
        raise FileNotFoundError("Исходный документ не найден")

    uploaded_dir = d / "uploaded_images"
    extra_images = collect_uploaded_images(uploaded_dir) if uploaded_dir.is_dir() else []

    fonts_dir = d / "uploaded_fonts"
    job_fonts = fonts_dir if fonts_dir.is_dir() and any(fonts_dir.iterdir()) else None

    ref_dir = d / "reference_pdfs"
    refs = list(ref_dir.glob("*.pdf")) if ref_dir.is_dir() else []

    if ad_grid_json is not None:
        meta["ad_grid"] = ad_grid_json
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if layout_overrides_json is not None:
        meta["layout_overrides"] = layout_overrides_json
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    overrides = layout_overrides_json if layout_overrides_json is not None else meta.get("layout_overrides", "")

    _execute_pipeline(
        job_id, article_paths, profile_dict, extra_images or None, job_fonts,
        mapping_data, refs or None, use_reference_style, grid,
        layout_overrides_json=overrides,
    )


def _execute_pipeline(job_id: str, article_paths: list[Path], profile_dict: dict,
                extra_image_paths: list[Path] | None = None,
                job_fonts_dir: Path | None = None,
                mapping_data: list[dict] | None = None,
                reference_pdf_paths: list[Path] | None = None,
                use_reference_style: bool = True,
                ad_grid_json: str | None = None,
                layout_overrides_json: str | None = None) -> None:
    d = _job_dir(job_id)
    images_dir = d / "extracted_images"
    previews_dir = d / "previews"
    downloads_dir = d / "downloads"
    downloads_dir.mkdir(exist_ok=True)

    if job_fonts_dir and job_fonts_dir.is_dir():
        font_manager.register_job_fonts(job_fonts_dir)
    else:
        font_manager.scan_fonts(force=True)

    try:
        _write_status(job_id, "parsing")
        profile = TypographyProfile(**profile_dict)

        reference_style = None
        if reference_pdf_paths:
            reference_style = analyze_references(reference_pdf_paths)
            if reference_style and use_reference_style and reference_style.pages_analyzed > 0:
                profile = apply_reference_to_profile(profile, reference_style)

        docx_path, was_converted = None, False
        article_titles: list[str] = []
        if len(article_paths) == 1:
            docx_path, was_converted = ensure_docx(article_paths[0], d / "convert")
            parsed = parse_docx(docx_path, images_dir)
            article_titles = [_extract_headings(parsed)[0] if _extract_headings(parsed) else "Материал 1"]
        else:
            parsed, was_converted, article_titles = parse_issue(
                article_paths, images_dir, d / "convert",
            )

        _write_status(
            job_id, "analyzing",
            reference_analysis=reference_style.to_dict() if reference_style else None,
        )
        keywords = extract_keywords(parsed.full_text)

        sources = list(extra_image_paths) if extra_image_paths else collect_uploaded_images(d / "uploaded_images")
        uploaded: list[Path] = []
        for i, p in enumerate(sources):
            ingested = ingest_into_extracted(p, images_dir, i)
            if ingested:
                uploaded.append(ingested)

        match_result = match_uploaded_images(parsed, uploaded, mapping_data, upload_dir=d / "uploaded_images")
        parsed = ParsedDocument(
            blocks=match_result.blocks, images=match_result.images,
            footnotes=parsed.footnotes,
        )
        for img in parsed.images:
            resolved = resolve_image_on_disk(img.path, d)
            if resolved.is_file():
                img.path = resolved
        image_paths = [img.path for img in parsed.images]
        placements_report = [_placement_to_dict(p) for p in match_result.placements]
        banner_count = sum(1 for img in parsed.images if img.role == "banner")
        ad_count = sum(1 for img in parsed.images if img.role == "ad")

        if profile.auto_stock_images and (
            UNSPLASH_ACCESS_KEY or PEXELS_API_KEY
        ):
            min_images = min(4, max(2, len(article_paths) * 2))
            if len(image_paths) < min_images:
                for kw in keywords[: min_images - len(image_paths)]:
                    found = fetch_stock_photo(kw, images_dir, UNSPLASH_ACCESS_KEY, PEXELS_API_KEY)
                    if found:
                        parsed, placement = append_image_after_last_block(
                            parsed, found, "stock",
                            "стоковое фото по ключевому слову", anchor=kw,
                        )
                        image_paths.append(found)
                        placements_report.append(_placement_to_dict(placement))

        _write_status(
            job_id, "laying_out",
            image_placements=placements_report,
            doc_converted=was_converted,
            banner_count=banner_count,
            ad_count=ad_count,
        )
        mapping_json = json.dumps(_placements_to_mapping(placements_report), ensure_ascii=False, indent=2)
        (d / "mapping.json").write_text(mapping_json, encoding="utf-8")
        templates = select_templates(parsed.word_count, len(image_paths), profile, banner_count)
        templates = reorder_templates_by_reference(templates, reference_style)
        preferred_id = reference_style.preferred_template_id if reference_style else None
        ad_slots = resolve_ad_slots(ad_grid_json, reference_style)
        headings = _extract_headings(parsed)
        outline = _document_outline(parsed)

        ad_grid_out = ad_grid_json or ""
        if ad_slots and not ad_grid_out:
            ad_grid_out = json.dumps(
                {"slots": [s.to_dict() for s in ad_slots]}, ensure_ascii=False, indent=2,
            )
        (d / "ad_grid.json").write_text(ad_grid_out or '{"slots":[]}', encoding="utf-8")

        results = []
        ad_slot_report = None
        overrides = parse_overrides_json(layout_overrides_json)
        image_names = [p.name for p in image_paths]
        for tmpl in templates:
            plan = build_layout(parsed, tmpl, profile, ad_slots=ad_slots)
            if overrides:
                plan = apply_overrides(plan, overrides)
            layout_model = export_layout_model(plan, image_names)
            (d / f"layout_{tmpl.id}.json").write_text(
                json.dumps(layout_model, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            if ad_slots and ad_slot_report is None:
                ad_slot_report = analyze_ad_slots(
                    ad_slots, set(plan.used_ad_slot_indices), placements_report,
                )

            tmpl_previews_dir = previews_dir / tmpl.id
            preview_paths = render_preview_pages(
                plan, image_paths, tmpl_previews_dir,
                max_pages=min(len(plan.pages), MAX_PREVIEW_PAGES),
            )

            inx_bytes = build_inx(parsed, plan, image_paths)
            warnings: list[str] = []
            inx_error = None
            smoke_report = None
            try:
                warnings = validate_inx(inx_bytes)
                smoke_report = smoke_test_inx(
                    inx_bytes, profile.page_width_pt(), profile.page_height_pt(),
                )
                warnings.extend(smoke_report.warnings)
                if not smoke_report.passed:
                    inx_error = "; ".join(smoke_report.errors)
            except InxValidationError as exc:
                inx_error = str(exc)

            font_warns = []
            for ps_name in (tmpl.body_font, tmpl.heading_font):
                if font_manager.resolve(ps_name).is_fallback:
                    font_warns.append(f"{ps_name} — fallback")

            print_checklist = build_print_checklist(
                profile,
                smoke_report.to_dict() if smoke_report else None,
                inx_error,
                image_paths,
                len(plan.pages),
                font_warns,
                ad_slot_report,
            )

            ref_score = None
            if reference_style:
                ref_score = reference_style.template_scores.get(tmpl.id)

            pdf_path = downloads_dir / f"{tmpl.id}_print.pdf"
            pdf_ok = False
            pdf_meta: dict = {}
            try:
                export_print_pdf(
                    plan, image_paths, pdf_path,
                    dpi=float(PDF_EXPORT_DPI), export_info=pdf_meta,
                )
                pdf_ok = pdf_path.exists() and pdf_page_count(pdf_path) == len(plan.pages)
            except Exception:
                pdf_ok = False

            if pdf_ok:
                mode = "векторный" if pdf_meta.get("vector") else f"растровый {PDF_EXPORT_DPI} DPI"
                cmyk_note = " · CMYK" if pdf_meta.get("cmyk") else ""
                print_checklist.items.append(CheckItem(
                    "pdf_export", "automated", "PDF для печати", "pass",
                    f"layout_print.pdf · {mode}{cmyk_note} · {len(plan.pages)} полос",
                ))
            else:
                print_checklist.items.append(CheckItem(
                    "pdf_export", "automated", "PDF для печати", "warn",
                    "Не удалось сгенерировать layout_print.pdf",
                ))

            quality = compute_layout_quality(
                plan,
                smoke_report.to_dict() if smoke_report else None,
                print_checklist.to_dict(),
                ref_score,
                ad_slot_report,
            )
            if pdf_ok:
                quality["score"] = min(100.0, quality["score"] + 3)

            zip_path = downloads_dir / f"{tmpl.id}.zip"
            _build_zip(
                zip_path, tmpl, inx_bytes, image_paths, profile,
                page_count=len(plan.pages), warnings=warnings,
                inx_error=inx_error, keywords=keywords,
                placements=placements_report, mapping_json=mapping_json,
                ad_grid_json=ad_grid_out, ad_slot_report=ad_slot_report,
                footnote_count=len(parsed.footnotes),
                smoke_report=smoke_report.to_dict() if smoke_report else None,
                print_checklist=print_checklist,
                layout_model_json=json.dumps(layout_model, ensure_ascii=False, indent=2),
                layout_overrides_json=overrides_to_json(overrides) if overrides else "",
                pdf_path=pdf_path if pdf_ok else None,
            )

            results.append({
                "template_id": tmpl.id,
                "name": tmpl.name,
                "description": tmpl.description,
                "page_count": len(plan.pages),
                "preview_files": [p.name for p in preview_paths],
                "download_file": zip_path.name,
                "pdf_file": pdf_path.name if pdf_ok and pdf_path else None,
                "pdf_dpi": PDF_EXPORT_DPI if pdf_ok and not pdf_meta.get("vector") else None,
                "pdf_vector": bool(pdf_meta.get("vector")) if pdf_ok else False,
                "pdf_cmyk": bool(pdf_meta.get("cmyk")) if pdf_ok else False,
                "quality": quality,
                "inx_warnings": warnings,
                "inx_error": inx_error,
                "inx_smoke": smoke_report.to_dict() if smoke_report else None,
                "print_checklist": print_checklist.to_dict(),
                "layout_available": True,
                "fonts_used": {
                    "body": tmpl.body_font,
                    "heading": tmpl.heading_font,
                },
                "recommended": tmpl.id == preferred_id if preferred_id else False,
                "reference_score": round(ref_score, 1) if ref_score is not None else None,
            })

        _write_status(
            job_id, "done", results=results, keywords=keywords,
            word_count=parsed.word_count, image_count=len(image_paths),
            banner_count=banner_count,
            ad_count=ad_count,
            article_count=len(article_paths),
            article_titles=article_titles,
            mapping_available=True,
            image_placements=placements_report,
            doc_converted=was_converted,
            reference_analysis=reference_style.to_dict() if reference_style else None,
            selected_template=None,
            headings=headings,
            document_outline=outline,
            ad_slot_count=len(ad_slots),
            ad_slot_report=ad_slot_report,
            footnote_count=len(parsed.footnotes),
        )

    except DocxParseError as exc:
        _write_status(job_id, "error", message=str(exc))
    except Exception as exc:  # noqa: BLE001
        _write_status(
            job_id, "error",
            message=f"Внутренняя ошибка обработки: {exc}",
            trace=traceback.format_exc(),
        )


def select_template(job_id: str, template_id: str) -> dict | None:
    status = read_status(job_id)
    if not status or status.get("status") != "done":
        return None
    valid_ids = {r["template_id"] for r in status.get("results", [])}
    if template_id not in valid_ids:
        return None
    status["selected_template"] = template_id
    current = status.get("status", "done")
    extra = {k: v for k, v in status.items() if k not in ("job_id", "status")}
    _write_status(job_id, current, **extra)
    return read_status(job_id)


def _build_zip(zip_path: Path, template, inx_bytes: bytes,
                image_paths: list[Path], profile: TypographyProfile,
                page_count: int, warnings: list[str], inx_error: str | None,
                keywords: list[str], placements: list[dict],
                mapping_json: str = "", ad_grid_json: str = "",
                ad_slot_report: dict | None = None,
                footnote_count: int = 0,
                smoke_report: dict | None = None,
                print_checklist=None,
                layout_model_json: str = "",
                layout_overrides_json: str = "",
                pdf_path: Path | None = None) -> None:
    used_ps = {
        template.body_font, template.body_font_bold, template.body_font_italic,
        template.heading_font, template.heading_font_bold,
    }
    font_files = font_manager.collect_used_font_paths(used_ps)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("layout.inx", inx_bytes)
        if mapping_json:
            zf.writestr("mapping.json", mapping_json)
        if ad_grid_json:
            zf.writestr("ad_grid.json", ad_grid_json)
        if layout_model_json:
            zf.writestr("layout_model.json", layout_model_json)
        if layout_overrides_json:
            zf.writestr("layout_overrides.json", layout_overrides_json)
        if print_checklist is not None:
            zf.writestr(
                "print_checklist.json",
                json.dumps(print_checklist.to_dict(), ensure_ascii=False, indent=2),
            )
            zf.writestr("PRINT_CHECKLIST.txt", format_checklist_text(print_checklist))

        if pdf_path and pdf_path.exists():
            zf.write(pdf_path, arcname="layout_print.pdf")

        for img_path in image_paths:
            zf.write(img_path, arcname=f"Links/{img_path.name}")

        font_report_lines = []
        for ps_name, fpath in font_files:
            zf.write(fpath, arcname=f"Fonts/{fpath.name}")
            font_report_lines.append(f"OK    {ps_name} -> Fonts/{fpath.name}")

        for ps_name in used_ps:
            resolved = font_manager.resolve(ps_name)
            if resolved.is_fallback:
                font_report_lines.append(
                    f"WARN  {ps_name} не найден — InDesign подставит "
                    f"{resolved.family} {resolved.style}"
                )

        preflight = _build_preflight_report(
            template.id, image_paths, profile, page_count, warnings, inx_error,
            keywords, font_report_lines, template, placements, ad_slot_report,
            footnote_count=footnote_count, smoke_report=smoke_report,
        )
        zf.writestr("preflight_report.txt", preflight)
        zf.writestr("README.txt", _README_TXT)


def _build_preflight_report(template_id: str, image_paths: list[Path],
                             profile: TypographyProfile, page_count: int,
                             warnings: list[str], inx_error: str | None,
                             keywords: list[str], font_report_lines: list[str],
                             template, placements: list[dict],
                             ad_slot_report: dict | None = None,
                             footnote_count: int = 0,
                             smoke_report: dict | None = None) -> str:
    from PIL import Image as PILImage

    lines = [
        "LAYOUTGENIUS — PREFLIGHT REPORT",
        "=" * 40,
        f"Шаблон: {template_id}",
        f"Страниц в макете (оценка): {page_count}",
        f"Цветовой профиль (заявлен): {profile.color_profile}",
        f"Язык: {profile.language} ({profile.indesign_language()})",
        f"Поля: top={profile.margin_top_mm}mm bottom={profile.margin_bottom_mm}mm "
        f"inside={profile.margin_inside_mm}mm outside={profile.margin_outside_mm}mm "
        f"| колонок={profile.columns_count} gutter={profile.column_gutter_mm}mm",
        f"Формат полосы: {profile.page_format} ({profile.page_width_pt():.0f}×{profile.page_height_pt():.0f} pt)",
        f"Разворотные страницы: {'да' if profile.facing_pages else 'нет'}",
        f"H1 с новой полосы: {'да' if profile.heading_starts_new_page else 'нет'}",
        f"Bleed: {profile.bleed_mm}mm | Печатные метки: {'да' if profile.print_marks else 'нет'}",
        f"Переносы: {'вкл' if profile.hyphenation else 'выкл'}",
        f"Пометка «Реклама»: {'вкл' if profile.mark_advertising else 'выкл'}",
        f"Сносок в документе: {footnote_count}",
        f"Шрифты: body={template.body_font}, heading={template.heading_font}",
        f"Кегль: {template.body_size_pt}pt / лидинг {template.body_leading_pt}pt",
        f"Ключевые слова: {', '.join(keywords) if keywords else '—'}",
        "",
        "ПРИВЯЗКА ИЛЛЮСТРАЦИЙ К ТЕКСТУ", "-" * 40,
    ]
    if placements:
        for p in placements:
            role_label = ""
            if p.get("image_role") == "banner":
                role_label = " [БАННЕР]"
            elif p.get("image_role") == "ad":
                role_label = f" [РЕКЛАМА {p.get('width_mm')}×{p.get('height_mm')} мм]"
            lines.append(
                f"  {p['filename']}{role_label} -> «{p['anchor_heading']}» "
                f"({p['reason']})"
            )
    else:
        lines.append("  (отдельные иллюстрации не загружались — только inline из DOCX)")

    if ad_slot_report and ad_slot_report.get("total_slots"):
        lines += ["", "РЕКЛАМНАЯ СЕТКА", "-" * 40]
        lines.append(
            f"  Слотов: {ad_slot_report['total_slots']}, "
            f"занято: {ad_slot_report['used_slots']}, "
            f"пусто: {ad_slot_report['empty_slots']}"
        )
        for pg, items in sorted(ad_slot_report.get("by_page", {}).items(), key=lambda x: int(x[0])):
            lines.append(f"  Полоса {int(pg) + 1}:")
            for it in items:
                status = "OK" if it.get("used") else "ПУСТО"
                fn = f" → {it['filename']}" if it.get("filename") else ""
                lines.append(
                    f"    #{it['slot_index'] + 1} {it['width_mm']}×{it['height_mm']} мм "
                    f"[{status}]{fn}"
                )
        if ad_slot_report.get("unassigned_ads"):
            lines.append("  Реклама без слота: " + ", ".join(ad_slot_report["unassigned_ads"]))

    lines += ["", "ИЗОБРАЖЕНИЯ", "-" * 40]
    for p in image_paths:
        try:
            with PILImage.open(p) as im:
                dpi = im.info.get("dpi", (72, 72))
                ok = dpi[0] >= 200
                lines.append(
                    f"{p.name}: {im.width}x{im.height}px, DPI≈{int(dpi[0])} "
                    f"[{'OK' if ok else 'ВНИМАНИЕ: DPI < 200'}]"
                )
        except Exception as exc:
            lines.append(f"{p.name}: ошибка чтения ({exc})")
    if not image_paths:
        lines.append("(изображений нет)")

    lines += ["", "ШРИФТЫ", "-" * 40] + font_report_lines
    lines += ["", "ВАЛИДАЦИЯ INX", "-" * 40]
    if inx_error:
        lines.append(f"ОШИБКА: {inx_error}")
    elif warnings:
        lines += [f"WARN  {w}" for w in warnings]
    else:
        lines.append("Структурная проверка пройдена.")
    if smoke_report:
        lines.append("")
        lines.append("SMOKE-ТЕСТ CS3 (автоматический)")
        lines.append(f"  Статус: {'OK' if smoke_report.get('passed') else 'FAIL'}")
        stats = smoke_report.get("stats") or {}
        if stats:
            lines.append(
                f"  Story: {stats.get('stories', 0)}, TextFrame: {stats.get('text_frames', 0)}, "
                f"Spread: {stats.get('spreads', 0)}, Pages: {stats.get('pages', 0)}"
            )
        for err in smoke_report.get("errors") or []:
            lines.append(f"  ERR {err}")

    lines += [
        "", "ВАЖНО", "-" * 40,
        "Откройте layout.inx в InDesign CS3 и проверьте Preflight-панель.",
    ]
    return "\n".join(lines)


_README_TXT = """LayoutGenius — макет для Adobe InDesign CS3
================================================

СОДЕРЖИМОЕ
  layout.inx            — вёрстка (InDesign Interchange, DOMVersion 5.0)
  layout_print.pdf      — готовый PDF для печати (без InDesign)
  Links/                — связанные изображения
  Fonts/                — шрифты для установки
  preflight_report.txt  — отчёт: привязка иллюстраций, шрифты, DPI

ПРИВЯЗКА ИЛЛЮСТРАЦИЙ
  См. раздел «ПРИВЯЗКА ИЛЛЮСТРАЦИЙ К ТЕКСТУ» в preflight_report.txt —
  там указано, какая картинка к какому разделу документа привязана.

ОТКРЫТИЕ В INDESIGN CS3
  1. Распакуйте архив. Папки Links и Fonts рядом с layout.inx.
  2. Установите шрифты из Fonts/.
  3. File → Open → layout.inx
  4. Проверьте Preflight и Links.

ЭКСПОРТ: File → Adobe PDF Presets → High Quality Print.
"""

def process_kit_job(
    job_id: str,
    brief: str = "",
    use_ai: bool = True,
    include: list[str] | None = None,
    scene_id: str | None = None,
    mode: str = "auto",
    texts: dict | None = None,
    scene_ids: list[str] | None = None,
    ad_format_id: str | None = None,
    source_text: str = "",
    texts_by_scene: dict | None = None,
) -> None:
    """
    CS3 Element Kit / Issue Pack / Ad format.
    mode: auto|scene|catalog|issue|ad
    """
    from app.kit.compose import compose_kit_selection
    from app.kit.brand import list_element_ids
    from app.kit.preview import render_kit_preview_png
    from app.kit.checklist import format_kit_checklist
    from app.kit.preflight import run_kit_preflight
    from app.kit.scenes import get_scene
    from app.kit.issue_pack import plan_issue_pack, format_media_manifest
    from app.kit.ads import get_ad_format, format_ad_rate_card
    from app.kit.cs3_guarantee import run_cs3_open_guarantee, format_open_guarantee
    from app.inx.kit_generator import build_kit_inx
    from app.layout.okolica_profile import (
        FONT_BODY, FONT_BODY_BOLD, FONT_BODY_ITALIC, FONT_HEADLINE, FONT_RUBRIC,
    )

    d = _job_dir(job_id)
    downloads = d / "downloads"
    previews = d / "previews" / "kit"
    downloads.mkdir(exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)

    # DOCX из папки job (если загружен)
    source = (source_text or "").strip()
    if not source:
        for cand in (d / "source.docx", d / "source.doc"):
            if cand.exists():
                try:
                    docx_path = ensure_docx(cand)
                    parsed = parse_docx(docx_path, d / "inline_images")
                    source = parsed.full_text
                except Exception:
                    pass
                break

    mode = (mode or "catalog").lower()
    if mode == "auto" or mode == "issue":
        # Issue Pack больше не основной продукт — сводим к каталогу модулей
        if ad_format_id:
            mode = "ad"
        elif scene_id:
            mode = "scene"
        else:
            mode = "catalog"

    try:
        _write_status(job_id, "composing", kind="kit", mode=mode)
        font_manager.scan_fonts(force=True)
        used_ps = {FONT_BODY, FONT_BODY_BOLD, FONT_BODY_ITALIC, FONT_HEADLINE, FONT_RUBRIC}
        font_files = font_manager.collect_used_font_paths(used_ps)
        guarantee_reports = []
        preview_pages = []
        results = []
        compose_source = "rules"
        pack_texts_out = {}

        # ---------- ISSUE PACK ----------
        if mode == "issue":
            plan = plan_issue_pack(
                brief=brief,
                source_text=source or brief,
                use_ai=use_ai,
                scene_ids=scene_ids,
                texts_overrides=texts_by_scene,
            )
            compose_source = plan.scenes[0].source if plan.scenes else "rules"
            scenes_dir = downloads / "scenes"
            scenes_dir.mkdir(exist_ok=True)
            all_include = set()
            checklist_parts = []

            for sp in plan.scenes:
                sc = get_scene(sp.scene_id)
                if not sc:
                    continue
                # merge flat texts override
                scene_texts = dict(sp.texts)
                if texts:
                    scene_texts.update({k: str(v) for k, v in texts.items() if str(v).strip()})
                pack_texts_out[sp.scene_id] = scene_texts
                all_include.update(sc.elements)

                inx_bytes = build_kit_inx(
                    include=list(sc.elements), texts=scene_texts, scene_id=sp.scene_id,
                )
                inx_name = f"{sp.scene_id}.inx"
                (scenes_dir / inx_name).write_bytes(inx_bytes)

                g = run_cs3_open_guarantee(inx_bytes, include=list(sc.elements), label=sp.scene_id)
                guarantee_reports.append(g)

                prev = previews / f"{sp.scene_id}.png"
                render_kit_preview_png(list(sc.elements), scene_texts, prev, scene_id=sp.scene_id)
                preview_pages.append(f"/api/jobs/{job_id}/preview/kit/{sp.scene_id}.png")
                results.append({
                    "template_id": sp.scene_id,
                    "template_name": sc.name,
                    "description": sc.description,
                    "preview_pages": [f"/api/jobs/{job_id}/preview/kit/{sp.scene_id}.png"],
                    "download_url": f"/api/jobs/{job_id}/download/okolica_kit",
                })
                pf = run_kit_preflight(inx_bytes, include=list(sc.elements))
                checklist_parts.append(format_kit_checklist(
                    list(sc.elements), source=sp.source, smoke_ok=g.passed,
                    inx_bytes=inx_bytes, scene_id=sp.scene_id, preflight=pf,
                ))

            # primary preview = first scene
            if plan.scenes:
                first = plan.scenes[0].scene_id
                primary_prev = previews / "catalog.png"
                shutil.copy2(previews / f"{first}.png", primary_prev)
            else:
                primary_prev = previews / "catalog.png"
                primary_prev.write_bytes(b"")

            guarantee_txt = format_open_guarantee(guarantee_reports, pack_label="Issue Pack")
            (downloads / "cs3_open_guarantee.txt").write_text(guarantee_txt, encoding="utf-8")
            (downloads / "media_manifest.txt").write_text(
                format_media_manifest(plan.media_slots), encoding="utf-8",
            )
            (downloads / "ad_rate_card.txt").write_text(format_ad_rate_card(), encoding="utf-8")
            checklist = (
                "ISSUE PACK — СВОДНЫЙ ЧЕКЛИСТ\n"
                + "=" * 40 + "\n\n"
                + "\n\n".join(checklist_parts)
            )
            (downloads / "print_checklist.txt").write_text(checklist, encoding="utf-8")
            (downloads / "issue_plan.json").write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8",
            )

            readme = (
                "ОКОЛИЦА ISSUE PACK (LayoutGenius 3.3)\n"
                "=====================================\n\n"
                "scenes/*.inx          — готовые сцены (Group → Copy/Paste)\n"
                "cs3_open_guarantee.txt — гарантия открытия CS3\n"
                "media_manifest.txt    — слоты фото → Links/\n"
                "ad_rate_card.txt      — прайс рекламных форматов\n"
                "print_checklist.txt   — preflight по каждой сцене\n"
                "Fonts/                — фирменные шрифты\n\n"
                "1. Установите Fonts/\n"
                "2. Откройте нужную сцену .inx в InDesign CS3\n"
                "3. Выделите Group → Copy → Paste на рабочую полосу\n"
                "4. Place фото по media_manifest.txt\n"
            )
            (downloads / "README.txt").write_text(readme, encoding="utf-8")

            zip_path = downloads / "okolica_kit.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in scenes_dir.glob("*.inx"):
                    zf.write(p, arcname=f"scenes/{p.name}")
                for name in (
                    "README.txt", "print_checklist.txt", "cs3_open_guarantee.txt",
                    "media_manifest.txt", "ad_rate_card.txt", "issue_plan.json",
                ):
                    zf.write(downloads / name, arcname=name)
                if (previews / "catalog.png").exists():
                    zf.write(previews / "catalog.png", arcname="previews/catalog.png")
                for p in previews.glob("scene_*.png"):
                    zf.write(p, arcname=f"previews/{p.name}")
                for ps_name, fpath in font_files:
                    zf.write(fpath, arcname=f"Fonts/{fpath.name}")

            all_pass = all(g.passed for g in guarantee_reports) if guarantee_reports else False
            _write_status(
                job_id, "done", kind="kit", mode="issue",
                include=sorted(all_include),
                compose_source=compose_source,
                scene_ids=[s.scene_id for s in plan.scenes],
                texts_by_scene=pack_texts_out,
                media_slots=plan.media_slots,
                open_guarantee={"passed": all_pass, "files": len(guarantee_reports)},
                preview_url=f"/api/jobs/{job_id}/preview/kit/catalog.png",
                download_url=f"/api/jobs/{job_id}/download/okolica_kit",
                checklist_url=f"/api/jobs/{job_id}/kit/checklist",
                guarantee_url=f"/api/jobs/{job_id}/kit/guarantee",
                results=results,
                preview_pages=preview_pages,
            )
            return

        # ---------- AD FORMAT ----------
        if mode == "ad" or ad_format_id:
            fmt = get_ad_format(ad_format_id or "ad_row")
            if not fmt:
                raise ValueError(f"Неизвестный ad_format_id: {ad_format_id}")
            ad_texts = {
                "ad_body_wide": f"{fmt.name}\n{fmt.description}",
                "ad_price": f"ориентир {fmt.price_hint_rub} ₽ · {fmt.area_cm2} см²",
                **(texts or {}),
            }
            inx_bytes = build_kit_inx(
                include=list(fmt.elements), texts=ad_texts, ad_format_id=fmt.id,
            )
            include_ids = list(fmt.elements)
            resolved_scene = None
            compose_source = "ad_format"
            pack_label = fmt.name
        else:
            # ---------- SCENE / CATALOG ----------
            scene = get_scene(scene_id) if scene_id else None
            if scene is not None:
                selection = compose_kit_selection(
                    brief or source[:500], use_ai=use_ai, scene_id=scene.id,
                )
            elif include:
                valid = set(list_element_ids())
                picked = [i for i in include if i in valid]
                base = compose_kit_selection(brief or source[:500], use_ai=use_ai, scene_id=None)
                selection = {
                    "include": picked or base["include"],
                    "texts": base.get("texts") or {},
                    "source": "manual" if not use_ai else base.get("source", "rules"),
                    "scene_id": None,
                }
            else:
                selection = compose_kit_selection(
                    brief or source[:500], use_ai=use_ai, scene_id=scene_id,
                )

            include_ids = selection["include"]
            scene_texts = selection.get("texts") or {}
            if texts:
                scene_texts.update({k: str(v) for k, v in texts.items() if str(v).strip()})
            # from source for single scene
            if source and selection.get("scene_id"):
                from app.kit.issue_pack import fill_scene_texts_from_source, _split_articles
                scene_texts = fill_scene_texts_from_source(
                    selection["scene_id"], brief, source,
                    _split_articles(source), scene_texts,
                )
                if texts:
                    scene_texts.update({k: str(v) for k, v in texts.items() if str(v).strip()})

            compose_source = selection.get("source", "rules")
            resolved_scene = selection.get("scene_id") or scene_id
            inx_bytes = build_kit_inx(
                include=include_ids, texts=scene_texts, scene_id=resolved_scene,
            )
            pack_label = resolved_scene or "catalog"
            ad_texts = scene_texts

        inx_path = downloads / "okolica_kit.inx"
        inx_path.write_bytes(inx_bytes)

        smoke = smoke_test_inx(inx_bytes)
        try:
            validate_inx(inx_bytes)
            inx_valid = True
        except InxValidationError as e:
            inx_valid = False
            smoke.warnings.append(f"validate_inx: {e}")

        preflight = run_kit_preflight(inx_bytes, include=include_ids)
        g = run_cs3_open_guarantee(inx_bytes, include=include_ids, label=pack_label)
        guarantee_reports = [g]
        (downloads / "cs3_open_guarantee.txt").write_text(
            format_open_guarantee(guarantee_reports, pack_label=pack_label), encoding="utf-8",
        )
        (downloads / "ad_rate_card.txt").write_text(format_ad_rate_card(), encoding="utf-8")
        (downloads / "media_manifest.txt").write_text(
            format_media_manifest(
                [{"id": "lead_photo", "frame": "kit_article_photo_frame",
                  "hint": "Place CMYK ≥300 dpi → kit_article_photo_frame",
                  "caption_key": "photo_caption"}]
                if "article_photo_frame" in include_ids else []
            ),
            encoding="utf-8",
        )

        preview_path = previews / "catalog.png"
        render_kit_preview_png(
            include_ids, ad_texts if mode == "ad" or ad_format_id else scene_texts,
            preview_path,
            scene_id=resolved_scene if mode != "ad" else None,
        )

        checklist = format_kit_checklist(
            include_ids, source=compose_source, smoke_ok=smoke.passed and inx_valid and g.passed,
            inx_bytes=inx_bytes, scene_id=resolved_scene, preflight=preflight,
        )
        checklist_path = downloads / "print_checklist.txt"
        checklist_path.write_text(checklist, encoding="utf-8")

            readme = (
                "ОКОЛИЦА CS3 MODULE KIT (LayoutGenius 4.0)\n"
                "=========================================\n\n"
                f"Режим: {mode}\n"
                "Помощник дизайнеру: модули Group для Copy/Paste.\n"
                "okolica_kit.inx + cs3_open_guarantee.txt + Fonts/\n\n"
                "1. Установите Fonts/\n"
                "2. Open INX в InDesign CS3\n"
                "3. Выделите Group → Copy → Paste на свою полосу\n"
                "4. Свой текст и фото ставите вы\n"
            )
        (downloads / "README.txt").write_text(readme, encoding="utf-8")

        zip_path = downloads / "okolica_kit.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(inx_path, arcname="okolica_kit.inx")
            for name in (
                "print_checklist.txt", "README.txt", "cs3_open_guarantee.txt",
                "media_manifest.txt", "ad_rate_card.txt",
            ):
                zf.write(downloads / name, arcname=name)
            zf.write(preview_path, arcname="previews/catalog.png")
            for ps_name, fpath in font_files:
                zf.write(fpath, arcname=f"Fonts/{fpath.name}")

        scene_obj = get_scene(resolved_scene) if resolved_scene else None
        out_texts = ad_texts if (mode == "ad" or ad_format_id) else scene_texts
        _write_status(
            job_id, "done", kind="kit", mode=mode,
            include=include_ids,
            compose_source=compose_source,
            scene_id=resolved_scene,
            ad_format_id=ad_format_id,
            texts=out_texts,
            smoke=smoke.to_dict(),
            preflight=preflight.to_dict(),
            open_guarantee=g.to_dict(),
            inx_valid=inx_valid,
            preview_url=f"/api/jobs/{job_id}/preview/kit/catalog.png",
            download_url=f"/api/jobs/{job_id}/download/okolica_kit",
            checklist_url=f"/api/jobs/{job_id}/kit/checklist",
            guarantee_url=f"/api/jobs/{job_id}/kit/guarantee",
            results=[{
                "template_id": ad_format_id or resolved_scene or "okolica_kit",
                "template_name": (
                    get_ad_format(ad_format_id).name if ad_format_id and get_ad_format(ad_format_id)
                    else (scene_obj.name if scene_obj else "Околица CS3 Kit")
                ),
                "description": "Process CMYK CS3 Kit",
                "preview_pages": [f"/api/jobs/{job_id}/preview/kit/catalog.png"],
                "download_url": f"/api/jobs/{job_id}/download/okolica_kit",
            }],
        )
    except Exception as exc:
        traceback.print_exc()
        _write_status(job_id, "error", kind="kit", error=f"Ошибка кита: {exc}")
