import json
import os
import re
import urllib.request


def _character_ngram_recall(query, content, size=6):
    query = re.sub(r"\s+", "", query)
    content = re.sub(r"\s+", "", content)
    query_grams = {query[index:index + size] for index in range(len(query) - size + 1)}
    content_grams = {content[index:index + size] for index in range(len(content) - size + 1)}
    return len(query_grams & content_grams) / max(len(query_grams), 1)


QUESTIONS = [
    "ဖခင်သည် လင်မယားကွာရှင်းသည့်အခါ ကလေးအားငွေကြေးထောက်ပံ့မှု မရှိပါ။",
    "ကလေးစရိတ်မပေးသည့်ဖခင်ကို မိခင်က ဘယ်မှာလျှောက်ထားရမလဲ။",
    "တရားရုံးက ကလေးစရိတ်ကို လစဉ်ဘယ်လောက်သတ်မှတ်နိုင်သလဲ။",
    "ကလေးတစ်ဦး၏ ပညာသင်ယူခွင့်ကို တားမြစ်ထားသည်။",
    "မသမာသူလူတစ်စုက ကလေးသူငယ်အား လိင်ပိုင်းဆိုင်ရာ ခေါင်းပုံဖြတ်ခြင်း ပြုလုပ်ခဲ့သည်။",
    "ကလေးသူငယ်ကို ရောင်းချခြင်း၊ ပြည့်တန်ဆာပြုလုပ်ခိုင်းစေခြင်းကို မည်သို့စီရင်နိုင်သနည်း။",
    "လင်မယားကွာရှင်းပြီးနောက် ကလေးကို မည်သူက အုပ်ထိန်းရမလဲ။",
    "အသက် ၈ နှစ်အရွယ် ကလေးတစ်ဦးက အိမ်နီးချင်း၏ ပစ္စည်းကို ဖျက်ဆီးခဲ့သည်။",
    "ယာဉ်မောင်းလိုင်စင်မရှိဘဲ ကားမောင်းလျှင် ဘာဖြစ်မလဲ။",
]


for question in QUESTIONS:
    print("\nQ", question)
    if not os.getenv("LEXICAL_ONLY"):
        request = urllib.request.Request(
            "http://127.0.0.1:8000/api/ask",
            data=json.dumps({"question": question}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
        print(
            json.dumps(
                {
                    "answerable": payload.get("answerable"),
                    "mode": payload.get("mode"),
                    "answer": payload.get("answer"),
                    "sections": [
                        [source.get("section"), source.get("score")]
                        for source in payload.get("sources", [])
                    ],
                    "retrieval": payload.get("retrieval"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    chunks = json.load(open("workflows/legal_chunks_for_colab.json", encoding="utf-8"))
    lexical = sorted(
        (
            (_character_ngram_recall(question, item.get("content", "")), item.get("section"))
            for item in chunks
        ),
        key=lambda item: item[0],
        reverse=True,
    )[:5]
    print("lexical", lexical)
