"""
Рендерер PNG-превью макета с поддержкой inline-форматирования.
"""
from __future__ import annotations

from pathlib import Path

from app.layout.engine import LayoutPlan
from app.preview.page_render import render_page_image, DEFAULT_SCALE


def render_preview_pages(plan: LayoutPlan, image_paths: list[Path],
                          out_dir: Path, max_pages: int | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    template = plan.template
    out_paths: list[Path] = []
    pages_slice = plan.pages if max_pages is None else plan.pages[:max_pages]

    for page in pages_slice:
        img = render_page_image(plan, page, image_paths, scale=DEFAULT_SCALE)
        out_path = out_dir / f"preview_{template.id}_p{page.index + 1}.png"
        img.save(out_path, "PNG", optimize=True)
        out_paths.append(out_path)

    return out_paths
