/* LayoutGenius — простые кнопки действий для дизайнера */

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

(async function initDesignerKit() {
  const genBtn = document.getElementById("kitGenerateBtn");
  const actionGrid = document.getElementById("kitActionGrid");
  const panel = document.getElementById("kitActionPanel");
  if (!genBtn || !actionGrid) return;

  let catalog = { packs: [] };
  let selectedPackId = null;

  const CAPTION_PLACEHOLDERS = {
    pack_decor: "Например: В эти дни",
    pack_backdrop: "Текст на подложке (цитата, врезка)",
    pack_masthead: "Сибирская околица  или  № 28 / 22 июля 2026",
    pack_weather: "Ясно, +22 °C · ветер слабый",
    pack_shorts: "Короткие новости",
    pack_teasers: "Школа, Ярмарка, Погода",
  };

  function packById(id) {
    return catalog.packs?.find(p => p.id === id);
  }

  function selectAction(id) {
    selectedPackId = id;
    const pack = packById(id);
    if (!pack) return;

    actionGrid.querySelectorAll(".kit-action-btn").forEach(btn => {
      btn.classList.toggle("is-selected", btn.dataset.pack === id);
    });

    panel.hidden = false;
    document.getElementById("kitSelectedTitle").textContent = pack.action;
    document.getElementById("kitSelectedNeeds").textContent = "Что нужно: " + pack.needs;

    const capWrap = document.getElementById("kitCaptionWrap");
    const capInput = document.getElementById("kitCaption");
    const photoNote = document.getElementById("kitPhotoNote");

    if (pack.wants_caption) {
      capWrap.hidden = false;
      document.getElementById("kitCaptionLabel").textContent =
        pack.id === "pack_teasers" ? "Темы (через запятую)" :
        pack.id === "pack_weather" ? "Текст прогноза" :
        pack.id === "pack_masthead" ? "Название или номер/дата" :
        "Подпись (необязательно)";
      capInput.placeholder = CAPTION_PLACEHOLDERS[pack.id] || "По желанию";
    } else {
      capWrap.hidden = true;
      capInput.value = "";
    }

    photoNote.hidden = !pack.wants_photo_in_cs3;

    document.getElementById("kitResults").hidden = true;
    document.getElementById("kitError").hidden = true;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function buildTexts(pack) {
    const cap = (document.getElementById("kitCaption")?.value || "").trim();
    if (!cap) return null;
    const texts = {};
    if (pack.id === "pack_decor" || pack.id === "pack_backdrop") {
      texts.wave_caption = cap;
    } else if (pack.id === "pack_masthead") {
      if (/№|\d{1,2}[./]/.test(cap)) texts.masthead_issue = cap;
      else texts.masthead_logo = cap;
    } else if (pack.id === "pack_weather") {
      texts.weather_badge = "ПРОГНОЗ ПОГОДЫ";
      texts.weather_body = cap;
    } else if (pack.id === "pack_shorts") {
      texts.news_header = cap;
    } else if (pack.id === "pack_teasers") {
      const parts = cap.split(/[,;]/).map(s => s.trim()).filter(Boolean);
      parts.slice(0, 3).forEach((t, i) => {
        texts[`cover_teaser_${i + 1}`] = `• ${t}  Стр. ${i + 3}`;
      });
    } else {
      texts.ad_body_wide = cap;
    }
    return texts;
  }

  try {
    const resp = await fetch("/api/kit/catalog");
    catalog = await resp.json();
    const packs = (catalog.packs || []).filter(p => p.primary !== false);

    actionGrid.innerHTML = packs.map(p => `
      <button type="button" class="kit-action-btn" data-pack="${escapeHtml(p.id)}">
        <span class="kit-action-icon" aria-hidden="true">${escapeHtml(p.icon || "◆")}</span>
        <span class="kit-action-label">${escapeHtml(p.action)}</span>
        <span class="kit-action-name">${escapeHtml(p.name)}</span>
        <span class="kit-action-needs">📎 ${escapeHtml(p.needs_hint)}</span>
      </button>`).join("");

    actionGrid.addEventListener("click", (e) => {
      const btn = e.target.closest(".kit-action-btn");
      if (btn) selectAction(btn.dataset.pack);
    });

    const tbody = document.getElementById("kitNeedsTableBody");
    if (tbody) {
      tbody.innerHTML = (catalog.packs || []).map(p => `
        <tr>
          <td><strong>${escapeHtml(p.action)}</strong></td>
          <td>${escapeHtml(p.needs)}</td>
        </tr>`).join("");
    }
  } catch (err) {
    console.warn(err);
  }

  genBtn.addEventListener("click", async () => {
    const pack = packById(selectedPackId);
    if (!pack) {
      document.getElementById("kitError").hidden = false;
      document.getElementById("kitError").textContent = "Сначала выберите функцию кнопкой выше.";
      return;
    }

    const statusEl = document.getElementById("kitStatus");
    const statusTextEl = document.getElementById("kitStatusText");
    const progressEl = document.getElementById("kitProgressFill");
    const errEl = document.getElementById("kitError");
    const resultsEl = document.getElementById("kitResults");
    errEl.hidden = true;
    resultsEl.hidden = true;
    statusEl.hidden = false;
    statusTextEl.textContent = pack.action + "…";
    progressEl.style.width = "20%";
    genBtn.disabled = true;

    const body = {
      mode: pack.ad_format_id ? "ad" : "catalog",
      use_ai: false,
      pack_id: pack.id,
      include: pack.elements || [],
      ad_format_id: pack.ad_format_id || null,
      texts: buildTexts(pack),
      brief: document.getElementById("kitCaption")?.value || "",
    };

    try {
      const resp = await fetch("/api/kit/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail ? JSON.stringify(err.detail) : `HTTP ${resp.status}`);
      }
      const { job_id } = await resp.json();
      progressEl.style.width = "40%";

      for (let i = 0; i < 100; i++) {
        await new Promise(r => setTimeout(r, 350));
        const st = await fetch(`/api/jobs/${job_id}`).then(r => r.json());
        statusTextEl.textContent = st.status === "done" ? "Готово" : `Статус: ${st.status}`;
        progressEl.style.width = `${Math.min(92, 40 + i)}%`;
        if (st.status === "error") throw new Error(st.error || "Ошибка");
        if (st.status === "done") {
          progressEl.style.width = "100%";
          document.getElementById("kitPreviewImg").src =
            st.preview_url || `/api/jobs/${job_id}/preview/kit/catalog.png`;
          document.getElementById("kitDownloadLink").href =
            st.download_url || `/api/jobs/${job_id}/download/okolica_kit`;
          document.getElementById("kitChecklistLink").href =
            st.checklist_url || `/api/jobs/${job_id}/kit/checklist`;
          const g = document.getElementById("kitGuaranteeLink");
          if (g) g.href = st.guarantee_url || `/api/jobs/${job_id}/kit/guarantee`;
          resultsEl.hidden = false;
          statusEl.hidden = true;
          break;
        }
      }
    } catch (e) {
      errEl.hidden = false;
      errEl.textContent = e.message || String(e);
      statusEl.hidden = true;
    } finally {
      genBtn.disabled = false;
    }
  });
})();
