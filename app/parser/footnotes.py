"""Извлечение сносок из OOXML (word/footnotes.xml)."""
from __future__ import annotations

from lxml import etree

from app.parser.docx_parser import Run

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _qn(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def load_footnotes_blob(doc) -> dict[int, list[Run]]:
    """Возвращает {footnote_id: runs} для обычных сносок (не separator/continuation)."""
    out: dict[int, list[Run]] = {}
    try:
        for rel in doc.part.rels.values():
            if "footnotes" not in rel.reltype:
                continue
            blob = rel.target_part.blob
            root = etree.fromstring(blob)
            for fn in root.findall(_qn("footnote")):
                fn_type = fn.get(_qn("type"), "normal")
                if fn_type in ("separator", "continuationSeparator", "continuationNotice"):
                    continue
                fid = int(fn.get(_qn("id"), "0"))
                runs: list[Run] = []
                for p in fn.findall(_qn("p")):
                    for r in p.findall(_qn("r")):
                        texts = [t.text for t in r.findall(_qn("t")) if t.text]
                        if not texts:
                            continue
                        rpr = r.find(_qn("rPr"))
                        bold = rpr is not None and rpr.find(_qn("b")) is not None
                        italic = rpr is not None and rpr.find(_qn("i")) is not None
                        runs.append(Run(text="".join(texts), bold=bold, italic=italic))
                if runs:
                    out[fid] = runs
            break
    except Exception:
        pass
    return out
