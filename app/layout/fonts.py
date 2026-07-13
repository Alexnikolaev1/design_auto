"""Менеджер шрифтов: сканирует /fonts и загруженные файлы, разрешает
PostScript-имена, подбирает fallback (Liberation/DejaVu, Windows Fonts).
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import FONTS_DIR, FONT_CATALOG

_FONT_EXT = {".ttf", ".otf", ".ttc"}


@dataclass
class ResolvedFont:
    postscript_name: str
    family: str
    style: str
    path: Path | None
    is_fallback: bool = False


@dataclass
class FontEntry:
    postscript_name: str
    family: str
    style: str
    path: Path
    category: str  # serif | sans | display | mono | other

    def to_dict(self) -> dict:
        return {
            "postscript_name": self.postscript_name,
            "family": self.family,
            "style": self.style,
            "category": self.category,
            "filename": self.path.name,
        }


@dataclass
class _FontRegistry:
    by_ps: dict[str, FontEntry] = field(default_factory=dict)
    by_family: dict[str, list[FontEntry]] = field(default_factory=dict)
    job_dirs: list[Path] = field(default_factory=list)

    def clear_job_dirs(self) -> None:
        self.job_dirs.clear()


_registry = _FontRegistry()
_scanned = False


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = [FONTS_DIR]
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs += [
            windir / "Fonts",
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        ]
    else:
        dirs += [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / ".local/share/fonts",
        ]
    return [d for d in dirs if d.exists()]


def _first_existing(paths: list[str | Path]) -> Path | None:
    for p in paths:
        pp = Path(p)
        if pp.exists():
            return pp
    return None


_SYSTEM_SERIF = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    r"C:\Windows\Fonts\times.ttf",
    r"C:\Windows\Fonts\georgia.ttf",
])
_SYSTEM_SERIF_BOLD = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    r"C:\Windows\Fonts\timesbd.ttf",
    r"C:\Windows\Fonts\georgiab.ttf",
])
_SYSTEM_SERIF_ITALIC = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    r"C:\Windows\Fonts\timesi.ttf",
    r"C:\Windows\Fonts\georgiai.ttf",
])
_SYSTEM_SANS = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
])
_SYSTEM_SANS_BOLD = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
])
_SYSTEM_SANS_ITALIC = _first_existing([
    "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    r"C:\Windows\Fonts\ariali.ttf",
])


def _read_font_meta(path: Path) -> tuple[str, str, str]:
    """Возвращает (postscript_name, family, style)."""
    try:
        from fontTools.ttLib import TTFont

        with TTFont(str(path), lazy=True) as font:
            name_table = font["name"]
            ps = family = style = ""
            for rec in name_table.names:
                if rec.nameID == 6 and not ps:
                    ps = rec.toUnicode()
                elif rec.nameID == 1 and not family:
                    family = rec.toUnicode()
                elif rec.nameID == 2 and not style:
                    style = rec.toUnicode()
            if ps or family:
                return (
                    ps or path.stem,
                    family or path.stem.split("-")[0],
                    style or _style_from_filename(path.name),
                )
    except Exception:
        pass
    stem = path.stem
    if "-" in stem:
        family, style_part = stem.rsplit("-", 1)
        return stem, family, _normalize_style(style_part)
    return stem, stem, "Regular"


def _normalize_style(s: str) -> str:
    sl = s.lower().replace("_", " ")
    if "bold" in sl and "italic" in sl:
        return "Bold Italic"
    if "bold" in sl or sl in ("bd", "b"):
        return "Bold"
    if "italic" in sl or sl in ("it", "i", "oblique"):
        return "Italic"
    return "Regular"


def _style_from_filename(fname: str) -> str:
    return _normalize_style(Path(fname).stem)


def _guess_category(family: str, path: Path) -> str:
    blob = (family + path.stem).lower()
    if any(k in blob for k in ("serif", "times", "georgia", "garamond", "baskerville", "ptserif")):
        return "serif"
    if any(k in blob for k in ("mono", "courier", "consolas", "code")):
        return "mono"
    if any(k in blob for k in ("display", "montserrat", "impact", "bebas", "oswald")):
        return "display"
    if any(k in blob for k in ("sans", "arial", "helvetica", "calibri", "roboto", "ptsans", "verdana")):
        return "sans"
    return "other"


def _register_entry(entry: FontEntry) -> None:
    _registry.by_ps[entry.postscript_name] = entry
    _registry.by_family.setdefault(entry.family, []).append(entry)
    base = entry.postscript_name.split("-")[0]
    if base != entry.postscript_name:
        _registry.by_ps.setdefault(base, entry)


def scan_fonts(force: bool = False) -> None:
    global _scanned
    if _scanned and not force:
        return
    _registry.by_ps.clear()
    _registry.by_family.clear()

    seen_paths: set[Path] = set()
    search_dirs = list(_system_font_dirs()) + _registry.job_dirs

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.suffix.lower() not in _FONT_EXT or path in seen_paths:
                continue
            seen_paths.add(path)
            ps, family, style = _read_font_meta(path)
            entry = FontEntry(
                postscript_name=ps,
                family=family,
                style=style,
                path=path,
                category=_guess_category(family, path),
            )
            _register_entry(entry)

    for ps_name, fname in FONT_CATALOG.items():
        candidate = FONTS_DIR / fname
        if candidate.exists() and candidate not in seen_paths:
            ps, family, style = _read_font_meta(candidate)
            _register_entry(FontEntry(ps or ps_name, family, style, candidate, _guess_category(family, candidate)))

    _scanned = True


def register_job_fonts(job_fonts_dir: Path) -> None:
    if job_fonts_dir.is_dir():
        _registry.job_dirs.append(job_fonts_dir)
        scan_fonts(force=True)


def list_available_fonts() -> list[dict]:
    scan_fonts()
    families: dict[str, FontEntry] = {}
    for entries in _registry.by_family.values():
        for e in entries:
            if e.style == "Regular" or e.family not in families:
                families[e.family] = e
    result = sorted((e.to_dict() for e in families.values()), key=lambda x: x["family"].lower())
    return result


def _find_variant(family_or_ps: str, style: str = "Regular") -> FontEntry | None:
    if not family_or_ps:
        return None
    scan_fonts()
    if family_or_ps in _registry.by_ps:
        return _registry.by_ps[family_or_ps]
    for entry in _registry.by_ps.values():
        if entry.family == family_or_ps and entry.style == style:
            return entry
    for entry in _registry.by_ps.values():
        if entry.postscript_name.startswith(family_or_ps):
            if style == "Regular" or style.lower() in entry.style.lower():
                return entry
    return None


def resolve_variant(base_ps: str, bold: bool = False, italic: bool = False) -> ResolvedFont:
    """Разрешает шрифт с учётом начертания (Regular/Bold/Italic)."""
    scan_fonts()
    entry = _registry.by_ps.get(base_ps)
    if entry is None:
        entry = _find_variant(base_ps)

    if entry:
        want_style = "Bold Italic" if bold and italic else ("Bold" if bold else ("Italic" if italic else "Regular"))
        if entry.style != want_style:
            variant = _find_variant(entry.family, want_style)
            if variant:
                entry = variant
        return ResolvedFont(entry.postscript_name, entry.family, entry.style, entry.path, False)

    return _system_fallback(base_ps, bold, italic)


def resolve(postscript_name: str) -> ResolvedFont:
    return resolve_variant(postscript_name, bold=False, italic=False)


def _system_fallback(postscript_name: str, bold: bool, italic: bool) -> ResolvedFont:
    is_serif = (
        "serif" in postscript_name.lower()
        or postscript_name.startswith("PTSerif")
        or "Serif" in postscript_name
    )
    if is_serif:
        if bold and italic:
            path = _SYSTEM_SERIF_BOLD or _SYSTEM_SERIF
        elif bold:
            path = _SYSTEM_SERIF_BOLD or _SYSTEM_SERIF
        elif italic:
            path = _SYSTEM_SERIF_ITALIC or _SYSTEM_SERIF
        else:
            path = _SYSTEM_SERIF
        family = "Liberation Serif" if path and "liberation" in str(path).lower() else "Times New Roman"
    else:
        if bold and italic:
            path = _SYSTEM_SANS_BOLD or _SYSTEM_SANS
        elif bold:
            path = _SYSTEM_SANS_BOLD or _SYSTEM_SANS
        elif italic:
            path = _SYSTEM_SANS_ITALIC or _SYSTEM_SANS
        else:
            path = _SYSTEM_SANS
        family = "Liberation Sans" if path and "liberation" in str(path).lower() else "Arial"

    style = "Bold Italic" if bold and italic else ("Bold" if bold else ("Italic" if italic else "Regular"))
    return ResolvedFont(postscript_name, family, style, path, True)


def pick_font_for_role(role: str, profile_serif: str, profile_sans: str, profile_display: str,
                       default: str) -> str:
    """Подбирает PostScript-имя шрифта для роли (body/heading/display)."""
    scan_fonts()
    preference = {
        "serif": profile_serif,
        "sans": profile_sans,
        "display": profile_display,
    }.get(role, "")

    if preference:
        entry = _find_variant(preference)
        if entry:
            return entry.postscript_name

    entry = _find_variant(default)
    if entry:
        return entry.postscript_name

    resolved = resolve(default)
    if resolved.path:
        return resolved.postscript_name

    cat = {"serif": "serif", "sans": "sans", "display": "display"}.get(role, "sans")
    for entries in _registry.by_family.values():
        for e in entries:
            if e.category == cat and e.style == "Regular":
                return e.postscript_name

    return default


def collect_used_font_paths(ps_names: set[str]) -> list[tuple[str, Path]]:
    """Возвращает список (postscript_name, path) для включения в ZIP."""
    scan_fonts()
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for ps in ps_names:
        for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
            resolved = resolve_variant(ps, bold, italic)
            if resolved.path and resolved.path not in seen and not resolved.is_fallback:
                out.append((resolved.postscript_name, resolved.path))
                seen.add(resolved.path)
    return out
