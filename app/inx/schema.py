"""
Мини-валидатор сгенерированного INX.

Это НЕ полноценная XSD-схема Adobe InDesign Interchange (Adobe её не
публикует в открытом виде для программной валидации) — это набор
структурных проверок здравого смысла: обязательные элементы на месте,
единицы измерения корректны, есть хотя бы одна Story и один Spread.
Пройденная проверка НЕ является гарантией, что файл на 100% откроется
в реальном InDesign CS3 без единого предупреждения — только то, что
базовая структура документа не нарушена.
"""
from __future__ import annotations

from lxml import etree


class InxValidationError(Exception):
    pass


REQUIRED_TAGS = ["Document", "MasterSpread", "Spread", "Story"]


def validate_inx(xml_bytes: bytes) -> list[str]:
    """Возвращает список предупреждений (пустой = всё ок).
    Бросает InxValidationError при фатальных структурных проблемах."""
    warnings: list[str] = []
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise InxValidationError(f"Невалидный XML: {exc}") from exc

    tag_names = {etree.QName(el).localname for el in root.iter()}

    for required in REQUIRED_TAGS:
        if required not in tag_names:
            raise InxValidationError(f"Отсутствует обязательный элемент <{required}>")

    stories = [el for el in root.iter() if etree.QName(el).localname == "Story"]
    if not stories:
        raise InxValidationError("Документ не содержит ни одной Story")

    spreads = [el for el in root.iter() if etree.QName(el).localname == "Spread"]
    if not spreads:
        raise InxValidationError("Документ не содержит ни одного Spread")

    for spread in spreads:
        pc = spread.get("PageCount", "1")
        pages_in_spread = [el for el in spread if etree.QName(el).localname == "Page"]
        try:
            expected = int(pc)
            if len(pages_in_spread) != expected:
                warnings.append(
                    f"Spread PageCount={pc}, но элементов Page: {len(pages_in_spread)}"
                )
        except ValueError:
            warnings.append(f"Некорректный PageCount у Spread: {pc}")

    text_frames = [el for el in root.iter() if etree.QName(el).localname == "TextFrame"]
    if not text_frames:
        warnings.append("В документе нет ни одного TextFrame — весь текст останется вне вёрстки.")

    # Проверка геометрии: координаты должны быть в разумных пределах A4 c учётом bleed
    for tf in text_frames:
        geo = tf.get("GeometricBounds", "")
        parts = geo.split()
        if len(parts) == 4:
            try:
                vals = [float(p) for p in parts]
                if any(v < -100 or v > 2500 for v in vals):
                    warnings.append(f"Подозрительные координаты фрейма: {geo}")
            except ValueError:
                warnings.append(f"Нечисловые координаты GeometricBounds: {geo}")

    return warnings
