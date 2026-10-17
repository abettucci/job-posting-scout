/* global JobFilterRules */
(function scoutLensContentScript() {
  "use strict";

  const IS_SEARCH_PAGE = /\/jobs\/search|\/jobs\/collections/.test(location.pathname);
  const CARD_SELECTOR = [
    "li.jobs-search-results__list-item",
    ".scaffold-layout__list-item",
    "li[data-occludable-job-id]",
    ".job-card-container",
  ].join(",");
  const state = {
    filters: JobFilterRules.defaultFilters(),
    paused: false,
    analyses: new Map(),
    scannedUrls: new Set(),
    panel: null,
    retryTimer: null,
    status: "Listo para analizar la búsqueda actual.",
  };

  function textOf(element) {
    return String(element?.innerText || element?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function textWithLines(element) {
    return String(element?.innerText || element?.textContent || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .replace(/\r/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;",
    }[char]));
  }

  function queryFirst(root, selectors) {
    for (const selector of selectors) {
      const found = root.querySelector(selector);
      if (found) return found;
    }
    return null;
  }

  function currentJobDetails() {
    const descriptionNode = queryFirst(document, [
      ".jobs-description__content",
      ".jobs-box__html-content",
      ".jobs-description-content__text",
      ".jobs-description",
      "[class*='jobs-description']",
    ]);
    const titleNode = queryFirst(document, [
      ".job-details-jobs-unified-top-card__job-title h1",
      ".jobs-unified-top-card__job-title",
      "h1",
    ]);
    const companyNode = queryFirst(document, [
      ".job-details-jobs-unified-top-card__company-name a",
      ".jobs-unified-top-card__company-name a",
      "a[href*='/company/']",
    ]);
    return {
      title: textOf(titleNode),
      company: textOf(companyNode),
      companyUrl: companyNode?.href || "",
      description: textWithLines(descriptionNode),
      pageText: textOf(document.body).slice(0, 80_000),
    };
  }

  function currentCompanyDetails() {
    return { pageText: textOf(document.body).slice(0, 80_000) };
  }

  function findJobLink(card) {
    const links = [...card.querySelectorAll("a[href*='/jobs/view/']")];
    return links.find((link) => link.href) || null;
  }

  function canonicalJobUrl(value) {
    try {
      const parsed = new URL(value);
      parsed.search = "";
      parsed.hash = "";
      return parsed.href.replace(/\/$/, "");
    } catch {
      return "";
    }
  }

  function candidateFromCard(card) {
    const jobLink = findJobLink(card);
    if (!jobLink) return null;
    const titleNode = queryFirst(card, [
      ".job-card-list__title",
      ".job-card-container__link",
      "strong",
      "a[href*='/jobs/view/']",
    ]);
    const companyNode = queryFirst(card, [
      ".job-card-container__company-name",
      ".artdeco-entity-lockup__subtitle",
      "a[href*='/company/']",
    ]);
    const companyLink = card.querySelector("a[href*='/company/']");
    return {
      jobUrl: canonicalJobUrl(jobLink.href),
      title: textOf(titleNode),
      company: textOf(companyNode),
      companyUrl: companyLink?.href || "",
    };
  }

  function cardForUrl(jobUrl) {
    const normalized = canonicalJobUrl(jobUrl);
    return [...document.querySelectorAll(CARD_SELECTOR)].find((card) => {
      const candidate = candidateFromCard(card);
      return candidate?.jobUrl === normalized;
    });
  }

  function labelForSize(size) {
    return { startup: "Startup", midsize: "Mediana", enterprise: "Enterprise", unknown: "Desconocido" }[size] || "Desconocido";
  }

  function labelForSeniority(level) {
    return {
      internship: "Pasantía", entry: "Junior", associate: "Associate", mid: "Semi senior",
      senior: "Senior", staff: "Staff/Lead", director: "Director", executive: "Executive",
    }[level] || "Desconocido";
  }

  function decorateCard(card, analysis) {
    const evaluation = analysis.status === "ready" ? JobFilterRules.evaluate(analysis, state.filters) : {
      visible: true, state: "unknown", reasons: [], unknown: [analysis.status === "rate_limited" ? "límite de análisis" : "datos"],
    };
    card.classList.toggle("js-lens-hidden", !evaluation.visible);
    card.dataset.jsLensState = evaluation.state;
    let badge = card.querySelector(".js-lens-card-badge");
    if (!badge) {
      badge = document.createElement("div");
      badge.className = "js-lens-card-badge";
      card.prepend(badge);
    }
    if (!evaluation.visible) {
      badge.textContent = `Scout Lens · oculto: ${evaluation.reasons.join(", ")}`;
      return;
    }
    const details = [
      analysis.minYears !== null && analysis.minYears !== undefined ? `${analysis.minYears}+ años` : "años ?",
      labelForSeniority(analysis.seniority),
      labelForSize(analysis.companySize),
    ];
    if (analysis.requiredTechnologies?.length) {
      details.push(analysis.requiredTechnologies.slice(0, 2).join(", "));
    }
    if (evaluation.state === "unknown") details.push("datos incompletos");
    badge.textContent = `Scout Lens · ${details.join(" · ")}`;
  }

  function applyAllAnalyses() {
    for (const analysis of state.analyses.values()) {
      const card = cardForUrl(analysis.jobUrl);
      if (card) decorateCard(card, analysis);
    }
    renderPanel();
  }

  function removeChip(listName, value) {
    state.filters[listName] = state.filters[listName].filter((item) => item !== value);
    saveFilters();
  }

  function chipEditor(label, listName, placeholder) {
    const values = state.filters[listName];
    return `
      <div class="js-lens-field">
        <span class="js-lens-label">${label}</span>
        <div class="js-lens-chips" data-chip-list="${listName}">
          ${values.map((value) => `<button type="button" class="js-lens-chip" data-remove="${listName}" data-value="${encodeURIComponent(value)}">${escapeHtml(value)}<b>×</b></button>`).join("")}
        </div>
        <input class="js-lens-input" data-chip-input="${listName}" placeholder="${placeholder}" />
      </div>`;
  }

  function renderPanel() {
    if (!state.panel) return;
    const native = JobFilterRules.extractNativeFilters(location.href);
    const analysed = [...state.analyses.values()].filter((item) => item.status === "ready");
    const hidden = analysed.filter((item) => !JobFilterRules.evaluate(item, state.filters).visible).length;
    state.panel.innerHTML = `
      <section class="js-lens-shell" aria-label="Scout Lens filters">
        <header class="js-lens-header">
          <div><p class="js-lens-kicker">LOCAL JOB LENS</p><h2>Scout Lens</h2></div>
          <button type="button" class="js-lens-icon-button" data-action="collapse" aria-label="Minimizar panel">−</button>
        </header>
        <p class="js-lens-status ${state.paused ? "is-paused" : ""}">${state.paused ? "⏸ " : "◌ "}${state.status}</p>
        <div class="js-lens-native">
          <span>LinkedIn activo</span>
          <small>${native.keywords ? `“${escapeHtml(native.keywords)}”` : "sin keywords"}${native.location ? ` · ${escapeHtml(native.location)}` : ""}</small>
        </div>
        <div class="js-lens-fields">
          <label class="js-lens-field"><span class="js-lens-label">Máximo de años pedidos</span>
            <input class="js-lens-input" data-filter="maxYears" type="number" min="1" max="40" value="${state.filters.maxYears || ""}" placeholder="Sin límite" />
          </label>
          <div class="js-lens-field"><span class="js-lens-label">Seniorities permitidos</span>
            <div class="js-lens-toggle-grid">
              ${JobFilterRules.SENIORITY_LEVELS.map((level) => `<button type="button" class="js-lens-toggle ${state.filters.allowedSeniorities.includes(level) ? "is-selected" : ""}" data-seniority="${level}">${labelForSeniority(level)}</button>`).join("")}
            </div>
          </div>
          ${chipEditor("Tecnologías a incluir", "includeTechnologies", "Ej. Python")}
          ${chipEditor("Tecnologías a excluir", "excludeTechnologies", "Ej. SAP")}
          <div class="js-lens-field"><span class="js-lens-label">Tamaño de empresa</span>
            <div class="js-lens-toggle-grid js-lens-size-grid">
              ${["startup", "midsize", "enterprise"].map((size) => `<button type="button" class="js-lens-toggle ${state.filters.companySizes.includes(size) ? "is-selected" : ""}" data-company-size="${size}">${labelForSize(size)}</button>`).join("")}
            </div>
          </div>
        </div>
        <footer class="js-lens-footer">
          <strong>${analysed.length} analizadas · ${hidden} ocultas</strong>
          <div><button type="button" class="js-lens-text-button" data-action="scan">Analizar ahora</button><button type="button" class="js-lens-text-button" data-action="pause">${state.paused ? "Reanudar" : "Pausar"}</button></div>
        </footer>
      </section>`;
    bindPanelEvents();
  }

  async function saveFilters() {
    await chrome.runtime.sendMessage({ type: "SCOUT_LENS_SET_FILTERS", filters: state.filters });
    applyAllAnalyses();
  }

  function addChip(listName, rawValue) {
    const value = JobFilterRules.normalizeTechnology(rawValue);
    if (!value || state.filters[listName].some((item) => item.toLowerCase() === value.toLowerCase())) return;
    state.filters[listName] = [...state.filters[listName], value];
    saveFilters();
  }

  function bindPanelEvents() {
    state.panel.querySelector("[data-filter='maxYears']")?.addEventListener("change", (event) => {
      const value = Number(event.target.value);
      state.filters.maxYears = Number.isInteger(value) && value > 0 ? value : null;
      saveFilters();
    });
    state.panel.querySelectorAll("[data-seniority]").forEach((button) => button.addEventListener("click", () => {
      const level = button.dataset.seniority;
      state.filters.allowedSeniorities = state.filters.allowedSeniorities.includes(level)
        ? state.filters.allowedSeniorities.filter((item) => item !== level)
        : [...state.filters.allowedSeniorities, level];
      saveFilters();
    }));
    state.panel.querySelectorAll("[data-company-size]").forEach((button) => button.addEventListener("click", () => {
      const size = button.dataset.companySize;
      state.filters.companySizes = state.filters.companySizes.includes(size)
        ? state.filters.companySizes.filter((item) => item !== size)
        : [...state.filters.companySizes, size];
      saveFilters();
    }));
    state.panel.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => {
      removeChip(button.dataset.remove, decodeURIComponent(button.dataset.value));
    }));
    state.panel.querySelectorAll("[data-chip-input]").forEach((input) => input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      addChip(input.dataset.chipInput, event.target.value);
    }));
    state.panel.querySelector("[data-action='scan']")?.addEventListener("click", scanVisibleCards);
    state.panel.querySelector("[data-action='pause']")?.addEventListener("click", async () => {
      await chrome.runtime.sendMessage({ type: "SCOUT_LENS_SET_PAUSED", paused: !state.paused });
    });
    state.panel.querySelector("[data-action='collapse']")?.addEventListener("click", () => {
      state.panel.classList.toggle("is-collapsed");
    });
  }

  function scanVisibleCards() {
    if (state.paused) return;
    const candidates = [...document.querySelectorAll(CARD_SELECTOR)]
      .map(candidateFromCard)
      .filter(Boolean)
      .filter((candidate) => !state.scannedUrls.has(candidate.jobUrl));
    candidates.forEach((candidate) => state.scannedUrls.add(candidate.jobUrl));
    if (!candidates.length) return;
    state.status = `Analizando ${candidates.length} ofertas cargadas…`;
    renderPanel();
    chrome.runtime.sendMessage({ type: "SCOUT_LENS_SCAN", candidates });
  }

  function scheduleRetry() {
    if (state.paused || state.retryTimer) return;
    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      scanVisibleCards();
    }, 60_000);
  }

  function mountPanel() {
    if (state.panel || !document.body) return;
    state.panel = document.createElement("aside");
    state.panel.id = "js-lens-root";
    document.body.append(state.panel);
    renderPanel();
  }

  function observeResults() {
    let debounce;
    const schedule = () => {
      clearTimeout(debounce);
      debounce = setTimeout(scanVisibleCards, 700);
    };
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    schedule();
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "SCOUT_LENS_EXTRACT_PAGE") {
      const extractor = message.pageType === "company" ? currentCompanyDetails : currentJobDetails;
      let responded = false;
      const respond = () => {
        if (responded) return;
        responded = true;
        sendResponse(extractor());
      };
      const hasContent = () => message.pageType === "company" || Boolean(extractor().description);
      if (hasContent()) {
        respond();
        return;
      }
      const deadline = Date.now() + 5_000;
      const observer = new MutationObserver(() => {
        if (hasContent() || Date.now() >= deadline) {
          observer.disconnect();
          respond();
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => {
        observer.disconnect();
        respond();
      }, 5_100);
      return true;
    }
    if (!IS_SEARCH_PAGE) return;
    if (message?.type === "SCOUT_LENS_ANALYSIS" && message.analysis?.jobUrl) {
      state.analyses.set(message.analysis.jobUrl, message.analysis);
      if (message.analysis.status === "rate_limited") {
        state.scannedUrls.delete(message.analysis.jobUrl);
        scheduleRetry();
      }
      state.status = message.analysis.status === "rate_limited"
        ? "Límite temporal alcanzado. Las ofertas restantes quedan visibles."
        : "Filtro activo sobre ofertas cargadas.";
      applyAllAnalyses();
    }
    if (message?.type === "SCOUT_LENS_FILTERS") {
      state.filters = { ...JobFilterRules.defaultFilters(), ...(message.filters || {}) };
      applyAllAnalyses();
    }
    if (message?.type === "SCOUT_LENS_PAUSED") {
      state.paused = Boolean(message.reason);
      state.status = message.reason || "Escaneo reanudado.";
      renderPanel();
    }
    if (message?.type === "SCOUT_LENS_CACHE_CLEARED") {
      state.analyses.clear();
      state.scannedUrls.clear();
      state.status = "Caché limpiada. Se analizarán nuevamente las ofertas cargadas.";
      renderPanel();
      scanVisibleCards();
    }
  });

  if (IS_SEARCH_PAGE) {
    chrome.runtime.sendMessage({ type: "SCOUT_LENS_GET_STATE" }).then((saved) => {
      state.filters = saved?.filters || JobFilterRules.defaultFilters();
      state.paused = Boolean(saved?.paused);
      if (state.paused) state.status = "Escaneo pausado.";
      mountPanel();
      observeResults();
    });
  }
})();
