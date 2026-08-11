const form = document.querySelector("#questionForm");
const questionInput = document.querySelector("#question");
const askButton = document.querySelector("#askButton");
const characterCount = document.querySelector("#characterCount");
const indexStatus = document.querySelector("#indexStatus");
const resultRegion = document.querySelector("#resultRegion");
const emptyState = document.querySelector("#emptyState");
const answerText = document.querySelector("#answerText");
const sourceList = document.querySelector("#sourceList");
const disclaimerText = document.querySelector("#disclaimerText");
const responseTime = document.querySelector("#responseTime");
const analysisPanel = document.querySelector("#analysisPanel");
const confidenceBadge = document.querySelector("#confidenceBadge");
const classificationName = document.querySelector("#classificationName");
const classificationReason = document.querySelector("#classificationReason");
const factList = document.querySelector("#factList");
const lawSummary = document.querySelector("#lawSummary");
const penaltyText = document.querySelector("#penaltyText");
const recommendedActions = document.querySelector("#recommendedActions");
const relatedLawList = document.querySelector("#relatedLawList");
const answerCard = document.querySelector("#answerCard");
const sidebar = document.querySelector("#sidebar");
const menuButton = document.querySelector("#menuButton");
const utilityDialog = document.querySelector("#utilityDialog");
const utilityTitle = document.querySelector("#utilityTitle");
const utilityKicker = document.querySelector("#utilityKicker");
const utilityBody = document.querySelector("#utilityBody");
const dialogClose = document.querySelector("#dialogClose");
const saveResultButton = document.querySelector("#saveResultButton");
const historyCount = document.querySelector("#historyCount");
const savedCount = document.querySelector("#savedCount");

const myanmarDigits = new Intl.NumberFormat("my-MM");
const STORAGE = {
  history: "legalInsight.history.v1",
  saved: "legalInsight.saved.v1",
  settings: "legalInsight.settings.v1",
};
const DEFAULT_SETTINGS = { fontSize: "normal", resultDetail: "detailed", autoHistory: true };
let currentResultEntry = null;

function readStorage(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function getHistory() { return readStorage(STORAGE.history, []); }
function getSaved() { return readStorage(STORAGE.saved, []); }
function getSettings() { return { ...DEFAULT_SETTINGS, ...readStorage(STORAGE.settings, {}) }; }

function createEntry(question, data) {
  return {
    id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    question,
    createdAt: new Date().toISOString(),
    data,
  };
}

function updateNavCounts() {
  historyCount.textContent = myanmarDigits.format(getHistory().length);
  savedCount.textContent = myanmarDigits.format(getSaved().length);
}

function applySettings(settings = getSettings()) {
  document.body.dataset.fontSize = settings.fontSize;
  document.body.dataset.resultDetail = settings.resultDetail;
}

function updateCharacterCount() {
  characterCount.textContent = `${myanmarDigits.format(questionInput.value.length)} / ၁၀၀၀`;
}

function setLoading(isLoading) {
  askButton.disabled = isLoading;
  askButton.querySelector("span:first-child").textContent = isLoading
    ? "ဥပဒေအထောက်အထား ရှာဖွေနေသည်…"
    : "ဥပဒေအရ သုံးသပ်ရန်";
}

function createSource(source) {
  const item = document.createElement("article");
  item.className = "source-item";

  const meta = document.createElement("div");
  meta.className = "source-meta";

  const title = document.createElement("strong");
  const chapter = source.chapter ? ` · ${source.chapter}` : "";
  const section = source.section ? ` · ပုဒ်မ ${source.section}` : "";
  const subsection = source.subsection ? ` (${source.subsection})` : "";
  title.textContent = `${source.law_name || "ဥပဒေစာတမ်း"}${chapter}${section}${subsection}`;

  const sourceType = document.createElement("span");
  sourceType.className = "source-score";
  sourceType.textContent = "ကိုးကားပုဒ်မ";
  if (source.matched_by === "verified_rule") {
    sourceType.textContent = "အတည်ပြုပုဒ်မ";
  } else if (source.matched_by === "hierarchical_semantic") {
    sourceType.textContent = "ဆက်စပ်ပုဒ်မ";
  }
  meta.append(title, sourceType);

  const excerpt = document.createElement("p");
  excerpt.textContent = source.content || "";
  item.append(meta, excerpt);

  if (source.source_url) {
    const link = document.createElement("a");
    link.href = source.source_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "မူရင်းရင်းမြစ်ကို ဖွင့်ရန် ↗";
    item.append(link);
  }

  return item;
}

function renderAnalysis(analysis) {
  const hasAnalysis = Boolean(analysis);
  analysisPanel.hidden = !hasAnalysis;
  if (!hasAnalysis) return;

  const urgentRules = new Set(["child_sexual_exploitation", "child_cruelty_or_torture"]);
  const isUrgent = urgentRules.has(analysis.rule_id);
  const isInsufficient = analysis.mode === "insufficient_evidence";
  const status = analysis.status || (isUrgent ? "အရေးကြီး" : isInsufficient ? "အထောက်အထားမလုံလောက်" : "စိစစ်ပြီး");

  confidenceBadge.textContent = status;
  confidenceBadge.classList.toggle("urgent", isUrgent || status === "အရေးကြီး");
  confidenceBadge.classList.toggle("insufficient", isInsufficient);

  classificationName.textContent = analysis.classification?.name || "ဥပဒေဆိုင်ရာ သုံးသပ်ချက်";
  classificationReason.textContent = analysis.classification?.reasoning || "";
  lawSummary.textContent = analysis.law_summary || "";
  penaltyText.hidden = !analysis.penalty;
  penaltyText.textContent = analysis.penalty ? `ပြစ်ဒဏ်သတ်မှတ်ချက် — ${analysis.penalty}` : "";

  factList.replaceChildren();
  (analysis.facts || []).forEach((fact) => {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = fact.label;
    description.textContent = fact.value;
    wrapper.append(term, description);
    factList.append(wrapper);
  });

  recommendedActions.replaceChildren();
  (analysis.recommended_actions || []).forEach((action) => {
    const item = document.createElement("li");
    item.textContent = action;
    recommendedActions.append(item);
  });

  relatedLawList.replaceChildren();
  (analysis.related_sections || []).forEach((provision) => {
    const card = document.createElement("article");
    card.className = "related-law-item";

    const role = document.createElement("span");
    role.className = "related-law-role";
    role.textContent = getClearProvisionRole(provision.role);

    const body = document.createElement("div");
    const citation = document.createElement("strong");
    citation.textContent = provision.citation || "";
    const summary = document.createElement("p");
    summary.textContent = provision.summary || "";
    body.append(citation, summary);
    card.append(role, body);
    relatedLawList.append(card);
  });

  const relatedSection = document.querySelector(".related-laws");
  relatedSection.hidden = !relatedLawList.children.length;
}

function getDisplayLawName(data) {
  const analysisText = JSON.stringify(data.analysis || {});
  const lawPriority = [
    ["ကလေးသူငယ်", "ကလေးသူငယ် အခွင့်အရေးများဆိုင်ရာဥပဒေ"],
    ["ဆက်သွယ်ရေးဥပဒေ", "ဆက်သွယ်ရေးဥပဒေ"],
    ["ဆိုက်ဘာလုံခြုံရေးဥပဒေ", "ဆိုက်ဘာလုံခြုံရေးဥပဒေ"],
    ["သစ်တောဥပဒေ", "သစ်တောဥပဒေ"],
    ["မြန်မာနိုင်ငံကူးလက်မှတ်ဆိုင်ရာဥပဒေ", "မြန်မာနိုင်ငံကူးလက်မှတ်ဆိုင်ရာဥပဒေ"],
    ["မူးယစ်ဆေးဝါးနှင့် စိတ်ကိုပြောင်းလဲစေသော ဆေးဝါးများဆိုင်ရာဥပဒေ", "မူးယစ်ဆေးဝါးနှင့် စိတ်ကိုပြောင်းလဲစေသော ဆေးဝါးများဆိုင်ရာဥပဒေ"],
    ["ရာဇသတ်ကြီး", "ရာဇသတ်ကြီး"],
  ];
  const analysisLaw = lawPriority.find(([keyword]) => analysisText.includes(keyword))?.[1];
  if (analysisLaw) return analysisLaw;

  const factLaw = (data.analysis?.facts || []).find((fact) =>
    String(fact.label || "").includes("ဥပဒေ")
  )?.value;
  const sourceLaw = (data.sources || []).find((source) => source.law_name)?.law_name;
  return factLaw || sourceLaw || "";
}

function ensureMainLawFact(lawName) {
  if (!lawName || !factList) return;
  const alreadyShown = Array.from(factList.querySelectorAll("dt")).some((term) =>
    term.textContent.includes("အဓိကဥပဒေ") || term.textContent.includes("သက်ဆိုင်ရာဥပဒေ")
  );
  if (alreadyShown) return;

  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = "သက်ဆိုင်ရာ အဓိကဥပဒေ";
  description.textContent = lawName;
  wrapper.append(term, description);
  factList.prepend(wrapper);
}

function getClearProvisionRole(role) {
  const normalized = String(role || "").trim();
  if (normalized.includes("ပြစ်ဒဏ်")) return "ပြစ်ဒဏ်ပုဒ်မ";
  if (normalized.includes("ပြစ်မှု")) return "ကျူးလွန်မှုပုဒ်မ";
  if (normalized === "အဓိက") return "အဓိကပုဒ်မ";
  if (normalized.includes("ဆက်စပ်")) return "ဆက်စပ်ပုဒ်မ";
  if (normalized.includes("အဓိပ္ပါယ်")) return "အဓိပ္ပါယ်ဖွင့်ဆိုချက်";
  if (normalized.includes("ကာကွယ်")) return "ကာကွယ်မှုပုဒ်မ";
  return normalized || "ဆက်စပ်ပုဒ်မ";
}

function isCurrentSaved() {
  return Boolean(currentResultEntry && getSaved().some((entry) => entry.id === currentResultEntry.id));
}

function updateSaveButton() {
  saveResultButton.hidden = !currentResultEntry;
  const saved = isCurrentSaved();
  saveResultButton.classList.toggle("saved", saved);
  saveResultButton.textContent = saved ? "★ သိမ်းထားပြီး" : "☆ သိမ်းမည်";
}

function displayResponse(data, question, options = {}) {
  currentResultEntry = options.entry || createEntry(question, data);
  questionInput.value = question;
  updateCharacterCount();
  sourceList.replaceChildren();
  answerText.classList.remove("error-message");
  answerCard.classList.remove("insufficient");
  answerText.textContent = data.answer || "";
  disclaimerText.textContent = data.disclaimer || "";
  responseTime.textContent = Number.isFinite(data.response_ms)
    ? `${(data.response_ms / 1000).toFixed(1)} စက္ကန့်`
    : "သိမ်းထားသောရလဒ်";
  renderAnalysis(data.analysis);
  const displayLawName = getDisplayLawName(data);
  if (displayLawName) {
    classificationName.textContent = displayLawName;
    ensureMainLawFact(displayLawName);
  }

  (data.sources || []).forEach((source) => sourceList.append(createSource(source)));
  if (!(data.sources || []).length) {
    const emptySources = document.createElement("p");
    emptySources.className = "source-empty";
    emptySources.textContent = "ခိုင်လုံစွာကိုးကားနိုင်သည့် ပုဒ်မ မတွေ့ရှိပါ။";
    sourceList.append(emptySources);
  }

  answerCard.classList.toggle("insufficient", !data.answerable);
  emptyState.hidden = true;
  resultRegion.hidden = false;
  updateSaveButton();
  if (options.scroll !== false) {
    resultRegion.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function addHistoryEntry(entry) {
  const history = getHistory().filter((item) => item.id !== entry.id);
  history.unshift(entry);
  writeStorage(STORAGE.history, history.slice(0, 50));
  updateNavCounts();
}

function resetAnalysis() {
  const hasWork = questionInput.value.trim() || !resultRegion.hidden;
  if (hasWork && !window.confirm("လက်ရှိမေးခွန်းနှင့် ရလဒ်ကို ရှင်းပြီး အသစ်စတင်မည်လား။")) return;
  form.reset();
  currentResultEntry = null;
  resultRegion.hidden = true;
  updateSaveButton();
  updateCharacterCount();
  questionInput.focus();
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function closeUtilityDialog() {
  if (utilityDialog.open) utilityDialog.close();
  sidebar.classList.remove("open");
  menuButton?.setAttribute("aria-expanded", "false");
}

function emptyUtility(icon, message) {
  const empty = document.createElement("div");
  empty.className = "utility-empty";
  const symbol = document.createElement("span");
  symbol.textContent = icon;
  const text = document.createElement("p");
  text.textContent = message;
  empty.append(symbol, text);
  return empty;
}

function renderEntryList(kind, searchText = "") {
  const entries = kind === "history" ? getHistory() : getSaved();
  const query = searchText.trim().toLocaleLowerCase("my");
  const filtered = entries.filter((entry) => {
    const analysis = entry.data?.analysis || {};
    const haystack = [entry.question, entry.data?.answer, analysis.classification?.name, analysis.penalty]
      .filter(Boolean).join(" ").toLocaleLowerCase("my");
    return !query || haystack.includes(query);
  });

  utilityBody.replaceChildren();
  if (entries.length) {
    const search = document.createElement("input");
    search.className = "utility-search";
    search.type = "search";
    search.placeholder = "မေးခွန်း၊ ပုဒ်မ သို့မဟုတ် ပြစ်ဒဏ်ဖြင့် ရှာရန်…";
    search.value = searchText;
    search.addEventListener("input", () => renderEntryList(kind, search.value));
    utilityBody.append(search);
    requestAnimationFrame(() => search.focus());
  }
  if (!filtered.length) {
    utilityBody.append(emptyUtility(kind === "history" ? "◷" : "☆", entries.length ? "ရှာဖွေမှုနှင့် ကိုက်ညီသောရလဒ် မရှိပါ။" : kind === "history" ? "သုံးသပ်ထားသော မှတ်တမ်းမရှိသေးပါ။" : "သိမ်းထားသောအဖြေ မရှိသေးပါ။"));
    return;
  }

  const list = document.createElement("div");
  list.className = "utility-list";
  filtered.forEach((entry) => {
    const item = document.createElement("article");
    item.className = "utility-item";
    const main = document.createElement("div");
    main.className = "utility-item-main";
    const question = document.createElement("strong");
    question.textContent = entry.question;
    const summary = document.createElement("p");
    summary.textContent = entry.data?.answer || entry.data?.analysis?.law_summary || "";
    const meta = document.createElement("div");
    meta.className = "utility-item-meta";
    const date = document.createElement("span");
    date.textContent = new Intl.DateTimeFormat("my-MM", { dateStyle: "medium", timeStyle: "short" }).format(new Date(entry.createdAt));
    meta.append(date);
    const classification = entry.data?.analysis?.classification?.name;
    if (classification) {
      const tag = document.createElement("span");
      tag.className = "utility-tag";
      tag.textContent = classification;
      meta.append(tag);
    }
    main.append(question, summary, meta);

    const actions = document.createElement("div");
    actions.className = "utility-item-actions";
    const open = document.createElement("button");
    open.type = "button";
    open.textContent = "ဖွင့်မည်";
    open.addEventListener("click", () => {
      closeUtilityDialog();
      displayResponse(entry.data, entry.question, { entry });
    });
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "ကူးယူ";
    copy.addEventListener("click", async () => {
      await navigator.clipboard?.writeText(`${entry.question}\n\n${entry.data?.answer || ""}`);
      copy.textContent = "ကူးယူပြီး";
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "danger-button";
    remove.textContent = "ဖျက်မည်";
    remove.addEventListener("click", () => {
      const key = kind === "history" ? STORAGE.history : STORAGE.saved;
      writeStorage(key, entries.filter((candidate) => candidate.id !== entry.id));
      updateNavCounts();
      updateSaveButton();
      renderEntryList(kind, searchText);
    });
    actions.append(open, copy, remove);
    item.append(main, actions);
    list.append(item);
  });
  utilityBody.append(list);
}

async function renderSettings() {
  const settings = getSettings();
  utilityBody.innerHTML = `
    <section class="settings-list">
      <label class="setting-row"><span><strong>စာလုံးအရွယ်အစား</strong><small>UI စာသားအရွယ်ကို ရွေးပါ</small></span><select id="fontSizeSetting"><option value="small">သေး</option><option value="normal">ပုံမှန်</option><option value="large">ကြီး</option></select></label>
      <label class="setting-row"><span><strong>ရလဒ်ဖော်ပြမှုပုံစံ</strong><small>အသေးစိတ် သို့မဟုတ် အကျဉ်းချုပ်</small></span><select id="resultDetailSetting"><option value="detailed">အသေးစိတ်</option><option value="compact">အကျဉ်းချုပ်</option></select></label>
      <label class="setting-row"><span><strong>မှတ်တမ်း အလိုအလျောက်သိမ်းရန်</strong><small>အောင်မြင်သော သုံးသပ်ချက်များကို browser တွင်သိမ်းမည်</small></span><span class="toggle-control"><input id="autoHistorySetting" type="checkbox" /> ဖွင့်ထားမည်</span></label>
      <div class="setting-row"><span><strong>စနစ်ချိတ်ဆက်မှု</strong><small>Backend နှင့် ဥပဒေ database အခြေအနေ</small></span><span class="service-status" id="serviceStatus">စစ်ဆေးနေသည်…</span></div>
    </section>
    <div class="settings-actions"><button type="button" class="danger-button" id="clearHistoryButton">မှတ်တမ်းရှင်းမည်</button><button type="button" class="danger-button" id="clearSavedButton">သိမ်းထားသည်များရှင်းမည်</button></div>`;
  const font = utilityBody.querySelector("#fontSizeSetting");
  const detail = utilityBody.querySelector("#resultDetailSetting");
  const autoHistory = utilityBody.querySelector("#autoHistorySetting");
  font.value = settings.fontSize;
  detail.value = settings.resultDetail;
  autoHistory.checked = settings.autoHistory;
  const saveSettings = () => {
    const next = { ...getSettings(), fontSize: font.value, resultDetail: detail.value, autoHistory: autoHistory.checked };
    writeStorage(STORAGE.settings, next);
    applySettings(next);
  };
  [font, detail, autoHistory].forEach((control) => control.addEventListener("change", saveSettings));
  utilityBody.querySelector("#clearHistoryButton").addEventListener("click", () => {
    if (window.confirm("မှတ်တမ်းအားလုံးကို ဖျက်မည်လား။")) { writeStorage(STORAGE.history, []); updateNavCounts(); }
  });
  utilityBody.querySelector("#clearSavedButton").addEventListener("click", () => {
    if (window.confirm("သိမ်းထားသောအဖြေအားလုံးကို ဖျက်မည်လား။")) { writeStorage(STORAGE.saved, []); updateNavCounts(); updateSaveButton(); }
  });
  const serviceStatus = utilityBody.querySelector("#serviceStatus");
  try {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error();
    const stats = await response.json();
    serviceStatus.textContent = `အသင့် · ဥပဒေ ${myanmarDigits.format(stats.documents)} · အပိုင်း ${myanmarDigits.format(stats.chunks)}`;
    serviceStatus.classList.add("ready");
  } catch {
    serviceStatus.textContent = "ချိတ်ဆက်၍မရပါ";
  }
}

function openUtility(view) {
  const titles = { history: "သုံးသပ်ချက်မှတ်တမ်း", saved: "သိမ်းထားသောအဖြေများ", guide: "စနစ်အသုံးပြုနည်း", about: "စနစ်အကြောင်း", settings: "ဆက်တင်များ" };
  utilityTitle.textContent = titles[view] || "Legal Insight";
  utilityKicker.textContent = view === "history" || view === "saved" ? "YOUR LIBRARY" : "LEGAL INSIGHT";
  if (view === "history" || view === "saved") renderEntryList(view);
  if (view === "guide" || view === "about") {
    utilityBody.replaceChildren(document.querySelector(`#${view}Template`).content.cloneNode(true));
  }
  if (view === "settings") renderSettings();
  if (!utilityDialog.open) utilityDialog.showModal();
}

async function loadStats() {
  if (!indexStatus) return;
  indexStatus.hidden = true;
  try {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error("stats unavailable");
    const stats = await response.json();
    indexStatus.classList.add("ready");
    indexStatus.lastChild.textContent = "";
  } catch {
    indexStatus.lastChild.textContent = "";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  setLoading(true);
  currentResultEntry = null;
  updateSaveButton();
  sourceList.replaceChildren();
  answerText.classList.remove("error-message");
  answerCard.classList.remove("insufficient");

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({ question }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "မေးခွန်းကို သုံးသပ်၍မရပါ။");

    const entry = createEntry(question, data);
    if (getSettings().autoHistory) addHistoryEntry(entry);
    displayResponse(data, question, { entry });
  } catch (error) {
    answerText.textContent = error.message;
    answerText.classList.add("error-message");
    renderAnalysis(null);
    disclaimerText.textContent = "Ollama၊ Docker နှင့် PostgreSQL ဝန်ဆောင်မှုများ ဖွင့်ထားကြောင်း စစ်ဆေးပါ။";
    responseTime.textContent = "";
    emptyState.hidden = true;
    resultRegion.hidden = false;
  } finally {
    setLoading(false);
  }
});

questionInput.addEventListener("input", updateCharacterCount);

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    updateCharacterCount();
    questionInput.focus();
    document.querySelector("#questionForm").scrollIntoView({ behavior: "smooth", block: "center" });
  });
});

menuButton?.addEventListener("click", () => {
  const isOpen = sidebar.classList.toggle("open");
  menuButton.setAttribute("aria-expanded", String(isOpen));
});

document.querySelectorAll("[data-nav-view]").forEach((button) => {
  button.addEventListener("click", () => openUtility(button.dataset.navView));
});

document.querySelectorAll("[data-nav-action]").forEach((button) => {
  button.addEventListener("click", () => {
    sidebar.classList.remove("open");
    menuButton?.setAttribute("aria-expanded", "false");
    if (button.dataset.navAction === "new") {
      resetAnalysis();
    } else {
      document.querySelector("#home").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

saveResultButton?.addEventListener("click", () => {
  if (!currentResultEntry) return;
  const saved = getSaved();
  const existing = saved.findIndex((entry) => entry.id === currentResultEntry.id);
  if (existing >= 0) {
    saved.splice(existing, 1);
  } else {
    saved.unshift(currentResultEntry);
  }
  writeStorage(STORAGE.saved, saved.slice(0, 50));
  updateNavCounts();
  updateSaveButton();
});

dialogClose?.addEventListener("click", closeUtilityDialog);
utilityDialog?.addEventListener("click", (event) => {
  if (event.target === utilityDialog) closeUtilityDialog();
});

updateCharacterCount();
applySettings();
updateNavCounts();
updateSaveButton();
loadStats();
