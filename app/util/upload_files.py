"""Безопасное сохранение загрузок (кириллица, пробелы) + manifest для привязки."""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}
MANIFEST_NAME = "upload_manifest.json"


def normalize_name_key(name: str) -> str:
    return unicodedata.normalize("NFC", Path(name).name).casefold()


def stored_image_name(index: int, original: str) -> str:
    ext = Path(original).suffix.lower()
    if ext not in IMAGE_SUFFIXES:
        ext = ".jpg"
    return f"upload_{index:03d}{ext}"


def write_upload_manifest(upload_dir: Path, entries: list[dict]) -> None:
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / MANIFEST_NAME).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def read_upload_manifest(upload_dir: Path) -> list[dict]:
    path = upload_dir / MANIFEST_NAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_uploaded_image(upload_dir: Path, original_name: str, content: bytes, index: int) -> dict:
    """Сохраняет файл под ASCII-именем, возвращает запись manifest."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    original = Path(original_name or f"image_{index}.jpg").name
    stored = stored_image_name(index, original)
    dest = upload_dir / stored
    dest.write_bytes(content)
    return {"stored": stored, "original": original}


def collect_uploaded_images(upload_dir: Path) -> list[Path]:
    """Все загруженные картинки из каталога (по manifest или сканированию)."""
    if not upload_dir.is_dir():
        return []
    manifest = read_upload_manifest(upload_dir)
    found: list[Path] = []
    seen: set[str] = set()
    for entry in manifest:
        stored = entry.get("stored", "")
        if not stored:
            continue
        p = upload_dir / stored
        if p.is_file() and stored not in seen:
            found.append(p)
            seen.add(stored)
    if found:
        return found
    for p in sorted(upload_dir.iterdir()):
        if p.suffix.lower() in IMAGE_SUFFIXES and p.name != MANIFEST_NAME:
            found.append(p)
    return found


def build_filename_index(paths: list[Path], upload_dir: Path | None = None) -> dict[str, Path]:
    """Ключи: stored name, original name (из manifest), нормализованные варианты."""
    index: dict[str, Path] = {}
    manifest = read_upload_manifest(upload_dir) if upload_dir else []
    orig_by_stored = {e.get("stored", ""): e.get("original", "") for e in manifest}

    for p in paths:
        if not p.is_file():
            continue
        index[normalize_name_key(p.name)] = p
        orig = orig_by_stored.get(p.name) or p.name
        index[normalize_name_key(orig)] = p
        # без расширения
        index[normalize_name_key(Path(orig).stem)] = p
    return index


def resolve_upload_path(name: str, index: dict[str, Path]) -> Path | None:
    key = normalize_name_key(name)
    if key in index:
        return index[key]
    for k, p in index.items():
        if k.endswith(key) or key.endswith(k):
            return p
    return None


def ingest_into_extracted(src: Path, images_dir: Path, index: int) -> Path | None:
    """Копирует upload → extracted_images, гарантируя существование файла."""
    if not src.is_file():
        return None
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    if dest.is_file():
        return dest
    fallback = images_dir / stored_image_name(index, src.name)
    shutil.copy2(src, fallback)
    return fallback if fallback.is_file() else None


def resolve_image_on_disk(path: Path, job_dir: Path | None = None) -> Path:
    """Если путь битый — ищем файл в uploaded_images / extracted_images."""
    if path.is_file():
        return path
    if job_dir is None:
        return path
    name_key = normalize_name_key(path.name)
    for sub in ("extracted_images", "uploaded_images"):
        base = job_dir / sub
        if not base.is_dir():
            continue
        for candidate in base.iterdir():
            if candidate.is_file() and normalize_name_key(candidate.name) == name_key:
                return candidate
        manifest = read_upload_manifest(base) if sub == "uploaded_images" else []
        for entry in manifest:
            if normalize_name_key(entry.get("original", "")) == name_key:
                stored = base / entry.get("stored", "")
                if stored.is_file():
                    return stored
    return path
