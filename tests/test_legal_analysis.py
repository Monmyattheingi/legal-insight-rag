import unittest

from legal_analysis import classify_case, extract_case_facts


class LegalAnalysisTests(unittest.TestCase):
    def test_extracts_myanmar_age_and_abuse_facts(self):
        report = (
            "အိမ်အကူအဖြစ် လုပ်ကိုင်နေသော အသက် ၁၄ နှစ်အရွယ် ကလေးတစ်ဦးကို "
            "အိမ်ရှင်က တုတ်ဖြင့်ရိုက်နှက်ပြီး အစားအစာငတ်ထားကာ ဒဏ်ရာရစေခဲ့သည်။"
        )
        facts = extract_case_facts(report)
        self.assertEqual(facts["age"], 14)
        self.assertEqual(facts["perpetrator"], "အိမ်ရှင်")
        self.assertIn("ရုပ်ပိုင်းဆိုင်ရာ ရိုက်နှက်မှု", facts["actions"])
        self.assertIn("အစားအစာမပေးဘဲ ထားရှိမှု", facts["actions"])

    def test_classifies_under_ten_property_damage(self):
        result = classify_case("အသက် ၈ နှစ်အရွယ် ကလေးတစ်ဦးက အိမ်နီးချင်း၏ ပစ္စည်းကို ဖျက်ဆီးခဲ့သည်။")
        self.assertEqual(result["rule_id"], "minor_under_10_property_damage")
        self.assertEqual(result["expected_sections"][0]["section"], "၇၈")

    def test_classifies_child_cruelty_to_section_103(self):
        report = (
            "အသက် ၁၄ နှစ်အရွယ် ကလေးတစ်ဦးကို အိမ်ရှင်က တုတ်ဖြင့်ရိုက်နှက်ခြင်း၊ "
            "အစားအစာ ငတ်ထားခြင်းနှင့် ဒဏ်ရာများရအောင် ပြုလုပ်ခဲ့သည်။"
        )
        result = classify_case(report)
        self.assertEqual(result["rule_id"], "child_cruelty_or_torture")
        self.assertEqual(result["expected_sections"][0]["section"], "၁၀၃")
        self.assertIn("၈ လ", result["penalty"])

    def test_classifies_child_sexual_exploitation_to_section_105(self):
        result = classify_case(
            "မသမာသူလူတစ်စုက ကလေးသူငယ်အား လိင်ပိုင်းဆိုင်ရာ ခေါင်းပုံဖြတ်ခြင်း ပြုလုပ်ခဲ့သည်။"
        )
        self.assertEqual(result["rule_id"], "child_sexual_exploitation")
        self.assertEqual(result["expected_sections"][0]["section"], "၁၀၅")
        self.assertEqual(result["expected_sections"][0]["subsections"], ["ခ", "၃"])
        self.assertIn("၂ နှစ်", result["penalty"])
        self.assertIn("၁၀ နှစ်", result["penalty"])
        self.assertEqual(result["related_sections"][0]["citation"], "ပုဒ်မ ၁၀၅(ခ)(၃)")

    def test_child_sale_and_prostitution_returns_both_penalties(self):
        result = classify_case(
            "ကလေးသူငယ်ကို ရောင်းချခြင်း၊ ပြည့်တန်ဆာပြုလုပ်ခိုင်းစေခြင်းကို မည်သို့စီရင်နိုင်သနည်း။"
        )
        self.assertEqual(result["rule_id"], "child_sale_and_prostitution")
        self.assertEqual(
            [item["section"] for item in result["expected_sections"]],
            ["၁၀၆", "၃", "၁၀၅", "၃"],
        )
        self.assertIn("ပုဒ်မ ၁၀၆(က)", result["penalty"])
        self.assertIn("၁၀ နှစ်", result["penalty"])
        self.assertIn("နှစ် ၂၀", result["penalty"])
        self.assertIn("သိန်း ၅၀", result["penalty"])
        self.assertIn("သိန်း ၁၀၀", result["penalty"])
        self.assertIn("ပုဒ်မ ၁၀၅(ခ)(၁)", result["penalty"])
        self.assertIn("၂ နှစ်", result["penalty"])
        self.assertIn("၁၅ သိန်း", result["penalty"])

    def test_child_sale_alone_uses_section_106(self):
        result = classify_case("ကလေးသူငယ်ကို ရောင်းချခြင်းအတွက် ပြစ်ဒဏ်ကဘာလဲ။")
        self.assertEqual(result["rule_id"], "child_sale_and_prostitution")
        self.assertIn("ပုဒ်မ ၁၀၆(က)", result["penalty"])
        self.assertNotIn("ပုဒ်မ ၁၀၅(ခ)(၁)", result["penalty"])

    def test_child_prostitution_alone_uses_section_105(self):
        result = classify_case("ကလေးသူငယ်ကို ပြည့်တန်ဆာပြုလုပ်ခိုင်းစေခြင်းအတွက် ပြစ်ဒဏ်ကဘာလဲ။")
        self.assertEqual(result["rule_id"], "child_sale_and_prostitution")
        self.assertIn("ပုဒ်မ ၁၀၅(ခ)(၁)", result["penalty"])
        self.assertNotIn("ပုဒ်မ ၁၀၆(က)", result["penalty"])

    def test_plural_child_sale_and_prostitution_keeps_both_offenses(self):
        result = classify_case(
            "မသမာသူများက အသက်မပြည့်သေးသော ကလေးများအား ရောင်းချခြင်း နှင့် "
            "ပြည့်တန်ဆာခိုင်းခြင်းများ ပြုလုပ်ရန်စေခိုင်းခဲ့ကြသည်။"
        )
        self.assertEqual(result["rule_id"], "child_sale_and_prostitution")
        self.assertIn("ပုဒ်မ ၁၀၆(က)", result["penalty"])
        self.assertIn("ပုဒ်မ ၁၀၅(ခ)(၁)", result["penalty"])
        self.assertEqual(
            [item["citation"] for item in result["related_sections"][:2]],
            ["ပုဒ်မ ၁၀၆(က)", "ပုဒ်မ ၁၀၅(ခ)(၁)"],
        )

    def test_general_question_is_not_forced_into_case_rule(self):
        self.assertIsNone(classify_case("ကလေးသူငယ်၏ ပညာသင်ကြားခွင့်ကို ရှင်းပြပါ။"))

    def test_guardianship_after_divorce_uses_chapter_10(self):
        result = classify_case(
            "မိဘများကွာရှင်းခြင်း ဖြစ်ပွားပြီးနောက် ကလေးသူငယ်ကို အုပ်ထိန်းခွင့်ကို မည်သူက ရရှိမည်နည်း။"
        )
        self.assertEqual(result["rule_id"], "guardianship_after_separation")
        self.assertEqual(
            [item["section"] for item in result["expected_sections"]],
            ["၃၆", "၃၈", "၃၉"],
        )
        self.assertIn("အခန်း (၁၀)", result["law_summary"])


if __name__ == "__main__":
    unittest.main()
