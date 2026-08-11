import unittest

from ocr_service import (
    _is_telecom_66d_query,
    _preferred_law_name_fragment,
    normalize_query_for_search,
)


class QueryIntentTests(unittest.TestCase):
    def test_human_spoken_reputation_harm_on_social_media_routes_to_telecom(self):
        question = "လူမှုကွန်ရက်တွင် အမျိုးသမီးတစ်ဦးက မိမိအား ဂုဏ်ကိုထိပါးပြောဆိုခဲ့သည်။"

        self.assertTrue(_is_telecom_66d_query(question))
        self.assertEqual(_preferred_law_name_fragment(question), "ဆက်သွယ်ရေး")

    def test_formal_reputation_harm_on_social_media_routes_to_telecom(self):
        question = "လူမှုကွန်ရက်ပေါ်တွင် မမှန်သတင်းဖြန့်ဝေ၍ ဂုဏ်သိက္ခာထိခိုက်စေခဲ့သည်။"

        self.assertTrue(_is_telecom_66d_query(question))
        self.assertEqual(_preferred_law_name_fragment(question), "ဆက်သွယ်ရေး")

    def test_reputation_harm_without_telecom_medium_does_not_force_telecom(self):
        question = "လူတစ်ဦးက မိမိအား ဂုဏ်ကိုထိပါးပြောဆိုခဲ့သည်။"

        self.assertFalse(_is_telecom_66d_query(question))

    def test_conversational_neighbor_insult_routes_to_penal_code(self):
        question = "ဘေးအိမ်ကမိန်းမက ကျွန်မကို ဆဲဆိုနေတယ်။ အဲဒါ ဘယ်ကိုတိုင်ရမလဲ။"

        self.assertEqual(_preferred_law_name_fragment(question), "ရာဇသတ်ကြီး")

    def test_long_conversational_penal_cases_route_to_penal_code(self):
        cases = (
            "ကျွန်မအလုပ်သွားတဲ့လမ်းမှာ လူတစ်ယောက်က ညစ်ညမ်းတဲ့စကားတွေပြောပြီး မသင့်တော်တဲ့ကိုယ်အမူအရာနဲ့ နောက်ကလိုက်နေပါတယ်။",
            "ကျွန်တော်မလုပ်ခဲ့တဲ့ကိစ္စတစ်ခုကို ကျွန်တော်လုပ်ခဲ့သလို လူတစ်ယောက်က လူအများရှေ့မှာ ပြောနေပါတယ်။",
            "အလုပ်လုပ်တဲ့လူတစ်ယောက်က အိမ်ရှင်မရှိတဲ့အချိန် အိမ်ထဲဝင်ပြီး ငွေသားတွေ ယူသွားပါတယ်။",
            "Facebook က ဖုန်းရောင်းမယ်ဆိုပြီး ငွေလွှဲခိုင်းကာ ပစ္စည်းမပို့ဘဲ block လုပ်သွားပါတယ်။",
        )

        for question in cases:
            with self.subTest(question=question):
                self.assertEqual(_preferred_law_name_fragment(question), "ရာဇသတ်ကြီး")

    def test_conversational_queries_are_expanded_and_routed(self):
        cases = (
            ("သူများရဲ့ Facebook account ကို ဖောက်ဝင်ခဲ့တယ်။", "ဆိုက်ဘာ"),
            ("ပတ်စ်ပို့အတုနဲ့ နိုင်ငံခြားထွက်ဖို့လုပ်တယ်။", "နိုင်ငံကူးလက်မှတ်"),
            ("ရာမဆေးပြားတွေကို ရောင်းစားနေတယ်။", "မူးယစ်"),
            ("တောထဲက သစ်ပင်တွေကို ခိုးခုတ်သယ်သွားတယ်။", "သစ်တော"),
            ("ကလေးကို ခိုင်းစားပြီး ကျောင်းမထားဘူး။", "ကလေးသူငယ်"),
            ("သူများအိမ်ထဲ ခိုးဝင်ပြီး ပစ္စည်းယူပြေးတယ်။", "ရာဇသတ်ကြီး"),
            ("လူ့အခွင့်အရေး ချိုးဖောက်ခံရလို့ တိုင်ချင်တယ်။", "လူ့အခ"),
            ("သူများရဲ့ တီထွင်မှုကို မူပိုင်ခွင့်ယူထားတယ်။", "တီထွင်မှု"),
        )

        for question, expected_law in cases:
            with self.subTest(question=question):
                normalized = normalize_query_for_search(question)
                self.assertNotEqual(normalized, "")
                self.assertEqual(_preferred_law_name_fragment(question), expected_law)

    def test_latest_long_conversational_cases_route_to_correct_law(self):
        cases = (
            (
                "Facebook ပေါ်မှာ လူတစ်ယောက်က ကျွန်တော့်ပုံကိုတင်ပြီး မဟုတ်မမှန်တဲ့အကြောင်းတွေ ရေးထားပါတယ်။ တခြားလူတွေကပါ share လုပ်နေပါတယ်။",
                "ဆက်သွယ်ရေး",
            ),
            (
                "မိဘတွေက ကလေးကို စောင့်ရှောက်မယ့်သူမရှိဘဲ အိမ်မှာထားပြီး ရက်အတော်ကြာ ပျောက်သွားပါတယ်။",
                "ကလေးသူငယ်",
            ),
            (
                "ရွာနားက ကြိုးဝိုင်းတောထဲကို လူတစ်စုဝင်ပြီး ကျွန်းပင်တွေ ခိုးခုတ်ကာ သစ်လုံးတွေကို ကားနဲ့ သယ်သွားပါတယ်။",
                "သစ်တော",
            ),
            (
                "တခြားသူရဲ့ passport ကို ပိုင်ရှင်က အသုံးပြုခွင့်မပေးဘဲ ကိုင်ဆောင်အသုံးပြုထားပါတယ်။",
                "နိုင်ငံကူးလက်မှတ်",
            ),
        )

        for question, expected_law in cases:
            with self.subTest(question=question):
                self.assertEqual(_preferred_law_name_fragment(question), expected_law)


if __name__ == "__main__":
    unittest.main()
