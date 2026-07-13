"""Тесты форматов полос и обтекания."""
from app.config import TypographyProfile
from app.layout.page_formats import get_page_format, detect_format_from_mm
from app.layout.text_flow import ColumnObstacle, line_geometry, flow_runs_into_lines
from app.layout.templates import TEMPLATES
from app.parser.docx_parser import Run
from PIL import ImageFont


def test_tabloid_larger_than_a4():
    a4 = get_page_format("a4")
    tab = get_page_format("tabloid")
    assert tab.width_pt > a4.width_pt
    assert tab.height_pt > a4.height_pt


def test_detect_format():
    assert detect_format_from_mm(280, 430) == "tabloid"


def test_line_geometry_with_left_float():
    obstacles = [ColumnObstacle(y_top=100, y_bottom=200, side="left", float_width=80)]
    x_off, width = line_geometry(200, 150, obstacles)
    assert x_off > 80
    assert width < 200


def test_flow_wrap_lines():
    template = TEMPLATES[1]
    runs = [Run(text=" ".join(["слово"] * 30))]
    obstacles = [ColumnObstacle(y_top=50, y_bottom=180, side="left", float_width=90)]

    def loader(name, px, bold, italic):
        return ImageFont.load_default()

    lines, end_y = flow_runs_into_lines(
        runs, "body", template, 0, 220, 60, obstacles, loader,
    )
    assert len(lines) >= 2
    assert any(l.x_offset > 0 for l in lines)
