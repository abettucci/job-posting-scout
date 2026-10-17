import "./rules.js";

const JobFilterRules = globalThis.JobFilterRules;

const CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const WINDOW_MS = 10 * 60 * 1000;
const MAX_JOB_LOOKUPS = 12;
const MAX_COMPANY_LOOKUPS = 8;
const DEFAULT_STATE = {
  filters: JobFilterRules.defaultFilters(),
  paused: false,
  cache: {},
  jobLookups: [],
  companyLookups: [],
};

let queue = [];
let queueRunning = false;
let activeLookup = null;

function now() {
  return Date.now();
}

async function getState() {
  const stored = await chrome.storage.local.get(DEFAULT_STATE);
  return {
    ...DEFAULT_STATE,
    ...stored,
    filters: { ...JobFilterRules.defaultFilters(), ...(stored.filters || {}) },
    cache: stored.cache || {},
  };
}

async function updateState(patch) {
  const current = await getState();
  const next = { ...current, ...patch };
  await chrome.storage.local.set(next);
  return next;
}

function pruneTimestamps(timestamps) {
  const threshold = now() - WINDOW_MS;
  return (timestamps || []).filter((timestamp) => Number(timestamp) > threshold);
}

async function reserveLookup(kind) {
  const state = await getState();
  const key = kind === "job" ? "jobLookups" : "companyLookups";
  const cap = kind === "job" ? MAX_JOB_LOOKUPS : MAX_COMPANY_LOOKUPS;
  const timestamps = pruneTimestamps(state[key]);
  if (timestamps.length >= cap) {
    await chrome.storage.local.set({ [key]: timestamps });
    return false;
  }
  timestamps.push(now());
  await chrome.storage.local.set({ [key]: timestamps });
  return true;
}

function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname !== "www.linkedin.com") return "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.href.replace(/\/$/, "");
  } catch {
    return "";
  }
}

function companyAboutUrl(companyUrl) {
  const normalized = normalizeUrl(companyUrl);
  if (!normalized || !/\/company\//.test(normalized)) return "";
  return `${normalized.replace(/\/about$/, "")}/about/`;
}

function cachedValue(state, key) {
  const value = state.cache[key];
  if (!value || now() - Number(value.cachedAt || 0) > CACHE_TTL_MS) return null;
  return value;
}

async function remember(key, data) {
  const state = await getState();
  const cache = { ...state.cache, [key]: { ...data, cachedAt: now() } };
  const expired = Object.entries(cache)
    .filter(([, value]) => now() - Number(value.cachedAt || 0) > CACHE_TTL_MS)
    .map(([cacheKey]) => cacheKey);
  expired.forEach((cacheKey) => delete cache[cacheKey]);
  await chrome.storage.local.set({ cache });
  return cache[key];
}

async function sendToOrigin(tabId, message) {
  if (!tabId) return;
  try {
    await chrome.tabs.sendMessage(tabId, message);
  } catch {
    // The original LinkedIn tab may have closed or navigated while a hidden
    // tab was being analysed. The cache remains useful on the next scan.
  }
}

async function broadcast(message) {
  const tabs = await chrome.tabs.query({ url: "https://www.linkedin.com/jobs/*" });
  await Promise.all(tabs.map((tab) => sendToOrigin(tab.id, message)));
}

function enqueueCandidates(originTabId, candidates) {
  const existing = new Set(queue.map((item) => item.jobUrl));
  for (const candidate of candidates || []) {
    const jobUrl = normalizeUrl(candidate.jobUrl);
    if (!jobUrl || existing.has(jobUrl) || activeLookup?.jobUrl === jobUrl) continue;
    existing.add(jobUrl);
    queue.push({
      originTabId,
      jobUrl,
      title: String(candidate.title || "").trim(),
      company: String(candidate.company || "").trim(),
      companyUrl: normalizeUrl(candidate.companyUrl),
    });
  }
  processQueue();
}

async function requestExtraction(tabId, pageType) {
  let lastError;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      return await chrome.tabs.sendMessage(tabId, { type: "SCOUT_LENS_EXTRACT_PAGE", pageType });
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
  }
  throw lastError || new Error("Content script was unavailable");
}

async function createExtractionTab(url, type) {
  return new Promise((resolve, reject) => {
    chrome.tabs.create({ url, active: false }).then((tab) => {
      let processing = false;
      let settled = false;
      const timeout = setTimeout(async () => {
        if (settled) return;
        settled = true;
        cleanup();
        try { await chrome.tabs.remove(tab.id); } catch { /* already gone */ }
        reject(new Error(`${type} lookup timed out`));
      }, 20_000);

      const onUpdated = async (tabId, info) => {
        if (tabId !== tab.id || info.status !== "complete" || processing || settled) return;
        processing = true;
        try {
          const payload = await requestExtraction(tab.id, type);
          settled = true;
          cleanup();
          try { await chrome.tabs.remove(tab.id); } catch { /* already gone */ }
          resolve(payload || {});
        } catch (error) {
          settled = true;
          cleanup();
          try { await chrome.tabs.remove(tab.id); } catch { /* already gone */ }
          reject(error);
        }
      };

      const cleanup = () => {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(onUpdated);
      };
      chrome.tabs.onUpdated.addListener(onUpdated);
      if (tab.status === "complete") onUpdated(tab.id, { status: "complete" });
    }).catch(reject);
  });
}

function isChallenge(payload) {
  const text = String(payload?.pageText || "").toLowerCase();
  return /checkpoint|security verification|verify your identity|unusual activity|authwall|challenge/.test(text);
}

async function pauseForChallenge() {
  await updateState({ paused: true });
  queue = [];
  await broadcast({ type: "SCOUT_LENS_PAUSED", reason: "LinkedIn pidió una verificación. El escaneo fue pausado." });
}

async function analyseCandidate(candidate) {
  const state = await getState();
  const cachedJob = cachedValue(state, `job:${candidate.jobUrl}`);
  if (cachedJob) return cachedJob;
  if (!(await reserveLookup("job"))) {
    return { status: "rate_limited", jobUrl: candidate.jobUrl, title: candidate.title, company: candidate.company };
  }

  const details = await createExtractionTab(candidate.jobUrl, "job");
  if (isChallenge(details)) {
    await pauseForChallenge();
    return { status: "paused", jobUrl: candidate.jobUrl };
  }
  const description = String(details.description || "");
  const title = String(details.title || candidate.title || "");
  let companySize = "unknown";
  const aboutUrl = companyAboutUrl(candidate.companyUrl || details.companyUrl);

  if (aboutUrl) {
    const fresh = await getState();
    const cachedCompany = cachedValue(fresh, `company:${aboutUrl}`);
    if (cachedCompany) {
      companySize = cachedCompany.companySize || "unknown";
    } else if (await reserveLookup("company")) {
      try {
        const companyPage = await createExtractionTab(aboutUrl, "company");
        if (isChallenge(companyPage)) {
          await pauseForChallenge();
          return { status: "paused", jobUrl: candidate.jobUrl };
        }
        companySize = JobFilterRules.extractCompanySize(companyPage.pageText || "");
        await remember(`company:${aboutUrl}`, { companySize });
      } catch {
        companySize = "unknown";
      }
    }
  }

  return remember(`job:${candidate.jobUrl}`, {
    status: "ready",
    jobUrl: candidate.jobUrl,
    title,
    company: String(details.company || candidate.company || ""),
    minYears: JobFilterRules.extractMinimumYears(description),
    seniority: JobFilterRules.extractSeniority(title, description),
    requiredTechnologies: JobFilterRules.extractRequiredTechnologies(description),
    mentionedTechnologies: JobFilterRules.extractTechnologies(description),
    companySize,
  });
}

async function processQueue() {
  if (queueRunning) return;
  queueRunning = true;
  try {
    while (queue.length) {
      const state = await getState();
      if (state.paused) break;
      const candidate = queue.shift();
      activeLookup = candidate;
      try {
        const analysis = await analyseCandidate(candidate);
        await sendToOrigin(candidate.originTabId, { type: "SCOUT_LENS_ANALYSIS", analysis });
        if (analysis.status === "paused") break;
      } catch {
        await sendToOrigin(candidate.originTabId, {
          type: "SCOUT_LENS_ANALYSIS",
          analysis: { status: "unknown", jobUrl: candidate.jobUrl, title: candidate.title, company: candidate.company },
        });
      } finally {
        activeLookup = null;
      }
    }
  } finally {
    queueRunning = false;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case "SCOUT_LENS_GET_STATE": {
        const state = await getState();
        sendResponse({
          filters: state.filters,
          paused: state.paused,
          jobLookups: pruneTimestamps(state.jobLookups).length,
          companyLookups: pruneTimestamps(state.companyLookups).length,
        });
        break;
      }
      case "SCOUT_LENS_SET_FILTERS": {
        const filters = { ...JobFilterRules.defaultFilters(), ...(message.filters || {}) };
        await updateState({ filters });
        await broadcast({ type: "SCOUT_LENS_FILTERS", filters });
        sendResponse({ ok: true, filters });
        break;
      }
      case "SCOUT_LENS_SET_PAUSED": {
        await updateState({ paused: Boolean(message.paused) });
        if (!message.paused) processQueue();
        await broadcast({ type: "SCOUT_LENS_PAUSED", reason: message.paused ? "Pausado manualmente." : "" });
        sendResponse({ ok: true });
        break;
      }
      case "SCOUT_LENS_CLEAR_CACHE": {
        queue = [];
        await updateState({ cache: {}, jobLookups: [], companyLookups: [] });
        await broadcast({ type: "SCOUT_LENS_CACHE_CLEARED" });
        sendResponse({ ok: true });
        break;
      }
      case "SCOUT_LENS_SCAN": {
        enqueueCandidates(sender.tab?.id, message.candidates);
        sendResponse({ ok: true });
        break;
      }
      default:
        sendResponse({ ok: false });
    }
  })().catch((error) => {
    console.error("Scout Lens background request failed", error);
    sendResponse({ ok: false, error: "No se pudo completar la operación local." });
  });
  return true;
});
