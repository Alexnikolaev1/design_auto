from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import JOBS_DIR, MAX_UPLOAD_BYTES, TypographyProfile, MAX_IMAGES_PER_JOB, MAX_REFERENCE_PDFS, MAX_ARTICLES_PER_JOB, PAGE_FORMAT_IDS, APP_VERSION
from app.layout import fonts as font_manager
from app.layout import grid_templates as grid_tpl
from app.tasks.worker import process_job, read_status, select_template, rebuild_job, _job_dir
from app.nlp.image_matcher import parse_mapping_json

app = FastAPI(title="LayoutGenius", version=APP_VERSION)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup():
    font_manager.scan_fonts()
    from app.config import JOB_TTL_HOURS
    from app.tasks.cleanup import cleanup_old_jobs
    cleanup_old_jobs(JOB_TTL_HOURS)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/grid-presets")
def grid_presets():
    from app.layout.ad_grid import presets_catalog, GRID_PRESETS
    return {"presets": presets_catalog(), "details": {
        k: {"name": v["name"], "slots": v["slots"]} for k, v in GRID_PRESETS.items()
    }}


@app.get("/api/grid-templates")
def list_grid_templates():
    return {"templates": grid_tpl.list_templates()}


@app.get("/api/grid-templates/{template_id}")
def get_grid_template(template_id: str):
    data = grid_tpl.load_template(template_id)
    if data is None:
        raise HTTPException(404, "Шаблон не найден")
    return data


class GridTemplateBody(BaseModel):
    name: str
    slots: list[dict] = []
    page_format: str = "a4"


@app.post("/api/grid-templates")
def save_grid_template(body: GridTemplateBody):
    if not body.name.strip():
        raise HTTPException(400, "Укажите имя шаблона")
    if not body.slots:
        raise HTTPException(400, "Сетка пуста")
    return grid_tpl.save_template(body.name, body.slots, body.page_format)


@app.delete("/api/grid-templates/{template_id}")
def remove_grid_template(template_id: str):
    if not grid_tpl.delete_template(template_id):
        raise HTTPException(404, "Шаблон не найден")
    return {"deleted": template_id}


@app.get("/api/page-formats")
def list_page_formats():
    from app.layout.page_formats import PAGE_FORMATS
    return {
        "formats": [
            {"id": f.id, "name": f.name, "width_mm": f.width_mm, "height_mm": f.height_mm,
             "description": f.description}
            for f in PAGE_FORMATS.values()
        ]
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/inx/smoke")
async def inx_smoke_check(file: UploadFile = File(...)):
    """Автоматический smoke-тест INX (структура для InDesign CS3)."""
    from app.inx.smoke import smoke_test_inx
    content = await file.read()
    if not content:
        raise HTTPException(400, "Пустой файл")
    return smoke_test_inx(content).to_dict()


@app.get("/api/fonts")
def list_fonts():
    return {"fonts": font_manager.list_available_fonts()}


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extra_articles: Optional[list[UploadFile]] = File(None),
    images: Optional[list[UploadFile]] = File(None),
    fonts: Optional[list[UploadFile]] = File(None),
    margin_top_mm: float = Form(20.0),
    margin_bottom_mm: float = Form(20.0),
    margin_left_mm: float = Form(18.0),
    margin_right_mm: float = Form(18.0),
    bleed_mm: float = Form(3.0),
    color_profile: str = Form("Coated FOGRA39"),
    print_marks: bool = Form(False),
    hyphenation: bool = Form(True),
    auto_stock_images: bool = Form(True),
    language: str = Form("ru-RU"),
    font_serif: str = Form(""),
    font_sans: str = Form(""),
    font_display: str = Form(""),
    body_size_override_pt: float = Form(0.0),
    references: Optional[list[UploadFile]] = File(None),
    mark_advertising: bool = Form(True),
    use_reference_style: bool = Form(True),
    page_format: str = Form("a4"),
    facing_pages: bool = Form(False),
    heading_starts_new_page: bool = Form(False),
    jump_lines: bool = Form(True),
    smart_crop: bool = Form(True),
    pdf_vector_export: bool = Form(True),
    custom_page_width_mm: float = Form(0.0),
    custom_page_height_mm: float = Form(0.0),
    ad_grid: str = Form(""),
):
    fname = (file.filename or "").lower()
    if not (fname.endswith(".docx") or fname.endswith(".doc")):
        raise HTTPException(400, "Ожидается файл .doc или .docx")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"Файл превышает лимит ({MAX_UPLOAD_BYTES // (1024 * 1024)} МБ)")
    if not raw:
        raise HTTPException(400, "Файл пуст")

    job_id = uuid.uuid4().hex[:16]
    d = _job_dir(job_id)
    ext = ".doc" if fname.endswith(".doc") else ".docx"
    sources_dir = d / "sources"
    sources_dir.mkdir(exist_ok=True)
    source_path = sources_dir / f"article_00{ext}"
    source_path.write_bytes(raw)
    # Обратная совместимость для старых задач / rebuild
    (d / f"source{ext}").write_bytes(raw)

    for i, art_file in enumerate((extra_articles or [])[:MAX_ARTICLES_PER_JOB - 1]):
        if not art_file.filename:
            continue
        aname = art_file.filename.lower()
        if not (aname.endswith(".docx") or aname.endswith(".doc")):
            continue
        content = await art_file.read()
        if not content or len(content) > MAX_UPLOAD_BYTES:
            continue
        aext = ".doc" if aname.endswith(".doc") else ".docx"
        (sources_dir / f"article_{i + 1:02d}{aext}").write_bytes(content)

    uploaded_images_dir = d / "uploaded_images"
    uploaded_images_dir.mkdir(exist_ok=True)
    extra_images: list[Path] = []
    mapping_data: list[dict] | None = None

    for i, img_file in enumerate((images or [])[:MAX_IMAGES_PER_JOB + 2]):
        if not img_file.filename:
            continue
        ext_img = Path(img_file.filename).suffix.lower()
        content = await img_file.read()
        if not content:
            continue
        if ext_img == ".json":
            mapping_data = parse_mapping_json(content)
            dest = uploaded_images_dir / Path(img_file.filename).name
            dest.write_bytes(content)
            continue
        if ext_img not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"):
            continue
        dest = uploaded_images_dir / f"{Path(img_file.filename).name}"
        dest.write_bytes(content)
        extra_images.append(dest)

    job_fonts_dir = d / "uploaded_fonts"
    job_fonts_dir.mkdir(exist_ok=True)
    for i, font_file in enumerate((fonts or [])[:10]):
        if not font_file.filename:
            continue
        ext = Path(font_file.filename).suffix.lower()
        if ext not in (".ttf", ".otf"):
            continue
        content = await font_file.read()
        if not content:
            continue
        dest = job_fonts_dir / f"user_font_{i + 1}{ext}"
        dest.write_bytes(content)

    reference_pdfs_dir = d / "reference_pdfs"
    reference_pdfs_dir.mkdir(exist_ok=True)
    reference_paths: list[Path] = []
    for ref_file in (references or [])[:MAX_REFERENCE_PDFS]:
        if not ref_file.filename:
            continue
        if not ref_file.filename.lower().endswith(".pdf"):
            continue
        content = await ref_file.read()
        if not content:
            continue
        dest = reference_pdfs_dir / Path(ref_file.filename).name
        dest.write_bytes(content)
        reference_paths.append(dest)

    if page_format == "custom":
        if custom_page_width_mm < 100 or custom_page_height_mm < 100:
            raise HTTPException(400, "Для своего формата укажите ширину и высоту ≥ 100 мм")
    elif page_format not in PAGE_FORMAT_IDS:
        page_format = "a4"

    profile = TypographyProfile(
        margin_top_mm=margin_top_mm,
        margin_bottom_mm=margin_bottom_mm,
        margin_left_mm=margin_left_mm,
        margin_right_mm=margin_right_mm,
        bleed_mm=bleed_mm,
        color_profile=color_profile,
        print_marks=print_marks,
        hyphenation=hyphenation,
        auto_stock_images=auto_stock_images,
        language=language,
        font_serif=font_serif,
        font_sans=font_sans,
        font_display=font_display,
        body_size_override_pt=body_size_override_pt,
        mark_advertising=mark_advertising,
        page_format=page_format,
        facing_pages=facing_pages,
        heading_starts_new_page=heading_starts_new_page,
        jump_lines=jump_lines,
        smart_crop=smart_crop,
        pdf_vector_export=pdf_vector_export,
        custom_page_width_mm=custom_page_width_mm,
        custom_page_height_mm=custom_page_height_mm,
    )

    has_fonts = any(job_fonts_dir.iterdir()) if job_fonts_dir.exists() else False
    background_tasks.add_task(
        process_job, job_id, source_path, profile.model_dump(),
        extra_images, job_fonts_dir if has_fonts else None, mapping_data,
        reference_paths if reference_paths else None, use_reference_style,
        ad_grid or None,
    )
    article_total = 1 + len([
        a for a in (extra_articles or [])
        if a.filename and (a.filename.lower().endswith(".docx") or a.filename.lower().endswith(".doc"))
    ])
    return {"job_id": job_id, "status": "queued", "article_count": min(article_total, MAX_ARTICLES_PER_JOB)}


class RebuildRequest(BaseModel):
    mapping: list[dict] = []
    ad_grid: str | None = None
    layout_overrides: str | None = None


@app.post("/api/jobs/{job_id}/rebuild")
async def rebuild_job_endpoint(job_id: str, body: RebuildRequest, background_tasks: BackgroundTasks):
    if not _job_dir(job_id).exists():
        raise HTTPException(404, "Задача не найдена")
    background_tasks.add_task(
        rebuild_job, job_id, body.mapping or None, body.ad_grid, body.layout_overrides,
    )
    return {"job_id": job_id, "status": "queued", "rebuild": True}


@app.get("/api/jobs/{job_id}/layout/{template_id}")
def get_layout_model(job_id: str, template_id: str):
    if ".." in template_id or "/" in template_id:
        raise HTTPException(400, "Некорректный идентификатор")
    p = JOBS_DIR / job_id / f"layout_{template_id}.json"
    if not p.exists():
        raise HTTPException(404, "Модель макета ещё не готова")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/jobs/{job_id}/print-checklist/{template_id}")
def get_print_checklist(job_id: str, template_id: str):
    status = read_status(job_id)
    if not status:
        raise HTTPException(404, "Задача не найдена")
    for r in status.get("results", []):
        if r.get("template_id") == template_id:
            return r.get("print_checklist") or {}
    raise HTTPException(404, "Вариант не найден")


@app.get("/api/jobs/{job_id}/ad_grid.json")
def get_ad_grid(job_id: str):
    p = JOBS_DIR / job_id / "ad_grid.json"
    if not p.exists():
        return JSONResponse({"slots": []})
    return FileResponse(str(p), media_type="application/json", filename="ad_grid.json")


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    status = read_status(job_id)
    if status is None:
        return {"job_id": job_id, "status": "queued"}
    return status


@app.post("/api/jobs/{job_id}/select/{template_id}")
def choose_template(job_id: str, template_id: str):
    if ".." in template_id or "/" in template_id:
        raise HTTPException(400, "Некорректный идентификатор")
    result = select_template(job_id, template_id)
    if result is None:
        raise HTTPException(404, "Задача не найдена или шаблон недоступен")
    return {"job_id": job_id, "selected_template": template_id, "status": "done"}


@app.get("/api/jobs/{job_id}/preview/{template_id}/{filename}")
def get_preview(job_id: str, template_id: str, filename: str):
    if ".." in filename or "/" in filename or ".." in template_id:
        raise HTTPException(400, "Некорректный путь")
    p = JOBS_DIR / job_id / "previews" / template_id / filename
    if not p.exists():
        raise HTTPException(404, "Превью не найдено")
    return FileResponse(str(p), media_type="image/png")


@app.get("/api/jobs/{job_id}/mapping.json")
def get_mapping(job_id: str):
    p = JOBS_DIR / job_id / "mapping.json"
    if not p.exists():
        raise HTTPException(404, "mapping.json ещё не готов")
    return FileResponse(str(p), media_type="application/json", filename="mapping.json")


@app.get("/api/jobs/{job_id}/pdf/{template_id}")
def download_pdf(job_id: str, template_id: str):
    if ".." in template_id or "/" in template_id:
        raise HTTPException(400, "Некорректный идентификатор")
    p = JOBS_DIR / job_id / "downloads" / f"{template_id}_print.pdf"
    if not p.exists():
        raise HTTPException(404, "PDF ещё не готов")
    return FileResponse(
        str(p), media_type="application/pdf",
        filename=f"layoutgenius_{template_id}.pdf",
    )


@app.get("/api/jobs/{job_id}/download/{template_id}")
def download_zip(job_id: str, template_id: str):
    if ".." in template_id or "/" in template_id:
        raise HTTPException(400, "Некорректный идентификатор")
    p = JOBS_DIR / job_id / "downloads" / f"{template_id}.zip"
    if not p.exists():
        raise HTTPException(404, "Архив не найден")
    return FileResponse(
        str(p), media_type="application/zip",
        filename=f"layoutgenius_{template_id}.zip",
    )
