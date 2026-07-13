"""Очистка устаревших задач с диска (важно для Railway /tmp)."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.config import JOBS_DIR

logger = logging.getLogger(__name__)


def cleanup_old_jobs(max_age_hours: float = 48.0) -> int:
    """Удаляет каталоги задач старше max_age_hours. Возвращает число удалённых."""
    if max_age_hours <= 0 or not JOBS_DIR.is_dir():
        return 0
    cutoff = time.time() - max_age_hours * 3600.0
    removed = 0
    for job_dir in JOBS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        marker = job_dir / "status.json"
        try:
            mtime = marker.stat().st_mtime if marker.exists() else job_dir.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                shutil.rmtree(job_dir)
                removed += 1
            except OSError as exc:
                logger.warning("Failed to remove job dir %s: %s", job_dir.name, exc)
    if removed:
        logger.info("Cleaned up %d job(s) older than %.1f h", removed, max_age_hours)
    return removed
