/**
 * Визуальный редактор полосы: перетаскивание и масштабирование фреймов изображений.
 */
(function () {
  let modal, canvas, ctx, model = null, jobId = null, templateId = null;
  let pageIndex = 0, scale = 1, selectedId = null;
  let drag = null, overrides = [], savedOverridesJson = null;

  function mmToPx(mm) { return mm * scale; }
  function pxToMm(px) { return px / scale; }

  function currentPage() {
    return model?.pages?.find(p => p.index === pageIndex) || model?.pages?.[0];
  }

  function getOverridesFromModel() {
    const out = [];
    for (const p of model?.pages || []) {
      for (const img of p.images || []) {
        out.push({
          element_id: img.element_id,
          page_index: p.index,
          x_mm: img.x_mm,
          y_mm: img.y_mm,
          width_mm: img.width_mm,
          height_mm: img.height_mm,
        });
      }
    }
    return out;
  }

  function applyOverride(elId, patch) {
    const p = currentPage();
    if (!p) return;
    const img = p.images.find(i => i.element_id === elId);
    if (!img) return;
    Object.assign(img, patch);
  }

  function resizeCanvas() {
    if (!canvas || !model) return;
    const wrap = canvas.parentElement;
    const maxW = Math.min(wrap.clientWidth - 8, 640);
    scale = maxW / model.page_width_mm;
    canvas.width = Math.round(model.page_width_mm * scale);
    canvas.height = Math.round(model.page_height_mm * scale);
    draw();
  }

  function draw() {
    if (!ctx || !model) return;
    const cw = canvas.width, ch = canvas.height;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cw, ch);
    ctx.strokeStyle = "#cbd5e1";
    ctx.strokeRect(0.5, 0.5, cw - 1, ch - 1);

    const m = model.margins_mm;
    const mx = mmToPx(m.left), my = mmToPx(m.top);
    const mw = mmToPx(model.page_width_mm - m.left - m.right);
    const mh = mmToPx(model.page_height_mm - m.top - m.bottom);
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#94a3b8";
    ctx.strokeRect(mx, my, mw, mh);
    ctx.setLineDash([]);

    const page = currentPage();
    if (!page) return;

    for (const col of page.columns || []) {
      const x = mmToPx(col.x_mm), y = mmToPx(col.y_mm);
      const w = mmToPx(col.width_mm), h = mmToPx(col.height_mm);
      ctx.fillStyle = "rgba(148,163,184,0.08)";
      ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = "#e2e8f0";
      ctx.strokeRect(x, y, w, h);
    }

    for (const img of page.images || []) {
      const x = mmToPx(img.x_mm), y = mmToPx(img.y_mm);
      const w = mmToPx(img.width_mm), h = mmToPx(img.height_mm);
      const sel = img.element_id === selectedId;
      const isAd = img.role === "ad";
      ctx.fillStyle = sel
        ? "rgba(59,130,246,0.35)"
        : (isAd ? "rgba(251,191,36,0.4)" : "rgba(52,211,153,0.35)");
      ctx.strokeStyle = sel ? "#2563eb" : (isAd ? "#d97706" : "#059669");
      ctx.lineWidth = sel ? 2 : 1;
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = "#1e293b";
      ctx.font = "9px sans-serif";
      const label = img.filename || img.role || img.element_id;
      ctx.fillText(label.slice(0, 18), x + 4, y + 12);
      if (sel) {
        const hs = 8;
        ctx.fillStyle = "#2563eb";
        ctx.fillRect(x + w - hs, y + h - hs, hs, hs);
      }
    }

    ctx.fillStyle = "#64748b";
    ctx.font="10px sans-serif";
    ctx.fillText(`Полоса ${pageIndex + 1}`, 8, 14);
  }

  function hitTest(px, py) {
    const page = currentPage();
    if (!page) return null;
    const mmx = pxToMm(px), mmy = pxToMm(py);
    for (let i = page.images.length - 1; i >= 0; i--) {
      const img = page.images[i];
      if (mmx >= img.x_mm && mmy >= img.y_mm &&
          mmx <= img.x_mm + img.width_mm && mmy <= img.y_mm + img.height_mm) {
        const hx = img.x_mm + img.width_mm - 3;
        const hy = img.y_mm + img.height_mm - 3;
        const mode = (mmx >= hx && mmy >= hy) ? "resize" : "move";
        return { img, mode };
      }
    }
    return null;
  }

  function canvasPos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function onDown(e) {
    const p = canvasPos(e);
    const hit = hitTest(p.x, p.y);
    if (!hit) {
      selectedId = null;
      draw();
      return;
    }
    selectedId = hit.img.element_id;
    drag = {
      mode: hit.mode,
      id: hit.img.element_id,
      x0: p.x, y0: p.y,
      orig: { ...hit.img },
    };
    draw();
  }

  function onMove(e) {
    if (!drag) return;
    const p = canvasPos(e);
    const dx = pxToMm(p.x - drag.x0);
    const dy = pxToMm(p.y - drag.y0);
    const o = drag.orig;
    if (drag.mode === "move") {
      applyOverride(drag.id, {
        x_mm: Math.max(0, o.x_mm + dx),
        y_mm: Math.max(0, o.y_mm + dy),
      });
    } else {
      applyOverride(drag.id, {
        width_mm: Math.max(10, o.width_mm + dx),
        height_mm: Math.max(10, o.height_mm + dy),
      });
    }
    draw();
  }

  function onUp() { drag = null; }

  async function open(jid, tid, tname) {
    jobId = jid;
    templateId = tid;
    modal = document.getElementById("spreadEditorModal");
    canvas = document.getElementById("spreadEditorCanvas");
    if (!modal || !canvas) return;
    ctx = canvas.getContext("2d");
    document.getElementById("spreadEditorTitle").textContent =
      `Редактор полосы — ${tname || tid}`;
    try {
      const resp = await fetch(`/api/jobs/${jid}/layout/${tid}`);
      if (!resp.ok) throw new Error("Модель макета недоступна");
      model = await resp.json();
      pageIndex = 0;
      selectedId = null;
      overrides = getOverridesFromModel();
      renderPageSelect();
      resizeCanvas();
      modal.hidden = false;
    } catch (e) {
      alert(e.message || "Не удалось загрузить макет");
    }
  }

  function close() {
    if (modal) modal.hidden = true;
    drag = null;
  }

  function renderPageSelect() {
    const sel = document.getElementById("spreadEditorPage");
    if (!sel || !model) return;
    sel.innerHTML = (model.pages || []).map(p =>
      `<option value="${p.index}">Полоса ${p.index + 1}</option>`
    ).join("");
    sel.value = String(pageIndex);
  }

  async function saveAndRebuild() {
    overrides = getOverridesFromModel();
    savedOverridesJson = JSON.stringify({ overrides });
    const payload = {
      mapping: window.buildMappingPayload ? window.buildMappingPayload() : [],
      ad_grid: window.AdGridEditor ? window.AdGridEditor.getJson() : null,
      layout_overrides: JSON.stringify({ overrides }),
    };
    try {
      const resp = await fetch(`/api/jobs/${jobId}/rebuild`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error("Ошибка пересборки");
      close();
      if (window.pollJob) window.pollJob(jobId);
      const statusSec = document.getElementById("status-section");
      if (statusSec) statusSec.hidden = false;
    } catch (e) {
      alert(e.message || "Не удалось пересобрать");
    }
  }

  function init() {
    canvas = document.getElementById("spreadEditorCanvas");
    if (!canvas) return;
    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseup", onUp);
    canvas.addEventListener("mouseleave", onUp);
    document.getElementById("spreadEditorClose")?.addEventListener("click", close);
    document.getElementById("spreadEditorSave")?.addEventListener("click", saveAndRebuild);
    document.getElementById("spreadEditorPage")?.addEventListener("change", e => {
      pageIndex = parseInt(e.target.value, 10) || 0;
      selectedId = null;
      draw();
    });
    modal = document.getElementById("spreadEditorModal");
    modal?.querySelector(".modal-backdrop")?.addEventListener("click", close);
    window.addEventListener("resize", () => { if (!modal?.hidden) resizeCanvas(); });
  }

  window.SpreadEditor = {
    init, open, close,
    getOverridesJson: () => savedOverridesJson,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
