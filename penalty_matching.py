import re


# These concepts are deliberately phrased as acts, not generic words such as
# "child" or "cause". Generic words occur throughout the Act and can make an
# unrelated provision outrank the provision describing the actual conduct.
PENALTY_ACT_CONCEPTS = {
    "cyber_unauthorized_access": (
        "password",
        "account",
        "login",
        "hack",
        "စကားဝှက်",
        "အကောင့်",
        "ခွင့်ပြုချက်မရှိဘဲ ဝင်ရောက်",
        "ကွန်ပျူတာစနစ်",
        "ထိန်းချုပ်ခြင်း",
        "ချိတ်ဆက်ထိန်းချုပ်ခြင်း",
    ),
    "cyber_information_theft": (
        "data",
        "personal data",
        "အချက်အလက်",
        "သတင်းအချက်အလက်",
        "အီလက်ထရောနစ်သတင်းအချက်အလက်",
        "ကိုယ်ရေးအချက်အလက်",
        "ရယူခြင်း",
        "ခိုးယူခြင်း",
    ),
    "cyber_fake_link_fraud": (
        "phishing",
        "link",
        "fake link",
        "scam",
        "ချိတ်ဆက်လင့်ခ်",
        "လင့်ခ်",
        "လိမ်လည်",
        "လှည့်ဖြား",
        "ငွေကြေးလိမ်လည်",
        "မရိုးမဖြောင့်သောသဘော",
    ),
    "alcohol_supply": (
        "အရက်ဝယ်ခိုင်း",
        "ဘီယာဝယ်ခိုင်း",
        "အရက်သောက်ရန်တိုက်တွန်း",
        "ဘီယာသောက်ရန်တိုက်တွန်း",
    ),
    "adult_venue_entry": (
        "ကပွဲတွင်ဝင်ရောက်ခွင့်ပြု",
        "ကာရာအိုကေတွင်ဝင်ရောက်ခွင့်ပြု",
        "အနှိပ်ခန်းတွင်ဝင်ရောက်ခွင့်ပြု",
    ),
    "psychological_violence": ("စိတ်ပိုင်းဆိုင်ရာအကြမ်းဖက်",),
    "corporal_punishment": ("ရိုက်နှက်ပြစ်ဒဏ်ပေး", "ရိုက်နှက်ဒဏ်ပေး"),
    "physical_bullying": ("ရုပ်ပိုင်းဆိုင်ရာနှိပ်ကွပ်", "နိုင်ထက်စီးနင်း"),
    "gambling": ("လောင်းကစား",),
    "pawn_transaction": ("အပေါင်ခံ", "ပစ္စည်းပေါင်နှံ"),
    "runaway_assistance": ("ထွက်ပြေးလွတ်မြောက်",),
    "sexual_touching": (
        "လိင်ပိုင်းဆိုင်ရာခန္ဓာကိုယ်အစိတ်အပိုင်းအားထိတွေ့",
        "ခန္ဓာကိုယ်အစိတ်အပိုင်းအားထိတွေ့ပွတ်သပ်",
    ),
    "unlicensed_care_home": ("တည်ထောင်ခွင့်ပြုမိန့်မရှိဘဲ",),
    "alcohol_business_work": (
        "အရက်အရောင်းအဝယ်ပြုလုပ်သောလုပ်ငန်းတွင်အလုပ်",
        "ဘီယာအရောင်းအဝယ်ပြုလုပ်သောလုပ်ငန်းတွင်အလုပ်",
    ),
    "sexual_venue_work": ("လိင်ပိုင်းဆိုင်ရာလုပ်ငန်းနှင့်ဆက်စပ်",),
    "causing_child_begging": (
        "ကလေးသူငယ်အားတောင်းရမ်းစေ",
        "ကလေးကိုတောင်းရမ်းခိုင်း",
        "တောင်းရမ်းခိုင်း",
        "တောင်းရမ်းစေ",
    ),
    "using_child_while_begging": (
        "တောင်းရမ်းရာတွင်ကလေးသူငယ်ကိုအသုံးပြု",
        "တောင်းရမ်းရာတွင်ကလေးကိုအသုံးပြု",
        "တောင်းရမ်းရာ၌ကလေးကိုအသုံးပြု",
    ),
    "disabled_child_abuse": ("မသန်စွမ်းကလေးသူငယ်အားနိုင်ထက်စီးနင်း",),
    "harmful_work": ("ထိခိုက်မှုဖြစ်စေသောအလုပ်",),
    "dangerous_work": (
        "ဘေးအန္တရာယ်ရှိသောအလုပ်",
        "ကျန်းမာရေးထိခိုက်စေသောအလုပ်",
    ),
    "forced_labour": ("အဓမ္မအလုပ်", "အတင်းအဓမ္မအလုပ်"),
    "armed_conflict_use": ("လက်နက်ကိုင်ပဋိပက္ခ",),
    "prostitution_household": (
        "ပြည့်တန်ဆာလုပ်ငန်းဖြင့်အသက်မွေးဝမ်းကျောင်းပြုနေသူနှင့်အတူနေ",
        "ပြည့်တန်ဆာအဖြစ်အသက်မွေးဝမ်းကျောင်းပြုနေသည်ကိုသိလျက်",
        "ပြည့်တန်ဆာကိစ္စအလို့ငှာပေါင်းသင်းဆက်ဆံရန်",
    ),
    "child_prostitution": ("ပြည့်တန်ဆာ",),
    "child_sale": (
        "ကလေးသူငယ်ရောင်းချ",
        "ကလေးသူငယ်ကိုရောင်းချ",
        "ကလေးသူငယ်အားရောင်းချ",
        "ကလေးရောင်းချ",
        "ကလေးကိုရောင်းချ",
        "ကလေးအားရောင်းချ",
    ),
    "sexual_exploitation": (
        "လိင်ပိုင်းဆိုင်ရာခေါင်းပုံဖြတ်",
        "လိင်ပိုင်းဆိုင်ရာအလွဲသုံး",
    ),
    "child_pornography": ("ကလေးသူငယ်ညစ်ညမ်းပုံ", "ညစ်ညမ်းပုံ"),
    "forced_marriage": ("အတင်းအကြပ်လက်ထပ်", "အတင်းလက်ထပ်"),
    "torture": ("နှိပ်စက်", "ညှဉ်းပန်း"),
    "trafficking": ("လူကုန်ကူး",),
    "body_part_sale": (
        "ကိုယ်အင်္ဂါရောင်းချ",
        "ကိုယ်ခန္ဓာအစိတ်အပိုင်းအားရောင်းချ",
        "ခန္ဓာကိုယ်အစိတ်အပိုင်းရောင်းချ",
        "ခန္ဓာကိုယ်အစိတ်အပိုင်းတရားမဝင်ထုတ်ယူ",
    ),
    "kidnapping": ("ပြန်ပေးဆွဲ", "ခိုးယူ"),
}


def _compact_burmese_match_text(value):
    return re.sub(r"[\s၊။,.()\[\]{}\-_/]+", "", value or "").lower()


def _penalty_concept_names(value):
    compact_value = _compact_burmese_match_text(value)
    return {
        name
        for name, phrases in PENALTY_ACT_CONCEPTS.items()
        if any(_compact_burmese_match_text(phrase) in compact_value for phrase in phrases)
    }


def _penalty_concept_overlap(question, content):
    question_concepts = _penalty_concept_names(question)
    if not question_concepts:
        return 0.0
    content_concepts = _penalty_concept_names(content)
    return len(question_concepts & content_concepts) / len(question_concepts)
