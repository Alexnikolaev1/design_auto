"""
Конвертация .doc (Word 97–2003) → .docx для дальнейшего разбора.

Стратегии (по приоритету):
  1. LibreOffice headless (soffice) — Linux/Docker/Windows
  2. Microsoft Word через COM (win32com) — только Windows с установленным Word
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.parser.docx_parser import DocxParseError


def _find_soffice() -> Path | None:
    if shutil.which("soffice"):
        return Path(shutil.which("soffice"))  # type: ignore[arg-type]
    if shutil.which("libreoffice"):
        return Path(shutil.which("libreoffice"))  # type: ignore[arg-type]
    if sys.platform == "win32":
        candidates = [
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ]
        for c in candidates:
            if c.exists():
                return c
    return None


def _convert_with_libreoffice(source: Path, dest_dir: Path) -> Path:
    soffice = _find_soffice()
    if not soffice:
        raise DocxParseError(
            "Для файлов .doc нужен LibreOffice. Установите LibreOffice "
            "(https://www.libreoffice.org) или сохраните документ как .docx в Word."
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(soffice),
        "--headless", "--norestore", "--nolockcheck",
        "--convert-to", "docx",
        "--outdir", str(dest_dir),
        str(source.resolve()),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise DocxParseError("Конвертация .doc превысила лимит времени (120 с).") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise DocxParseError(f"LibreOffice не смог конвертировать .doc: {err or 'неизвестная ошибка'}")

    out = dest_dir / f"{source.stem}.docx"
    if not out.exists():
        docx_files = list(dest_dir.glob("*.docx"))
        if len(docx_files) == 1:
            out = docx_files[0]
        else:
            raise DocxParseError("После конвертации .doc не найден ожидаемый .docx файл.")
    return out


def _convert_with_word_com(source: Path, dest: Path) -> Path:
    if sys.platform != "win32":
        raise DocxParseError("COM-конвертация доступна только на Windows.")
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DocxParseError(
            "Установите pywin32 (`pip install pywin32`) для конвертации через Microsoft Word."
        ) from exc

    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(source.resolve()))
        doc.SaveAs2(str(dest.resolve()), FileFormat=16)  # wdFormatXMLDocument
        doc.Close(False)
        return dest
    except Exception as exc:
        raise DocxParseError(
            f"Microsoft Word не смог конвертировать .doc: {exc}. "
            "Установите LibreOffice или сохраните файл как .docx."
        ) from exc
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


def ensure_docx(source: Path, work_dir: Path) -> tuple[Path, bool]:
    """
    Возвращает путь к .docx и флаг, была ли выполнена конвертация.
  """
    ext = source.suffix.lower()
    if ext == ".docx":
        return source, False
    if ext != ".doc":
        raise DocxParseError(f"Неподдерживаемый формат «{ext}». Нужен .doc или .docx.")

    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / "converted.docx"

    if _find_soffice():
        converted = _convert_with_libreoffice(source, work_dir)
        if converted != dest:
            shutil.copy2(converted, dest)
        return dest, True

    if sys.platform == "win32":
        try:
            return _convert_with_word_com(source, dest), True
        except DocxParseError:
            pass

    raise DocxParseError(
        "Не удалось конвертировать .doc в .docx. Варианты:\n"
        "  • Установите LibreOffice (бесплатно)\n"
        "  • Сохраните документ в Word как .docx\n"
        "  • На Windows с Word: pip install pywin32"
    )
