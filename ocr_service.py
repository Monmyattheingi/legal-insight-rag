import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request

import psycopg
import pytesseract
from psycopg.rows import dict_row
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from flask import Flask, jsonify, request, send_from_directory
from grounded_answer import call_grounded_model, validate_and_normalize
from legal_analysis import classify_case
from penalty_matching import _penalty_concept_names, _penalty_concept_overlap
from pdf2image import convert_from_path, pdfinfo_from_path

app = Flask(__name__)

LANGUAGES = os.getenv("OCR_LANGUAGES", "mya+eng")
DPI = int(os.getenv("OCR_DPI", "300"))
PSM = int(os.getenv("OCR_PSM", "6"))
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "100"))
MAX_FILE_BYTES = int(os.getenv("OCR_MAX_FILE_MB", "50")) * 1024 * 1024
ALLOWED_LANGUAGES = {"mya", "eng", "mya+eng"}
ALLOWED_PSM = {3, 4, 6, 11, 12}
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "legal_rag"),
    "user": os.getenv("POSTGRES_USER", "legal_rag"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}
OLLAMA_EMBED_URL = os.getenv(
    "OLLAMA_EMBED_URL",
    "http://host.docker.internal:11434/api/embed",
)
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3-q4")
OLLAMA_CHAT_URL = os.getenv(
    "OLLAMA_CHAT_URL",
    "http://host.docker.internal:11434/api/chat",
)
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:1.5b")
ENABLE_AI_LAW_SUMMARY = os.getenv("ENABLE_AI_LAW_SUMMARY", "0") == "1"
MAX_QUESTION_CHARS = 1000
MIN_SEMANTIC_SCORE = float(os.getenv("MIN_SEMANTIC_SCORE", "0.68"))
MIN_SEMANTIC_MARGIN = float(os.getenv("MIN_SEMANTIC_MARGIN", "0.035"))
STRONG_SEMANTIC_SCORE = float(os.getenv("STRONG_SEMANTIC_SCORE", "0.78"))

ENGLISH_QUERY_EXPANSIONS = (
    (r"\bpasswords?\b", " စကားဝှက် လျှို့ဝှက်နံပါတ် ဝင်ရောက်ခွင့်အချက်အလက် "),
    (r"\baccounts?\b", " အကောင့် အသုံးပြုသူအကောင့် ကွန်ပျူတာစနစ် "),
    (r"\bdata\b", " သတင်းအချက်အလက် အီလက်ထရောနစ်သတင်းအချက်အလက် ကိုယ်ရေးအချက်အလက် "),
    (r"\bpersonal\s+data\b", " ကိုယ်ရေးအချက်အလက် "),
    (r"\bphishing\b", " လိမ်လည်လှည့်ဖြား link အတု ချိတ်ဆက်လင့်ခ် ငွေကြေးလိမ်လည် "),
    (r"\blink\b", " ချိတ်ဆက်လင့်ခ် ချိတ်ဆက်မှု ကွန်ရက် "),
    (r"\blinks\b", " ချိတ်ဆက်လင့်ခ် ချိတ်ဆက်မှု ကွန်ရက် "),
    (r"\bwebsite\b", " ဝက်ဘ်ဆိုက် ကွန်ရက် "),
    (r"\bemail\b", " အီးမေးလ် အီလက်ထရောနစ်သတင်းအချက်အလက် "),
    (r"\bhack(?:ed|ing)?\b", " ခွင့်ပြုချက်မရှိဘဲ ဝင်ရောက်ခြင်း ထိန်းချုပ်ခြင်း ချိတ်ဆက်ထိန်းချုပ်ခြင်း "),
    (r"\blogin\b", " ဝင်ရောက်ခြင်း အသုံးပြုခွင့် "),
    (r"\bpassport\b", " နိုင်ငံကူးလက်မှတ် ပြည်ဝင်ပြည်ထွက် ခရီးသွားစာရွက်စာတမ်း "),
    (r"\bvisa\b", " ပြည်ဝင်ခွင့် နိုင်ငံကူးလက်မှတ် ပြည်ဝင်ပြည်ထွက် "),
    (r"\bdrug(?:s)?\b", " မူးယစ်ဆေးဝါး စိတ်ကိုပြောင်းလဲစေသောဆေးဝါး သုံးစွဲ ရောင်းချ သယ်ဆောင် "),
    (r"\bnarcotic(?:s)?\b", " မူးယစ်ဆေးဝါး စိတ်ကိုပြောင်းလဲစေသောဆေးဝါး "),
    (r"\bhuman\s+rights?\b", " လူ့အခွင့်အရေး လူ့အခွင့်အရေး ချိုးဖောက် တိုင်ကြား ကော်မရှင် "),
    (r"\bpatent\b", " တီထွင်မှု မူပိုင်ခွင့် မူပိုင်ခွင့် တီထွင်သူ "),
    (r"\bfacebook\b", " ဖေ့စ်ဘွတ် လူမှုကွန်ရက် ဆက်သွယ်ရေးကွန်ရက် "),
    (r"\bsocial\s+media\b", " လူမှုကွန်ရက် ဆက်သွယ်ရေးကွန်ရက် "),
    (r"\btelegram\b", " တယ်လီဂရမ် လူမှုကွန်ရက် ဆက်သွယ်ရေးကွန်ရက် "),
    (r"\bviber\b", " ဗိုက်ဘာ လူမှုကွန်ရက် ဆက်သွယ်ရေးကွန်ရက် "),
    (r"\bonline\b", " အွန်လိုင်း ဆက်သွယ်ရေးကွန်ရက် "),
)


# Common spoken/colloquial Myanmar expressions are expanded to the formal
# legal vocabulary used by the indexed statutes.  The original wording is
# retained in the search text, so semantic retrieval can still use it.
MYANMAR_QUERY_EXPANSIONS = (
    # Cyber / electronic accounts
    (r"(?:အကောင့်|အေကာင့်)(?:ကို)?\s*(?:ဖောက်|ခိုးဝင်|ခိုးသုံး)", " အကောင့် ခွင့်ပြုချက်မရှိဘဲ ဝင်ရောက်ခြင်း hack "),
    (r"စကားဝှက်(?:ကို)?\s*(?:ခိုး|ယူ|သိမ်း)", " စကားဝှက် ကိုယ်ရေးအချက်အလက် ခွင့်ပြုချက်မရှိဘဲ ရယူခြင်း "),
    (r"(?:လင့်ခ်|link)\s*အတု", " phishing link အတု လိမ်လည်လှည့်ဖြား "),
    (r"အချက်အလက်\s*(?:ခိုး|ယူ|ပေါက်ကြား)", " data ကိုယ်ရေးအချက်အလက် ခွင့်ပြုချက်မရှိဘဲ ရယူခြင်း "),

    # Passport / travel document
    (r"ပတ်စ်?ပို့", " နိုင်ငံကူးလက်မှတ် passport "),
    (r"နိုင်ငံခြားသွား\s*စာအုပ်", " နိုင်ငံကူးလက်မှတ် passport "),
    (r"(?:တခြားသူ|သူများ|အခြားသူ)(?:ရဲ့|၏)?\s*(?:passport|နိုင်ငံကူးလက်မှတ်)", " မိမိကိုင်ဆောင်ခွင့်မရှိသော နိုင်ငံကူးလက်မှတ် သူတစ်ပါးနိုင်ငံကူးလက်မှတ် အသုံးပြုခြင်း "),

    # Narcotics
    (r"(?:ရာမ|ယာမ|စိတ်ကြွ)\s*ဆေးပြား", " မူးယစ်ဆေးဝါး မက်အင်မ်ဖီတမင်း ဆေးပြား "),
    (r"ဆေး\s*(?:ရောင်းစား|ဖြန့်|ဖြန့်|သယ်ပေး)", " မူးယစ်ဆေးဝါး ရောင်းချ ဖြန့်ဖြူး သယ်ယူပို့ဆောင် "),
    (r"မူးယစ်ဆေး\s*(?:ကိုင်|သိမ်း|ထား)", " မူးယစ်ဆေးဝါး လက်ဝယ်ထားရှိ "),

    # Forestry
    (r"သစ်\s*(?:ခိုးခုတ်|ခိုးထုတ်|ခိုးသယ်)", " သစ်တော သစ်ပင် တရားမဝင် ခုတ်လှဲ သယ်ယူ "),
    (r"တော(?:ထဲ|အတွင်း)\s*(?:က\s*)?သစ်", " သစ်တောနယ်မြေ သစ်ပင် "),
    (r"(?:ကြိုးဝိုင်းတော|ကြိုးပြင်ကာကွယ်တော|သစ်တောနယ်မြေ)", " သစ်တော သစ်တောနယ်မြေ "),
    (r"(?:ကျွန်းပင်|သစ်လုံး)(?:တွေ|များ)?\s*(?:ခိုးခုတ်|ခုတ်|သယ်)", " သစ်တော သစ်ပင် တရားမဝင် ခုတ်လှဲ သယ်ယူ "),
    (r"တောမီး\s*ရှို့", " သစ်တောနယ်မြေ မီးရှို့ ဖျက်ဆီး "),

    # Child protection / education
    (r"ကလေး\s*(?:ကို|အား)?\s*(?:ခိုင်းစား|အလုပ်ကြမ်းခိုင်း)", " ကလေးသူငယ် အဓမ္မအလုပ်ခိုင်းစေခြင်း "),
    (r"ကလေး\s*(?:ကို|အား)?\s*ကျောင်းမထား", " ကလေးသူငယ် ကျောင်းမတက်ခိုင်း ပညာသင်ယူခွင့်ပိတ်ပင်ခြင်း "),
    (r"ကလေး\s*(?:ကို|အား)?\s*(?:ရောင်းစား|ရောင်းချ)", " ကလေးသူငယ် ရောင်းချခြင်း "),
    (r"(?:မိဘ|အုပ်ထိန်းသူ).*(?:စောင့်ရှောက်သူ|စောင့်ရှောက်သူ)?\s*မရှိဘဲ.*(?:ထား|ပစ်)", " ကလေးသူငယ် လျစ်လျူရှုခြင်း အခြေခံလိုအပ်ချက်များ ဖြည့်ဆည်းပေးရန်ပျက်ကွက်ခြင်း ကာကွယ်စောင့်ရှောက်မှုလိုအပ် "),
    (r"ကလေး.*(?:အစာမစား|ဗိုက်ဆာ|အားနည်း|တစ်ယောက်တည်း).*(?:ထား|ဖြစ်)", " ကလေးသူငယ် လျစ်လျူရှုခြင်း ကာကွယ်စောင့်ရှောက်မှုလိုအပ် "),

    # Reputation / communication
    (r"ဂုဏ်(?:ကို|အား)?\s*(?:ထိပါး|ထိခိုက်)", " အသရေဖျက် ဂုဏ်သရေထိခိုက် "),
    (r"နာမည်\s*(?:ဖျက်|ချ)", " အသရေဖျက် နာမည်ပျက် "),

    # Penal-code everyday wording
    (r"အိမ်(?:ထဲ|ခြံထဲ)?\s*(?:ခိုးဝင်|ကျော်ဝင်)", " အိမ်ကျော်နင်း ခိုးဝင်ခြင်း "),
    (r"ပစ္စည်း\s*(?:ခိုးယူ|ခိုးသွား|ယူပြေး)", " ခိုးယူခြင်း ပစ္စည်းခိုးမှု "),
    (r"(?:ငွေ|ပိုက်ဆံ)\s*(?:လိမ်ယူ|လိမ်စား)", " လိမ်လည်လှည့်ဖြား ငွေလိမ် "),
    (r"(?:ထိုး|ရိုက်|ထိုးကြိတ်)\s*(?:တယ်|ခဲ့|လိုက်)", " ရိုက်နှက် နာကျင်စေခြင်း "),
    (r"သတ်\s*(?:ပစ်|လိုက်)", " လူသတ် သေစေခြင်း "),
)


def normalize_query_for_search(question):
    normalized = unicodedata.normalize("NFC", str(question or ""))
    expanded = normalized
    for pattern, replacement in ENGLISH_QUERY_EXPANSIONS:
        expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    for pattern, replacement in MYANMAR_QUERY_EXPANSIONS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            expanded = f"{expanded} {replacement}"
    return re.sub(r"\s+", " ", expanded).strip()


TELECOM_66D_MEDIUM_TERMS = (
    "ဆက်သွယ်ရေး",
    "ဆက်သွယ်ရေးကွန်ရက်",
    "ဖုန်း",
    "မိုဘိုင်း",
    "အွန်လိုင်း",
    "online",
    "internet",
    "facebook",
    "ဖေ့စ်ဘွတ်",
    "ဖေ့ဘွတ်",
    "fb",
    "messenger",
    "telegram",
    "တယ်လီဂရမ်",
    "viber",
    "ဗိုက်ဘာ",
    "လူမှုကွန်ရက်",
    "social media",
)

TELECOM_66D_ACT_TERMS = (
    "အသရေဖျက်",
    "အသရေပျက်",
    "ဂုဏ်သရေ",
    "ဂုဏ်ကိုထိပါး",
    "ဂုဏ်အားထိပါး",
    "ဂုဏ်ထိပါး",
    "ဂုဏ်ကိုထိခိုက်",
    "ဂုဏ်အားထိခိုက်",
    "ဂုဏ်ထိခိုက်",
    "ဂုဏ်သိက္ခာထိခိုက်",
    "ဂုဏ်သိက္ခာကျဆင်း",
    "ဂုဏ်သိက္ခာချ",
    "နာမည်ပျက်",
    "မဟုတ်မမှန်",
    "သတင်းအမှား",
    "အကြောင်းအရာအမှား",
    "နှောင့်ယှက်",
    "နှောင့်ယှက်",
    "စော်ကား",
    "ခြိမ်းခြောက်",
    "ခြောက်လှန့်",
    "ခြောက်လှန့်",
    "တောင်းယူ",
    "blackmail",
    "extort",
    "extortion",
    "harass",
    "harassment",
    "threat",
    "threaten",
    "defamation",
    "reputation",
)


def _is_telecom_66d_query(question):
    text = normalize_query_for_search(question).lower()
    cyber_account_terms = (
        "account",
        "အကောင့်",
        "အေကာင့်",
        "password",
        "စကားဝှက်",
        "login",
        "hack",
        "ခွင့်ပြုချက်မရှိဘဲ ဝင်",
        "ခွင့်ပြုချက်မရှိဘဲ ဝင်",
        "ဝင်ရောက်",
    )
    if any(term in text for term in cyber_account_terms):
        return False
    explicit_section = any(
        marker in text
        for marker in (
            "၆၆(ဃ)",
            "၆၆ (ဃ)",
            "66(d)",
            "66 d",
            "ပုဒ်မ ၆၆",
            "ပုဒ်မ၆၆",
        )
    )
    explicit_law = "ဆက်သွယ်ရေးဥပဒေ" in text
    has_medium = any(term in text for term in TELECOM_66D_MEDIUM_TERMS)
    has_act = any(term in text for term in TELECOM_66D_ACT_TERMS)
    return (explicit_section or explicit_law or has_medium) and has_act


def _preferred_law_name_fragment(question):
    text = normalize_query_for_search(question).lower()
    if _is_telecom_66d_query(text):
        return "ဆက်သွယ်ရေး"
    # A social-media marketplace is only the medium.  When the facts describe
    # advance payment followed by non-delivery/blocking, route to Penal Code
    # cheating rather than treating the word "Facebook" as a cyber offence.
    has_marketplace_payment = any(
        term in text for term in ("ငွေလွှဲ", "ပိုက်ဆံလွှဲ", "ငွေပေး", "payment")
    )
    has_marketplace_deception = any(
        term in text
        for term in ("ပစ္စည်းမပို့", "မပို့ဘဲ", "block လုပ်", "ဘလော့ခ်လုပ်", "ဆက်သွယ်မရ", "ငွေလိမ်")
    )
    if has_marketplace_payment and has_marketplace_deception:
        return "ရာဇသတ်ကြီး"
    if any(
        keyword in text
        for keyword in (
            "password",
            "account",
            "phishing",
            "link",
            "data",
            "hack",
            "login",
            "ဆိုက်ဘာ",
            "ကွန်ပျူတာ",
            "ကွန်ရက်",
            "အီလက်ထရောနစ်",
        )
    ):
        return "ဆိုက်ဘာ"
    if "နိုင်ငံကူးလက်မှတ်" in text or "passport" in text:
        return "နိုင်ငံကူးလက်မှတ်"
    if any(
        keyword in text
        for keyword in (
            "မူးယစ်",
            "စိတ်ကိုပြောင်းလဲ",
            "ဆေးဝါး",
            "drug",
            "drugs",
            "narcotic",
            "ဘိန်း",
            "ဆေးခြောက်",
            "စိတ်ကြွ",
            "ဘိန်းဖြူ",
            "ဟယ်ရိုးအင်း",
            "မော်ဖင်း",
            "မက်အင်",
            "ကိုကင်း",
        )
    ):
        return "မူးယစ်"
    if any(
        keyword in text
        for keyword in (
            "လူ့အခ",
            "လူ့အခွင့်အရေး",
            "လူ့အခွင့်အရေး",
            "human right",
            "human rights",
            "အခွင့်အရေးချိုးဖောက်",
            "အခွင့်အရေးချိုးဖောက်",
            "ကော်မရှင်",
        )
    ):
        return "လူ့အခ"
    if any(
        keyword in text
        for keyword in (
            "တီထွင်မှု",
            "မူပိုင်ခွင့်",
            "မူပိုင်ခွင့်",
            "patent",
            "invention",
            "inventor",
        )
    ):
        return "တီထွင်မှု"
    if any(
        keyword in text
        for keyword in (
            "သစ်တော",
            "သစ်ပင်",
            "သစ်တောထွက်",
            "ကြိုးဝိုင်းတော",
            "ကြိုးပြင်ကာကွယ်တော",
            "ကျွန်းပင်",
            "သစ်လုံး",
        )
    ):
        return "သစ်တော"
    if "ကလေး" in text or "ကလေးသူငယ်" in text:
        return "ကလေးသူငယ်"
    if any(
        keyword in text
        for keyword in (
            "ရာဇသတ်ကြီး",
            "ရာဇဝတ်",
            "penal",
            "ခိုး",
            "ခိုးယူ",
            "လိမ်လည်",
            "လှည့်ဖြား",
            "လှည့်ဖြား",
            "ငွေလိမ်",
            "လူသတ်",
            "သတ်ပစ်",
            "မုဒိမ်း",
            "လုယက်",
            "ဓားပြ",
            "ခြောက်လှန့်",
            "ခြောက်လှန့်",
            "တောင်းယူ",
            "ရိုက်နှက်",
            "နာကျင်",
            "အပြင်းအထန်",
            "အနှောင့်အယှက်",
            "အနှောင့်အယှက်",
            "ဆူညံ",
            "ကျော်နင်း",
            "ကျော်ဝင်",
            "အိမ်ကျော်",
            "အိမ်ဖောက်",
            "အိမ်ခြံ",
            "ဖောက်ထွင်း",
            "ကာယိန္ဒြေ",
            "စော်ကား",
            "ဆဲဆို",
            "အော်ဆဲ",
            "ရန်စ",
            "ကိုယ်အမူအရာ",
            "ဆိတ်ကွယ်ရာ",
            "ပစ္စည်းဖျက်",
            "ဖျက်ဆီး",
            "အကျိုးဖျက်",
            "အသရေ",
            "အသရေဖျက်",
            "အသရေပျက်",
            "ဂုဏ်သရေ",
            "နာမည်ပျက်",
            "မဟုတ်မမှန်",
            "မလုပ်ခဲ့တဲ့",
            "မလုပ်ခဲ့သည့်",
            "စွပ်စွဲ",
            "လူအများရှေ့",
            "ညစ်ညမ်းတဲ့စကား",
            "ညစ်ညမ်းသောစကား",
            "မသင့်တော်တဲ့ကိုယ်အမူအရာ",
            "မသင့်တော်တဲ့ကိုယ်အမူအရာ",
            "နောက်ကလိုက်",
            "အိမ်ထဲဝင်",
            "အိမ်ထဲကိုဝင်",
            "ငွေသားတွေ ယူသွား",
            "ငွေသားယူသွား",
            "ပစ္စည်းမပို့",
            "ငွေလွှဲပြီး",
            "block လုပ်",
            "ဘလော့ခ်လုပ်",
            "ဖောက်ပြန်",
            "မယားခိုး",
            "မတရားကာမ",
            "ကာမစပ်ယှက်",
            "လင်ရှိမယား",
            "အိမ်ထောင်ရှင်မိန်းမ",
            "defamation",
            "reputation",
        )
    ):
        return "ရာဇသတ်ကြီး"
    return None


@app.get("/")
def frontend():
    return send_from_directory("frontend_static", "index.html")


@app.get("/assets/<path:filename>")
def frontend_asset(filename):
    return send_from_directory("frontend_static", filename)


@app.get("/health")
def health():
    # Keep health checks independent of CPU-heavy OCR subprocesses.
    return jsonify(status="ok", languages=LANGUAGES)


@app.get("/api/stats")
def legal_stats():
    try:
        with psycopg.connect(**POSTGRES_CONFIG) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM legal_documents) AS documents,
                      (SELECT count(*) FROM legal_chunks) AS chunks,
                      (SELECT count(*) FROM legal_chunks WHERE embedding IS NOT NULL) AS embeddings
                    """
                )
                return jsonify(cursor.fetchone())
    except psycopg.Error as exc:
        return jsonify(error="database unavailable", detail=str(exc)), 503


def embed_text(text):
    body = json.dumps(
        {
            "model": OLLAMA_EMBED_MODEL,
            "input": text,
            "truncate": True,
            "keep_alive": "30m",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    embedding_request = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(embedding_request, timeout=300) as response:
        payload = json.load(response)

    embeddings = payload.get("embeddings") or []
    if len(embeddings) != 1 or len(embeddings[0]) != 1024:
        raise ValueError("embedding service returned an invalid vector")
    return embeddings[0]


def _character_ngram_recall(query, content, size=6):
    compact_query = re.sub(r"\s+", "", query)
    compact_content = re.sub(r"\s+", "", content)
    if len(compact_query) < size or len(compact_content) < size:
        return 0.0
    query_grams = {
        compact_query[index:index + size]
        for index in range(len(compact_query) - size + 1)
    }
    content_grams = {
        compact_content[index:index + size]
        for index in range(len(compact_content) - size + 1)
    }
    return len(query_grams & content_grams) / max(len(query_grams), 1)


def _meaningful_token_recall(query, content):
    tokens = [
        token.strip("၊။()[]{}'\"“”‘’")
        for token in re.split(r"\s+", str(query or ""))
    ]
    tokens = [
        token
        for token in tokens
        if len(token) >= 3 and token not in {"လူတစ်ဦးက", "တစ်ဦးက", "ပြုလုပ်ခဲ့သည်"}
    ]
    if not tokens:
        return 0.0
    content = str(content or "")
    return sum(1 for token in tokens if token in content) / len(tokens)


def _trace_search_terms(original_question, normalized_question, semantic_rows, penalty_match):
    """Return only human-readable terms that genuinely participated in retrieval."""
    generic = {
        "လူတစ်ဦးက", "တစ်ဦးက", "ပြုလုပ်ခဲ့သည်", "ဖြစ်ပါသလား", "နိုင်ပါသလား",
        "ဘယ်လို", "မည်သို့", "အတွက်", "အကြောင်း", "ပါတယ်", "တယ်လို့",
    }

    def tokens(value):
        result = []
        for token in re.split(r"\s+", str(value or "")):
            cleaned = token.strip("၊။()[]{}'\"“”‘’!?—–-")
            if len(cleaned) >= 3 and cleaned not in generic and cleaned not in result:
                result.append(cleaned)
        return result

    original_terms = tokens(original_question)
    normalized_terms = tokens(normalized_question)
    expanded_terms = [term for term in normalized_terms if term not in original_terms]

    evidence_text = " ".join(
        str(row.get("matched_excerpt") or row.get("content") or "")
        for row in (semantic_rows or [])[:5]
    )
    if penalty_match:
        evidence_text += " " + " ".join(
            str(row.get("matched_excerpt") or row.get("content") or "")
            for row in (penalty_match.get("evidence") or [])
        )

    matched_terms = [term for term in normalized_terms if term in evidence_text]
    search_terms = matched_terms or expanded_terms or normalized_terms

    candidate_laws = []
    for row in (semantic_rows or []):
        law_name = row.get("law_name")
        if law_name and law_name not in candidate_laws:
            candidate_laws.append(law_name)

    route = None
    if penalty_match:
        for row in penalty_match.get("evidence") or []:
            if row.get("matched_by"):
                route = row["matched_by"]
                break

    route_terms = []
    route_key = str(route or "").lower()
    route_term_rules = (
        ("telecom_66d", ["လူမှုကွန်ရက်", "ဂုဏ်သရေထိခိုက်ခြင်း", "အသရေဖျက်ခြင်း"]),
        ("telecom_license", ["ဆက်သွယ်ရေးလိုင်စင်", "ခွင့်ပြုချက်မရှိအသုံးပြုခြင်း"]),
        ("cyber", ["အွန်လိုင်းစနစ်", "အကောင့်နှင့်ဒေတာ", "ဆိုက်ဘာလုံခြုံရေး"]),
        ("penal_adultery", ["အိမ်ထောင်ရှိသူ", "ဖောက်ပြန်ဆက်ဆံခြင်း"]),
        ("penal_defamation", ["အသရေဖျက်ခြင်း", "ဂုဏ်သရေထိခိုက်ခြင်း"]),
        ("penal_house_trespass", ["အိမ်ကျော်နင်းခြင်း", "ခွင့်ပြုချက်မရှိဝင်ရောက်ခြင်း"]),
        ("penal_criminal_trespass", ["ကျူးကျော်ဝင်ရောက်ခြင်း", "အနှောင့်အယှက်ပေးခြင်း"]),
        ("penal_theft", ["ပစ္စည်းခိုးယူခြင်း"]),
        ("penal_cheating", ["လိမ်လည်လှည့်ဖြားခြင်း"]),
        ("penal_robbery", ["လုယက်ခြင်း"]),
        ("penal_rape", ["လိင်ပိုင်းဆိုင်ရာကျူးလွန်ခြင်း"]),
        ("penal_hurt", ["ကိုယ်ထိလက်ရောက်နာကျင်စေခြင်း"]),
        ("forest", ["သစ်တောထွက်ပစ္စည်း", "ခွင့်ပြုချက်မရှိထုတ်ယူခြင်း"]),
        ("passport", ["နိုင်ငံကူးလက်မှတ်", "အတုပြုလုပ်ခြင်း သို့မဟုတ် မမှန်အသုံးပြုခြင်း"]),
        ("drug_quantity", ["မူးယစ်ဆေးဝါး", "သတ်မှတ်ပမာဏ"]),
        ("drug_offense", ["မူးယစ်ဆေးဝါး", "လက်ဝယ်ထားရှိ/သယ်ယူ/ရောင်းချခြင်း"]),
    )
    for route_fragment, terms in route_term_rules:
        if route_fragment in route_key:
            route_terms = terms
            break

    if route_terms:
        matched_terms = route_terms
        search_terms = route_terms

    return {
        "search_terms": search_terms[:8],
        "matched_terms": matched_terms[:8],
        "expanded_terms": expanded_terms[:8],
        "candidate_laws": candidate_laws[:4],
        "matching_route": route,
    }


def _retrieve_hierarchical_sections(cursor, vector, question, category):
    preferred_law = _preferred_law_name_fragment(question)
    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url,
          1 - (c.embedding <=> %s::vector) AS vector_score
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
          AND (%s::text IS NULL OR d.category = %s::text)
          AND (%s::text IS NULL OR d.law_name LIKE %s)
        ORDER BY c.embedding <=> %s::vector
        LIMIT 100
        """,
        (
            vector,
            category,
            category,
            preferred_law,
            f"%{preferred_law}%" if preferred_law else None,
            vector,
        ),
    )
    candidates = cursor.fetchall()
    if not candidates:
        return [], 0.0, 0.0, 0

    section_groups = {}
    chapter_groups = {}
    for row in candidates:
        lexical_score = _character_ngram_recall(question, row["content"])
        # Longer character phrases distinguish exact Burmese legal concepts
        # (for example, education rights) from generic repeated words such as
        # "child". Equal weighting prevents a generic semantic neighbour from
        # outranking a provision containing the user's exact legal phrase.
        hit_score = 0.50 * float(row["vector_score"]) + 0.50 * lexical_score
        row["hit_score"] = hit_score

        section_key = (
            row["document_id"],
            row["chapter"] or "",
            row["section"] or "",
        )
        section_group = section_groups.setdefault(
            section_key,
            {"best_score": 0.0, "hits": [], "sample": row},
        )
        section_group["best_score"] = max(section_group["best_score"], hit_score)
        section_group["hits"].append(row)

        chapter_key = (row["document_id"], row["chapter"] or "")
        chapter_group = chapter_groups.setdefault(
            chapter_key,
            {"best_score": 0.0, "hits": [], "sample": row},
        )
        chapter_group["best_score"] = max(chapter_group["best_score"], hit_score)
        chapter_group["hits"].append(row)

    matching_sections = []
    for key, group in section_groups.items():
        if not key[2]:
            continue
        close_hits = [
            hit
            for hit in group["hits"]
            if hit["hit_score"] >= group["best_score"] - 0.10
        ]
        support_bonus = min(0.025, max(0, len(close_hits) - 1) * 0.006)
        matching_sections.append((group["best_score"] + support_bonus, key, group))
    matching_sections.sort(key=lambda item: item[0], reverse=True)
    best_section_score = matching_sections[0][0] if matching_sections else 0.0
    second_section_score = matching_sections[1][0] if len(matching_sections) > 1 else 0.0
    matching_sections = [
        item for item in matching_sections
        if item[0] >= best_section_score - 0.20
    ][:8]

    sections = []
    for section_score, section_key, group in matching_sections:
        document_id, chapter, section = section_key
        cursor.execute(
            """
            SELECT
              min(c.id) AS chunk_id,
              d.law_name,
              d.law_number,
              c.chapter,
              c.section,
              string_agg(c.content, E'\n' ORDER BY c.chunk_index) AS content,
              d.source_url
            FROM legal_chunks c
            JOIN legal_documents d ON d.id = c.document_id
            WHERE c.document_id = %s
              AND COALESCE(c.chapter, '') = %s
              AND c.section = %s
            GROUP BY d.law_name, d.law_number, c.chapter, c.section, d.source_url
            """,
            (document_id, chapter, section),
        )
        assembled = cursor.fetchone()
        if not assembled:
            continue
        best_hit = max(group["hits"], key=lambda hit: hit["hit_score"])
        assembled["subsection"] = None
        assembled["vector_score"] = section_score
        assembled["matched_by"] = "hierarchical_semantic"
        assembled["matched_excerpt"] = best_hit["content"]
        sections.append(assembled)

    top_chapter = sections[0].get("chapter") if sections else None
    chapter_support = sum(1 for row in sections if row.get("chapter") == top_chapter)
    return sections, best_section_score, best_section_score - second_section_score, chapter_support


PENALTY_CONTEXT_KEYWORDS = (
    "ပြစ်ဒဏ်",
    "ထောင်ဒဏ်",
    "ငွေဒဏ်",
    "အရေးယူ",
    "စီရင်",
    "ကျူးလွန်",
    "ရောင်းချ",
    "ပြည့်တန်ဆာ",
    "နှိပ်စက်",
    "ညှဉ်းပန်း",
    "ရိုက်နှက်",
    "အလွဲသုံး",
    "ခေါင်းပုံဖြတ်",
    "ညစ်ညမ်းပုံ",
    "အဓမ္မအလုပ်",
    "အတင်းအကြပ်လက်ထပ်",
)


PUNISHMENT_TEXT_KEYWORDS = (
    "ပြစ်ဒဏ်",
    "ထောင်ဒဏ်",
    "ငွေဒဏ်",
    "ဒဏ်ငွေ",
    "ပြစ်မှုထင်ရှား",
    "ချမှတ်",
    "အရေးယူ",
    "ကျခံစေရမည်",
    "ဒဏ်နှစ်ရပ်လုံး",
    "ဒဏ်တစ်ရပ်ရပ်",
    "မပိုသော",
)


STRONG_PUNISHMENT_TEXT_KEYWORDS = (
    "ထောင်ဒဏ်",
    "ငွေဒဏ်",
    "ဒဏ်ငွေ",
    "ကျခံစေရမည်",
    "ဒဏ်နှစ်ရပ်လုံး",
)


PUNISHMENT_SQL_PATTERNS = (
    "%ထောင်ဒဏ်%",
    "%ငွေဒဏ်%",
    "%ဒဏ်ငွေ%",
    "%ကျခံစေရမည်%",
    "%ဒဏ်နှစ်ရပ်လုံး%",
)


def _question_may_need_penalty(question):
    text = str(question or "").lower().strip()
    if not text:
        return False

    punishment_or_offense_terms = (
        "ပြစ်ဒဏ်",
        "ထောင်ဒဏ်",
        "ငွေဒဏ်",
        "အရေးယူ",
        "ကျူးလွန်",
        "တရားမဝင်",
        "တရားမ၀င်",
        "ဖောက်ဖျက်",
        "ချိုးဖောက်",
        "မပြုရ",
        "တားမြစ်",
        "အတု",
        "ခိုး",
        "ကျော်နင်း",
        "ကျော်ဝင်",
        "အိမ်ကျော်",
        "အိမ်ခြံ",
        "ဖောက်ထွင်း",
        "ရောင်းချ",
        "စိုက်ပျိုး",
        "သယ်ဆောင်",
        "သုံးစွဲ",
        "ဝင်ရောက်",
        "လိမ်လည်",
        "password",
        "account",
        "phishing",
        "fake",
        "forged",
        "drug",
        "narcotic",
    )
    if any(term in text for term in punishment_or_offense_terms):
        return True

    general_info_terms = (
        "ပြောပြ",
        "ရှင်းပြ",
        "ဘာလဲ",
        "အကြောင်း",
        "သိချင်",
        "about",
        "explain",
        "what is",
    )
    if any(term in text for term in general_info_terms):
        return False

    # Most free-text reports are incident descriptions, so still allow
    # punishment matching unless the input is clearly a general info request.
    return True


def _penalty_row_source(row, matched_by):
    return {
        "chunk_id": row["chunk_id"],
        "law_name": row["law_name"],
        "law_number": row["law_number"],
        "chapter": row["chapter"],
        "section": row["section"],
        "subsection": row["subsection"],
        "content": _clean_display_content(row["content"]),
        "source_url": row["source_url"],
        "score": None,
        "matched_by": matched_by,
    }


def _fetch_law_chunk(cursor, law_fragment, section, subsection=None):
    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE d.law_name LIKE %s
          AND c.section = %s
          AND (
            %s::text IS NULL
            OR c.subsection = %s
          )
        ORDER BY c.chunk_index
        LIMIT 1
        """,
        (f"%{law_fragment}%", section, subsection, subsection),
    )
    return cursor.fetchone()


def _fetch_law_section(cursor, law_fragment, section):
    cursor.execute(
        """
        SELECT
          min(c.id) AS chunk_id,
          min(c.document_id::text)::uuid AS document_id,
          min(c.chunk_index) AS chunk_index,
          min(c.chapter) AS chapter,
          c.section,
          NULL::text AS subsection,
          string_agg(c.content, E'\n' ORDER BY c.chunk_index) AS content,
          d.law_name,
          d.law_number,
          d.source_url
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE d.law_name LIKE %s
          AND c.section = %s
        GROUP BY d.law_name, d.law_number, d.source_url, c.section
        LIMIT 1
        """,
        (f"%{law_fragment}%", section),
    )
    return cursor.fetchone()


def _retrieve_cyber_keyword_match(cursor, question):
    raw_text = str(question or "").lower()
    text = f"{raw_text} {normalize_query_for_search(question).lower()}"
    # Keep this route deterministic.  Asking the generic law router to infer
    # the law from one English token broke once that token was expanded into
    # Burmese before classification.
    cyber_law = "ဆိုက်ဘာ"
    if _preferred_law_name_fragment(text) != cyber_law:
        return None

    if any(keyword in text for keyword in ("phishing", "link", "fake link", "scam")):
        offense = _fetch_law_chunk(cursor, cyber_law, "\u1046\u1048", "\u1004")
        penalty = _fetch_law_chunk(cursor, cyber_law, "\u1046\u1048")
    elif any(keyword in text for keyword in ("account", "login", "hack")):
        offense = _fetch_law_chunk(cursor, cyber_law, "\u1043\u1046", "\u1004")
        penalty = _fetch_law_chunk(cursor, cyber_law, "\u1046\u1047")
    elif any(keyword in text for keyword in ("password", "data")):
        offense = _fetch_law_chunk(cursor, cyber_law, "\u1043\u1046", "\u1002")
        penalty = _fetch_law_chunk(cursor, cyber_law, "\u1046\u1046")
    else:
        return None

    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, "cyber_keyword_offense")
    penalty_source = _penalty_row_source(penalty, "cyber_keyword_penalty")
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([penalty_source], [offense_source]),
        "score": 0.74,
    }


def _retrieve_telecom_66d_match(cursor, question):
    text = unicodedata.normalize("NFC", str(question or "")).lower()
    if not _is_telecom_66d_query(text):
        return None

    telecom_law = "ဆက်သွယ်ရေး"
    offense = _fetch_law_chunk(cursor, telecom_law, "၆၆", "ဃ")
    penalty = _fetch_law_chunk(cursor, telecom_law, "၆၆")
    complaint = None
    if any(term in text for term in ("တိုင်", "တိုင်တန်း", "တိုင်ကြား", "complaint", "အရေးယူ")):
        complaint = _fetch_law_chunk(cursor, telecom_law, "၈၀", "ဂ")
    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, "telecom_66d_offense")
    penalty_source = _penalty_row_source(penalty, "telecom_66d_penalty")
    compact_penalty = re.sub(r"\s+", " ", penalty_source.get("content") or "").strip()
    marker = "ပုဒ်မခွဲ (ဃ)"
    marker_index = compact_penalty.find(marker)
    if marker_index >= 0:
        end_index = compact_penalty.find("ချမှတ်ရမည်", marker_index)
        if end_index >= 0:
            end_index += len("ချမှတ်ရမည်")
            if end_index < len(compact_penalty) and compact_penalty[end_index:end_index + 1] == "။":
                end_index += 1
            penalty_source["matched_excerpt"] = compact_penalty[marker_index:end_index].strip()
        else:
            penalty_source["matched_excerpt"] = compact_penalty[marker_index:].strip()
    evidence = [offense_source, penalty_source]
    if complaint:
        complaint_source = _penalty_row_source(complaint, "telecom_66d_complaint_rule")
        evidence.append(complaint_source)
    else:
        complaint_source = None
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "complaint": complaint_source,
        "evidence": _dedupe_evidence(evidence),
        "score": 0.86,
    }


def _retrieve_telecom_license_equipment_match(cursor, question):
    text = unicodedata.normalize("NFC", str(question or "")).lower()
    compact = re.sub(r"[\s၊။,.()\[\]{}\-_/]+", "", text)
    telecom_law = "ဆက်သွယ်ရေး"
    has_telecom_context = (
        "ဆက်သွယ်ရေး" in text
        or "ရေဒီယိုစက်" in text
        or "စက်ပစ္စည်း" in text
        or "telecom" in text
    )
    if _preferred_law_name_fragment(text) != telecom_law and not has_telecom_context:
        return None

    license_terms = (
        "လိုင်စင်မရှိ",
        "လိုင်စင် မရှိ",
        "လိုင်စင်မယူ",
        "လိုင်စင်မရ",
        "ခွင့်ပြုချက်မရှိ",
        "ခွင့်ပြုချက်မရှိ",
        "license",
        "licence",
        "permit",
    )
    equipment_terms = (
        "ဆက်သွယ်ရေးပစ္စည်း",
        "ဆက်သွယ်ရေးစက်ပစ္စည်း",
        "ပစ္စည်း",
        "စက်ပစ္စည်း",
        "ဖုန်းစက်",
        "ရေဒီယိုစက်",
        "အသုံးပြု",
        "လက်ဝယ်ထား",
        "ကိုင်ဆောင်",
        "equipment",
        "device",
        "possess",
        "use",
    )
    compact_license_terms = tuple(
        re.sub(r"[\s၊။,.()\[\]{}\-_/]+", "", term.lower())
        for term in license_terms
    )
    compact_equipment_terms = tuple(
        re.sub(r"[\s၊။,.()\[\]{}\-_/]+", "", term.lower())
        for term in equipment_terms
    )
    if not (
        any(term and term in compact for term in compact_license_terms)
        and any(term and term in compact for term in compact_equipment_terms)
    ):
        return None

    section = _fetch_law_section(cursor, telecom_law, "\u1046\u1047")
    if not section:
        return None

    source = _penalty_row_source(section, "telecom_license_equipment")
    source["matched_excerpt"] = _extract_punishment_excerpt(source)
    return {
        "offense": source,
        "penalty": source,
        "evidence": [source],
        "score": 0.84,
    }


def _retrieve_forest_keyword_match(cursor, question):
    """Resolve common spoken descriptions of illegal logging to exact clauses."""
    text = normalize_query_for_search(question).lower()
    forest_law = "သစ်တော"
    if _preferred_law_name_fragment(text) != forest_law:
        return None

    cutting_terms = (
        "ခိုးခုတ်",
        "ခုတ်လှဲ",
        "ခုတ်ထွင်",
        "ပိုင်းဖြတ်",
        "သင်းသတ်",
        "သစ်ပင်တွေကို ခုတ်",
        "သစ်ပင်ကို ခုတ်",
    )
    transport_terms = (
        "ခိုးသယ်",
        "သယ်ယူ",
        "သယ်သွား",
        "သယ်ထုတ်",
        "ရွှေ့ပြောင်း",
    )
    fire_terms = ("တောမီး", "မီးရှို့", "မီးဖြင့် ပျက်စီး")

    subsection = None
    if any(term in text for term in fire_terms):
        subsection = "ဃ"
    elif any(term in text for term in cutting_terms):
        subsection = "ခ"
    elif any(term in text for term in transport_terms):
        subsection = "က"
    if not subsection:
        return None

    offense = _fetch_law_chunk(cursor, forest_law, "၄၁", subsection)
    penalty = _fetch_law_chunk(cursor, forest_law, "၄၁")
    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, "forest_spoken_offense")
    penalty_source = _penalty_row_source(penalty, "forest_spoken_penalty")
    penalty_source["matched_excerpt"] = _extract_punishment_excerpt(penalty_source)
    evidence = [offense_source, penalty_source]

    # When a user describes both cutting and carrying the timber away, retain
    # the transport clause as a supporting source without replacing the main
    # cutting offense.
    if subsection == "ခ" and any(term in text for term in transport_terms):
        transport = _fetch_law_chunk(cursor, forest_law, "၄၁", "က")
        if transport:
            evidence.append(_penalty_row_source(transport, "forest_transport_related"))

    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence(evidence),
        "score": 0.88,
    }


def _retrieve_drug_quantity_match(cursor, question):
    text = unicodedata.normalize("NFC", str(question or "")).lower()
    drug_law = _preferred_law_name_fragment("drug")
    explicit_drug_section_26 = (
        ("\u1015\u102f\u1012\u103a\u1019 \u1042\u1046" in text or "\u1015\u102f\u1012\u103a\u1019\u1042\u1046" in text)
        and any(term in text for term in ("\u1021\u1000\u102f\u1014\u103a", "\u1021\u1015\u103c\u100a\u1037\u103a", "\u1021\u1015\u103c\u100a\u103a\u1037", "list", "full"))
    )
    if _preferred_law_name_fragment(text) != drug_law and not explicit_drug_section_26:
        return None

    quantity_terms = (
        "ဂရမ်",
        "ကီလို",
        "မီလီ",
        "အလေးချိန်",
        "ပမာဏ",
        "အရေအတွက်",
        "ရောင်းချရန်အလို့ငှာ",
        "ဘိန်းဖြူ",
        "ဟယ်ရိုးအင်း",
        "မော်ဖင်း",
        "မက်အင်မ်ဖီတမင်း",
        "metamfetamine",
        "methamphetamine",
        "ဘိန်းမဲ",
        "ဘိန်းစာ",
        "ဆေးခြောက်",
        "ကိုကင်း",
        "coca",
        "cocaine",
        "heroin",
        "morphine",
    )
    if not explicit_drug_section_26 and not any(term in text for term in quantity_terms):
        return None

    full_list_terms = (
        "\u1021\u1000\u102f\u1014\u103a",
        "\u1021\u1015\u103c\u100a\u1037\u103a",
        "\u1021\u1015\u103c\u100a\u103a\u1037",
        "\u1021\u102c\u1038\u101c\u102f\u1036\u1038",
        "\u1015\u102f\u1012\u103a\u1019 \u1042\u1046",
        "\u1015\u102f\u1012\u103a\u1019\u1042\u1046",
        "full",
        "all",
        "list",
        "threshold list",
    )
    subsection_matchers = (
        ("\u1000", ("\u1018\u102d\u1014\u103a\u1038\u1016\u103c\u1030", "\u101f\u101a\u103a\u101b\u102d\u102f\u1038\u1021\u1004\u103a\u1038", "heroin")),
        ("\u1001", ("\u1019\u1031\u102c\u103a\u1016\u1004\u103a\u1038", "morphine")),
        ("\u1002", ("\u1019\u1000\u103a\u1021\u1004\u103a", "metamfetamine", "methamphetamine", "meth")),
        ("\u1004", ("\u1018\u102d\u1014\u103a\u1038\u1019\u1032", "\u1015\u103c\u102f\u1015\u103c\u1004\u103a\u1011\u102c\u1038\u101e\u1031\u102c \u1018\u102d\u1014\u103a\u1038")),
        ("\u1005", ("\u1018\u102d\u1014\u103a\u1038\u1005\u102c",)),
        ("\u1006", ("\u1006\u1031\u1038\u1001\u103c\u1031\u102c\u1000\u103a",)),
        ("\u1007", ("\u1000\u102d\u102f\u1000 \u101b\u103d\u1000\u103a", "coca")),
        ("\u1008", ("\u1000\u102d\u102f\u1000\u1004\u103a\u1038", "cocaine")),
        ("\u100b", ("\u1021\u101b\u100a\u103a", "\u1019\u102e\u101c\u102e", "ml")),
    )
    subsection = None
    if not any(term in text for term in full_list_terms):
        for candidate_subsection, terms in subsection_matchers:
            if any(term in text for term in terms):
                subsection = candidate_subsection
                break

    quantity_rule = (
        _fetch_law_chunk(cursor, drug_law, "\u1042\u1046", subsection)
        if subsection
        else _fetch_law_section(cursor, drug_law, "\u1042\u1046")
    )
    penalty = _fetch_law_chunk(cursor, drug_law, "\u1042\u1040")
    if not quantity_rule or not penalty:
        return None

    offense_source = _penalty_row_source(quantity_rule, "drug_quantity_rule")
    penalty_source = _penalty_row_source(penalty, "drug_quantity_penalty")
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([offense_source], [penalty_source]),
        "score": 0.82,
    }


def _retrieve_drug_offense_match(cursor, question):
    text = unicodedata.normalize("NFC", str(question or "")).lower()
    drug_law = _preferred_law_name_fragment("drug")
    if _preferred_law_name_fragment(text) != drug_law:
        return None

    offense_terms = (
        "လက်ဝယ်ထား",
        "သယ်ယူ",
        "ပို့ဆောင်",
        "တစ်ဆင့်ပေးပို့",
        "လွှဲပြောင်း",
        "ရောင်းချ",
        "ဖြန့်ဖြူး",
        "ဖြန့်ဖြူး",
        "ထုတ်လုပ်",
        "တရားမဝင်",
        "တရားမ၀င်",
        "possess",
        "sell",
        "transport",
        "distribute",
        "produce",
    )
    if not any(term in text for term in offense_terms):
        return None

    serious_sale_terms = (
        "ရောင်းချ",
        "ဖြန့်ဖြူး",
        "ဖြန့်ဖြူး",
        "ထုတ်လုပ်",
        "တင်သွင်း",
        "တင်ပို့",
        "sell",
        "distribute",
        "produce",
        "import",
        "export",
    )
    if any(term in text for term in serious_sale_terms):
        offense = _fetch_law_section(cursor, drug_law, "\u1042\u1040")
        penalty = offense
    else:
        offense = _fetch_law_section(cursor, drug_law, "\u1041\u1049")
        penalty = offense
    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, "drug_offense_rule")
    penalty_source = _penalty_row_source(penalty, "drug_offense_penalty")
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([offense_source], [penalty_source]),
        "score": 0.80,
    }


def _retrieve_passport_keyword_match(cursor, question):
    text = str(question or "").lower()
    passport_law = _preferred_law_name_fragment("passport")
    if _preferred_law_name_fragment(text) != passport_law:
        return None

    # A genuine passport used or held by somebody who is not entitled to it
    # is a different offence from forging a passport (35(d), not 35(c)).
    unauthorized_terms = (
        "တခြားသူ", "သူတစ်ပါး", "အခြားသူ", "တစ်ပါးသူ",
        "ကိုင်ဆောင်ခွင့်မရှိ", "အသုံးပြုခွင့်မရှိ", "ခွင့်မပေး",
        "ခွင့်ပြုချက်မရှိ", "ပိုင်ရှင်ကခွင့်မပြု",
    )
    use_terms = (
        "passport", "နိုင်ငံကူးလက်မှတ်", "ကိုင်ထား", "ကိုင်ဆောင်", "သုံး", "အသုံးပြု",
    )
    if any(keyword in text for keyword in unauthorized_terms) and any(
        keyword in text for keyword in use_terms
    ):
        offense = _fetch_law_chunk(cursor, passport_law, "၃၅", "ဃ")
        penalty = _fetch_law_chunk(cursor, passport_law, "၃၉", "ဃ")
        if not offense or not penalty:
            return None
        offense_source = _penalty_row_source(offense, "passport_unauthorized_use_rule")
        penalty_source = _penalty_row_source(penalty, "passport_unauthorized_use_penalty")
        return {
            "offense": offense_source,
            "penalty": penalty_source,
            "evidence": _dedupe_evidence([penalty_source], [offense_source]),
            "score": 0.82,
        }

    if not any(keyword in text for keyword in ("အတု", "fake", "false", "forged", "forge")):
        return None

    offense = _fetch_law_chunk(cursor, passport_law, "\u1043\u1045", "\u1002")
    penalty = _fetch_law_chunk(cursor, passport_law, "\u1043\u1049", "\u1002")
    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, "passport_keyword_offense")
    penalty_source = _penalty_row_source(penalty, "passport_keyword_penalty")
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([penalty_source], [offense_source]),
        "score": 0.78,
    }


def _retrieve_penal_code_keyword_match(cursor, question):
    text = unicodedata.normalize("NFC", str(question or "")).lower()
    penal_law = "ရာဇသတ်ကြီး"
    if _preferred_law_name_fragment(text) != penal_law:
        return None

    routes = (
        {
            # Section 497 is intentionally gated by both an adultery/sexual-act
            # expression and an explicit married-woman fact.  A vague suspicion
            # that a spouse is "cheating" must not be forced into this offence.
            "terms": (
                "ဖောက်ပြန်",
                "မယားခိုး",
                "မတရားကာမ",
                "ကာမစပ်ယှက်",
                "အတူအိပ်",
            ),
            "required_terms": (
                "လင်ရှိမယား",
                "လင်ရှိတဲ့",
                "လင်ရှိသော",
                "အိမ်ထောင်ရှင်မိန်းမ",
                "အိမ်ထောင်ရှိတဲ့ အမျိုးသမီး",
                "အိမ်ထောင်ရှိသော အမျိုးသမီး",
            ),
            "offense_section": "၄၉၇",
            "penalty_section": "၄၉၇",
            "matched_by": "penal_adultery",
        },
        {
            "terms": (
                "ကာယိန္ဒြေ",
                "မိန်းမ၏ကာယိန္ဒြေ",
                "စော်ကား",
                "ညစ်ညမ်းတဲ့စကား",
                "ညစ်ညမ်းသောစကား",
                "မသင့်တော်တဲ့ကိုယ်အမူအရာ",
                "မသင့်တော်တဲ့ကိုယ်အမူအရာ",
            ),
            "required_terms": ("ပြောဆို", "အသံပြု", "ကိုယ်အမူအရာ", "အရာဝတ္ထု", "ဆိတ်ကွယ်ရာ", "နောက်ကလိုက်", "gesture", "word", "sound", "privacy"),
            "offense_section": "၅၀၉",
            "penalty_section": "၅၀၉",
            "matched_by": "penal_insult_modesty_of_woman",
        },
        {
            "terms": (
                "ဆဲဆို",
                "အော်ဆဲ",
                "ရန်စ",
                "တမင်စော်ကား",
                "စကားနဲ့စော်ကား",
                "insult",
                "verbal abuse",
            ),
            "offense_section": "၅၀၄",
            "penalty_section": "၅၀၄",
            "matched_by": "penal_intentional_insult",
        },
        {
            "terms": ("ကာယိန္ဒြေ", "မိန်းမ၏ကာယိန္ဒြေ"),
            "required_terms": ("လက်ရောက်", "အနိုင်အထက်", "force", "assault"),
            "offense_section": "၃၅၄",
            "penalty_section": "၃၅၄",
            "matched_by": "penal_assault_to_outrage_modesty",
        },
        {
            "terms": ("အသရေ", "အသရေဖျက်", "အသရေပျက်", "ဂုဏ်သရေ", "နာမည်ပျက်", "defamation", "reputation"),
            "required_terms": ("ခြိမ်းခြောက်", "ခြောက်လှန့်", "ခြောက်လှန့်", "ထိတ်လန့်", "ထိတ်လန့်", "threat"),
            "offense_section": "၅၀၃",
            "penalty_section": "၅၀၆",
            "matched_by": "penal_reputation_criminal_intimidation",
        },
        {
            "terms": ("အသရေ", "အသရေဖျက်", "အသရေပျက်", "ဂုဏ်သရေ", "နာမည်ပျက်", "defamation", "reputation"),
            "required_terms": ("ပုံနှိပ်", "ထုထွင်း", "print", "printed", "engrave"),
            "offense_section": "၅၀၁",
            "penalty_section": "၅၀၁",
            "matched_by": "penal_printed_defamation",
        },
        {
            "terms": ("အသရေ", "အသရေဖျက်", "အသရေပျက်", "ဂုဏ်သရေ", "နာမည်ပျက်", "defamation", "reputation"),
            "required_terms": ("ရောင်းချ", "ကမ်းလှမ်း", "sell", "sale"),
            "offense_section": "၅၀၂",
            "penalty_section": "၅၀၂",
            "matched_by": "penal_sale_of_defamatory_material",
        },
        {
            "terms": (
                "အသရေ",
                "အသရေဖျက်",
                "အသရေပျက်",
                "ဂုဏ်သရေ",
                "နာမည်ပျက်",
                "မဟုတ်မမှန်",
                "မလုပ်ခဲ့တဲ့",
                "မလုပ်ခဲ့သည့်",
                "စွပ်စွဲ",
                "defamation",
                "reputation",
            ),
            "required_terms": ("ပြော", "ရေး", "ဖြန့်", "ဖြန့်", "လူအများရှေ့", "စွပ်စွဲ", "accuse", "publish"),
            "offense_section": "၄၉၉",
            "penalty_section": "၅၀၀",
            "matched_by": "penal_defamation",
        },
        {
            "terms": ("သေဒဏ်ထိုက်", "သေဒဏ်ထိုက်သော ပြစ်မှု", "death punishable", "capital offense"),
            "required_terms": ("အိမ်ကျော်", "ကျော်နင်း"),
            "offense_section": "၄၄၉",
            "penalty_section": "၄၄၉",
            "matched_by": "penal_house_trespass_capital_offense",
        },
        {
            "terms": ("ထောင်ဒဏ်နှစ် နှစ်ဆယ်ထိုက်", "နှစ် နှစ်ဆယ်ထိုက်", "20 years"),
            "required_terms": ("အိမ်ကျော်", "ကျော်နင်း"),
            "offense_section": "၄၅၀",
            "penalty_section": "၄၅၀",
            "matched_by": "penal_house_trespass_twenty_year_offense",
        },
        {
            "terms": ("ထောင်ဒဏ်ထိုက်", "ခိုးမှု", "imprisonable"),
            "required_terms": ("အိမ်ကျော်", "ကျော်နင်း"),
            "offense_section": "၄၅၁",
            "penalty_section": "၄၅၁",
            "matched_by": "penal_house_trespass_imprisonable_offense",
        },
        {
            "terms": ("နာကျင်စေ", "လက်ရောက်", "မတရားတားဆီး", "ရိုက်နှက်", "hurt", "assault"),
            "required_terms": ("အိမ်ကျော်", "ကျော်နင်း"),
            "offense_section": "၄၅၂",
            "penalty_section": "၄၅၂",
            "matched_by": "penal_house_trespass_with_hurt_preparation",
        },
        {
            "terms": ("အိမ်ကျော်", "အိမ်ကျော်နင်း", "house trespass"),
            "offense_section": "၄၄၂",
            "penalty_section": "၄၄၈",
            "matched_by": "penal_house_trespass",
        },
        {
            "terms": ("ကျော်နင်း", "ကျော်ဝင်", "ခြံဝင်", "အိမ်ခြံ", "trespass"),
            "offense_section": "၄၄၁",
            "penalty_section": "၄၄၇",
            "matched_by": "penal_criminal_trespass",
        },
        {
            "terms": ("အနှောင့်အယှက်", "အနှောင့်အယှက်", "ဆူညံ", "နားငြီး", "တိုင်တန်း", "public nuisance", "nuisance"),
            "offense_section": "၂၆၈",
            "penalty_section": "၂၉၀",
            "matched_by": "penal_public_nuisance",
        },
        {
            "terms": ("ပစ္စည်းဖျက်", "ဖျက်ဆီး", "အကျိုးဖျက်", "ပျက်စီး", "damage", "destroy", "mischief"),
            "offense_section": "၄၂၅",
            "penalty_section": "၄၂၆",
            "matched_by": "penal_mischief",
        },
        {
            "terms": ("ငွေသားတွေ ယူသွား", "ငွေသားယူသွား", "ပစ္စည်းယူသွား", "ပစ္စည်းတွေယူသွား"),
            "required_terms": ("အိမ်ထဲဝင်", "အိမ်ထဲကိုဝင်", "အဆောက်အအုံထဲ", "အိမ်ရှင်မရှိ"),
            "offense_section": "၃၇၈",
            "penalty_section": "၃၈၀",
            "matched_by": "penal_theft_in_dwelling",
        },
        {
            "terms": ("ခိုး", "ခိုးယူ", "ပစ္စည်းယူ", "steal", "stolen", "theft"),
            "offense_section": "၃၇၈",
            "penalty_section": "၃၇၉",
            "matched_by": "penal_theft",
        },
        {
            "terms": (
                "လိမ်လည်",
                "လှည့်ဖြား",
                "လှည့်ဖြား",
                "ငွေလိမ်",
                "ပစ္စည်းမပို့",
                "ငွေလွှဲပြီး",
                "block လုပ်",
                "ဘလော့ခ်လုပ်",
                "cheat",
                "fraud",
                "scam",
            ),
            "required_terms": ("ငွေ", "ပိုက်ဆံ", "ငွေလွှဲ", "ပစ္စည်း", "ရောင်း", "ဝယ်", "payment", "money"),
            "offense_section": "၄၁၅",
            "penalty_section": "၄၂၀",
            "matched_by": "penal_cheating",
        },
        {
            "terms": ("ခြောက်လှန့်", "ခြောက်လှန့်", "ခြိမ်းခြောက်", "တောင်းယူ", "blackmail", "extortion"),
            "offense_section": "၃၈၃",
            "penalty_section": "၃၈၄",
            "matched_by": "penal_extortion",
        },
        {
            "terms": ("လုယက်", "ဓားပြ", "robbery", "rob"),
            "offense_section": "၃၉၀",
            "penalty_section": "၃၉၂",
            "matched_by": "penal_robbery",
        },
        {
            "terms": ("မုဒိမ်း", "အဓမ္မ", "rape"),
            "offense_section": "၃၇၅",
            "penalty_section": "၃၇၆",
            "matched_by": "penal_rape",
        },
        {
            "terms": ("လူသတ်", "သတ်ပစ်", "သေစေ", "murder", "kill"),
            "offense_section": "၂၉၉",
            "penalty_section": "၃၀၂",
            "matched_by": "penal_homicide",
        },
        {
            "terms": ("ရိုက်နှက်", "နာကျင်", "ထိုးကြိတ်", "hurt", "assault", "beat"),
            "offense_section": "၃၁၉",
            "penalty_section": "၃၂၃",
            "matched_by": "penal_hurt",
        },
    )

    route = next(
        (
            candidate
            for candidate in routes
            if any(term in text for term in candidate["terms"])
            and (
                not candidate.get("required_terms")
                or any(term in text for term in candidate["required_terms"])
            )
        ),
        None,
    )
    if not route:
        return None

    offense = _fetch_law_section(cursor, penal_law, route["offense_section"])
    penalty = _fetch_law_section(cursor, penal_law, route["penalty_section"])
    if not offense or not penalty:
        return None

    offense_source = _penalty_row_source(offense, f'{route["matched_by"]}_offense')
    penalty_source = _penalty_row_source(penalty, f'{route["matched_by"]}_penalty')
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([offense_source], [penalty_source]),
        "score": 0.82,
    }


def _retrieve_penalty_match(cursor, vector, question, category):
    """Link a described legal act to a nearby/parent punishment provision.

    This is intentionally law-agnostic.  It first finds the best non-punishment
    chunk for the user's facts, then looks inside the same document and section
    for a punishment-bearing parent/nearby chunk.  That covers common Myanmar
    law layouts such as section 40(a) containing the punishment while 40(a)(3)
    contains the concrete prohibited act.
    """
    cyber_match = _retrieve_cyber_keyword_match(cursor, question)
    if cyber_match:
        return cyber_match

    telecom_license_match = _retrieve_telecom_license_equipment_match(cursor, question)
    if telecom_license_match:
        return telecom_license_match

    telecom_match = _retrieve_telecom_66d_match(cursor, question)
    if telecom_match:
        return telecom_match

    forest_match = _retrieve_forest_keyword_match(cursor, question)
    if forest_match:
        return forest_match

    passport_match = _retrieve_passport_keyword_match(cursor, question)
    if passport_match:
        return passport_match

    penal_code_match = _retrieve_penal_code_keyword_match(cursor, question)
    if penal_code_match:
        return penal_code_match

    drug_quantity_match = _retrieve_drug_quantity_match(cursor, question)
    if drug_quantity_match:
        return drug_quantity_match

    drug_offense_match = _retrieve_drug_offense_match(cursor, question)
    if drug_offense_match:
        return drug_offense_match

    # Only gate the generic vector-based linker.  Explicit fact routes above
    # are already narrowly constrained and must still work when conversational
    # input contains words such as "အကြောင်း", which can look like a general
    # information request to the broad heuristic.
    if not _question_may_need_penalty(question):
        return None

    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url,
          1 - (c.embedding <=> %s::vector) AS vector_score
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
          AND (%s::text IS NULL OR d.category = %s::text)
        ORDER BY c.embedding <=> %s::vector
        LIMIT 80
        """,
        (vector, category, category, vector),
    )
    candidates = cursor.fetchall()
    if not candidates:
        candidates = []

    seen_candidate_ids = {row["chunk_id"] for row in candidates}
    cursor.execute(
        """
        SELECT DISTINCT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url,
          0.0 AS vector_score,
          true AS linked_candidate
        FROM legal_section_links l
        JOIN legal_chunks c ON c.id = l.source_chunk_id
        JOIN legal_documents d ON d.id = c.document_id
        WHERE l.link_type = 'punishment'
          AND c.embedding IS NOT NULL
          AND (%s::text IS NULL OR d.category = %s::text)
        """,
        (category, category),
    )
    for row in cursor.fetchall():
        if row["chunk_id"] in seen_candidate_ids:
            continue
        candidates.append(row)
        seen_candidate_ids.add(row["chunk_id"])
    if not candidates:
        return None

    question_concepts = _penalty_concept_names(question)
    preferred_law = _preferred_law_name_fragment(question)
    for row in candidates:
        lexical_score = _character_ngram_recall(question, row["content"])
        token_score = _meaningful_token_recall(question, row["content"])
        concept_score = _penalty_concept_overlap(question, row["content"])
        row["lexical_score"] = lexical_score
        row["token_score"] = token_score
        row["concept_score"] = concept_score
        linked_bonus = (
            0.22
            if row.get("linked_candidate") and max(lexical_score, token_score) >= 0.035
            else 0.0
        )
        row["penalty_hit_score"] = (
            0.10 * float(row["vector_score"])
            + 0.30 * lexical_score
            + 0.30 * token_score
            + 0.40 * concept_score
            + linked_bonus
        )

    # Prefer a concrete prohibited-act chunk.  A generic punishment chunk is
    # useful only as the parent after the act itself has been identified.
    act_candidates = [
        row
        for row in candidates
        if not _row_has_punishment_text(row)
    ]
    ranked = sorted(
        act_candidates or candidates,
        key=lambda row: row["penalty_hit_score"],
        reverse=True,
    )

    offense = None
    penalty = None
    for candidate in ranked[:25]:
        if preferred_law and preferred_law not in (candidate.get("law_name") or ""):
            continue
        if (
            "နိုင်ငံကူးလက်မှတ်" in question
            and "အတု" in question
            and "အတု" not in candidate["content"]
        ):
            continue
        # When the question contains a known legal act, never let a merely
        # similar provision win.  It must contain the same act concept.
        if question_concepts and candidate["concept_score"] <= 0:
            continue
        if candidate["penalty_hit_score"] < 0.30:
            continue
        # The exact concept is stronger evidence than character n-gram overlap.
        # This matters for natural paraphrases such as "တောင်းရမ်းခိုင်း" versus
        # the statutory wording "တောင်းရမ်းစေ".
        if (
            candidate["concept_score"] <= 0
            and candidate["lexical_score"] < 0.08
            and candidate.get("token_score", 0) < 0.35
        ):
            continue

        linked_penalty = _find_structural_penalty_for_offense(cursor, candidate)
        if not linked_penalty:
            continue
        offense = candidate
        penalty = linked_penalty
        break

    if not offense or not penalty:
        return None

    penalty_source = _penalty_row_source(penalty, "structural_penalty")
    offense_source = _penalty_row_source(offense, "penalty_offense_match")
    return {
        "offense": offense_source,
        "penalty": penalty_source,
        "evidence": _dedupe_evidence([penalty_source], [offense_source]),
        "score": offense["penalty_hit_score"],
    }


def _find_structural_penalty_for_offense(cursor, offense):
    """Find the most likely punishment chunk connected to an offense chunk."""
    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url
        FROM legal_section_links l
        JOIN legal_chunks c ON c.id = l.target_chunk_id
        JOIN legal_documents d ON d.id = c.document_id
        WHERE l.source_chunk_id = %s
          AND l.link_type = 'punishment'
        ORDER BY l.confidence DESC, c.chunk_index
        LIMIT 1
        """,
        (offense["chunk_id"],),
    )
    linked_penalty = cursor.fetchone()
    if linked_penalty:
        return linked_penalty

    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE c.document_id = %s
          AND c.section = %s
          AND (
            c.content LIKE %s OR c.content LIKE %s OR c.content LIKE %s
            OR c.content LIKE %s OR c.content LIKE %s
          )
        ORDER BY
          CASE WHEN c.chunk_index <= %s THEN 0 ELSE 1 END,
          abs(c.chunk_index - %s),
          c.chunk_index
        LIMIT 1
        """,
        (
            offense["document_id"],
            offense["section"],
            *PUNISHMENT_SQL_PATTERNS,
            offense["chunk_index"],
            offense["chunk_index"],
        ),
    )
    penalty = cursor.fetchone()
    if penalty:
        return penalty

    # Fallback for laws where the punishment is placed just before/after a
    # separate offense section rather than inside the same section number.
    cursor.execute(
        """
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.chunk_index,
          c.chapter,
          c.section,
          c.subsection,
          c.content,
          d.law_name,
          d.law_number,
          d.source_url
        FROM legal_chunks c
        JOIN legal_documents d ON d.id = c.document_id
        WHERE c.document_id = %s
          AND c.chunk_index BETWEEN %s AND %s
          AND (
            c.content LIKE %s OR c.content LIKE %s OR c.content LIKE %s
            OR c.content LIKE %s OR c.content LIKE %s
          )
        ORDER BY abs(c.chunk_index - %s), c.chunk_index
        LIMIT 1
        """,
        (
            offense["document_id"],
            max(0, offense["chunk_index"] - 8),
            offense["chunk_index"] + 8,
            *PUNISHMENT_SQL_PATTERNS,
            offense["chunk_index"],
        ),
    )
    return cursor.fetchone()


def _penalty_citations(penalty_match):
    offense = penalty_match["offense"]
    penalty = penalty_match["penalty"]
    offense_section = offense["section"]
    penalty_section = penalty.get("section") or offense_section
    parent = penalty.get("subsection")
    child = offense.get("subsection")
    if penalty_section == offense_section and parent and child and parent != child:
        offense_citation = f"ပုဒ်မ {offense_section}({parent})({child})"
    elif child:
        offense_citation = f"ပုဒ်မ {offense_section}({child})"
    elif penalty_section == offense_section and parent:
        offense_citation = f"ပုဒ်မ {offense_section}({parent})"
    else:
        offense_citation = f"ပုဒ်မ {offense_section}"
    penalty_citation = f"ပုဒ်မ {penalty_section}" + (f"({parent})" if parent else "")
    return offense_citation, penalty_citation


def _row_has_punishment_text(row):
    content = row.get("content") or row.get("matched_excerpt") or ""
    return any(keyword in content for keyword in PUNISHMENT_TEXT_KEYWORDS)


def _extract_punishment_excerpt(row):
    def punishment_clause(text):
        compact_text = re.sub(r"\s+", " ", str(text or "")).strip()
        for marker in ("ထိုသူကို", "ထိုသူအား", "ထိုသူကိုတော့", "ထိုသူအားတော့"):
            index = compact_text.find(marker)
            if index >= 0:
                compact_text = compact_text[index:].strip()
                break
        punishment_endings = (
            "ကျခံစေရမည်",
            "ချမှတ်ရမည်",
            "ချမှတ်နိုင်သည်",
            "ချမှတ်နိုင်ပါသည်",
            "အရေးယူခြင်းခံရမည်",
            "အရေးယူခံရမည်",
        )
        end_positions = []
        for ending in punishment_endings:
            index = compact_text.find(ending)
            if index >= 0:
                end_positions.append(index + len(ending))
        if end_positions:
            end_index = min(end_positions)
            if end_index < len(compact_text) and compact_text[end_index:end_index + 1] == "။":
                end_index += 1
            return compact_text[:end_index].strip()
        return compact_text

    matched_excerpt = row.get("matched_excerpt") or ""
    if any(keyword in matched_excerpt for keyword in STRONG_PUNISHMENT_TEXT_KEYWORDS):
        return punishment_clause(matched_excerpt)

    content = row.get("content") or ""
    compact = re.sub(r"\s+", " ", str(content or "")).strip()
    sentence_candidates = re.split(r"(?<=[။])\s+", compact)
    for sentence in sentence_candidates:
        if any(keyword in sentence for keyword in STRONG_PUNISHMENT_TEXT_KEYWORDS):
            return punishment_clause(sentence)
    for sentence in sentence_candidates:
        if any(keyword in sentence for keyword in PUNISHMENT_TEXT_KEYWORDS):
            return punishment_clause(sentence)

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for line in lines:
        if any(keyword in line for keyword in STRONG_PUNISHMENT_TEXT_KEYWORDS):
            return punishment_clause(line)
    for line in lines:
        if any(keyword in line for keyword in PUNISHMENT_TEXT_KEYWORDS):
            return punishment_clause(line)
    return content


def _full_legal_excerpt(text, limit=5000):
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}…"


def _looks_like_trailing_section_heading(line):
    """Detect headings that OCR/chunking attached to the previous section.

    MLIS often renders a section title immediately before the next numbered
    section. When our chunk boundary cuts after the current section body but
    before the next section number, that title can appear at the end of the
    previous source card. Keep the database unchanged; only hide that dangling
    heading in UI/API display text.
    """
    compact = re.sub(r"\s+", " ", str(line or "")).strip()
    if not compact or len(compact) > 120 or not compact.endswith("။"):
        return False
    if re.match(r"^[၀-၉0-9]+\s*။", compact):
        return False

    # Very strong signal: a standalone "punishment for ..." title.
    if "အတွက်" in compact and "ပြစ်ဒဏ်" in compact:
        return True

    heading_endings = (
        "မှု။",
        "ခြင်း။",
        "ပြုမှု။",
        "ပြစ်ဒဏ်။",
        "အိမ်ကျော်နင်းမှု။",
        "နှောင့်ယှက်မှု။",
    )
    if not compact.endswith(heading_endings):
        return False

    sentence_words = (
        "သည်",
        "မည်",
        "လျှင်",
        "ဖြစ်သည်",
        "ချမှတ်",
        "ထိုသူ",
        "မဟုတ်",
        "ရမည်",
        "နိုင်သည်",
        "သော်လည်း",
        "ကျူးလွန်သည်",
    )
    return not any(word in compact for word in sentence_words)


def _clean_display_content(text):
    """Return source-card text without a dangling next-section title."""
    raw = str(text or "").strip()
    if not raw:
        return raw
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    removed = False
    while len(lines) > 1 and _looks_like_trailing_section_heading(lines[-1]):
        lines.pop()
        removed = True
    if removed:
        return "\n".join(lines).strip()
    return raw


def _ui_legal_excerpt(text, limit=420):
    """Short readable excerpt for the main UI card.

    Some Penal Code sections, especially section 499, contain many explanations,
    exceptions, and examples. Those are useful as raw evidence, but too long for
    the user's first answer. Keep only the main rule unless the section itself is
    already short.
    """
    compact = re.sub(r"\s+", " ", _clean_display_content(text)).strip()
    for marker in (
        "ရှင်းလင်းချက်",
        "ကင်းလွတ်ချက်",
        "ဥပမာ",
        "ပထမကင်းလွတ်ချက်",
        "အသရေပျက်စေမည်ဟု သိသော",
        "အိမ်ကျော်နင်းမှုအတွက် ပြစ်ဒဏ်",
        "သေဒဏ်ထိုက်သည့် ပြစ်မှု",
        "ခိုးမှုအတွက်ပြစ်ဒဏ်",
    ):
        index = compact.find(marker)
        if index > 80:
            compact = compact[:index].rstrip()
            break
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}…"


def _semantic_penalty_summary(rows):
    for row in rows:
        if not _row_has_punishment_text(row):
            continue
        section = row.get("section") or "မသတ်မှတ်ထား"
        citation = f"ပုဒ်မ {section}"
        content = _extract_punishment_excerpt(row)
        return f"{citation} — {_full_legal_excerpt(content)}"
    return None


def _penalty_summary_from_match(penalty_match):
    if not penalty_match:
        return None
    _, penalty_citation = _penalty_citations(penalty_match)
    penalty = penalty_match["penalty"]
    return f"{penalty_citation} — {_ui_legal_excerpt(_extract_punishment_excerpt(penalty), limit=300)}"


def _infer_penalty_from_analysis(analysis):
    """Promote punishment-like related sections into the main penalty field."""
    if not analysis or analysis.get("penalty"):
        return None

    for item in analysis.get("related_sections") or []:
        summary = item.get("summary") or ""
        if not any(keyword in summary for keyword in STRONG_PUNISHMENT_TEXT_KEYWORDS):
            continue
        citation = item.get("citation") or "ပြစ်ဒဏ်သတ်မှတ်ပုဒ်မ"
        return f"{citation} — {_full_legal_excerpt(summary)}"
    return None


def _ensure_analysis_penalty(analysis, penalty_match=None):
    if not analysis or analysis.get("penalty"):
        return analysis

    penalty = _penalty_summary_from_match(penalty_match)
    if not penalty:
        penalty = _infer_penalty_from_analysis(analysis)
    if penalty:
        analysis["penalty"] = penalty
    return analysis


def _semantic_source(row):
    return {
        "chunk_id": row["chunk_id"],
        "law_name": row["law_name"],
        "law_number": row["law_number"],
        "chapter": row.get("chapter"),
        "section": row["section"],
        "subsection": row["subsection"],
        "content": _clean_display_content(row.get("matched_excerpt") or row["content"]),
        "source_url": row["source_url"],
        "score": round(float(row["vector_score"]), 4),
        "matched_by": row.get("matched_by", "semantic"),
    }


def _load_verified_rule_sources(cursor, expected_sections, law_fragment=None):
    sources = []
    seen = set()
    for expected in expected_sections:
        section = expected["section"]
        subsections = expected.get("subsections") or []
        cursor.execute(
            """
            SELECT
              c.id AS chunk_id,
              d.law_name,
              d.law_number,
              c.chapter,
              c.section,
              c.subsection,
              c.content,
              d.source_url
            FROM legal_chunks c
            JOIN legal_documents d ON d.id = c.document_id
            WHERE c.section = %s
              AND (%s::text IS NULL OR d.law_name LIKE %s)
              AND (
                %s = '{}'::text[]
                OR c.subsection IS NULL
                OR c.subsection = ANY(%s::text[])
              )
            ORDER BY c.chunk_index
            """,
            (
                section,
                law_fragment,
                f"%{law_fragment}%" if law_fragment else None,
                subsections,
                subsections,
            ),
        )
        for row in cursor.fetchall():
            if row["chunk_id"] in seen:
                continue
            seen.add(row["chunk_id"])
            sources.append(
                {
                    "chunk_id": row["chunk_id"],
                    "law_name": row["law_name"],
                    "law_number": row["law_number"],
                    "chapter": row["chapter"],
                    "section": row["section"],
                    "subsection": row["subsection"],
                    "content": row["content"],
                    "source_url": row["source_url"],
                    "score": None,
                    "matched_by": "verified_rule",
                }
            )
    return sources


def _dedupe_evidence(*groups):
    evidence = []
    seen = set()
    for group in groups:
        for item in group or []:
            key = (
                item.get("law_name"),
                item.get("chapter"),
                item.get("section"),
                item.get("subsection"),
                item.get("content"),
            )
            if key in seen:
                continue
            seen.add(key)
            evidence.append(item)
    return evidence


def _answer_sources(evidence, analysis):
    citations = " ".join(
        item.get("citation", "")
        for item in analysis.get("related_sections", [])
    )
    selected = []
    for item in evidence:
        section = item.get("section")
        if section and f"ပုဒ်မ {section}" not in citations:
            continue
        if item.get("vector_score") is not None:
            selected.append(_semantic_source(item))
        else:
            cleaned = dict(item)
            cleaned["content"] = _clean_display_content(cleaned.get("content"))
            selected.append(cleaned)
    return selected[:8]


def _semantic_is_answerable(rows, top_score=None, margin=None, support=0):
    if not rows:
        return False, 0.0, 0.0
    if top_score is None:
        top_score = float(rows[0]["vector_score"])
    if margin is None:
        second_score = float(rows[1]["vector_score"]) if len(rows) > 1 else 0.0
        margin = top_score - second_score
    # Full-section aggregation lowers cosine scores compared with the original
    # individual chunks. A single strong section is enough; moderately strong
    # matches need corroboration from another retrieved section.
    answerable = (
        top_score >= 0.40
        or (top_score >= 0.38 and support >= 2)
    )
    return answerable, top_score, margin


def _retrieval_confidence_label(score, answerable):
    if not answerable:
        return "နိမ့်"
    if score >= STRONG_SEMANTIC_SCORE:
        return "မြင့်"
    return "အလယ်အလတ်"


def _compact_legal_excerpt(text, limit=260):
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    shortened = compact[:limit].rstrip()
    last_boundary = max(
        shortened.rfind("။"),
        shortened.rfind("၊"),
        shortened.rfind(" "),
    )
    if last_boundary >= int(limit * 0.65):
        shortened = shortened[:last_boundary].rstrip(" ၊။")
    return f"{shortened}…"


def _section_numbers_from_text(value):
    normalized = unicodedata.normalize("NFC", str(value or "")).translate(
        str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
    )
    return set(re.findall(r"ပုဒ်မ\s*([0-9]+)", normalized))


def _safe_readable_law_summary(question, analysis, evidence):
    """Rewrite only the UI's law_summary field into short readable Burmese.

    Retrieval, citations, punishment matching, source cards, and the main answer
    remain unchanged. The rewrite is accepted only if it cites no new sections.
    """
    if not analysis or analysis.get("mode") == "insufficient_evidence":
        return analysis

    original_summary = str(analysis.get("law_summary") or "").strip()
    if not original_summary:
        return analysis

    def fallback_summary():
        related = analysis.get("related_sections") or []
        primary = next(
            (
                item
                for item in related
                if item.get("role") in {"ပြစ်မှု", "အဓိက"}
            ),
            related[0] if related else {},
        )
        citation = primary.get("citation") or ""
        penalty = str(analysis.get("penalty") or "").strip()
        penalty_citation = ""
        match = re.search(r"(ပုဒ်မ\s*[၀-၉0-9]+(?:\s*\([^)]+\))?)", penalty)
        if match:
            penalty_citation = match.group(1)
        complaint = next(
            (
                item
                for item in related
                if "တိုင်" in str(item.get("role") or "")
                or "အရေးယူ" in str(item.get("role") or "")
            ),
            None,
        )

        lines = []
        if citation:
            lines.append(
                f"မေးမြန်းထားသောဖြစ်စဉ်သည် {citation} တွင် ဖော်ပြထားသော ဥပဒေပြဋ္ဌာန်းချက်နှင့် သက်ဆိုင်နိုင်ပါသည်။"
            )
        else:
            lines.append(
                "မေးမြန်းထားသောဖြစ်စဉ်သည် လက်ရှိရှာဖွေတွေ့ရှိထားသော ဥပဒေပြဋ္ဌာန်းချက်နှင့် သက်ဆိုင်နိုင်ပါသည်။"
            )
        if penalty_citation:
            lines.append(
                f"ပြစ်ဒဏ်နှင့်ပတ်သက်၍ {penalty_citation} ကို သီးခြားစိစစ်ရန်လိုပါသည်။"
            )
        elif penalty:
            lines.append("ပြစ်ဒဏ်သတ်မှတ်ချက်ကို သီးခြားစိစစ်ရန်လိုပါသည်။")
        if complaint and complaint.get("citation"):
            lines.append(
                f"တိုင်တန်း/အရေးယူရန်အချက်အလက်အတွက် {complaint['citation']} ကိုလည်း ကြည့်ရန်လိုပါသည်။"
            )
        lines.append("အသေးစိတ်မူရင်းစာသားကို အောက်ရှိ ဆက်စပ်ဥပဒေပုဒ်မများတွင် ဆက်လက်စစ်ဆေးနိုင်ပါသည်။")
        updated = dict(analysis)
        updated["law_summary"] = " ".join(lines)
        updated["composer_used_for_law_summary"] = False
        return updated

    if not ENABLE_AI_LAW_SUMMARY:
        return fallback_summary()

    related_sections = analysis.get("related_sections") or []
    allowed_text = " ".join(
        [
            original_summary,
            str(analysis.get("penalty") or ""),
            str(analysis.get("decision") or ""),
            " ".join(
                f"{item.get('citation') or ''} {item.get('summary') or ''}"
                for item in related_sections
            ),
            " ".join(
                f"ပုဒ်မ {item.get('section') or ''} {item.get('content') or ''}"
                for item in evidence[:6]
            ),
        ]
    )
    allowed_sections = _section_numbers_from_text(allowed_text)

    system_prompt = (
        "Rewrite only. Use Burmese. Do not add new law, section, punishment, or amount. "
        "Return JSON only: {\"law_summary\":\"...\"}"
    )
    prompt = (
        f"မေးခွန်း: {question[:220]}\n"
        f"ဥပဒေအချက်: {_compact_legal_excerpt(original_summary, 280)}\n"
        f"ပြစ်ဒဏ်: {_compact_legal_excerpt(analysis.get('penalty') or '', 180)}\n"
        "အထက်ပါအချက်ကိုသာ အသုံးပြုပြီး နားလည်လွယ်သော မြန်မာစာ ၂ ကြောင်းအဖြစ် ပြန်ရေးပါ။"
    )
    body = json.dumps(
        {
            "model": OLLAMA_CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0,
                "num_ctx": 1024,
                "num_predict": 120,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        model_request = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(model_request, timeout=90) as response:
            payload = json.load(response)
        content = ((payload.get("message") or {}).get("content") or "").strip()
        generated = json.loads(content)
        readable = ""
        if isinstance(generated, dict):
            readable = str(
                generated.get("law_summary")
                or generated.get("summary")
                or generated.get("answer")
                or generated.get("field_value")
                or ""
            )
            if not readable:
                string_values = [
                    value
                    for value in generated.values()
                    if isinstance(value, str) and len(value.strip()) > 20
                ]
                readable = string_values[0] if len(string_values) == 1 else ""
        readable = re.sub(r"\s+", " ", readable).strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return fallback_summary()

    if not readable or len(readable) > 650:
        return fallback_summary()
    cited_sections = _section_numbers_from_text(readable)
    if cited_sections and not cited_sections.issubset(allowed_sections):
        return fallback_summary()

    updated = dict(analysis)
    updated["law_summary"] = readable
    updated["composer_used_for_law_summary"] = True
    return updated


def _recommended_actions_for_law(law_name, has_complaint_rule=False):
    law = str(law_name or "")
    if "ကလေးသူငယ်" in law:
        return [
            "ဖြစ်စဉ်၏ အချိန်၊ နေရာ၊ သက်ဆိုင်သူများနှင့် လုပ်ရပ်အတိအကျကို မှတ်တမ်းတင်ရန်",
            "သက်သေအထောက်အထားများကို မဖျက်ဆီးဘဲ ထိန်းသိမ်းရန်",
            "ရဲတပ်ဖွဲ့၊ သက်ဆိုင်ရာ ကလေးကာကွယ်ရေးအဖွဲ့ သို့မဟုတ် ဥပဒေအကူအညီပေးသူထံ ဆက်သွယ်ရန်",
        ]
    if "ဆက်သွယ်ရေး" in law:
        actions = [
            "ဖုန်းနံပါတ်၊ အကောင့်အမည်၊ ပို့စ်/မက်ဆေ့ခ်ျ link၊ screenshot နှင့် အချိန်မှတ်တမ်းများကို သိမ်းဆည်းရန်",
            "သက်ဆိုင်ရာ ဆက်သွယ်ရေးဝန်ဆောင်မှုပေးသူ၊ ရဲတပ်ဖွဲ့ သို့မဟုတ် ဥပဒေအကူအညီပေးသူထံ ဆက်သွယ်ရန်",
        ]
        if has_complaint_rule:
            actions.insert(1, "အသရေဖျက်မှုဖြစ်ပါက နစ်နာသူကိုယ်တိုင် သို့မဟုတ် ကိုယ်စားလှယ်မှ တိုင်တန်းချက်လိုအပ်နိုင်သည်ကို စစ်ဆေးရန်")
        return actions
    if "ဆိုက်ဘာ" in law:
        return [
            "အကောင့်၊ link၊ message၊ transaction နှင့် screenshot များကို မဖျက်ဘဲ သိမ်းဆည်းရန်",
            "စကားဝှက်ပြောင်းခြင်း၊ အကောင့်လုံခြုံရေးစစ်ဆေးခြင်းနှင့် သက်ဆိုင်ရာ platform ကို report လုပ်ရန်",
            "ရဲတပ်ဖွဲ့ သို့မဟုတ် ဥပဒေအကူအညီပေးသူထံ အထောက်အထားများနှင့်အတူ ဆက်သွယ်ရန်",
        ]
    return [
        "ဖြစ်စဉ်၏ အချိန်၊ နေရာ၊ သက်ဆိုင်သူများနှင့် သက်သေအထောက်အထားများကို စနစ်တကျ မှတ်တမ်းတင်ရန်",
        "ကိုးကားထားသော မူရင်းပုဒ်မနှင့် ပြစ်ဒဏ်ပုဒ်မကို အောက်ရှိ ဆက်စပ်ဥပဒေပုဒ်မများတွင် စစ်ဆေးရန်",
        "လက်တွေ့တိုင်တန်း/အရေးယူမည်ဆိုပါက ရဲတပ်ဖွဲ့ သို့မဟုတ် ဥပဒေအကူအညီပေးသူထံ ဆက်သွယ်ရန်",
    ]


def _build_retrieval_analysis(
    question, rows, answerable, top_score, penalty_match=None
):
    confidence = _retrieval_confidence_label(top_score, answerable)

    if penalty_match:
        offense = penalty_match["offense"]
        penalty = penalty_match["penalty"]
        complaint = penalty_match.get("complaint")
        offense_citation, penalty_citation = _penalty_citations(penalty_match)
        offense_summary = _ui_legal_excerpt(offense["content"])
        penalty_summary = _ui_legal_excerpt(
            _extract_punishment_excerpt(penalty),
            limit=300,
        )
        complaint_citation = None
        complaint_summary = None
        if complaint:
            complaint_citation = f"ပုဒ်မ {complaint['section']}"
            if complaint.get("subsection"):
                complaint_citation += f"({complaint['subsection']})"
            complaint_summary = _ui_legal_excerpt(complaint["content"], limit=300)
        law_name = offense.get("law_name") or penalty.get("law_name") or "သက်ဆိုင်ရာဥပဒေ"
        facts = [
            {"label": "မေးမြန်းသည့်အကြောင်းအရာ", "value": question},
            {"label": "သက်ဆိုင်ရာဥပဒေ", "value": law_name},
            {"label": "သက်ဆိုင်ရာပြစ်မှု ပုဒ်မ", "value": offense_citation},
            {"label": "ပြစ်ဒဏ်သတ်မှတ်ပုဒ်မ", "value": penalty_citation},
        ]
        related_sections = [
            {
                "role": "ပြစ်မှု",
                "citation": offense_citation,
                "summary": offense_summary,
            },
            {
                "role": "ပြစ်ဒဏ်",
                "citation": penalty_citation,
                "summary": penalty_summary,
            },
        ]
        decision = (
            f"ဖော်ပြထားသောလုပ်ရပ်သည် {offense_citation} နှင့် သက်ဆိုင်နိုင်သည်။ "
            f"ယင်းအတွက် {penalty_citation} ပါ ပြစ်ဒဏ်သတ်မှတ်ချက်ကို စိစစ်အသုံးပြုရမည်။"
        )
        if complaint_citation and complaint_summary:
            facts.append({"label": "တိုင်တန်း/အရေးယူပုဒ်မ", "value": complaint_citation})
            related_sections.append(
                {
                    "role": "တိုင်တန်း/အရေးယူ",
                    "citation": complaint_citation,
                    "summary": complaint_summary,
                }
            )
            decision += f" တိုင်တန်း/အရေးယူမှုနှင့်ပတ်သက်၍ {complaint_citation} ကိုလည်း စစ်ဆေးရန်လိုပါသည်။"
        return {
            "rule_id": "legal_offense_penalty_link",
            "mode": "penalty_linked_legal_analysis",
            "status": "စိစစ်ပြီး",
            "facts": facts,
            "classification": {
                "name": law_name,
                "severity": f"{law_name} ပါ ပြစ်မှုနှင့်ပြစ်ဒဏ်ဆိုင်ရာကိစ္စ",
                "reasoning": (
                    "မေးမြန်းချက်ပါလုပ်ရပ်နှင့် တိုက်ရိုက်ဆင်တူသော ပြစ်မှုသတ်မှတ်ချက်ကို "
                    "သက်ဆိုင်ရာဥပဒေဒေတာတွင်တွေ့ရှိပြီး ယင်းနှင့်ဆက်စပ်သော ပြစ်ဒဏ်ပုဒ်မနှင့် ချိတ်ဆက်ထားသည်။"
                ),
            },
            "law_summary": f"{offense_citation} — {offense_summary}",
            "penalty": f"{penalty_citation} — {penalty_summary}",
            "decision": decision,
            "recommended_actions": _recommended_actions_for_law(
                law_name,
                has_complaint_rule=bool(complaint_citation),
            ),
            "related_sections": related_sections,
            "confidence": {
                "label": "မြင့်" if penalty_match["score"] >= 0.46 else "အလယ်အလတ်",
                "basis": "လုပ်ရပ်အမျိုးအစားနှင့် သက်ဆိုင်ရာပြစ်ဒဏ်ပုဒ်မကို အဆင့်လိုက်ချိတ်ဆက်ထားမှု",
            },
        }

    if answerable and rows:
        top = rows[0]
        law_name = top.get("law_name") or "သက်ဆိုင်ရာဥပဒေ"
        chapter = top.get("chapter") or "သက်ဆိုင်ရာအခန်း"
        section_labels = []
        related_sections = []
        seen_sections = set()
        top_chapter = top.get("chapter")
        focused_rows = [top]
        for row in rows[1:]:
            same_chapter = top_chapter and row.get("chapter") == top_chapter
            if same_chapter:
                focused_rows.append(row)
            if len(focused_rows) >= 3:
                break
        for row in focused_rows:
            section = row["section"] or "မသတ်မှတ်ထား"
            subsection = f" ({row['subsection']})" if row["subsection"] else ""
            citation = f"ပုဒ်မ {section}{subsection}"
            if citation in seen_sections:
                continue
            seen_sections.add(citation)
            section_labels.append(citation)
            excerpt = _full_legal_excerpt(
                row.get("matched_excerpt") or row["content"]
            )
            related_sections.append(
                {
                    "role": "အဓိက" if not related_sections else "ဆက်စပ်",
                    "citation": citation,
                    "summary": excerpt,
                }
            )
        penalty_summary = _semantic_penalty_summary(focused_rows) or _semantic_penalty_summary(rows[:6])
        section_summary = "၊ ".join(section_labels)
        primary_summary = related_sections[0]["summary"]
        decision = (
            f"မေးမြန်းချက်အတွက် {chapter}၊ {section_summary} ကို သက်ဆိုင်ရာပြဋ္ဌာန်းချက်အဖြစ် တွေ့ရှိသည်။ "
            f"{primary_summary}"
        )
        return {
            "rule_id": "semantic_legal_search",
            "mode": "legal_search",
            "facts": [
                {"label": "မေးမြန်းသည့်အကြောင်းအရာ", "value": question},
                {"label": "သက်ဆိုင်ရာဥပဒေ", "value": law_name},
                {"label": "သက်ဆိုင်ရာအခန်း", "value": chapter},
                {"label": "သက်ဆိုင်ရာပုဒ်မ", "value": section_summary},
            ],
            "classification": {
                "name": law_name,
                "severity": "ဥပဒေပြဋ္ဌာန်းချက် ချိတ်ဆက်မှု",
                "reasoning": "မေးမြန်းသည့်အကြောင်းအရာနှင့် တိုက်ရိုက်သက်ဆိုင်သော အခန်းနှင့် ပုဒ်မများကို စိစစ်ရွေးချယ်ထားသည်။",
            },
            "law_summary": primary_summary,
            "decision": decision,
            "penalty": penalty_summary,
            "recommended_actions": [
                "ကိုးကားထားသော မူရင်းပုဒ်မကို ဖွင့်၍ ပြဋ္ဌာန်းချက်အပြည့်အစုံကို စစ်ဆေးရန်",
                "ဖြစ်ရပ်တစ်ခုအပေါ် လက်တွေ့အသုံးချမည်ဆိုပါက ဥပဒေပညာရှင်ထံ အကြံဉာဏ်ရယူရန်",
            ],
            "related_sections": related_sections,
            "confidence": {
                "label": confidence,
                "basis": "သက်ဆိုင်ရာအခန်းနှင့် ပုဒ်မများတွင် တိုက်ရိုက်ဆက်စပ်သော ပြဋ္ဌာန်းချက်များ တွေ့ရှိမှု",
            },
        }

    return {
        "rule_id": "insufficient_evidence",
        "mode": "insufficient_evidence",
        "facts": [
            {"label": "မေးမြန်းသည့်အကြောင်းအရာ", "value": question},
            {"label": "စိစစ်မှုရလဒ်", "value": "လက်ရှိဥပဒေဒေတာအတွင်း တိုက်ရိုက်သက်ဆိုင်သော ပုဒ်မမတွေ့ရှိ"},
        ],
        "classification": {
            "name": "ခိုင်လုံသော ဥပဒေအထောက်အထား မတွေ့ရှိ",
            "severity": "အဖြေထုတ်ပြန်ရန် အထောက်အထားမလုံလောက်",
            "reasoning": "မသေချာသော သို့မဟုတ် မသက်ဆိုင်သောပုဒ်မကို အဖြေအဖြစ် မတင်ပြရန် ရလဒ်ကို ရပ်တန့်ထားသည်။",
        },
        "law_summary": "လက်ရှိဒေတာဘေ့စ်မှ ခိုင်လုံစွာကိုးကားနိုင်သည့် ဥပဒေပုဒ်မ မတွေ့ရှိပါ။",
        "decision": "သက်ဆိုင်ရာဥပဒေအထောက်အထား မလုံလောက်သဖြင့် စနစ်မှ ဥပဒေဆိုင်ရာဆုံးဖြတ်ချက် မထုတ်ပြန်ပါ။",
        "penalty": None,
        "recommended_actions": [
            "ဖြစ်ရပ်၊ အသက်၊ လုပ်ရပ်နှင့် သက်ဆိုင်သူများကို ပိုမိုတိကျစွာ ဖော်ပြရန်",
            "လိုအပ်သော ဥပဒေစာတမ်းကို ဒေတာဘေ့စ်ထဲ ထည့်သွင်းထားခြင်းရှိမရှိ စစ်ဆေးရန်",
        ],
        "related_sections": [],
        "confidence": {
            "label": confidence,
            "basis": "တိုက်ရိုက်ကိုးကားနိုင်သော ပြဋ္ဌာန်းချက် မလုံလောက်ခြင်း",
        },
    }


@app.post("/api/ask")
def analyze_legal_report():
    payload = request.get_json(silent=True) or {}
    question = unicodedata.normalize("NFC", str(payload.get("question", ""))).strip()
    category = payload.get("category") or None

    if not question:
        return jsonify(error="မေးခွန်း သို့မဟုတ် ဖြစ်ရပ်ဖော်ပြချက်တစ်ခု ရေးထည့်ပါ။"), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"စာလုံးရေ {MAX_QUESTION_CHARS} ထက် မကျော်ရပါ။"), 400

    started = time.perf_counter()
    trace_steps = []

    def record_step(step_name, step_started, details=None, status="completed"):
        trace_steps.append({
            "step_order": len(trace_steps) + 1,
            "step_name": step_name,
            "status": status,
            "duration_ms": max(0, round((time.perf_counter() - step_started) * 1000)),
            "details": details or {},
        })

    record_step("input_received", started, {"question_length": len(question)})
    try:
        step_started = time.perf_counter()
        search_question = normalize_query_for_search(question)
        matching_question = (
            question
            if search_question == question
            else f"{question} {search_question}"
        )
        record_step(
            "query_normalized", step_started,
            {"normalized_question": search_question, "changed": search_question != question},
        )

        step_started = time.perf_counter()
        case_analysis = classify_case(search_question)
        record_step(
            "case_classified", step_started,
            {
                "case_type": case_analysis.get("rule_id") if case_analysis else None,
                "classification": (case_analysis.get("classification") or {}).get("name") if case_analysis else None,
            },
            "completed" if case_analysis else "skipped",
        )

        step_started = time.perf_counter()
        embedding = embed_text(search_question)
        vector = json.dumps(embedding, separators=(",", ":"))
        record_step("embedding_generated", step_started, {"model": OLLAMA_EMBED_MODEL, "dimensions": len(embedding)})

        with psycopg.connect(**POSTGRES_CONFIG) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                step_started = time.perf_counter()
                (
                    semantic_rows,
                    top_score,
                    score_margin,
                    chapter_support,
                ) = _retrieve_hierarchical_sections(
                    cursor, vector, search_question, category
                )
                semantic_ok, top_score, score_margin = _semantic_is_answerable(
                    semantic_rows,
                    top_score=top_score,
                    margin=score_margin,
                    support=chapter_support,
                )
                penalty_match = _retrieve_penalty_match(
                    cursor, vector, matching_question, category
                )
                trace_terms = _trace_search_terms(
                    question, search_question, semantic_rows, penalty_match
                )
                record_step(
                    "hybrid_retrieval", step_started,
                    {
                        "candidate_count": len(semantic_rows),
                        "top_score": round(float(top_score or 0), 4),
                        "score_margin": round(float(score_margin or 0), 4),
                        "penalty_candidate_found": bool(penalty_match),
                        **trace_terms,
                    },
                )

                step_started = time.perf_counter()
                verified_sources = []
                if case_analysis:
                    verified_sources = _load_verified_rule_sources(
                        cursor,
                        case_analysis["expected_sections"],
                        _preferred_law_name_fragment(search_question),
                    )
                evidence = _dedupe_evidence(
                    verified_sources,
                    penalty_match["evidence"] if penalty_match else [],
                    semantic_rows,
                )
                record_step(
                    "candidates_ranked", step_started,
                    {
                        "verified_source_count": len(verified_sources),
                        "evidence_count": len(evidence),
                        "semantic_answerable": bool(semantic_ok),
                        "candidate_sections": [
                            f"{row.get('law_name') or 'အမည်မသတ်မှတ်ရသေး'} — ပုဒ်မ {row.get('section') or 'မသတ်မှတ်ရသေး'}"
                            for row in semantic_rows[:4]
                        ],
                    },
                )

                step_started = time.perf_counter()
                composer_used = False
                composer_validated = False
                display_analysis = None
                if (
                    not case_analysis
                    and evidence
                    and (penalty_match or top_score >= 0.36)
                ):
                    composer_used = True
                    try:
                        generated = call_grounded_model(
                            question,
                            evidence,
                            OLLAMA_CHAT_URL,
                            OLLAMA_CHAT_MODEL,
                        )
                        display_analysis = validate_and_normalize(
                            generated, question, evidence
                        )
                        if penalty_match and not display_analysis.get("penalty"):
                            raise ValueError(
                                "model omitted punishment supported by Chapter 27 evidence"
                            )
                        composer_validated = True
                    except (
                        urllib.error.URLError,
                        TimeoutError,
                        json.JSONDecodeError,
                        ValueError,
                    ):
                        display_analysis = None

                if display_analysis:
                    answerable = display_analysis["mode"] != "insufficient_evidence"
                    response_mode = display_analysis["mode"]
                    answer = display_analysis["decision"]
                    sources = (
                        _answer_sources(evidence, display_analysis)
                        if answerable
                        else []
                    )
                elif case_analysis and verified_sources:
                    answerable = True
                    response_mode = "verified_rule_fallback"
                    display_analysis = case_analysis
                    answer = case_analysis["decision"]
                    sources = verified_sources
                elif penalty_match:
                    answerable = True
                    response_mode = "penalty_linked_fallback"
                    display_analysis = _build_retrieval_analysis(
                        question,
                        semantic_rows,
                        True,
                        max(top_score, penalty_match["score"]),
                        penalty_match=penalty_match,
                    )
                    answer = display_analysis["decision"]
                    sources = penalty_match["evidence"]
                elif semantic_ok:
                    answerable = True
                    response_mode = "extractive_fallback"
                    display_analysis = _build_retrieval_analysis(
                        question, semantic_rows, True, top_score
                    )
                    answer = display_analysis["decision"]
                    sources = [_semantic_source(row) for row in semantic_rows[:5]]
                else:
                    answerable = False
                    response_mode = "insufficient_evidence"
                    display_analysis = _build_retrieval_analysis(
                        question, semantic_rows, False, top_score
                    )
                    answer = display_analysis["decision"]
                    sources = []

                selected_source = sources[0] if sources else {}
                selected_law = selected_source.get("law_name")
                selected_section = selected_source.get("section")
                record_step(
                    "main_section_selected", step_started,
                    {
                        "law_name": selected_law,
                        "section": selected_section,
                        "response_mode": response_mode,
                        "source_count": len(sources),
                    },
                    "completed" if sources else "skipped",
                )

                step_started = time.perf_counter()
                if _question_may_need_penalty(matching_question):
                    display_analysis = _ensure_analysis_penalty(
                        display_analysis, penalty_match
                    )
                elif display_analysis:
                    display_analysis["penalty"] = ""

                # A court order, burden-of-proof rule, injunction, or civil remedy
                # is not automatically a criminal punishment.  Keep the dedicated
                # punishment field only when the final text contains an explicit
                # imprisonment/fine formulation.  This also guards against a
                # composer labelling phrases such as "အမိန့်ချမှတ်နိုင်သည်" alone
                # as a punishment.
                if display_analysis and display_analysis.get("penalty"):
                    penalty_text = str(display_analysis.get("penalty") or "")
                    if not any(
                        keyword in penalty_text
                        for keyword in STRONG_PUNISHMENT_TEXT_KEYWORDS
                    ):
                        display_analysis["penalty"] = ""
                punishment_section = None
                punishment_excerpt = None
                punishment_found = False
                punishment_same_section = False
                if penalty_match:
                    punishment_sources = penalty_match.get("evidence") or []
                    if punishment_sources:
                        punishment_section = punishment_sources[-1].get("section")
                        punishment_excerpt = _extract_punishment_excerpt(
                            punishment_sources[-1]
                        )
                        punishment_found = True
                        punishment_same_section = bool(
                            selected_section and punishment_section
                            and str(selected_section) == str(punishment_section)
                        )
                elif display_analysis and display_analysis.get("penalty"):
                    # The final validated analysis is what the user UI renders.
                    # Use it for every response mode so Admin never disagrees with
                    # a source-backed punishment that is already visible to users.
                    punishment_excerpt = display_analysis.get("penalty")
                    related_sections = display_analysis.get("related_sections") or []
                    punishment_citation = next(
                        (
                            item.get("citation")
                            for item in related_sections
                            if item.get("citation")
                            and (
                                "ပြစ်ဒဏ်" in str(item.get("role") or "")
                                or "ပြစ်ဒဏ်" in str(item.get("summary") or "")
                                or "ထောင်ဒဏ်" in str(item.get("summary") or "")
                                or "ငွေဒဏ်" in str(item.get("summary") or "")
                            )
                        ),
                        None,
                    )
                    primary_citation = next(
                        (
                            item.get("citation")
                            for item in related_sections
                            if item.get("role") == "အဓိက" and item.get("citation")
                        ),
                        None,
                    )
                    punishment_section = re.sub(
                        r"^ပုဒ်မ\s*",
                        "",
                        str(punishment_citation or primary_citation or selected_section or ""),
                    ).strip() or selected_section
                    punishment_found = True
                    punishment_same_section = bool(
                        selected_section and punishment_section
                        and str(selected_section) == str(punishment_section)
                    )
                record_step(
                    "punishment_linked", step_started,
                    {
                        "required": _question_may_need_penalty(matching_question),
                        "found": punishment_found,
                        "section": punishment_section,
                        "offense_section": selected_section,
                        "same_section": punishment_same_section,
                        "punishment_excerpt": punishment_excerpt,
                    },
                    "completed" if punishment_found else "skipped",
                )

                step_started = time.perf_counter()
                record_step(
                    "evidence_validated", step_started,
                    {
                        "answerable": bool(answerable),
                        "composer_used": composer_used,
                        "composer_validated": composer_validated,
                        "evidence_count": len(evidence),
                        "law_name": selected_law,
                        "section": selected_section,
                        "punishment_found": punishment_found,
                        "source_names": list(dict.fromkeys(
                            source.get("law_name")
                            for source in sources
                            if source.get("law_name")
                        )),
                    },
                    "completed" if answerable else "failed",
                )

                step_started = time.perf_counter()
                display_analysis = _safe_readable_law_summary(
                    question, display_analysis, evidence
                )
                record_step(
                    "answer_composed", step_started,
                    {"response_mode": response_mode, "answer_length": len(answer or "")},
                )

                cursor.execute(
                    """
                    INSERT INTO retrieval_audit (question, retrieved_chunk_ids, answer)
                    VALUES (%s, %s, %s)
                    """,
                    (question, [source["chunk_id"] for source in sources], answer),
                )

                total_ms = round((time.perf_counter() - started) * 1000)
                cursor.execute(
                    """
                    INSERT INTO query_runs (
                        question, normalized_question, case_type, selected_law,
                        selected_section, punishment_section, response_mode,
                        answerable, top_score, total_ms
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        question, search_question,
                        case_analysis.get("rule_id") if case_analysis else None,
                        selected_law, selected_section, punishment_section,
                        response_mode, answerable, float(top_score or 0), total_ms,
                    ),
                )
                query_run_id = cursor.fetchone()["id"]
                for trace in trace_steps:
                    cursor.execute(
                        """
                        INSERT INTO query_trace_steps (
                            query_run_id, step_order, step_name, status,
                            duration_ms, details
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            query_run_id, trace["step_order"], trace["step_name"],
                            trace["status"], trace["duration_ms"],
                            json.dumps(trace["details"], ensure_ascii=False),
                        ),
                    )

        return jsonify(
            question=question,
            answer=answer,
            answerable=answerable,
            mode=response_mode,
            analysis=display_analysis,
            sources=sources,
            retrieval={
                "top_score": round(top_score, 4),
                "score_margin": round(score_margin, 4),
                "semantic_search_used": True,
                "chapter_support": chapter_support,
                "composer_used": composer_used,
                "composer_validated": composer_validated,
            },
            response_ms=round((time.perf_counter() - started) * 1000),
            disclaimer=(
                "ဤရလဒ်သည် ထည့်သွင်းထားသော ဥပဒေစာတမ်းများနှင့် "
                "စနစ်၏ ကနဦးစိစစ်မှုအပေါ် အခြေခံထားပြီး တရားဝင်ဥပဒေအကြံဉာဏ် မဟုတ်ပါ။"
            ),
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return jsonify(error="Embedding ဝန်ဆောင်မှုကို ချိတ်ဆက်၍မရပါ။", detail=str(exc)), 503
    except psycopg.Error as exc:
        return jsonify(error="ဥပဒေဒေတာဘေ့စ်ကို ချိတ်ဆက်၍မရပါ။", detail=str(exc)), 503


@app.post("/api/ask-legacy")
def ask_legal_question():
    payload = request.get_json(silent=True) or {}
    question = unicodedata.normalize("NFC", str(payload.get("question", ""))).strip()
    category = payload.get("category") or None

    if not question:
        return jsonify(error="မေးခွန်းတစ်ခု ရေးထည့်ပါ။"), 400
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify(error=f"မေးခွန်းသည် စာလုံးရေ {MAX_QUESTION_CHARS} ထက် မကျော်ရပါ။"), 400

    started = time.perf_counter()
    try:
        embedding = embed_text(question)
        vector = json.dumps(embedding, separators=(",", ":"))
        with psycopg.connect(**POSTGRES_CONFIG) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM match_legal_chunks(%s::vector, %s, 5, %s)",
                    (vector, question, category),
                )
                rows = cursor.fetchall()

                if not rows or float(rows[0]["vector_score"]) < 0.40:
                    answer = (
                        "လက်ရှိထည့်သွင်းထားသော ဥပဒေစာတမ်းများအတွင်း "
                        "ဤမေးခွန်းကို ခိုင်လုံစွာဖြေဆိုနိုင်သည့် အထောက်အထား မတွေ့ရှိပါ။"
                    )
                    sources = []
                else:
                    answer = rows[0]["content"]
                    sources = [
                        {
                            "chunk_id": row["chunk_id"],
                            "law_name": row["law_name"],
                            "law_number": row["law_number"],
                            "section": row["section"],
                            "subsection": row["subsection"],
                            "content": row["content"],
                            "source_url": row["source_url"],
                            "score": round(float(row["vector_score"]), 4),
                        }
                        for row in rows
                    ]

                cursor.execute(
                    """
                    INSERT INTO retrieval_audit (question, retrieved_chunk_ids, answer)
                    VALUES (%s, %s, %s)
                    """,
                    (question, [source["chunk_id"] for source in sources], answer),
                )

        return jsonify(
            question=question,
            answer=answer,
            sources=sources,
            response_ms=round((time.perf_counter() - started) * 1000),
            disclaimer=(
                "ဤအဖြေသည် ထည့်သွင်းထားသော ဥပဒေစာတမ်းများမှ အချက်အလက်ရှာဖွေတင်ပြခြင်းသာဖြစ်ပြီး "
                "တရားဝင်ဥပဒေအကြံဉာဏ် မဟုတ်ပါ။"
            ),
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return jsonify(error="Embedding ဝန်ဆောင်မှုကို ချိတ်ဆက်၍မရပါ။", detail=str(exc)), 503
    except psycopg.Error as exc:
        return jsonify(error="ဥပဒေဒေတာဘေ့စ်ကို ချိတ်ဆက်၍မရပါ။", detail=str(exc)), 503


def iter_document_blocks(document):
    """Yield top-level paragraphs and tables in their original document order."""
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


@app.post("/extract-docx")
def extract_docx():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="multipart field 'file' is required"), 400
    if not uploaded.filename.lower().endswith(".docx"):
        return jsonify(error="only DOCX files are accepted"), 415

    uploaded.stream.seek(0, os.SEEK_END)
    size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if size > MAX_FILE_BYTES:
        return jsonify(error=f"file exceeds {MAX_FILE_BYTES // 1024 // 1024} MB"), 413

    try:
        document = Document(uploaded.stream)
    except Exception as exc:
        return jsonify(error="invalid or unreadable DOCX", detail=str(exc)), 400

    blocks = []
    paragraph_count = 0
    table_count = 0
    table_row_count = 0

    for block in iter_document_blocks(document):
        if isinstance(block, Paragraph):
            value = unicodedata.normalize("NFC", block.text).strip()
            if value:
                blocks.append(value)
                paragraph_count += 1
            continue

        table_count += 1
        for row in block.rows:
            cells = [
                unicodedata.normalize("NFC", cell.text).strip()
                for cell in row.cells
            ]
            if any(cells):
                blocks.append("\t".join(cells))
                table_row_count += 1

    text = "\n".join(blocks).strip()
    if not text:
        return jsonify(error="DOCX contains no extractable text"), 422

    return jsonify(
        text=text,
        filename=uploaded.filename,
        format="docx",
        paragraph_count=paragraph_count,
        table_count=table_count,
        table_row_count=table_row_count,
        character_count=len(text),
    )


@app.post("/ocr")
def ocr_pdf():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error="multipart field 'file' is required"), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify(error="only PDF files are accepted"), 415

    uploaded.stream.seek(0, os.SEEK_END)
    size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if size > MAX_FILE_BYTES:
        return jsonify(error=f"file exceeds {MAX_FILE_BYTES // 1024 // 1024} MB"), 413

    request_languages = request.form.get("languages", LANGUAGES)
    request_dpi = request.form.get("dpi", default=DPI, type=int)
    request_psm = request.form.get("psm", default=PSM, type=int)
    if request_languages not in ALLOWED_LANGUAGES:
        return jsonify(error="languages must be mya, eng, or mya+eng"), 400
    if request_dpi is None or not 150 <= request_dpi <= 450:
        return jsonify(error="dpi must be between 150 and 450"), 400
    if request_psm not in ALLOWED_PSM:
        return jsonify(error="psm must be one of 3, 4, 6, 11, or 12"), 400

    with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_pdf:
        uploaded.save(temporary_pdf.name)
        try:
            page_count = int(pdfinfo_from_path(temporary_pdf.name)["Pages"])
        except Exception as exc:
            return jsonify(error="invalid or unreadable PDF", detail=str(exc)), 400

        if page_count > MAX_PAGES:
            return jsonify(error=f"PDF has {page_count} pages; maximum is {MAX_PAGES}"), 413

        requested_pages = request.form.get("max_pages", type=int)
        pages_to_process = page_count
        if requested_pages is not None:
            if requested_pages < 1:
                return jsonify(error="max_pages must be at least 1"), 400
            pages_to_process = min(page_count, requested_pages)

        pages = []
        config = f"--oem 1 --psm {request_psm} -c preserve_interword_spaces=1"
        for page_number in range(1, pages_to_process + 1):
            images = convert_from_path(
                temporary_pdf.name,
                dpi=request_dpi,
                first_page=page_number,
                last_page=page_number,
                fmt="png",
                thread_count=1,
            )
            text = pytesseract.image_to_string(
                images[0],
                lang=request_languages,
                config=config,
            )
            pages.append(
                {
                    "page": page_number,
                    "text": unicodedata.normalize("NFC", text).strip(),
                }
            )
            images[0].close()

    combined = "\n\n".join(
        f"--- Page {page['page']} ---\n{page['text']}" for page in pages
    )
    return jsonify(
        text=combined,
        pages=pages,
        page_count=page_count,
        processed_page_count=pages_to_process,
        languages=request_languages,
        dpi=request_dpi,
        psm=request_psm,
    )
