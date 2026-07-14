const docDropzone = document.getElementById("docDropzone");
const imgDropzone = document.getElementById("imgDropzone");
const fontDropzone = document.getElementById("fontDropzone");
const fileInput = document.getElementById("fileInput");
const articlesDropzone = document.getElementById("articlesDropzone");
const articlesInput = document.getElementById("articlesInput");
const articlesListEl = document.getElementById("articlesList");
const imgInput = document.getElementById("imgInput");
const fontInput = document.getElementById("fontInput");
const fileNameEl = document.getElementById("fileName");
const imgListEl = document.getElementById("imgList");
const fontListEl = document.getElementById("fontList");
const submitBtn = document.getElementById("submitBtn");
const statusSection = document.getElementById("status-section");
const statusText = document.getElementById("statusText");
const statusDetail = document.getElementById("statusDetail");
const progressFill = document.getElementById("progressFill");
const refDropzone = document.getElementById("refDropzone");
const refInput = document.getElementById("refInput");
const refListEl = document.getElementById("refList");
const placementsSection = document.getElementById("placements-section");
const referenceSection = document.getElementById("reference-section");
const referenceSummary = document.getElementById("referenceSummary");
const referencePreferred = document.getElementById("referencePreferred");
const placementsList = document.getElementById("placementsList");
const downloadMappingBtn = document.getElementById("downloadMappingBtn");
const rebuildBtn = document.getElementById("rebuildBtn");
const outlineSection = document.getElementById("outline-section");
const outlineList = document.getElementById("outlineList");
const compareBtn = document.getElementById("compareBtn");
const compareModal = document.getElementById("compareModal");
const resultsSection = document.getElementById("results-section");
const resultsGrid = document.getElementById("results-grid");
const resultsMeta = document.getElementById("resultsMeta");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("errorText");

let selectedFile = null;
let selectedExtraArticles = [];
let selectedImages = [];
let selectedFonts = [];
let selectedReferences = [];
let currentJobId = null;
let selectedTemplateId = null;
let documentHeadings = [];
let editablePlacements = [];
let lastJobResults = [];
let previewViewer = { jobId: null, templateId: null, files: [], index: 0 };

const previewModal = document.getElementById("previewModal");
const previewModalImg = document.getElementById("previewModalImg");
const previewThumbs = document.getElementById("previewThumbs");
const previewPageLabel = document.getElementById("previewPageLabel");
const previewModalTitle = document.getElementById("previewModalTitle");

document.getElementById("previewClose")?.addEventListener("click", closePreviewViewer);
previewModal?.querySelector(".modal-backdrop")?.addEventListener("click", closePreviewViewer);
document.getElementById("previewPrev")?.addEventListener("click", () => stepPreview(-1));
document.getElementById("previewNext")?.addEventListener("click", () => stepPreview(1));
document.addEventListener("keydown", e => {
  if (previewModal?.hidden) return;
  if (e.key === "ArrowLeft") stepPreview(-1);
  if (e.key === "ArrowRight") stepPreview(1);
  if (e.key === "Escape") closePreviewViewer();
});

function openPreviewViewer(jobId, templateId, name, previewFiles, pageCount) {
  if (!previewFiles?.length) return;
  previewViewer = { jobId, templateId, files: previewFiles, index: 0 };
  if (previewModalTitle) {
    previewModalTitle.textContent = name || templateId;
  }
  renderPreviewModal();
  if (previewModal) previewModal.hidden = false;
}

function closePreviewViewer() {
  if (previewModal) previewModal.hidden = true;
}

function stepPreview(delta) {
  const n = previewViewer.files.length;
  if (!n) return;
  previewViewer.index = (previewViewer.index + delta + n) % n;
  renderPreviewModal();
}

function renderPreviewModal() {
  const { jobId, templateId, files, index } = previewViewer;
  if (!files.length || !previewModalImg) return;
  previewModalImg.src = `/api/jobs/${jobId}/preview/${templateId}/${files[index]}`;
  if (previewPageLabel) {
    previewPageLabel.textContent = `Стр. ${index + 1} из ${files.length}`;
  }
  if (previewThumbs) {
    previewThumbs.innerHTML = files.map((f, i) => `
      <img class="preview-thumb${i === index ? " active" : ""}" src="/api/jobs/${jobId}/preview/${templateId}/${f}" alt="стр. ${i + 1}" data-idx="${i}">
    `).join("");
    previewThumbs.querySelectorAll(".preview-thumb").forEach(th => {
      th.addEventListener("click", () => {
        previewViewer.index = parseInt(th.dataset.idx, 10);
        renderPreviewModal();
      });
    });
  }
}

function syncImagesToGrid() {
  if (!window.AdGridEditor) return;
  const names = selectedImages
    .filter(f => !f.name.toLowerCase().endsWith(".json"))
    .map(f => f.name);
  window.AdGridEditor.setAvailableImages(names);
}

// Tabs
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    if (tab.dataset.tab === "adgrid" && window.AdGridEditor) {
      setTimeout(() => window.AdGridEditor.resize(), 50);
    }
  });
});

// Dropzones
function setupDropzone(el, input, onFiles) {
  el.addEventListener("click", () => input.click());
  el.addEventListener("dragover", e => { e.preventDefault(); el.classList.add("dragover"); });
  el.addEventListener("dragleave", () => el.classList.remove("dragover"));
  el.addEventListener("drop", e => {
    e.preventDefault();
    el.classList.remove("dragover");
    if (e.dataTransfer.files.length) onFiles([...e.dataTransfer.files]);
  });
  input.addEventListener("change", () => {
    if (input.files.length) onFiles([...input.files]);
  });
}

setupDropzone(docDropzone, fileInput, files => {
  const f = files[0];
  const n = f?.name.toLowerCase() || "";
  if (!n.endsWith(".docx") && !n.endsWith(".doc")) {
    showError("Выберите файл .doc или .docx");
    return;
  }
  selectedFile = f;
  fileNameEl.textContent = f.name;
  fileNameEl.hidden = false;
  submitBtn.disabled = false;
});

if (articlesDropzone && articlesInput) {
  setupDropzone(articlesDropzone, articlesInput, files => {
    selectedExtraArticles = files.filter(f => {
      const n = f.name.toLowerCase();
      return n.endsWith(".docx") || n.endsWith(".doc");
    }).slice(0, 7);
    renderChips(articlesListEl, selectedExtraArticles.map(f => f.name));
  });
}

setupDropzone(imgDropzone, imgInput, files => {
  selectedImages = files.filter(f =>
    f.type.startsWith("image/") || f.name.toLowerCase().endsWith(".json")
  );
  renderChips(imgListEl, selectedImages.map(f => f.name));
  syncImagesToGrid();
});

setupDropzone(refDropzone, refInput, files => {
  selectedReferences = files.filter(f => f.name.toLowerCase().endsWith(".pdf")).slice(0, 3);
  renderChips(refListEl, selectedReferences.map(f => f.name));
});

setupDropzone(fontDropzone, fontInput, files => {
  selectedFonts = files.filter(f => /\.(ttf|otf)$/i.test(f.name));
  renderChips(fontListEl, selectedFonts.map(f => f.name));
});

function renderChips(container, names) {
  container.innerHTML = names.map(n => `<span class="chip">${escapeHtml(n)}</span>`).join("");
}

// Load fonts into selects
async function loadFonts() {
  try {
    const resp = await fetch("/api/fonts");
    const data = await resp.json();
    const fonts = data.fonts || [];
    const byCat = { serif: [], sans: [], display: [], other: [], mono: [] };
    for (const f of fonts) {
      const cat = byCat[f.category] ? f.category : "other";
      byCat[cat].push(f);
    }
    fillSelect("font_serif", [...byCat.serif, ...byCat.other], "SchoolBookC");
    fillSelect("font_sans", [...byCat.sans, ...byCat.other], "HeliosCondC");
    fillSelect("font_display", [...byCat.display, ...byCat.sans, ...byCat.other], "AdventureC");
  } catch (_) { /* fonts optional */ }
}

function fillSelect(id, fonts, preferredPs) {
  const sel = document.getElementById(id);
  const seen = new Set();
  for (const f of fonts) {
    if (seen.has(f.family)) continue;
    seen.add(f.family);
    const opt = document.createElement("option");
    opt.value = f.postscript_name;
    opt.textContent = `${f.family} (${f.style})`;
    sel.appendChild(opt);
  }
  if (preferredPs) {
    const hit = [...sel.options].find(
      o => o.value === preferredPs || o.value.startsWith(preferredPs)
    );
    if (hit) sel.value = hit.value;
  }
}

loadFonts();

submitBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  hide(errorSection);
  hide(resultsSection);
  show(statusSection);
  submitBtn.disabled = true;
  statusText.textContent = "Загрузка файлов...";
  progressFill.style.width = "5%";

  const form = new FormData();
  form.append("file", selectedFile);
  for (const art of selectedExtraArticles) form.append("extra_articles", art);
  for (const img of selectedImages) form.append("images", img);
  for (const font of selectedFonts) form.append("fonts", font);
  for (const ref of selectedReferences) form.append("references", ref);

  const fields = [
    "margin_top_mm", "margin_bottom_mm", "margin_inside_mm", "margin_outside_mm",
    "columns_count", "column_gutter_mm",
    "bleed_mm", "body_size_override_pt", "font_serif", "font_sans", "font_display",
  ];
  for (const id of fields) form.append(id, val(id));
  form.append("color_profile", document.getElementById("color_profile").value);
  form.append("language", document.getElementById("language").value);
  form.append("print_marks", document.getElementById("print_marks").checked);
  form.append("hyphenation", document.getElementById("hyphenation").checked);
  form.append("auto_stock_images", document.getElementById("auto_stock_images").checked);
  form.append("use_reference_style", document.getElementById("use_reference_style").checked);
  form.append("mark_advertising", document.getElementById("mark_advertising").checked);
  form.append("page_format", document.getElementById("page_format").value);
  form.append("facing_pages", document.getElementById("facing_pages").checked);
  form.append("heading_starts_new_page", document.getElementById("heading_starts_new_page").checked);
  form.append("jump_lines", document.getElementById("jump_lines")?.checked ?? true);
  form.append("smart_crop", document.getElementById("smart_crop")?.checked ?? true);
  form.append("pdf_vector_export", document.getElementById("pdf_vector_export")?.checked ?? true);
  form.append("custom_page_width_mm", val("custom_page_width_mm") || "0");
  form.append("custom_page_height_mm", val("custom_page_height_mm") || "0");
  if (window.AdGridEditor) {
    form.append("ad_grid", window.AdGridEditor.getJson());
  }

  try {
    const resp = await fetch("/api/jobs", { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "Ошибка запроса" }));
      const detail = err.detail;
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg || JSON.stringify(d)).join("; ")
        : (typeof detail === "string" ? detail : (detail || "Ошибка запроса"));
      throw new Error(msg);
    }
    const data = await resp.json();
    currentJobId = data.job_id;
    pollJob(data.job_id);
  } catch (e) {
    submitBtn.disabled = false;
    hide(statusSection);
    let msg = e.message || "Неизвестная ошибка";
    if (msg === "Failed to fetch") {
      msg = "Сервер не ответил на загрузку. Проверьте /api/health, размер файла (до 20 МБ) и что деплой завершён без ошибок.";
    }
    showError(msg);
  }
});

function val(id, fallback = "") {
  const el = document.getElementById(id);
  return el ? el.value : fallback;
}
function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }
function showError(msg) { errorText.textContent = msg; show(errorSection); }

const STAGE_LABELS = {
  queued: "Задача в очереди...",
  parsing: "Разбираем документ (.doc → .docx, текст, inline-картинки)...",
  analyzing: "Анализируем PDF-референсы и сопоставляем иллюстрации...",
  laying_out: "Строим 5 вариантов вёрстки и превью...",
  rebuilding: "Пересборка макета с новыми привязками...",
};
const STAGE_PROGRESS = { queued: 10, parsing: 30, analyzing: 50, laying_out: 75, done: 100 };

async function pollJob(jobId) {
  try {
    const resp = await fetch(`/api/jobs/${jobId}`);
    const data = await resp.json();
    statusText.textContent = STAGE_LABELS[data.status] || data.status;
    progressFill.style.width = `${STAGE_PROGRESS[data.status] || 50}%`;

    if (data.word_count) {
      const parts = [`${data.word_count} слов`, `${data.image_count || 0} изображений`];
      if (data.banner_count) parts.push(`${data.banner_count} баннер(ов)`);
      if (data.ad_count) parts.push(`${data.ad_count} реклам(а)`);
      if (data.doc_converted) parts.push(".doc → .docx");
      statusDetail.textContent = parts.join(" · ");
    }

    if (data.status === "done") {
      hide(statusSection);
      documentHeadings = data.headings || [];
      renderOutline(data.document_outline || []);
      renderReference(data.reference_analysis);
      if (data.ad_slot_report?.total_slots) {
        const r = data.ad_slot_report;
        statusDetail.textContent = (statusDetail.textContent ? statusDetail.textContent + " · " : "") +
          `рекламная сетка: ${r.used_slots}/${r.total_slots} слотов занято`;
      }
      renderPlacements(data.image_placements || [], documentHeadings);
      renderResults(jobId, data);
      return;
    }
    if (data.status === "error") {
      hide(statusSection);
      submitBtn.disabled = false;
      showError(data.message || "Не удалось обработать документ.");
      return;
    }
    setTimeout(() => pollJob(jobId), 1200);
  } catch (_) {
    setTimeout(() => pollJob(jobId), 2000);
  }
}

function renderOutline(outline) {
  if (!outline?.length) {
    hide(outlineSection);
    return;
  }
  outlineList.innerHTML = outline.map(item => `
    <li class="lvl-${Math.min(item.level || 1, 3)}">
      ${escapeHtml(item.title)}
      <span class="hint-small">~${item.word_estimate || 0} слов</span>
    </li>`).join("");
  show(outlineSection);
}

function renderReference(ref) {
  if (!ref || !ref.pages_analyzed) {
    hide(referenceSection);
    return;
  }
  let summary = ref.summary || "";
  const slots = ref.ad_slot_count || (ref.ad_slots || []).length;
  if (slots > 0) {
    summary += ` Рекламных слотов из PDF: ${slots}.`;
  }
  referenceSummary.textContent = summary;
  const parts = [];
  if (ref.page_format_id && ref.page_format_id !== "a4" && ref.page_size_mm) {
    parts.push(`Формат ${ref.page_size_mm.width}×${ref.page_size_mm.height} мм`);
  }
  const name = ref.preferred_template_name || ref.preferred_template_id || "";
  if (name) parts.push(`шаблон «${name}»`);
  referencePreferred.textContent = parts.length ? parts.join(" · ") : "";
  if (ref.ad_slots?.length && window.AdGridEditor) {
    const importBtn = document.createElement("button");
    importBtn.type = "button";
    importBtn.className = "btn btn-secondary";
    importBtn.style.marginTop = "10px";
    importBtn.textContent = `Импортировать ${ref.ad_slots.length} слотов из PDF в редактор сетки`;
    importBtn.onclick = () => {
      window.AdGridEditor.setSlots(ref.ad_slots);
      document.querySelector('.tab[data-tab="adgrid"]')?.click();
    };
    referencePreferred.appendChild(document.createElement("br"));
    referencePreferred.appendChild(importBtn);
  }
  show(referenceSection);
}

function headingOptions(current, headings) {
  const opts = ['<option value="">— не привязано —</option>'];
  for (const h of headings) {
    const sel = h === current ? " selected" : "";
    opts.push(`<option value="${escapeHtml(h)}"${sel}>${escapeHtml(h)}</option>`);
  }
  if (current && !headings.includes(current)) {
    opts.push(`<option value="${escapeHtml(current)}" selected>${escapeHtml(current)}</option>`);
  }
  return opts.join("");
}

function roleOptions(current) {
  const roles = [
    ["photo", "фото"],
    ["ad", "реклама"],
    ["banner", "баннер"],
    ["logo", "лого"],
  ];
  return roles.map(([v, l]) =>
    `<option value="${v}"${current === v ? " selected" : ""}>${l}</option>`
  ).join("");
}

function renderPlacements(placements, headings = []) {
  editablePlacements = placements.map(p => ({ ...p }));
  if (!editablePlacements.length) {
    hide(placementsSection);
    hide(downloadMappingBtn);
    hide(rebuildBtn);
    return;
  }
  placementsList.innerHTML = editablePlacements.map((p, idx) => {
    const badge = p.image_role === "ad"
      ? `<span class="role-badge ad">реклама</span>`
      : p.image_role === "banner"
      ? '<span class="role-badge banner">баннер</span>'
      : (p.image_role === "logo" ? '<span class="role-badge logo">лого</span>' : "");
    return `
    <li data-idx="${idx}">
      <strong>${escapeHtml(p.filename)}</strong> ${badge}
      <div class="placement-edit">
        <select class="pl-heading" data-idx="${idx}" title="Раздел">${headingOptions(p.anchor_heading, headings)}</select>
        <select class="pl-role" data-idx="${idx}" title="Тип">${roleOptions(p.image_role || "photo")}</select>
      </div>
      <span class="reason">${escapeHtml(p.reason)}</span>
    </li>`;
  }).join("");

  placementsList.querySelectorAll(".pl-heading").forEach(sel => {
    sel.addEventListener("change", () => {
      const i = parseInt(sel.dataset.idx, 10);
      editablePlacements[i].anchor_heading = sel.value;
    });
  });
  placementsList.querySelectorAll(".pl-role").forEach(sel => {
    sel.addEventListener("change", () => {
      const i = parseInt(sel.dataset.idx, 10);
      editablePlacements[i].image_role = sel.value;
    });
  });

  show(placementsSection);
  if (currentJobId) {
    downloadMappingBtn.hidden = false;
    rebuildBtn.hidden = false;
    downloadMappingBtn.onclick = () => {
      window.location.href = `/api/jobs/${currentJobId}/mapping.json`;
    };
    rebuildBtn.onclick = () => triggerRebuild();
  }
}

function buildMappingPayload() {
  const gridSlots = window.AdGridEditor ? window.AdGridEditor.getSlots() : [];
  const fileToSlot = {};
  gridSlots.forEach((s, i) => { if (s.filename) fileToSlot[s.filename] = i; });

  return editablePlacements.map(p => {
    const m = {
      filename: p.filename,
      anchor_heading: p.anchor_heading || "",
      role: p.image_role || "photo",
    };
    if (p.caption) m.caption = p.caption;
    if (p.width_mm) m.width_mm = p.width_mm;
    if (p.height_mm) m.height_mm = p.height_mm;
    const si = fileToSlot[p.filename];
    if (si !== undefined) m.slot_index = si;
    else if (p.slot_index != null) m.slot_index = p.slot_index;
    return m;
  });
}

async function triggerRebuild() {
  if (!currentJobId) return;
  rebuildBtn.disabled = true;
  hide(resultsSection);
  show(statusSection);
  statusText.textContent = STAGE_LABELS.rebuilding;
  progressFill.style.width = "40%";

  const body = {
    mapping: buildMappingPayload(),
    ad_grid: window.AdGridEditor ? window.AdGridEditor.getJson() : null,
  };
  const overridesJson = window.SpreadEditor?.getOverridesJson?.();
  if (overridesJson) body.layout_overrides = overridesJson;

  try {
    const resp = await fetch(`/api/jobs/${currentJobId}/rebuild`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error("Не удалось запустить пересборку");
    pollJob(currentJobId);
  } catch (e) {
    rebuildBtn.disabled = false;
    hide(statusSection);
    showError(e.message);
  }
}

function renderResults(jobId, data) {
  resultsGrid.innerHTML = "";
  selectedTemplateId = data.selected_template || null;
  lastJobResults = data.results || [];

  if (lastJobResults.length >= 2) {
    compareBtn.hidden = false;
    compareBtn.onclick = () => openCompareModal(jobId);
  } else {
    hide(compareBtn);
  }

  if (data.word_count) {
    const meta = [`${data.word_count} слов`, `${data.image_count || 0} иллюстраций`];
    if (data.article_count > 1) {
      meta.push(`${data.article_count} материалов в выпуске`);
    }
    if (data.banner_count) meta.push(`${data.banner_count} баннеров`);
    if (data.ad_count) meta.push(`${data.ad_count} рекламных модулей`);
    if (data.doc_converted) meta.push("конвертирован из .doc");
    resultsMeta.textContent = meta.join(" · ") +
      (data.keywords?.length ? ` · темы: ${data.keywords.slice(0, 4).join(", ")}` : "");
  }
  if (data.article_titles?.length > 1) {
    const issueEl = document.getElementById("issueArticles");
    if (issueEl) {
      issueEl.hidden = false;
      issueEl.innerHTML = "<strong>Материалы выпуска:</strong> " +
        data.article_titles.map(t => `<span class="chip">${escapeHtml(t)}</span>`).join(" ");
    }
  }

  for (const r of data.results) {
    const card = document.createElement("div");
    card.className = "result-card" + (r.template_id === selectedTemplateId ? " selected" : "");
    if (r.recommended) card.classList.add("recommended");
    card.dataset.templateId = r.template_id;

    const carousel = document.createElement("div");
    carousel.className = "preview-carousel";
    const previews = r.preview_files || [];
    let currentIdx = 0;

    if (previews.length) {
      const img = document.createElement("img");
      img.src = `/api/jobs/${jobId}/preview/${r.template_id}/${previews[0]}`;
      img.alt = r.name;
      img.style.cursor = "zoom-in";
      img.addEventListener("click", () => {
        openPreviewViewer(jobId, r.template_id, r.name, previews, r.page_count);
      });
      carousel.appendChild(img);

      if (previews.length > 1) {
        const prev = document.createElement("button");
        prev.className = "carousel-btn prev";
        prev.textContent = "‹";
        prev.addEventListener("click", e => {
          e.stopPropagation();
          currentIdx = (currentIdx - 1 + previews.length) % previews.length;
          img.src = `/api/jobs/${jobId}/preview/${r.template_id}/${previews[currentIdx]}`;
          updateDots();
        });
        const next = document.createElement("button");
        next.className = "carousel-btn next";
        next.textContent = "›";
        next.addEventListener("click", e => {
          e.stopPropagation();
          currentIdx = (currentIdx + 1) % previews.length;
          img.src = `/api/jobs/${jobId}/preview/${r.template_id}/${previews[currentIdx]}`;
          updateDots();
        });
        const dots = document.createElement("div");
        dots.className = "carousel-dots";
        previews.forEach((_, i) => {
          const dot = document.createElement("span");
          if (i === 0) dot.classList.add("active");
          dots.appendChild(dot);
        });
        function updateDots() {
          dots.querySelectorAll("span").forEach((d, i) => d.classList.toggle("active", i === currentIdx));
        }
        carousel.append(prev, next, dots);
      }

      const openAll = document.createElement("button");
      openAll.type = "button";
      openAll.className = "btn-preview-all";
      openAll.textContent = previews.length < r.page_count
        ? `Все страницы (${previews.length} из ${r.page_count} превью)`
        : `Все страницы (${previews.length})`;
      openAll.addEventListener("click", e => {
        e.stopPropagation();
        openPreviewViewer(jobId, r.template_id, r.name, previews, r.page_count);
      });
      carousel.appendChild(openAll);
    }
    card.appendChild(carousel);

    const body = document.createElement("div");
    body.className = "card-body";
    const fontsInfo = r.fonts_used
      ? `<span>Шрифты: ${escapeHtml(r.fonts_used.body)} / ${escapeHtml(r.fonts_used.heading)}</span>` : "";
    body.innerHTML = `
      ${r.recommended ? '<span class="rec-badge">★ по PDF-референсу</span>' : ""}
      <h3>${escapeHtml(r.name)}</h3>
      <p class="desc">${escapeHtml(r.description)}</p>
      <div class="card-meta">
        <span>Страниц: ${r.page_count}</span>
        <span>Превью: ${(r.preview_files || []).length} стр.</span>
        ${r.reference_score != null ? `<span>Сходство с референсом: ${r.reference_score}%</span>` : ""}
        ${fontsInfo}
      </div>
      <div class="card-actions">
        <button class="btn btn-select" data-id="${r.template_id}">
          ${r.template_id === selectedTemplateId ? "✓ Выбран" : "Выбрать"}
        </button>
        <a class="btn btn-download" href="/api/jobs/${jobId}/download/${r.template_id}">ZIP (INX)</a>
        ${r.pdf_file ? `<a class="btn btn-download btn-pdf" href="/api/jobs/${jobId}/pdf/${r.template_id}">PDF печать</a>` : ""}
      </div>
      ${r.pdf_vector ? `<p class="hint-small">PDF: векторный${r.pdf_cmyk ? " · CMYK" : ""}</p>` : (r.pdf_dpi ? `<p class="hint-small">PDF: растровый ${r.pdf_dpi} DPI</p>` : "")}
      ${r.quality ? `<p class="quality-badge grade-${r.quality.grade.replace('+','plus')}">Качество: ${r.quality.score} (${r.quality.grade})</p>` : ""}
      ${r.layout_available ? `<button type="button" class="btn-spread-edit" data-spread="${r.template_id}">✎ Редактор полосы</button>` : ""}
      ${r.print_checklist?.ready_for_print
        ? `<p class="checklist-ok">✓ Авто-чеклист печати пройден (см. PRINT_CHECKLIST.txt в ZIP)</p>`
        : (r.print_checklist ? `<p class="checklist-warn">⚠ Чеклист: ${r.print_checklist.counts?.fail || 0} ошибок, ${r.print_checklist.counts?.manual || 0} шагов в InDesign</p>` : "")}
      ${r.inx_error ? `<div class="warn">⚠ ${escapeHtml(r.inx_error)}</div>` : ""}
      ${r.inx_smoke && !r.inx_smoke.passed ? `<div class="warn">⚠ Smoke CS3: ${escapeHtml((r.inx_smoke.errors || []).join("; "))}</div>` : ""}
      ${r.inx_smoke?.passed ? `<div class="hint-small">✓ INX smoke CS3: ${r.inx_smoke.stats?.pages || "?"} стр., ${r.inx_smoke.stats?.text_frames || "?"} фреймов</div>` : ""}
      ${(r.inx_warnings || []).slice(0, 3).map(w => `<div class="warn">⚠ ${escapeHtml(w)}</div>`).join("")}
      ${(r.inx_warnings || []).length > 3 ? `<div class="hint-small">…ещё ${r.inx_warnings.length - 3} предупреждений в preflight</div>` : ""}
    `;
    card.appendChild(body);

    body.querySelector(".btn-select").addEventListener("click", async e => {
      e.preventDefault();
      await selectVariant(jobId, r.template_id);
    });

    const spreadBtn = body.querySelector("[data-spread]");
    if (spreadBtn && window.SpreadEditor) {
      spreadBtn.addEventListener("click", () => {
        window.SpreadEditor.open(jobId, r.template_id, r.name);
      });
    }

    resultsGrid.appendChild(card);
  }
  show(resultsSection);
  submitBtn.disabled = false;
  if (rebuildBtn) rebuildBtn.disabled = false;
}

async function selectVariant(jobId, templateId) {
  try {
    await fetch(`/api/jobs/${jobId}/select/${templateId}`, { method: "POST" });
    selectedTemplateId = templateId;
    document.querySelectorAll(".result-card").forEach(card => {
      const isSelected = card.dataset.templateId === templateId;
      card.classList.toggle("selected", isSelected);
      const btn = card.querySelector(".btn-select");
      if (btn) btn.textContent = isSelected ? "✓ Выбран" : "Выбрать";
    });
  } catch (_) { /* ignore */ }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function openCompareModal(jobId) {
  const leftSel = document.getElementById("compareLeft");
  const rightSel = document.getElementById("compareRight");
  const opts = lastJobResults.map(r =>
    `<option value="${r.template_id}">${escapeHtml(r.name)}</option>`).join("");
  leftSel.innerHTML = opts;
  rightSel.innerHTML = opts;
  if (lastJobResults.length > 1) rightSel.selectedIndex = 1;

  function updateCompare() {
    const l = lastJobResults.find(r => r.template_id === leftSel.value);
    const r = lastJobResults.find(r => r.template_id === rightSel.value);
    const li = document.getElementById("compareImgLeft");
    const ri = document.getElementById("compareImgRight");
    if (l?.preview_files?.[0]) {
      li.src = `/api/jobs/${jobId}/preview/${l.template_id}/${l.preview_files[0]}`;
      li.alt = l.name;
    }
    if (r?.preview_files?.[0]) {
      ri.src = `/api/jobs/${jobId}/preview/${r.template_id}/${r.preview_files[0]}`;
      ri.alt = r.name;
    }
  }
  leftSel.onchange = rightSel.onchange = updateCompare;
  updateCompare();
  compareModal.hidden = false;
}

document.getElementById("compareClose")?.addEventListener("click", () => {
  compareModal.hidden = true;
});
compareModal?.querySelector(".modal-backdrop")?.addEventListener("click", () => {
  compareModal.hidden = true;
});

window.buildMappingPayload = buildMappingPayload;
window.pollJob = pollJob;
