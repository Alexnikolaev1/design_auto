"""Тесты загрузки файлов с кириллическими именами."""
import tempfile
from pathlib import Path

from app.util.upload_files import (
    build_filename_index,
    ingest_into_extracted,
    normalize_name_key,
    resolve_upload_path,
    save_uploaded_image,
    write_upload_manifest,
)


def test_cyrillic_upload_manifest_and_match():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        upload_dir = root / "uploaded_images"
        entry = save_uploaded_image(upload_dir, "Оксана Чернова.jpg", b"fakejpeg", 0)
        write_upload_manifest(upload_dir, [entry])
        stored = upload_dir / entry["stored"]
        assert stored.is_file()
        assert entry["stored"].startswith("upload_")

        extracted = root / "extracted_images"
        ingested = ingest_into_extracted(stored, extracted, 0)
        assert ingested is not None
        assert ingested.is_file()

        index = build_filename_index([ingested], upload_dir)
        found = resolve_upload_path("Оксана Чернова.jpg", index)
        assert found is not None
        assert found.is_file()
        assert normalize_name_key("Оксана Чернова.jpg") in index
