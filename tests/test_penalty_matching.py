import unittest

from penalty_matching import _penalty_concept_names, _penalty_concept_overlap


class PenaltyConceptMatchingTests(unittest.TestCase):
    def test_forced_labour_does_not_match_prostitution(self):
        question = "ကလေးသူငယ်အား အဓမ္မအလုပ်ခိုင်းစေခဲ့သည်။"
        forced_labour = "ကလေးသူငယ်အား အဓမ္မ အလုပ်ခိုင်းစေခြင်း"
        prostitution = "ကလေးသူငယ်အား ပြည့်တန်ဆာပြုလုပ်ခိုင်းစေခြင်း"
        self.assertEqual(_penalty_concept_overlap(question, forced_labour), 1.0)
        self.assertEqual(_penalty_concept_overlap(question, prostitution), 0.0)

    def test_spaces_do_not_break_burmese_concept_matching(self):
        self.assertEqual(
            _penalty_concept_names("အဓမ္မ အလုပ် ခိုင်းစေမှု"),
            {"forced_labour"},
        )

    def test_combined_question_requires_both_concepts(self):
        question = "ကလေးသူငယ်ကို ရောင်းချပြီး ပြည့်တန်ဆာပြုလုပ်ခိုင်းသည်။"
        self.assertEqual(
            _penalty_concept_names(question),
            {"child_sale", "child_prostitution"},
        )
        self.assertEqual(
            _penalty_concept_overlap(question, "ကလေးသူငယ်အား ရောင်းချခြင်း"),
            0.5,
        )

    def test_other_chapter_27_acts_are_detected(self):
        cases = {
            "ကလေးကို တောင်းရမ်းခိုင်းခဲ့သည်။": "causing_child_begging",
            "ကလေးအား ဘေးအန္တရာယ်ရှိသော အလုပ်ခိုင်းသည်။": "dangerous_work",
            "ကလေးကို လောင်းကစားရန် တိုက်တွန်းသည်။": "gambling",
            "ကလေးကို စိတ်ပိုင်းဆိုင်ရာ အကြမ်းဖက်ခဲ့သည်။": "psychological_violence",
            "ကလေး၏ ကိုယ်ခန္ဓာအစိတ်အပိုင်းအား ရောင်းချခဲ့သည်။": "body_part_sale",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertIn(expected, _penalty_concept_names(question))


if __name__ == "__main__":
    unittest.main()
