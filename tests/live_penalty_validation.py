import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

CASES = [
    ("beating", "လူကြီးတစ်ဦးက ကလေးသူငယ်အား ရိုက်နှက်ပြစ်ဒဏ်ပေးခဲ့သည်။"),
    ("begging", "ကလေးသူငယ်ကို တောင်းရမ်းခိုင်းခဲ့သည်။"),
    ("dangerous_work", "ကလေးသူငယ်အား ဘေးအန္တရာယ်ရှိသော အလုပ်ခိုင်းစေခဲ့သည်။"),
    ("forced_labour", "ကလေးသူငယ်အား အဓမ္မအလုပ်ခိုင်းစေခဲ့သည်။"),
    ("pornography", "ကလေးသူငယ်ညစ်ညမ်းပုံများကို ဖြန့်ဝေခဲ့သည်။"),
    ("forced_marriage", "ကလေးသူငယ်ကို အတင်းအကြပ်လက်ထပ်စေခဲ့သည်။"),
    (
        "sale_and_prostitution",
        "ကလေးသူငယ်ကို ရောင်းချခြင်း၊ ပြည့်တန်ဆာပြုလုပ်ခိုင်းစေခြင်းကို မည်သို့စီရင်နိုင်သနည်း။",
    ),
    (
        "civil_support",
        "ဖခင်သည် လင်မယားကွာရှင်းသည့်အခါ ကလေးအား ငွေကြေးထောက်ပံ့မှု မရှိပါ။",
    ),
    ("unsupported_vehicle", "ယာဉ်မောင်းလိုင်စင်မရှိဘဲ ကားမောင်းလျှင် ပြစ်ဒဏ်ကဘာလဲ။"),
]


selected = set(sys.argv[1:])

for name, question in CASES:
    if selected and name not in selected:
        continue
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/ask",
        data=json.dumps({"question": question}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.load(response)
        analysis = payload.get("analysis") or {}
        print(
            json.dumps(
                {
                    "case": name,
                    "answerable": payload.get("answerable"),
                    "mode": payload.get("mode"),
                    "rule_id": analysis.get("rule_id"),
                    "penalty": analysis.get("penalty"),
                    "citations": [
                        item.get("citation")
                        for item in analysis.get("related_sections", [])
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        print(json.dumps({"case": name, "error": str(exc)}), flush=True)
