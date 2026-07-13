"""Поток текста с обтеканием, переносами и точными метриками."""
from __future__ import annotations

from dataclasses import dataclass

from app.layout import fonts as font_manager
from app.layout.metrics import advance_width_pt
from app.layout.hyphenation import split_for_line
from app.layout.templates import TemplateSpec
from app.parser.docx_parser import Run


@dataclass
class ColumnObstacle:
    y_top: float
    y_bottom: float
    side: str  # left | right
    float_width: float
    gutter: float = 6.0


@dataclass
class FlowLine:
    runs: list[Run]
    style: str
    column_index: int
    x_offset: float
    width_pt: float
    y_pt: float


def line_geometry(
    col_width: float,
    y: float,
    obstacles: list[ColumnObstacle],
) -> tuple[float, float]:
    x_off = 0.0
    width = col_width
    for ob in obstacles:
        if ob.y_top <= y < ob.y_bottom:
            if ob.side == "left":
                x_off = max(x_off, ob.float_width + ob.gutter)
                width = col_width - x_off
            else:
                width = min(width, col_width - ob.float_width - ob.gutter)
    return x_off, max(width, col_width * 0.32)


def _leading_for(style: str, template: TemplateSpec) -> float:
    if style.startswith("h"):
        lvl = min(int(style[1]) if len(style) > 1 and style[1].isdigit() else 1, 4)
        return template.h_size_pt.get(lvl, 12) * 1.15
    if style == "caption":
        return template.body_size_pt * 0.85 * 1.2
    if style in ("footnote", "table_row"):
        return template.body_size_pt * 0.88 * 1.15
    if style == "table_header":
        return template.body_size_pt * 0.92 * 1.2
    return template.body_leading_pt


def _font_for_word(style: str, template: TemplateSpec, bold: bool, italic: bool) -> tuple[str, float]:
    if style.startswith("h"):
        lvl = min(int(style[1]) if len(style) > 1 and style[1].isdigit() else 1, 4)
        return template.heading_font_bold, template.h_size_pt.get(lvl, 12)
    if bold:
        return template.body_font_bold, template.body_size_pt
    if italic:
        return template.body_font_italic, template.body_size_pt
    return template.body_font, template.body_size_pt


def _measure_word(word: str, style: str, template: TemplateSpec, bold: bool, italic: bool, loader) -> float:
    fam, size = _font_for_word(style, template, bold, italic)
    resolved = font_manager.resolve_variant(
        fam, bold=bold and not style.startswith("h"), italic=italic and not style.startswith("h"),
    )
    adv = advance_width_pt(resolved.path, word, size)
    if adv is not None and adv > 0:
        return adv
    pf = loader(fam, max(6, int(round(size * 4 / 3))), bold and not style.startswith("h"), italic)
    bbox = pf.getbbox(word)
    return bbox[2] - bbox[0]


def flow_runs_into_lines(
    runs: list[Run],
    style: str,
    template: TemplateSpec,
    col_index: int,
    col_width: float,
    start_y: float,
    obstacles: list[ColumnObstacle],
    font_loader,
    hyphenate: bool = False,
    language: str = "ru-RU",
) -> tuple[list[FlowLine], float]:
    words: list[tuple[str, bool, bool]] = []
    for run in runs:
        for word in run.text.split():
            if word:
                words.append((word, run.bold, run.italic))
    if not words:
        leading = _leading_for(style, template)
        return [FlowLine([Run(text="")], style, col_index, 0.0, col_width, start_y)], start_y + leading

    allow_hyph = hyphenate and not style.startswith("h") and style in ("body", "list", "footnote")
    lines: list[FlowLine] = []
    y = start_y
    leading = _leading_for(style, template)

    line_words: list[tuple[str, bool, bool]] = []
    line_text = ""
    line_bold = words[0][1]
    line_italic = words[0][2]

    def measure_fragment(fragment: str, bold: bool, italic: bool) -> float:
        x_off, width = line_geometry(col_width, y, obstacles)
        max_px = width * 4 / 3
        return _measure_word(fragment, style, template, bold, italic, font_loader)

    def emit_line():
        nonlocal y, line_text, line_words, line_bold, line_italic
        if not line_text and not line_words:
            return
        x_off, width = line_geometry(col_width, y, obstacles)
        if line_words:
            lr = [Run(text=t, bold=b, italic=i) for t, b, i in line_words]
        else:
            lr = [Run(text=line_text, bold=line_bold, italic=line_italic)]
        lines.append(FlowLine(lr, style, col_index, x_off, width, y))
        y += leading + (leading * 0.35 if style.startswith("h") else 0)
        line_words = []
        line_text = ""

    for word, bold, italic in words:
        x_off, width = line_geometry(col_width, y, obstacles)
        max_px = width * 4 / 3
        sep = " " if line_text else ""
        trial = f"{line_text}{sep}{word}".strip()
        w_px = _measure_word(trial, style, template, bold, italic, font_loader)

        if w_px <= max_px or not line_text:
            if bold != line_bold or italic != line_italic:
                if line_text:
                    line_words.append((line_text, line_bold, line_italic))
                line_text = word
                line_bold, line_italic = bold, italic
            else:
                line_text = trial
        elif allow_hyph and line_text:
            parts = line_text.split()
            last = parts[-1] if parts else word
            lb, li = line_bold, line_italic
            prefix = " ".join(parts[:-1])
            base = f"{prefix} " if prefix else ""
            room = max_px - _measure_word(base, style, template, lb, li, font_loader)
            split = split_for_line(last, language, max(room, max_px * 0.25), measure_fragment)
            if split:
                head, tail = split
                line_text = f"{base}{head}".strip()
                emit_line()
                line_text = tail
                line_bold, line_italic = bold, italic
                sep2 = ""
                trial2 = line_text
                w2 = _measure_word(trial2, style, template, bold, italic, font_loader)
                if w2 <= max_px:
                    continue
            if line_text:
                line_words.append((line_text, line_bold, line_italic))
            emit_line()
            line_text = word
            line_bold, line_italic = bold, italic
        else:
            if line_text:
                line_words.append((line_text, line_bold, line_italic))
            emit_line()
            line_text = word
            line_bold, line_italic = bold, italic

    if line_text:
        line_words.append((line_text, line_bold, line_italic))
    emit_line()
    return lines, y


def obstacle_bottom(obstacles: list[ColumnObstacle]) -> float:
    if not obstacles:
        return 0.0
    return max(o.y_bottom for o in obstacles)
