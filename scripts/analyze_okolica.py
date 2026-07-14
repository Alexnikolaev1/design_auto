"""Анализ полос «Сибирская околица» для эталонного профиля."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from pathlib import Path

import fitz

EX = Path(__file__).resolve().parent.parent / "examples"
MM = lambda pt: round(pt * 25.4 / 72, 2)  # noqa: E731


def analyze(path: Path) -> None:
    doc = fitz.open(path)
    page = doc[0]
    pw, ph = page.rect.width, page.rect.height
    data = page.get_text("dict", flags=0)

    spans = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                sx0, sy0, sx1, sy1 = span["bbox"]
                spans.append({
                    "text": text[:90],
                    "size": round(span.get("size", 0), 2),
                    "font": span.get("font", "").split("+")[-1],
                    "x0": sx0, "y0": sy0, "x1": sx1, "y1": sy1,
                    "w": sx1 - sx0,
                })

    imgs = []
    for block in data.get("blocks", []):
        if block.get("type") != 1:
            continue
        x0, y0, x1, y1 = block["bbox"]
        imgs.append({
            "x": MM(x0), "y": MM(y0),
            "w": MM(x1 - x0), "h": MM(y1 - y0),
            "cm2": round(MM(x1 - x0) * MM(y1 - y0) / 100, 1),
        })

    if spans:
        ml = min(s["x0"] for s in spans)
        mr = pw - max(s["x1"] for s in spans)
        mt = min(s["y0"] for s in spans)
        mb = ph - max(s["y1"] for s in spans)
    else:
        ml = mr = mt = mb = 0

    body = [s for s in spans if 7.0 <= s["size"] <= 11.5 and s["w"] > pw * 0.08]
    lefts = sorted(s["x0"] for s in body)
    clusters: list[float] = []
    for x in lefts:
        if not clusters or x - clusters[-1] > pw * 0.06:
            clusters.append(x)

    sizes = Counter(round(s["size"], 1) for s in spans)
    fonts = Counter(s["font"] for s in spans)
    heads = sorted([s for s in spans if s["size"] >= 14], key=lambda s: -s["size"])
    rubrics = [
        s for s in spans
        if "Helios" in s["font"] and 9 <= s["size"] <= 18 and len(s["text"]) < 50
    ]

    print("=" * 72)
    print(path.name)
    print(f"page mm: {MM(pw)} x {MM(ph)}")
    print(f"margins mm L/R/T/B: {MM(ml)}, {MM(mr)}, {MM(mt)}, {MM(mb)}")
    print(f"spans={len(spans)} images={len(imgs)}")
    print(f"cols~{len(clusters)} at mm {[MM(c) for c in clusters]}")
    if len(clusters) >= 2:
        gaps = [clusters[i + 1] - clusters[i] for i in range(len(clusters) - 1)]
        print(f"  gap between left-edges mm: {[MM(g) for g in gaps]}")
        # estimate col width from body spans near first cluster
        for i, c in enumerate(clusters):
            near = [s for s in body if abs(s["x0"] - c) < 8]
            if near:
                cw = statistics.median(s["w"] for s in near)
                print(f"  col{i} median width mm: {MM(cw)}")

    print(f"size hist: {sizes.most_common(14)}")
    print(f"fonts: {fonts.most_common(12)}")
    print("HEADLINES (>=14pt):")
    for s in heads[:10]:
        print(
            f"  {s['size']:5.1f} {s['font'][:30]:30} "
            f"y={MM(s['y0']):5.1f} x={MM(s['x0']):5.1f}  {s['text']}"
        )
    print("RUBRICS/kicker (Helios):")
    seen: set[str] = set()
    for s in rubrics:
        if s["text"] in seen:
            continue
        seen.add(s["text"])
        print(
            f"  {s['size']:5.1f} {s['font'][:30]:30} "
            f"y={MM(s['y0']):5.1f}  {s['text']}"
        )
        if len(seen) >= 12:
            break
    print("IMAGES (top 8):")
    for im in imgs[:8]:
        print(f"  {im}")
    if body:
        print(f"body median pt: {statistics.median(s['size'] for s in body):.2f}")

    by_col: dict[float, list] = defaultdict(list)
    for s in body:
        c = min(clusters, key=lambda cc: abs(cc - s["x0"])) if clusters else 0.0
        by_col[round(c, 0)].append(s)
    for ck, items in sorted(by_col.items())[:5]:
        ys = sorted({round(s["y0"], 1) for s in items})
        if len(ys) >= 4:
            diffs = [ys[i + 1] - ys[i] for i in range(len(ys) - 1) if 6 < ys[i + 1] - ys[i] < 18]
            if diffs:
                print(f"  lead x~{MM(ck)} mm median pt: {statistics.median(diffs):.2f}")
    doc.close()


def dump_text_map(path: Path, out: Path) -> None:
    """Сохранить текстовую карту полосы (y,x,size,font,text)."""
    doc = fitz.open(path)
    page = doc[0]
    data = page.get_text("dict", flags=0)
    lines_out = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            parts = []
            sizes = []
            fonts = []
            bbox = line["bbox"]
            for span in line.get("spans", []):
                t = span.get("text", "")
                if t.strip():
                    parts.append(t)
                    sizes.append(span.get("size", 0))
                    fonts.append(span.get("font", "").split("+")[-1])
            if not parts:
                continue
            text = "".join(parts).strip()
            sz = max(sizes) if sizes else 0
            font = fonts[0] if fonts else ""
            lines_out.append(
                f"y={MM(bbox[1]):6.1f} x={MM(bbox[0]):5.1f} "
                f"w={MM(bbox[2]-bbox[0]):5.1f} sz={sz:5.1f} "
                f"{font[:24]:24} | {text}"
            )
    out.write_text("\n".join(lines_out), encoding="utf-8")
    doc.close()
    print(f"wrote {out} ({len(lines_out)} lines)")


if __name__ == "__main__":
    pages = [
        "002_Okolica_027.pdf",
        "001_Okolica_027.pdf",
        "003_Okolica_027.pdf",
        "004_Okolica_027.pdf",
        "005_Okolica_027.pdf",
        "008_Okolica_027.pdf",
        "025_Okolica_027.pdf",
        "026_Okolica_027.pdf",
        "032_Okolica_027.pdf",
    ]
    for name in pages:
        p = EX / name
        if p.exists():
            analyze(p)
    out_dir = EX / "_analysis"
    out_dir.mkdir(exist_ok=True)
    for name in ["002_Okolica_027.pdf", "001_Okolica_027.pdf", "004_Okolica_027.pdf"]:
        dump_text_map(EX / name, out_dir / (name.replace(".pdf", ".txt")))
