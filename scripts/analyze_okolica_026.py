"""Анализ разворота Okolica_026.pdf — размеры фото и зоны."""
from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

import fitz

PDF = Path(__file__).resolve().parent.parent / "examples" / "Okolica_026.pdf"
OUT = Path(__file__).resolve().parent.parent / "examples" / "_analysis"
MM = lambda pt: round(pt * 25.4 / 72, 2)


def analyze_page(page, idx: int) -> None:
    pw, ph = page.rect.width, page.rect.height
    print(f"\n=== page {idx+1}  {MM(pw)}x{MM(ph)} mm ===")

    # drawings / images via get_image_info
    infos = []
    try:
        for info in page.get_image_info(xrefs=True):
            bbox = info.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            w, h = x1 - x0, y1 - y0
            if w < 20 or h < 20:
                continue
            infos.append({
                "x": MM(x0), "y": MM(y0), "w": MM(w), "h": MM(h),
                "aspect": round(w / max(h, 1), 2),
                "cm2": round(MM(w) * MM(h) / 100, 1),
            })
    except Exception as e:
        print("image_info err", e)

    infos.sort(key=lambda d: -d["cm2"])
    print(f"images/drawings: {len(infos)}")
    for im in infos[:12]:
        span = "LEAD" if im["w"] > MM(pw) * 0.35 else ("COL" if im["w"] < MM(pw) * 0.2 else "MID")
        print(f"  {span:4} {im}")

    data = page.get_text("dict", flags=0)
    sizes = Counter()
    large = []
    for b in data.get("blocks", []):
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                t = (s.get("text") or "").strip()
                if not t:
                    continue
                sz = round(s["size"], 1)
                sizes[sz] += 1
                if sz >= 18:
                    large.append((sz, s["font"].split("+")[-1][:24], MM(s["bbox"][1]), t[:60]))
    print("size top", sizes.most_common(8))
    for item in large[:6]:
        print("  head", item)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    doc = fitz.open(PDF)
    print(f"pages={len(doc)} file={PDF.name}")
    # cover + a few spreads
    for i in [0, 1, 2, 3, 5, 8, 12]:
        if i < len(doc):
            analyze_page(doc[i], i)
            # render half-res preview of interior
            if i in (0, 1, 2):
                mat = fitz.Matrix(100 / 72, 100 / 72)
                pix = doc[i].get_pixmap(matrix=mat, alpha=False)
                pix.save(str(OUT / f"026_p{i+1:02d}.png"))
    doc.close()


if __name__ == "__main__":
    main()
