/**
 * Редактор рекламной сетки: многостраничность, слоты, серверные шаблоны.
 */
(function () {
  const FORMATS = {
    a4: { w: 210, h: 297 },
    tabloid: { w: 280, h: 430 },
    newspaper_broadsheet: { w: 315, h: 470 },
    custom: { w: 210, h: 297 },
  };
  const STORAGE_KEY = "layoutgenius_grid_templates";

  let canvas, ctx, slotListEl, imageChipsEl, pageTabsEl, slots = [], selected = -1;
  let availableImages = [];
  let drawing = null, dragImage = null, scale = 1, pageW = 210, pageH = 297;
  let margins = { top: 20, bottom: 20, left: 18, right: 18 };
  let currentPageIndex = 0;

  function slotsOnPage(pg) {
    return slots.map((s, i) => ({ s, i })).filter(({ s }) => (s.page_index || 0) === pg);
  }

  function pageCount() {
    const fromSlots = slots.length ? Math.max(...slots.map(s => s.page_index || 0)) + 1 : 1;
    return Math.max(fromSlots, currentPageIndex + 1);
  }

  function getMargins() {
    const g = (id, def) => parseFloat(document.getElementById(id)?.value) || def;
    return {
      top: g("margin_top_mm", 6),
      bottom: g("margin_bottom_mm", 7),
      left: g("margin_inside_mm", 8),
      right: g("margin_outside_mm", 10),
    };
  }

  function getPageSize() {
    const fmt = document.getElementById("page_format")?.value || "a4";
    if (fmt === "custom") {
      return {
        w: parseFloat(document.getElementById("custom_page_width_mm")?.value) || 210,
        h: parseFloat(document.getElementById("custom_page_height_mm")?.value) || 297,
      };
    }
    return FORMATS[fmt] || FORMATS.a4;
  }

  function mmToPx(mm) { return mm * scale; }
  function pxToMm(px) { return px / scale; }

  function hitSlot(px, py) {
    const mmx = pxToMm(px), mmy = pxToMm(py);
    for (let i = slots.length - 1; i >= 0; i--) {
      const s = slots[i];
      if ((s.page_index || 0) !== currentPageIndex) continue;
      if (mmx >= s.x_mm && mmy >= s.y_mm &&
          mmx <= s.x_mm + s.width_mm && mmy <= s.y_mm + s.height_mm) {
        return i;
      }
    }
    return -1;
  }

  function renderPageTabs() {
    if (!pageTabsEl) return;
    const n = pageCount();
    let html = "";
    for (let p = 0; p < n; p++) {
      const cnt = slotsOnPage(p).length;
      html += `<button type="button" class="page-tab${p === currentPageIndex ? " active" : ""}" data-page="${p}">Стр. ${p + 1}${cnt ? ` (${cnt})` : ""}</button>`;
    }
    html += `<button type="button" class="page-tab page-tab-add" id="gridAddPage" title="Добавить полосу">+</button>`;
    pageTabsEl.innerHTML = html;
    pageTabsEl.querySelectorAll(".page-tab[data-page]").forEach(btn => {
      btn.addEventListener("click", () => {
        currentPageIndex = parseInt(btn.dataset.page, 10);
        selected = -1;
        renderPageTabs();
        renderList();
        draw();
      });
    });
    document.getElementById("gridAddPage")?.addEventListener("click", () => {
      currentPageIndex = n;
      renderPageTabs();
      renderList();
      draw();
    });
  }

  function resize() {
    if (!canvas) return;
    const wrap = canvas.parentElement;
    const maxW = Math.min(wrap.clientWidth - 4, 520);
    const ps = getPageSize();
    pageW = ps.w;
    pageH = ps.h;
    margins = getMargins();
    scale = maxW / pageW;
    canvas.width = Math.round(pageW * scale);
    canvas.height = Math.round(pageH * scale);
    renderPageTabs();
    draw();
  }

  function draw() {
    if (!ctx) return;
    const cw = canvas.width, ch = canvas.height;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, cw, ch);
    ctx.strokeStyle = "#cbd5e1";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, cw - 1, ch - 1);

    const mx = mmToPx(margins.left), my = mmToPx(margins.top);
    const mw = mmToPx(pageW - margins.left - margins.right);
    const mh = mmToPx(pageH - margins.top - margins.bottom);
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#94a3b8";
    ctx.strokeRect(mx, my, mw, mh);
    ctx.setLineDash([]);

    ctx.fillStyle = "#64748b";
    ctx.font = "10px sans-serif";
    ctx.fillText(`Полоса ${currentPageIndex + 1}`, 8, 14);

    slotsOnPage(currentPageIndex).forEach(({ s, i }) => {
      const x = mmToPx(s.x_mm), y = mmToPx(s.y_mm);
      const w = mmToPx(s.width_mm), h = mmToPx(s.height_mm);
      const hasFile = !!s.filename;
      ctx.fillStyle = i === selected
        ? "rgba(219,39,119,0.28)"
        : (hasFile ? "rgba(52,211,153,0.35)" : "rgba(251,191,36,0.35)");
      ctx.strokeStyle = i === selected ? "#be185d" : (hasFile ? "#059669" : "#d97706");
      ctx.lineWidth = i === selected ? 2 : 1;
      ctx.fillRect(x, y, w, h);
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = hasFile ? "#065f46" : "#78350f";
      ctx.font = "bold 9px sans-serif";
      ctx.fillText(`#${i + 1}`, x + 4, y + 11);
      ctx.font = "8px sans-serif";
      ctx.fillText(`${Math.round(s.width_mm)}×${Math.round(s.height_mm)}`, x + 4, y + 22);
      if (s.filename) {
        const short = s.filename.length > 14 ? s.filename.slice(0, 12) + "…" : s.filename;
        ctx.fillText(short, x + 4, y + h - 6);
      }
    });

    if (drawing) {
      const x = Math.min(drawing.x0, drawing.x1);
      const y = Math.min(drawing.y0, drawing.y1);
      const w = Math.abs(drawing.x1 - drawing.x0);
      const h = Math.abs(drawing.y1 - drawing.y0);
      ctx.strokeStyle = "#2563eb";
      ctx.setLineDash([3, 3]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  }

  function renderImageChips() {
    if (!imageChipsEl) return;
    if (!availableImages.length) {
      imageChipsEl.innerHTML = "<span class='hint-small'>Загрузите картинки — перетащите на слот</span>";
      return;
    }
    imageChipsEl.innerHTML = availableImages.map(name => `
      <span class="img-chip" draggable="true" data-filename="${escapeAttr(name)}">${escapeHtml(name)}</span>
    `).join("");
    imageChipsEl.querySelectorAll(".img-chip").forEach(chip => {
      chip.addEventListener("dragstart", e => {
        dragImage = chip.dataset.filename;
        e.dataTransfer.setData("text/plain", dragImage);
      });
      chip.addEventListener("dragend", () => { dragImage = null; });
    });
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, "&quot;"); }

  function renderList() {
    if (!slotListEl) return;
    const onPage = slotsOnPage(currentPageIndex);
    if (!onPage.length) {
      slotListEl.innerHTML = `<li class='empty'>На полосе ${currentPageIndex + 1} нет слотов — нарисуйте или выберите пресет</li>`;
      return;
    }
    const opts = ['<option value="">— файл —</option>']
      .concat(availableImages.map(n => `<option value="${escapeAttr(n)}">${escapeHtml(n)}</option>`));
    const optHtml = opts.join("");

    slotListEl.innerHTML = onPage.map(({ s, i }) => `
      <li class="${i === selected ? "active" : ""}" data-idx="${i}">
        <div class="slot-row">
          <span>#${i + 1} · ${s.width_mm.toFixed(0)}×${s.height_mm.toFixed(0)} мм</span>
          <button type="button" class="slot-del" data-idx="${i}">×</button>
        </div>
        <select class="slot-file" data-idx="${i}">${optHtml}</select>
      </li>`).join("");

    slotListEl.querySelectorAll(".slot-file").forEach(sel => {
      const idx = parseInt(sel.dataset.idx, 10);
      sel.value = slots[idx].filename || "";
      sel.addEventListener("change", () => {
        slots[idx].filename = sel.value;
        draw();
      });
    });
    slotListEl.querySelectorAll(".slot-del").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        slots.splice(parseInt(btn.dataset.idx, 10), 1);
        selected = -1;
        renderPageTabs();
        renderList();
        draw();
      });
    });
    slotListEl.querySelectorAll("li[data-idx]").forEach(li => {
      li.addEventListener("click", e => {
        if (e.target.tagName === "SELECT" || e.target.tagName === "BUTTON") return;
        selected = parseInt(li.dataset.idx, 10);
        renderList();
        draw();
      });
    });
  }

  function canvasPos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function onDown(e) {
    if (e.button !== 0) return;
    const p = canvasPos(e);
    const hit = hitSlot(p.x, p.y);
    if (hit >= 0) {
      selected = hit;
      renderList();
      draw();
      return;
    }
    drawing = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
    selected = -1;
    renderList();
  }

  function onMove(e) {
    if (!drawing) return;
    const p = canvasPos(e);
    drawing.x1 = p.x;
    drawing.y1 = p.y;
    draw();
  }

  function onUp(e) {
    if (drawing) {
      const x0 = pxToMm(Math.min(drawing.x0, drawing.x1));
      const y0 = pxToMm(Math.min(drawing.y0, drawing.y1));
      const w = pxToMm(Math.abs(drawing.x1 - drawing.x0));
      const h = pxToMm(Math.abs(drawing.y1 - drawing.y0));
      drawing = null;
      if (w >= 8 && h >= 8) {
        slots.push({
          page_index: currentPageIndex,
          x_mm: Math.round(x0 * 10) / 10,
          y_mm: Math.round(y0 * 10) / 10,
          width_mm: Math.round(w * 10) / 10,
          height_mm: Math.round(h * 10) / 10,
          filename: "",
        });
        selected = slots.length - 1;
      }
      renderPageTabs();
      renderList();
      draw();
    }
  }

  function onDrop(e) {
    e.preventDefault();
    const p = canvasPos(e);
    const hit = hitSlot(p.x, p.y);
    const fname = e.dataTransfer.getData("text/plain") || dragImage;
    if (hit >= 0 && fname) {
      slots[hit].filename = fname;
      selected = hit;
      renderList();
      draw();
    }
  }

  async function applyPreset(presetId) {
    const ps = getPageSize();
    const m = getMargins();
    try {
      const resp = await fetch("/api/grid-presets");
      const data = await resp.json();
      const preset = data.details?.[presetId];
      if (!preset) return;
      const baseW = 210 - 36, baseH = 297 - 40;
      const cw = ps.w - m.left - m.right;
      const ch = ps.h - m.top - m.bottom;
      const sx = cw / baseW, sy = ch / baseH;
      slots = preset.slots.map(s => ({
        page_index: s.page_index || 0,
        x_mm: Math.round((m.left + (s.x_mm - 18) * sx) * 10) / 10,
        y_mm: Math.round((m.top + (s.y_mm - 20) * sy) * 10) / 10,
        width_mm: Math.round(s.width_mm * sx * 10) / 10,
        height_mm: Math.round(s.height_mm * sy * 10) / 10,
        filename: s.filename || "",
      }));
      currentPageIndex = 0;
      selected = 0;
      renderPageTabs();
      renderList();
      draw();
    } catch (_) { /* ignore */ }
  }

  function loadLocalTemplates() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    } catch (_) {
      return {};
    }
  }

  async function refreshTemplateSelect() {
    const sel = document.getElementById("gridTemplateSelect");
    const serverSel = document.getElementById("gridServerTemplateSelect");
    const local = loadLocalTemplates();
    if (sel) {
      sel.innerHTML = '<option value="">— локальный шаблон —</option>' +
        Object.keys(local).map(k => `<option value="local:${escapeAttr(k)}">📁 ${escapeHtml(k)}</option>`).join("");
    }
    if (serverSel) {
      try {
        const resp = await fetch("/api/grid-templates");
        const data = await resp.json();
        serverSel.innerHTML = '<option value="">— серверный шаблон —</option>' +
          (data.templates || []).map(t =>
            `<option value="${escapeAttr(t.id)}">☁ ${escapeHtml(t.name)} (${t.page_count} стр., ${t.slot_count} сл.)</option>`
          ).join("");
      } catch (_) {
        serverSel.innerHTML = '<option value="">— сервер недоступен —</option>';
      }
    }
  }

  function applySlotsFromTemplate(tplSlots, pageFormat) {
    slots = (tplSlots || []).map(s => ({
      ...s,
      page_index: s.page_index || 0,
      filename: s.filename || "",
    }));
    if (pageFormat) {
      const pf = document.getElementById("page_format");
      if (pf) pf.value = pageFormat;
      const custom = document.getElementById("customSizeRow");
      if (custom) custom.hidden = pageFormat !== "custom";
    }
    currentPageIndex = 0;
    selected = slots.length ? 0 : -1;
    resize();
    renderList();
  }

  async function saveTemplate() {
    const name = prompt("Имя шаблона сетки (например «Выпуск №12»):");
    if (!name?.trim()) return;
    const pageFormat = document.getElementById("page_format")?.value || "a4";
    const payload = {
      name: name.trim(),
      slots: slots.map(s => ({ ...s })),
      page_format: pageFormat,
    };
    try {
      const resp = await fetch("/api/grid-templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        await refreshTemplateSelect();
        alert(`Шаблон «${name.trim()}» сохранён на сервере`);
        return;
      }
    } catch (_) { /* fallback local */ }
    const all = loadLocalTemplates();
    all[name.trim()] = { ...payload, saved_at: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    refreshTemplateSelect();
    alert(`Шаблон «${name.trim()}» сохранён локально`);
  }

  function loadSelectedTemplate() {
    const sel = document.getElementById("gridTemplateSelect");
    const val = sel?.value;
    if (!val) return;
    if (val.startsWith("local:")) {
      const name = val.slice(6);
      const tpl = loadLocalTemplates()[name];
      if (tpl?.slots) applySlotsFromTemplate(tpl.slots, tpl.page_format);
    }
  }

  async function loadServerTemplate() {
    const sel = document.getElementById("gridServerTemplateSelect");
    const id = sel?.value;
    if (!id) return;
    try {
      const resp = await fetch(`/api/grid-templates/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const tpl = await resp.json();
      applySlotsFromTemplate(tpl.slots, tpl.page_format);
    } catch (_) { /* ignore */ }
  }

  function init() {
    canvas = document.getElementById("adGridCanvas");
    slotListEl = document.getElementById("adGridSlotList");
    imageChipsEl = document.getElementById("adGridImageChips");
    pageTabsEl = document.getElementById("adGridPageTabs");
    if (!canvas) return;
    ctx = canvas.getContext("2d");

    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseup", onUp);
    canvas.addEventListener("mouseleave", () => { drawing = null; });
    canvas.addEventListener("dragover", e => e.preventDefault());
    canvas.addEventListener("drop", onDrop);

    document.getElementById("adGridClear")?.addEventListener("click", () => {
      slots = slots.filter(s => (s.page_index || 0) !== currentPageIndex);
      selected = -1;
      renderPageTabs();
      renderList();
      draw();
    });
    document.getElementById("gridSaveTemplate")?.addEventListener("click", saveTemplate);
    document.getElementById("gridLoadTemplate")?.addEventListener("click", loadSelectedTemplate);
    document.getElementById("gridLoadServerTemplate")?.addEventListener("click", loadServerTemplate);

    document.querySelectorAll("[data-grid-preset]").forEach(btn => {
      btn.addEventListener("click", () => applyPreset(btn.dataset.gridPreset));
    });

    ["page_format", "margin_top_mm", "margin_bottom_mm", "margin_inside_mm", "margin_outside_mm",
     "columns_count", "column_gutter_mm",
     "custom_page_width_mm", "custom_page_height_mm"].forEach(id => {
      document.getElementById(id)?.addEventListener("change", resize);
      document.getElementById(id)?.addEventListener("input", resize);
    });

    document.getElementById("page_format")?.addEventListener("change", () => {
      const custom = document.getElementById("customSizeRow");
      if (custom) custom.hidden = document.getElementById("page_format").value !== "custom";
      resize();
    });

    window.addEventListener("resize", resize);
    refreshTemplateSelect();
    resize();
    renderList();
    renderImageChips();
  }

  window.AdGridEditor = {
    init,
    getJson() {
      return JSON.stringify({
        slots: slots.map((s, i) => ({
          ...s,
          slot_index: i,
        })),
      });
    },
    setSlots(newSlots) {
      slots = (newSlots || []).map(s => ({
        ...s,
        page_index: s.page_index || 0,
        filename: s.filename || "",
      }));
      currentPageIndex = 0;
      selected = -1;
      renderPageTabs();
      renderList();
      draw();
    },
    setAvailableImages(names) {
      availableImages = names || [];
      renderImageChips();
      renderList();
    },
    getSlots() { return [...slots]; },
    resize,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
