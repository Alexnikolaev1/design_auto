"""Тесты серверных шаблонов сетки."""

from app.layout import grid_templates as gt


def test_save_and_list_template(tmp_path, monkeypatch):
    monkeypatch.setattr(gt, "GRID_TEMPLATES_DIR", tmp_path)
    saved = gt.save_template("Тест выпуск", [
        {"page_index": 0, "x_mm": 10, "y_mm": 20, "width_mm": 50, "height_mm": 40},
    ], "a4")
    assert saved["name"] == "Тест выпуск"
    items = gt.list_templates()
    assert len(items) == 1
    assert items[0]["slot_count"] == 1
    loaded = gt.load_template(saved["id"])
    assert loaded is not None
    assert len(loaded["slots"]) == 1
    assert gt.delete_template(saved["id"])
    assert gt.load_template(saved["id"]) is None
