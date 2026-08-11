import json
import re
import unicodedata
import urllib.request


MYANMAR_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
ALLOWED_STATUSES = {"စိစစ်ပြီး", "အရေးကြီး", "မလုံလောက်"}


SYSTEM_PROMPT = """သင်သည် မြန်မာဥပဒေစာတမ်းများကို စိစစ်ပေးသော evidence-grounded legal research assistant ဖြစ်သည်။

မဖြစ်မနေလိုက်နာရန် စည်းကမ်းများ-
1. ပေးထားသော ဥပဒေအထောက်အထားများအတွင်းမှသာ ဖြေပါ။ ပြင်ပဗဟုသုတ၊ ခန့်မှန်းချက်၊ မရှိသောပုဒ်မ သို့မဟုတ် ပြစ်ဒဏ်ကို မထည့်ပါနှင့်။
2. မေးခွန်းကို တိုက်ရိုက်ဖြေသောပုဒ်မကို အဓိကပုဒ်မအဖြစ် ရွေးပြီး အဓိပ္ပာယ်ဖွင့်ဆိုချက်၊ ကာကွယ်မှု၊ လျှောက်ထားခွင့်၊ ပြစ်ဒဏ် သို့မဟုတ် အမိန့်အကောင်အထည်ဖော်မှုဆိုင်ရာပုဒ်မများကိုသာ ဆက်စပ်ပုဒ်မအဖြစ် ရွေးပါ။
3. မေးခွန်းနှင့် တိုက်ရိုက်သက်ဆိုင်သော ဥပဒေအထောက်အထား မရှိပါက answerable=false ဟုပြန်ပါ။ အနီးစပ်ဆုံးပုဒ်မကို အတင်းမချိတ်ပါနှင့်။
4. ဥပဒေက မသတ်မှတ်ထားသော အချက်ကို မထည့်ပါနှင့်။ ပြစ်မှု၊ တာဝန်၊ အခွင့်အရေး၊ ပြစ်ဒဏ်နှင့် ငွေပမာဏကို evidence ထဲရှိအတိုင်းသာ ရေးပါ။
5. အဖြေကို မြန်မာဘာသာဖြင့် တိုတိုရှင်းရှင်းရေးပါ။ ဥပဒေစာသားအပြည့် မကူးပါနှင့်။
6. supporting_quote သည် evidence ထဲမှ မေးခွန်းကို တိုက်ရိုက်ထောက်ခံသော စာသားတိုကို မပြောင်းဘဲ ကူးထားရမည်။
7. JSON object တစ်ခုတည်းသာ ပြန်ပါ။ Markdown မသုံးပါနှင့်။

JSON fields:
answerable (boolean), status (စိစစ်ပြီး|အရေးကြီး|မလုံလောက်), classification {name,severity,reasoning}, facts [{label,value}], decision, law_summary, penalty (string or null), recommended_actions [string], related_sections [{role,citation,summary}], supporting_quote, cited_sections [string].
"""


def _clean_text(value, limit):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _normalize_digits(value):
    return unicodedata.normalize("NFC", str(value or "")).translate(MYANMAR_DIGITS)


def _numeric_tokens(value):
    normalized = _normalize_digits(value).replace(",", "")
    return set(re.findall(r"\d+(?:\.\d+)?", normalized))


def _citation_sections(value):
    normalized = _normalize_digits(value)
    return set(re.findall(r"ပုဒ်မ\s*([0-9]+)", normalized))


def _normalize_for_quote(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value or "")))


def build_evidence_prompt(question, evidence):
    blocks = []
    for index, item in enumerate(evidence, start=1):
        subsection = f"({item['subsection']})" if item.get("subsection") else ""
        heading = (
            f"[E{index}] {item['law_name']} | {item.get('chapter') or '-'} | "
            f"ပုဒ်မ {item.get('section') or '-'}{subsection}"
        )
        full_content = _clean_text(item.get("content"), 1600)
        matched_excerpt = _clean_text(item.get("matched_excerpt"), 520)
        if matched_excerpt and _normalize_for_quote(matched_excerpt) not in _normalize_for_quote(full_content):
            content = f"တိုက်ရိုက်ကိုက်ညီသည့်စာပိုဒ်: {matched_excerpt}\nပုဒ်မအကြောင်းအရာ: {full_content}"
        else:
            content = full_content
        blocks.append(f"{heading}\n{content}")
    return (
        f"မေးခွန်း/ဖြစ်ရပ်:\n{question}\n\n"
        f"ဥပဒေအထောက်အထားများ:\n" + "\n\n".join(blocks)
    )


def call_grounded_model(question, evidence, url, model, timeout=240):
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_evidence_prompt(question, evidence)},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 1100,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    model_request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(model_request, timeout=timeout) as response:
        payload = json.load(response)
    content = ((payload.get("message") or {}).get("content") or "").strip()
    return json.loads(content)


def validate_and_normalize(result, question, evidence):
    if not isinstance(result, dict):
        raise ValueError("grounded model did not return an object")

    if not result.get("answerable"):
        return {
            "rule_id": "insufficient_evidence",
            "mode": "insufficient_evidence",
            "status": "မလုံလောက်",
            "facts": [
                {"label": "မေးမြန်းသည့်အကြောင်းအရာ", "value": _clean_text(question, 260)},
                {"label": "စိစစ်မှုရလဒ်", "value": "တိုက်ရိုက်သက်ဆိုင်သော ဥပဒေအထောက်အထား မလုံလောက်ပါ။"},
            ],
            "classification": {
                "name": "ခိုင်လုံသော ဥပဒေအထောက်အထား မတွေ့ရှိ",
                "severity": "အဖြေထုတ်ပြန်ရန် အထောက်အထားမလုံလောက်",
                "reasoning": "လက်ရှိထည့်သွင်းထားသော ဥပဒေစာတမ်းများအတွင်းမှ တိုက်ရိုက်အတည်ပြု၍ မရပါ။",
            },
            "law_summary": "လက်ရှိဒေတာဘေ့စ်မှ ခိုင်လုံစွာကိုးကားနိုင်သည့် ပုဒ်မ မတွေ့ရှိပါ။",
            "decision": "မသေချာသော ဥပဒေအဖြေကို စနစ်က မထုတ်ပြန်ပါ။",
            "penalty": None,
            "recommended_actions": ["မေးခွန်း၏ ဖြစ်ရပ်၊ သက်ဆိုင်သူနှင့် လုပ်ရပ်ကို ပိုမိုတိကျစွာ ဖော်ပြရန်"],
            "related_sections": [],
            "confidence": {"label": "နိမ့်", "basis": "တိုက်ရိုက်အထောက်အထားမလုံလောက်ခြင်း"},
        }

    evidence_sections = {
        _normalize_digits(item.get("section"))
        for item in evidence
        if item.get("section")
    }
    cited_sections = set()
    for citation in result.get("cited_sections") or []:
        cited_sections.update(_citation_sections(citation))
    for item in result.get("related_sections") or []:
        cited_sections.update(_citation_sections(item.get("citation")))
    if not cited_sections or not cited_sections.issubset(evidence_sections):
        raise ValueError("model cited a section outside the retrieved evidence")

    evidence_text = " ".join(str(item.get("content") or "") for item in evidence)
    evidence_labels = " ".join(
        " ".join(
            str(item.get(field) or "")
            for field in ("law_name", "chapter", "section", "subsection")
        )
        for item in evidence
    )
    quote = _clean_text(result.get("supporting_quote"), 320)
    if not quote or _normalize_for_quote(quote) not in _normalize_for_quote(evidence_text):
        raise ValueError("supporting quote is not present in retrieved evidence")

    penalty = _clean_text(result.get("penalty"), 320) or None

    classification = result.get("classification") or {}
    facts = []
    for fact in (result.get("facts") or [])[:5]:
        if isinstance(fact, dict) and fact.get("label") and fact.get("value"):
            facts.append(
                {
                    "label": _clean_text(fact["label"], 80),
                    "value": _clean_text(fact["value"], 220),
                }
            )
    related = []
    for item in (result.get("related_sections") or [])[:4]:
        if not isinstance(item, dict):
            continue
        citation = _clean_text(item.get("citation"), 80)
        summary = _clean_text(item.get("summary"), 260)
        if citation and summary:
            related.append(
                {
                    "role": _clean_text(item.get("role") or "ဆက်စပ်", 40),
                    "citation": citation,
                    "summary": summary,
                }
            )
    if not related:
        raise ValueError("model did not provide validated related sections")

    numeric_claim_text = " ".join(
        [
            str(result.get("decision") or ""),
            str(result.get("law_summary") or ""),
            str(penalty or ""),
            *(item["summary"] for item in related),
        ]
    )
    allowed_numbers = _numeric_tokens(
        f"{question} {evidence_labels} {evidence_text}"
    )
    if not _numeric_tokens(numeric_claim_text).issubset(allowed_numbers):
        raise ValueError("answer contains a number outside the question or retrieved evidence")

    actions = [
        _clean_text(action, 240)
        for action in (result.get("recommended_actions") or [])[:4]
        if _clean_text(action, 240)
    ]
    status = result.get("status")
    if status not in ALLOWED_STATUSES:
        status = "စိစစ်ပြီး"

    decision = _clean_text(result.get("decision"), 520)
    law_summary = _clean_text(result.get("law_summary"), 520)
    classification_name = _clean_text(classification.get("name"), 180)
    if not decision or not law_summary or not classification_name:
        raise ValueError("model omitted a required grounded answer field")

    return {
        "rule_id": "grounded_rag",
        "mode": "grounded_legal_analysis",
        "status": status,
        "facts": facts,
        "classification": {
            "name": classification_name,
            "severity": _clean_text(classification.get("severity"), 180),
            "reasoning": _clean_text(classification.get("reasoning"), 360),
        },
        "law_summary": law_summary,
        "decision": decision,
        "penalty": penalty,
        "recommended_actions": actions,
        "related_sections": related,
        "confidence": {
            "label": "မြင့်",
            "basis": "ပြန်လည်ကိုးကားစစ်ဆေးပြီးသော ဥပဒေပုဒ်မနှင့် တိုက်ရိုက်အထောက်အထား",
        },
    }
