import unittest

from grounded_answer import validate_and_normalize


EVIDENCE = [
    {
        "law_name": "ကလေးသူငယ် အခွင့်အရေးများဆိုင်ရာဥပဒေ",
        "chapter": "အခန်း (၁၁)",
        "section": "၄၂",
        "subsection": "က",
        "content": "ဖခင်တိုင်းသည် လင်မယားကွာရှင်းသည်ဖြစ်စေ၊ မကွာရှင်းသည်ဖြစ်စေ မိမိ၏သားသမီးတိုင်းကို စရိတ်ထောက်ပံ့ရန် တာဝန်ရှိစေရမည်။",
    },
    {
        "law_name": "ကလေးသူငယ် အခွင့်အရေးများဆိုင်ရာဥပဒေ",
        "chapter": "အခန်း (၁၁)",
        "section": "၄၃",
        "subsection": "က",
        "content": "ကလေးသူငယ်တစ်ဦးလျှင် လစဉ်ကျပ် ၅၀၀၀၀ ထက် မပိုသော စရိတ်ပေးစေရန် အမိန့်ချမှတ်နိုင်သည်။",
    },
]


def valid_result():
    return {
        "answerable": True,
        "status": "စိစစ်ပြီး",
        "classification": {
            "name": "ကလေးစရိတ်ထောက်ပံ့ရန် ပျက်ကွက်မှု",
            "severity": "မိဘ၏ ဥပဒေတာဝန်",
            "reasoning": "ကွာရှင်းပြီးသော်လည်း ဖခင်၏တာဝန် ဆက်ရှိသည်။",
        },
        "facts": [{"label": "ဖြစ်ရပ်", "value": "ဖခင်က စရိတ်မထောက်ပံ့ခြင်း"}],
        "decision": "ဖခင်သည် ကလေးကို စရိတ်ထောက်ပံ့ရန် တာဝန်ရှိသည်။",
        "law_summary": "ပုဒ်မ ၄၂ နှင့် ၄၃ အရ တာဝန်နှင့် တရားရုံးအမိန့်ကို သတ်မှတ်ထားသည်။",
        "penalty": None,
        "recommended_actions": ["သက်ဆိုင်ရာတရားရုံးတွင် လျှောက်ထားရန်"],
        "related_sections": [
            {"role": "အဓိက", "citation": "ပုဒ်မ ၄၂(က)", "summary": "ဖခင်၏ စရိတ်ထောက်ပံ့ရန်တာဝန်"},
            {"role": "ဆက်စပ်", "citation": "ပုဒ်မ ၄၃(က)", "summary": "တရားရုံးက စရိတ်ပေးရန် အမိန့်ချမှတ်နိုင်မှု"},
        ],
        "supporting_quote": "ဖခင်တိုင်းသည် လင်မယားကွာရှင်းသည်ဖြစ်စေ၊ မကွာရှင်းသည်ဖြစ်စေ မိမိ၏သားသမီးတိုင်းကို စရိတ်ထောက်ပံ့ရန် တာဝန်ရှိစေရမည်။",
        "cited_sections": ["ပုဒ်မ ၄၂", "ပုဒ်မ ၄၃"],
    }


class GroundedAnswerTests(unittest.TestCase):
    def test_accepts_citations_and_quote_from_evidence(self):
        normalized = validate_and_normalize(valid_result(), "ဖခင်က ကလေးစရိတ်မပေးပါ။", EVIDENCE)
        self.assertEqual(normalized["rule_id"], "grounded_rag")
        self.assertEqual(normalized["related_sections"][0]["citation"], "ပုဒ်မ ၄၂(က)")

    def test_rejects_section_outside_evidence(self):
        result = valid_result()
        result["cited_sections"] = ["ပုဒ်မ ၉၉"]
        with self.assertRaises(ValueError):
            validate_and_normalize(result, "မေးခွန်း", EVIDENCE)

    def test_rejects_invented_penalty_number(self):
        result = valid_result()
        result["penalty"] = "ထောင်ဒဏ် ၁၀ နှစ်"
        with self.assertRaises(ValueError):
            validate_and_normalize(result, "မေးခွန်း", EVIDENCE)

    def test_rejects_invented_number_outside_penalty(self):
        result = valid_result()
        result["decision"] = "တစ်လလျှင် ကျပ် ၉၉၉၉၉၉ ပေးရမည်။"
        with self.assertRaisesRegex(ValueError, "number outside"):
            validate_and_normalize(result, "မေးခွန်း", EVIDENCE)

    def test_normalizes_model_refusal(self):
        normalized = validate_and_normalize(
            {"answerable": False}, "ယာဉ်မောင်းလိုင်စင်အကြောင်း", EVIDENCE
        )
        self.assertEqual(normalized["mode"], "insufficient_evidence")
        self.assertEqual(normalized["related_sections"], [])


if __name__ == "__main__":
    unittest.main()
