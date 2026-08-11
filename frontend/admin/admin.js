const $ = (id) => document.getElementById(id);
let documents = [];
const views = ["dashboard", "upload", "processing", "queries", "review"];

const number = (value) => new Intl.NumberFormat("my-MM").format(Number(value || 0));
function escapeHtml(value) { const node = document.createElement("div"); node.textContent = value ?? ""; return node.innerHTML; }

function renderDocuments(filter = "") {
  const query = filter.trim().toLowerCase();
  const rows = documents.filter((item) => (item.law_name || "").toLowerCase().includes(query));
  $("documentRows").innerHTML = rows.length ? rows.map((item) => {
    const ready = Number(item.chunks) > 0 && Number(item.embeddings) === Number(item.chunks);
    return `<tr><td>${escapeHtml(item.law_name || "အမည်မသတ်မှတ်ရသေး")}</td><td>${escapeHtml(item.format || "—")}</td><td>${number(item.chunks)}</td><td>${number(item.embeddings)}</td><td><span class="badge ${ready ? "" : "warn"}">${ready ? "Indexed" : "စစ်ဆေးရန်"}</span></td></tr>`;
  }).join("") : '<tr><td colspan="5" class="empty">ရှာဖွေမှုနှင့် ကိုက်ညီသော စာတမ်းမရှိပါ။</td></tr>';
}

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || data.error || "Request failed");
  return data;
}

async function loadDashboard() {
  try {
    const data = await api("/api/admin/overview");
    documents = data.documents || [];
    $("documentCount").textContent = number(data.summary.documents);
    $("chunkCount").textContent = number(data.summary.chunks);
    $("embeddingCount").textContent = number(data.summary.embeddings);
    $("warningCount").textContent = number(data.summary.warnings);
    const rate = data.summary.chunks ? Math.round(data.summary.embeddings * 100 / data.summary.chunks) : 0;
    $("embeddingRate").textContent = `${number(rate)}% ပြီးစီး`;
    $("systemStatus").textContent = "Database ချိတ်ဆက်ပြီး";
    document.querySelector(".system-status").className = "system-status ready";
    renderDocuments();
  } catch (error) {
    $("documentRows").innerHTML = '<tr><td colspan="5" class="empty">Database ကို ချိတ်ဆက်၍မရပါ။ Docker services ကို စစ်ဆေးပါ။</td></tr>';
    $("systemStatus").textContent = "Database မချိတ်ဆက်နိုင်ပါ";
    document.querySelector(".system-status").className = "system-status error";
  }
}

function showView(name) {
  const resolved = name === "documents" ? "dashboard" : name;
  views.forEach((view) => $(`${view}View`).classList.toggle("active", view === resolved));
  if (resolved === "processing") loadProcessing();
  if (resolved === "queries") loadQueryRuns();
  if (resolved === "review") loadQuality();
}

const traceLabels = {
  input_received: "User input လက်ခံခြင်း",
  query_normalized: "စကားပြောအသုံးအနှုန်း Normalize လုပ်ခြင်း",
  case_classified: "ဖြစ်စဉ်အမျိုးအစား ခွဲခြားခြင်း",
  embedding_generated: "မေးခွန်းအဓိပ္ပာယ် ပြောင်းလဲခြင်း",
  hybrid_retrieval: "Semantic + Keyword Search လုပ်ခြင်း",
  candidates_ranked: "Candidate ပုဒ်မများ အဆင့်သတ်မှတ်ခြင်း",
  main_section_selected: "အဓိကဥပဒေနှင့် ပုဒ်မရွေးခြင်း",
  punishment_linked: "ဆက်စပ်ပြစ်ဒဏ်ပုဒ်မ ချိတ်ဆက်ခြင်း",
  evidence_validated: "အထောက်အထားလုံလောက်မှု စစ်ဆေးခြင်း",
  answer_composed: "User မြင်မည့်အဖြေ တည်ဆောက်ခြင်း",
};

const detailLabels = {
  normalized_question: "ပြင်ဆင်ထားသောမေးခွန်း",
  changed: "ပြင်ဆင်မှုရှိ/မရှိ",
  case_type: "ဖြစ်စဉ်အမျိုးအစား",
  classification: "ခွဲခြားရလဒ်",
  candidate_count: "Candidate အရေအတွက်",
  top_score: "အမြင့်ဆုံး score",
  score_margin: "Score margin",
  penalty_candidate_found: "ပြစ်ဒဏ် candidate တွေ့/မတွေ့",
  verified_source_count: "အတည်ပြု source အရေအတွက်",
  evidence_count: "အထောက်အထားအရေအတွက်",
  semantic_answerable: "Semantic evidence လုံလောက်/မလုံလောက်",
  law_name: "ရွေးချယ်သောဥပဒေ",
  section: "ရွေးချယ်သောပုဒ်မ",
  response_mode: "အဖြေတည်ဆောက်ပုံ",
  source_count: "Source အရေအတွက်",
  required: "ပြစ်ဒဏ်လိုအပ်/မလိုအပ်",
  found: "ပြစ်ဒဏ်တွေ့/မတွေ့",
  answerable: "အဖြေပေးနိုင်/မနိုင်",
  composer_used: "AI composer အသုံးပြု/မပြု",
  composer_validated: "AI အဖြေ အတည်ပြု/မပြု",
  answer_length: "အဖြေစာလုံးရေ",
  question_length: "မေးခွန်းစာလုံးရေ",
};

function displayValue(value) {
  if (value === true) return "ရှိ / ဟုတ်";
  if (value === false) return "မရှိ / မဟုတ်";
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(" · ");
  return String(value);
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== "" && (!Array.isArray(value) || value.length > 0);
}

function readableSeconds(milliseconds) {
  return `${(Number(milliseconds || 0) / 1000).toFixed(3)} စက္ကန့်`;
}

function durationLabel(milliseconds) {
  const value = Number(milliseconds || 0);
  return value < 1 ? "၁ ms အောက်" : `${number(value)} ms`;
}

function sectionLabel(value) {
  if (!hasValue(value)) return null;
  const text = String(value);
  return text.includes("ပုဒ်မ") ? text : `ပုဒ်မ ${text}`;
}

function fact(label, value) {
  if (!hasValue(value)) return "";
  return `<span><b>${escapeHtml(label)}</b>${escapeHtml(displayValue(value))}</span>`;
}

function retrievalInterpretation(details, item) {
  const route = String(details.matching_route || "").toLowerCase();
  const keywords = details.matched_terms || details.search_terms;
  let understoodCase = "မေးခွန်းနှင့် အဓိပ္ပာယ်တူသော ဥပဒေဆိုင်ရာဖြစ်စဉ်";
  let legalTopic = item.selected_law || (details.candidate_laws || [])[0] || "သက်ဆိုင်ရာဥပဒေ";

  const rules = [
    ["penal_adultery", "အိမ်ထောင်ရှိသူနှင့် ဖောက်ပြန်ဆက်ဆံခြင်း", "ရာဇသတ်ကြီး၊ အိမ်ထောင်ရေးဆိုင်ရာပြစ်မှု"],
    ["telecom_66d", "ဆက်သွယ်ရေးကွန်ရက်မှတစ်ဆင့် ဂုဏ်သရေထိခိုက်စေခြင်း", "ဆက်သွယ်ရေးဥပဒေ၊ ကွန်ရက်အသုံးပြု၍ အသရေဖျက်မှု"],
    ["cyber", "အွန်လိုင်းစနစ်၊ အကောင့် သို့မဟုတ် ဒေတာကို မမှန်ကန်စွာအသုံးပြုခြင်း", "ဆိုက်ဘာလုံခြုံရေးဥပဒေ၊ အွန်လိုင်းစနစ်ဆိုင်ရာပြစ်မှု"],
    ["passport", "နိုင်ငံကူးလက်မှတ်ကို အတုပြုလုပ်ခြင်း သို့မဟုတ် မမှန်ကန်စွာအသုံးပြုခြင်း", "မြန်မာနိုင်ငံကူးလက်မှတ်ဆိုင်ရာဥပဒေ"],
    ["forest", "သစ်တောထွက်ပစ္စည်းကို ခွင့်ပြုချက်မရှိ ထုတ်ယူခြင်း သို့မဟုတ် သယ်ယူခြင်း", "သစ်တောဥပဒေ၊ သစ်တောထွက်ပစ္စည်းဆိုင်ရာပြစ်မှု"],
    ["drug", "မူးယစ်ဆေးဝါးကို လက်ဝယ်ထားရှိခြင်း၊ သယ်ယူခြင်း သို့မဟုတ် ရောင်းချခြင်း", "မူးယစ်ဆေးဝါးဆိုင်ရာဥပဒေ"],
    ["penal_defamation", "လူတစ်ဦး၏ဂုဏ်သရေကို ထိခိုက်စေသော အသရေဖျက်မှု", "ရာဇသတ်ကြီး၊ အသရေဖျက်မှုဆိုင်ရာပြစ်မှု"],
    ["penal_house_trespass", "အိမ်အတွင်း ခွင့်ပြုချက်မရှိ ကျော်နင်းဝင်ရောက်ခြင်း", "ရာဇသတ်ကြီး၊ အိမ်ကျော်နင်းမှုဆိုင်ရာပြစ်မှု"],
    ["penal_theft", "သူတစ်ပါးပိုင်ပစ္စည်းကို ခိုးယူခြင်း", "ရာဇသတ်ကြီး၊ ခိုးမှုဆိုင်ရာပြစ်မှု"],
  ];
  for (const [fragment, caseName, topic] of rules) {
    if (route.includes(fragment)) {
      understoodCase = caseName;
      legalTopic = topic;
      break;
    }
  }

  const section = item.selected_section ? `ပုဒ်မ ${item.selected_section}` : null;
  const reason = hasValue(keywords)
    ? `${displayValue(keywords)} ဟူသော အချက်များနှင့် ${legalTopic} ၏ ပြဋ္ဌာန်းချက်အဓိပ္ပာယ် တိုက်ရိုက်ကိုက်ညီသောကြောင့်`
    : `${legalTopic} နှင့် မေးခွန်း၏ဖြစ်စဉ်အဓိပ္ပာယ် အများဆုံးကိုက်ညီသောကြောင့်`;
  return {keywords, understoodCase, legalTopic, section, reason};
}

function describeTraceStep(step, item, longestDuration) {
  const d = step.details || {};
  const duration = Number(step.duration_ms || 0);
  const questionLength = d.question_length ?? item.question?.length;
  const selectedLaw = d.law_name || item.selected_law;
  const selectedSection = d.section || item.selected_section;
  let title = traceLabels[step.step_name] || step.step_name;
  let description = "ဤလုပ်ဆောင်မှုအဆင့်ကို အောင်မြင်စွာ ပြီးစီးခဲ့သည်။";
  let facts = [];

  switch (step.step_name) {
    case "input_received":
      title = "အသုံးပြုသူ၏ မေးခွန်းကို လက်ခံခဲ့သည်";
      description = `အသုံးပြုသူထည့်သွင်းထားသော မေးခွန်းကို အောင်မြင်စွာလက်ခံပြီး နောက်ဆက်တွဲစိစစ်မှုများအတွက် ပြင်ဆင်ခဲ့သည်${hasValue(questionLength) ? `။ မေးခွန်းတွင် စာလုံးရေ ${number(questionLength)} လုံး ပါဝင်သည်။` : "။"}`;
      facts = [fact("မေးခွန်းစာလုံးရေ", questionLength)];
      break;
    case "query_normalized":
      title = d.changed ? "မေးခွန်း၏ အသုံးအနှုန်းများကို ပြင်ဆင်ခဲ့သည်" : "မူရင်းမေးခွန်းကို ပြင်ဆင်ရန် မလိုအပ်ပါ";
      description = d.changed
        ? "စာလုံးပေါင်း၊ စကားပြောအသုံးအနှုန်းနှင့် အဓိပ္ပာယ်တူစကားလုံးများကို စစ်ဆေးပြီး ရှာဖွေမှုအတွက် ပိုမိုရှင်းလင်းသော မေးခွန်းပုံစံသို့ ပြင်ဆင်ခဲ့သည်။"
        : "မေးခွန်း၏ အဓိပ္ပာယ်ရှင်းလင်းပြီး ရှာဖွေမှုအတွက် တိုက်ရိုက်အသုံးပြုနိုင်သောကြောင့် မူရင်းမေးခွန်းကို မပြောင်းလဲဘဲ ဆက်လက်အသုံးပြုခဲ့သည်။";
      facts = [fact("အသုံးပြုထားသောမေးခွန်း", d.normalized_question)];
      break;
    case "case_classified":
      title = "ဖြစ်စဉ်အမျိုးအစားကို ခွဲခြားသတ်မှတ်ခဲ့သည်";
      description = `မေးခွန်းတွင် ဖော်ပြထားသော ပါဝင်သူများ၊ လုပ်ရပ်၊ ထိခိုက်မှုနှင့် အဓိကအသုံးအနှုန်းများကို စစ်ဆေးပြီး${hasValue(d.case_type || d.classification) ? ` “${displayValue(d.case_type || d.classification)}” ဖြစ်စဉ်အမျိုးအစားအဖြစ်` : " သက်ဆိုင်ရာဖြစ်စဉ်အမျိုးအစားကို"} သတ်မှတ်ခဲ့သည်။`;
      facts = [fact("ဖြစ်စဉ်အမျိုးအစား", d.case_type), fact("ခွဲခြားရလဒ်", d.classification)];
      break;
    case "embedding_generated":
      title = "မေးခွန်း၏အဓိပ္ပာယ်ကို ရှာဖွေမှုပုံစံသို့ ပြောင်းလဲခဲ့သည်";
      description = `မေးခွန်းထဲရှိ စကားလုံးတစ်လုံးချင်းသာမက ဖြစ်စဉ်တစ်ခုလုံး၏ အဓိပ္ပာယ်ကို ဥပဒေစာတမ်းများနှင့် နှိုင်းယှဉ်ရှာဖွေနိုင်သောပုံစံသို့ ပြောင်းလဲခဲ့သည်။ ဤအဆင့်သည် ${readableSeconds(duration)} ကြာခဲ့သည်${duration === longestDuration && duration > 0 ? "။ ယခု process အတွင်း အချိန်အများဆုံးအသုံးပြုခဲ့သောအဆင့်ဖြစ်သည်။" : "။"}`;
      facts = [fact("လုပ်ဆောင်ချိန်", readableSeconds(duration))];
      break;
    case "hybrid_retrieval": {
      const interpretation = retrievalInterpretation(d, item);
      title = "Database အတွင်းမှ သက်ဆိုင်နိုင်သော ဥပဒေပုဒ်မများကို ရှာဖွေခဲ့သည်";
      const countText = hasValue(d.candidate_count) ? ` ပေါင်းစပ်ရှာဖွေမှုမှ candidate ${number(d.candidate_count)} ခု ရရှိခဲ့သည်။` : "";
      const scoreText = hasValue(d.top_score) ? ` အမြင့်ဆုံးကိုက်ညီမှု score မှာ ${displayValue(d.top_score)} ဖြစ်သည်။` : "";
      const marginText = hasValue(d.score_margin) ? ` ထိပ်ဆုံး candidate နှစ်ခု၏ score ကွာဟချက်မှာ ${displayValue(d.score_margin)} ဖြစ်သည်။` : "";
      const termsText = hasValue(d.matched_terms || d.search_terms) ? ` တကယ်ကိုက်ညီခဲ့သော အဓိကအသုံးအနှုန်းများမှာ “${displayValue(d.matched_terms || d.search_terms)}” ဖြစ်သည်။` : "";
      const lawsText = hasValue(d.candidate_laws) ? ` Candidate ဥပဒေများအဖြစ် ${displayValue(d.candidate_laws)} ကို တွေ့ရှိခဲ့သည်။` : "";
      description = `စကားလုံးတိတိကျကျကိုက်ညီမှုနှင့် ဖြစ်စဉ်တစ်ခုလုံး၏ အဓိပ္ပာယ်တူညီမှုကို ပေါင်းစပ်ပြီး database ရှိ ဥပဒေအပိုင်းများအတွင်း ရှာဖွေခဲ့သည်။${termsText}${lawsText}${countText}${scoreText}${marginText} ရှာဖွေမှုသည် ${readableSeconds(duration)} ကြာခဲ့သည်။`;
      facts = [fact("အဓိကစကားလုံးများ", interpretation.keywords), fact("နားလည်ထားသောဖြစ်စဉ်", interpretation.understoodCase), fact("ရှာဖွေသည့်ဥပဒေအကြောင်းအရာ", interpretation.legalTopic), fact("ရရှိသောပုဒ်မ", interpretation.section), fact("ရွေးချယ်ရသည့်အကြောင်း", interpretation.reason)];
      break;
    }
    case "candidates_ranked":
      title = "အကောင်းဆုံးကိုက်ညီသော ဥပဒေရလဒ်ကို ရွေးချယ်ခဲ့သည်";
      description = `တွေ့ရှိထားသော ဥပဒေရလဒ်များကို မေးခွန်း၏အဓိကစကားလုံး၊ ဖြစ်စဉ်အဓိပ္ပာယ်နှင့် ဥပဒေအထောက်အထားတို့ဖြင့် နှိုင်းယှဉ်ပြီး${selectedLaw ? ` “${selectedLaw}”` : " သက်ဆိုင်ရာဥပဒေ"}${selectedSection ? `၊ ${sectionLabel(selectedSection)}` : "နှင့် ပုဒ်မ"} ကို ထိပ်ဆုံးရလဒ်အဖြစ် ရွေးချယ်ခဲ့သည်။`;
      facts = [
        fact("ရွေးချယ်သောဥပဒေ", selectedLaw),
        fact("ရွေးချယ်သောပုဒ်မ", sectionLabel(selectedSection)),
        fact("နှိုင်းယှဉ်ထားသောရလဒ်များ", d.candidate_sections),
        fact("ရွေးချယ်ရသည့်အကြောင်း", selectedLaw && selectedSection ? `မေးခွန်း၏ဖြစ်စဉ်နှင့် ${selectedLaw}၊ ${sectionLabel(selectedSection)} ၏ ပြဋ္ဌာန်းချက်အဓိပ္ပာယ် အများဆုံးကိုက်ညီသောကြောင့်` : null),
      ];
      break;
    case "main_section_selected":
      title = "အဓိကဥပဒေနှင့် ပုဒ်မကို ရွေးချယ်ခဲ့သည်";
      description = `အဆင့်သတ်မှတ်ထားသော candidate များမှ မေးခွန်း၏ဖြစ်စဉ်နှင့် အထောက်အထားအများဆုံးကိုက်ညီသော${selectedLaw ? ` “${selectedLaw}”` : " ဥပဒေ"}${selectedSection ? `၊ ${selectedSection}` : "နှင့် ပုဒ်မ"} ကို အဓိကရည်ညွှန်းချက်အဖြစ် ရွေးချယ်ခဲ့သည်။`;
      facts = [fact("ရွေးချယ်သောဥပဒေ", selectedLaw), fact("အဓိကပုဒ်မ", selectedSection), fact("Source အရေအတွက်", d.source_count), fact("အဖြေတည်ဆောက်ပုံ", d.response_mode)];
      break;
    case "punishment_linked":
      title = d.required === false ? "ပြစ်ဒဏ်သတ်မှတ်ချက် မလိုအပ်ကြောင်း စစ်ဆေးခဲ့သည်" : d.found ? "သက်ဆိုင်ရာပြစ်ဒဏ်သတ်မှတ်ချက်ကို တွေ့ရှိခဲ့သည်" : "ပြစ်ဒဏ်သတ်မှတ်ချက်ကို အတည်မပြုနိုင်သေးပါ";
      description = d.required === false
        ? "မေးခွန်း၏အကြောင်းအရာအရ ပြစ်ဒဏ်သတ်မှတ်ချက်ထည့်သွင်းရန် မလိုအပ်ကြောင်း စစ်ဆေးတွေ့ရှိခဲ့သည်။"
        : d.found
          ? d.same_section
            ? `${sectionLabel(d.offense_section || item.selected_section)} တွင် ပြစ်မှုဖော်ပြချက်နှင့် ပြစ်ဒဏ်သတ်မှတ်ချက်ကို တစ်ပါတည်းပြဋ္ဌာန်းထားကြောင်း source နှင့် တိုက်ဆိုင်စစ်ဆေးခဲ့သည်။`
            : `${sectionLabel(d.offense_section || item.selected_section) || "ပြစ်မှုပုဒ်မ —"} နှင့် ဆက်စပ်သော ${sectionLabel(d.section || item.punishment_section) || "ပြစ်ဒဏ်ပုဒ်မ"} ကို source အတွင်း ရှာဖွေတွေ့ရှိပြီး ချိတ်ဆက်ခဲ့သည်။`
          : "ပြစ်ဒဏ်သတ်မှတ်ချက်လိုအပ်မှုကို စစ်ဆေးခဲ့သော်လည်း ခိုင်လုံစွာချိတ်ဆက်နိုင်သော ပြစ်ဒဏ်ပုဒ်မ မတွေ့ရှိခဲ့ပါ။";
      facts = [
        fact("ပြစ်မှုပုဒ်မ", sectionLabel(d.offense_section || item.selected_section)),
        fact("ပြစ်ဒဏ်ပုဒ်မ", sectionLabel(d.section || item.punishment_section)),
        fact("ချိတ်ဆက်မှုပုံစံ", d.found ? (d.same_section ? "ပြစ်မှုနှင့် ပြစ်ဒဏ်ကို ပုဒ်မတစ်ခုတည်းတွင် ပြဋ္ဌာန်းထားသည်" : "သီးခြားပြစ်ဒဏ်ပုဒ်မနှင့် ချိတ်ဆက်ထားသည်") : null),
        fact("ပြစ်ဒဏ်အကျဉ်း", d.punishment_excerpt),
      ];
      break;
    case "evidence_validated":
      title = "အဖြေ၏ ဥပဒေအထောက်အထားကို စစ်ဆေးအတည်ပြုခဲ့သည်";
      description = d.answerable === false || item.answerable === false
        ? "ရွေးချယ်ထားသောအချက်အလက်များကို source များနှင့် စစ်ဆေးရာတွင် ခိုင်လုံသောအထောက်အထား မလုံလောက်သဖြင့် မသေချာသောပုဒ်မကို အဖြေအဖြစ်မတင်ပြရန် သတ်မှတ်ခဲ့သည်။"
        : `ရွေးချယ်ထားသော ဥပဒေ၊ အဓိကပုဒ်မနှင့် ဆက်စပ်ပြစ်ဒဏ်တို့ကို stored source များနှင့် တိုက်ဆိုင်စစ်ဆေးခဲ့သည်${hasValue(d.verified_source_count) ? `။ အတည်ပြုနိုင်သော source ${number(d.verified_source_count)} ခု တွေ့ရှိခဲ့သည်။` : "။"}`;
      facts = [
        fact("အတည်ပြုထားသောဥပဒေ", d.law_name || item.selected_law),
        fact("အတည်ပြုထားသောပုဒ်မ", sectionLabel(d.section || item.selected_section)),
        fact("အသုံးပြုသော Source", d.source_names),
        fact("ပြစ်ဒဏ်အထောက်အထား", (d.punishment_found ?? Boolean(item.punishment_section)) ? "တွေ့ရှိပြီး" : "မတွေ့ရှိ"),
        fact("နောက်ဆုံးဆုံးဖြတ်ချက်", (d.answerable ?? item.answerable) ? "အဖြေပေးရန် အထောက်အထားလုံလောက်သည်" : "အဖြေပေးရန် အထောက်အထားမလုံလောက်ပါ"),
      ];
      break;
    case "answer_composed":
      title = "အတည်ပြုထားသော ဥပဒေအချက်အလက်များဖြင့် အဖြေတည်ဆောက်ခဲ့သည်";
      description = item.answerable
        ? "စစ်ဆေးအတည်ပြုပြီးသော source များ၊ အဓိကပုဒ်မနှင့် ပြစ်ဒဏ်သတ်မှတ်ချက်တို့ကိုသာ အသုံးပြု၍ အသုံးပြုသူမြင်မည့်အဖြေကို တည်ဆောက်ခဲ့သည်။"
        : "ခိုင်လုံသော source မလုံလောက်သဖြင့် မသက်ဆိုင်သောပုဒ်မကို ခန့်မှန်းဖော်ပြခြင်းမပြုဘဲ အထောက်အထားမလုံလောက်သည့် ရလဒ်ကို တည်ဆောက်ခဲ့သည်။";
      facts = [fact("အဖြေစာလုံးရေ", d.answer_length), fact("အဖြေပေးနိုင်မှု", d.answerable ?? item.answerable)];
      break;
  }

  return {title, description, facts: facts.filter(Boolean)};
}

function queryRunCard(item) {
  const when = new Date(item.created_at).toLocaleString("my-MM");
  const outcome = item.answerable ? "အဖြေပေးပြီး" : "အထောက်အထားမလုံလောက်";
  return `<button class="query-run-card" data-run-id="${item.id}"><span class="query-run-question">${escapeHtml(item.question)}</span><span class="query-run-meta">${escapeHtml(when)} · ${number(item.total_ms)} ms</span><span class="badge ${item.answerable ? "" : "warn"}">${outcome}</span></button>`;
}

async function loadQueryRuns() {
  $("queryRunList").innerHTML = '<div class="empty">မေးခွန်းမှတ်တမ်း ရယူနေသည်…</div>';
  try {
    const data = await api("/api/admin/query-runs");
    $("queryRunList").innerHTML = data.items.length
      ? data.items.map(queryRunCard).join("")
      : '<div class="empty">Trace အသစ်မရှိသေးပါ။ User UI မှ မေးခွန်းတစ်ခု စမ်းကြည့်ပါ။</div>';
    if (data.items.length) loadQueryRunDetail(data.items[0].id);
  } catch (error) {
    $("queryRunList").innerHTML = `<div class="empty failure">${escapeHtml(error.message)}</div>`;
  }
}

async function loadQueryRunDetail(runId) {
  $("queryRunDetail").innerHTML = '<div class="empty">Timeline ရယူနေသည်…</div>';
  document.querySelectorAll(".query-run-card").forEach((card) => card.classList.toggle("selected", card.dataset.runId === String(runId)));
  try {
    const item = await api(`/api/admin/query-runs/${encodeURIComponent(runId)}`);
    const answerState = item.answerable ? "အထောက်အထားခိုင်လုံ" : "အထောက်အထားမလုံလောက်";
    const evidence = [
      ["စကားလုံးနှင့် အဓိပ္ပာယ်ကိုက်ညီမှု", true],
      ["ဥပဒေအမျိုးအစား ကိုက်ညီမှု", Boolean(item.selected_law)],
      ["အဓိကပုဒ်မ ရွေးချယ်နိုင်မှု", Boolean(item.selected_section)],
      ["ပြစ်ဒဏ်ပုဒ်မ ချိတ်ဆက်မှု", Boolean(item.punishment_section)],
      ["အထောက်အထား စစ်ဆေးမှု", Boolean(item.answerable)],
    ].map(([label, ok]) => `<li class="${ok ? "passed" : "pending"}"><i>${ok ? "✓" : "!"}</i><span>${label}</span></li>`).join("");
    const summary = `<div class="trace-review-grid"><div class="trace-conversation"><article class="question-card"><span>အသုံးပြုသူမေးခွန်း</span><h3>${escapeHtml(item.question)}</h3></article><article class="result-card"><span>စနစ်ရလဒ်</span><div class="trace-facts"><span><b>ရွေးချယ်သောဥပဒေ</b>${escapeHtml(item.selected_law || "—")}</span><span><b>အဓိကပုဒ်မ</b>${escapeHtml(item.selected_section || "—")}</span><span><b>ပြစ်ဒဏ်ပုဒ်မ</b>${escapeHtml(item.punishment_section || "—")}</span><span><b>စုစုပေါင်းကြာချိန်</b>${number(item.total_ms)} ms</span></div><em class="answer-state ${item.answerable ? "" : "warn"}">${answerState}</em></article></div><aside class="evidence-card"><span class="eyebrow">EVIDENCE DECISION</span><h3>ဘာကြောင့် ဤအဖြေကို ရွေးချယ်ခဲ့သနည်း?</h3><ul>${evidence}</ul><div class="confidence"><span>ရွေးချယ်မှုယုံကြည်ချက်</span><b>${item.answerable ? "ခိုင်လုံ" : "စစ်ဆေးရန်"}</b></div></aside></div>`;
    const longestDuration = Math.max(0, ...(item.steps || []).map((step) => Number(step.duration_ms || 0)));
    const steps = (item.steps || []).map((step) => {
      const explanation = describeTraceStep(step, item, longestDuration);
      const keyFacts = explanation.facts.length ? `<div class="trace-key-facts">${explanation.facts.join("")}</div>` : "";
      const body = step.step_name === "hybrid_retrieval"
        ? `${keyFacts}<p class="trace-step-explanation">${escapeHtml(explanation.description)}</p>`
        : `<p class="trace-step-explanation">${escapeHtml(explanation.description)}</p>${keyFacts}`;
      return `<article class="trace-step ${escapeHtml(step.status)} ${step.step_name === "hybrid_retrieval" ? "retrieval-insights" : ""}"><i></i><div><div class="trace-step-head"><h3>${escapeHtml(explanation.title)}</h3><span>${escapeHtml(durationLabel(step.duration_ms))}</span></div>${body}</div></article>`;
    }).join("");
    $("queryRunDetail").innerHTML = `${summary}<div class="timeline-heading"><span class="eyebrow">PROCESS TIMELINE</span><h2>တစ်ဆင့်ချင်းလုပ်ဆောင်မှုနှင့် ကြာချိန်</h2></div><div class="trace-timeline">${steps}</div>`;
  } catch (error) {
    $("queryRunDetail").innerHTML = `<div class="empty failure">${escapeHtml(error.message)}</div>`;
  }
}

function processCard(item) {
  const stage = item.stage || "Uploaded";
  const stageIndex = {Uploaded: 1, Extracted: 2, Chunked: 3, Embedded: 4, Indexed: 5}[stage] || 1;
  const labels = ["Uploaded", "Extracted", "Chunked", "Embedded", "Indexed"];
  const download = item.status === "chunked" && item.id
    ? `<a class="download-link" href="/api/admin/download/${encodeURIComponent(item.id)}">Chunks JSON Download</a>` : "";
  return `<article class="process-item"><div class="process-top"><div><h3>${escapeHtml(item.law_name)}</h3><small>${escapeHtml(item.file_name || item.format || "document")} · ${number(item.chunks)} chunks · ${number(item.embeddings)} embeddings</small>${download}</div><span class="badge ${stage === "Indexed" ? "" : "warn"}">${stage}</span></div><div class="steps">${labels.map((_, index) => `<i class="step ${index < stageIndex ? "done" : index === stageIndex ? "current" : ""}"></i>`).join("")}</div><div class="process-caption">${labels.map((label) => `<span>${label}</span>`).join("")}</div></article>`;
}

async function loadProcessing() {
  $("processingList").innerHTML = '<div class="empty">ဒေတာရယူနေသည်…</div>';
  try {
    const data = await api("/api/admin/processing");
    $("processingList").innerHTML = data.items.length ? data.items.map(processCard).join("") : '<div class="empty">စာတမ်းမရှိသေးပါ။</div>';
  } catch (error) { $("processingList").innerHTML = `<div class="empty failure">${escapeHtml(error.message)}</div>`; }
}

async function loadQuality() {
  $("qualityList").innerHTML = '<div class="empty">စစ်ဆေးနေသည်…</div>';
  try {
    const data = await api("/api/admin/quality");
    $("healthyDocs").textContent = number(data.summary.healthy);
    $("reviewDocs").textContent = number(data.summary.review);
    $("qualityIssues").textContent = number(data.summary.issues);
    $("qualityList").innerHTML = data.documents.map((item) => {
      const issues = item.issues || [];
      return `<article class="quality-item"><div><h3>${escapeHtml(item.law_name)}</h3><div class="issue-tags">${issues.length ? issues.map((issue) => `<span class="issue-tag">${escapeHtml(issue)}</span>`).join("") : '<span class="issue-tag good">ပြဿနာမတွေ့ပါ</span>'}</div></div><span class="quality-score ${issues.length ? "failure" : "success"}">${issues.length ? "စစ်ဆေးရန်" : "ကောင်းမွန်"}</span></article>`;
    }).join("");
  } catch (error) { $("qualityList").innerHTML = `<div class="empty failure">${escapeHtml(error.message)}</div>`; }
}

document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item === button));
  showView(button.dataset.view);
}));

$("lawSearch").addEventListener("input", (event) => renderDocuments(event.target.value));
$("refreshProcessing").addEventListener("click", loadProcessing);
$("refreshQueries").addEventListener("click", loadQueryRuns);
$("refreshQuality").addEventListener("click", loadQuality);
$("queryRunList").addEventListener("click", (event) => {
  const card = event.target.closest("[data-run-id]");
  if (card) loadQueryRunDetail(card.dataset.runId);
});
$("lawFile").addEventListener("change", (event) => { $("fileName").textContent = event.target.files[0]?.name || "ဖိုင်အရွယ်အစား 25 MB အထိ"; });
$("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("uploadButton"); const message = $("uploadMessage");
  button.disabled = true; message.className = ""; message.textContent = "Upload တင်နေသည်…";
  try {
    const data = await api("/api/admin/upload", {method: "POST", body: new FormData(event.target)});
    message.className = "success"; message.textContent = data.message;
    event.target.reset(); $("fileName").textContent = "ဖိုင်အရွယ်အစား 25 MB အထိ";
  } catch (error) { message.className = "failure"; message.textContent = error.message; }
  finally { button.disabled = false; }
});

$("embeddingCsv").addEventListener("change", (event) => {
  $("csvFileName").textContent = event.target.files[0]?.name || "*_embedded.csv · 100 MB အထိ";
});
$("csvImportForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("csvImportButton"); const message = $("csvImportMessage");
  button.disabled = true; message.className = ""; message.textContent = "Embedding CSV ကိုစစ်ဆေးပြီး database ထဲသို့ import လုပ်နေသည်…";
  try {
    const data = await api("/api/admin/import-csv", {method: "POST", body: new FormData(event.target)});
    message.className = "success"; message.textContent = data.message;
    event.target.reset(); $("csvFileName").textContent = "*_embedded.csv · 100 MB အထိ";
    await loadDashboard();
  } catch (error) { message.className = "failure"; message.textContent = error.message; }
  finally { button.disabled = false; }
});

loadDashboard();
