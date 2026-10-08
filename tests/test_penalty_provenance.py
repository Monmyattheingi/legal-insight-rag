import unittest

from ocr_service import _penalty_is_grounded_in_selected_law, _question_may_need_penalty


class PenaltyProvenanceTests(unittest.TestCase):
    def test_ordinary_tax_payment_question_does_not_request_penalty(self):
        self.assertFalse(_question_may_need_penalty(
            "နိုင်ငံခြားက ပစ္စည်းမှာပြီး ပြန်ရောင်းရင် tax ကို ဘယ်သူပေးရတာလဲ။"
        ))

    def test_tax_evasion_question_still_requests_penalty(self):
        self.assertTrue(_question_may_need_penalty(
            "ကုန်သွယ်လုပ်ငန်းခွန် အရောင်းစာရင်းဖျောက်ရင် ဘာပြစ်ဒဏ်ရှိလဲ။"
        ))

    def test_rejects_penal_code_penalty_for_commercial_tax_result(self):
        analysis = {"penalty": "ပုဒ်မ ၃၈၀ — ထောင်ဒဏ် ချမှတ်နိုင်သည်။"}
        sources = [{
            "law_name": "ကုန်သွယ်လုပ်ငန်းခွန်ဥပဒေ",
            "section": "၁၃",
            "content": "နှစ်ချုပ်ကြေညာလွှာကို သုံးလအတွင်း ပေးပို့ရမည်။",
        }]
        self.assertFalse(_penalty_is_grounded_in_selected_law(
            analysis, "ကုန်သွယ်လုပ်ငန်းခွန်ဥပဒေ", sources
        ))

    def test_accepts_matching_same_law_penalty_section(self):
        analysis = {"penalty": "ပုဒ်မ ၂၂ — ထောင်ဒဏ် ချမှတ်နိုင်သည်။"}
        sources = [{
            "law_name": "ကုန်သွယ်လုပ်ငန်းခွန်ဥပဒေ",
            "section": "၂၂",
            "content": "ပြစ်မှုထင်ရှားလျှင် ထောင်ဒဏ် ချမှတ်နိုင်သည်။",
        }]
        self.assertTrue(_penalty_is_grounded_in_selected_law(
            analysis, "ကုန်သွယ်လုပ်ငန်းခွန်ဥပဒေ", sources
        ))

    def test_rejects_explicit_cross_law_penalty_match(self):
        analysis = {"penalty": "ပုဒ်မ ၃၈၀ — ထောင်ဒဏ် ချမှတ်နိုင်သည်။"}
        penalty_match = {
            "offense": {"law_name": "ရာဇသတ်ကြီး"},
            "penalty": {"law_name": "ရာဇသတ်ကြီး"},
            "evidence": [],
        }
        self.assertFalse(_penalty_is_grounded_in_selected_law(
            analysis, "ကုန်သွယ်လုပ်ငန်းခွန်ဥပဒေ", [], penalty_match
        ))


if __name__ == "__main__":
    unittest.main()
