"""Validate newly indexed laws against human-written question cases.

Usage:
    python .\tests\validate_new_law.py --cases .\tests\new_law_cases.json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def normalize(value):
    return " ".join(str(value or "").split()).casefold()


def matches(actual, expected):
    if not expected:
        return True
    actual_text = normalize(actual)
    choices = expected if isinstance(expected, list) else [expected]
    return any(normalize(choice) in actual_text for choice in choices)


def ask(endpoint, question, timeout):
    request = urllib.request.Request(
        endpoint,
        data=json.dumps({"question": question}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description="Test a newly indexed law")
    parser.add_argument("--cases", required=True, help="UTF-8 JSON test-case file")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/ask")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    case_path = Path(args.cases)
    cases = json.loads(case_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise SystemExit("Cases file must contain a non-empty JSON array.")

    passed = 0
    print(f"Testing {len(cases)} cases against {args.endpoint}\n")

    for index, case in enumerate(cases, 1):
        question = str(case.get("question") or "").strip()
        if not question:
            print(f"[{index}] FAIL — question is empty")
            continue

        try:
            payload = ask(args.endpoint, question, args.timeout)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[{index}] ERROR — {exc}")
            continue

        analysis = payload.get("analysis") or {}
        sources = payload.get("sources") or []
        first_source = sources[0] if sources else {}
        actual_law = (
            analysis.get("law_name")
            or analysis.get("main_law")
            or first_source.get("law_name")
        )
        actual_section = (
            analysis.get("section")
            or analysis.get("main_section")
            or first_source.get("section")
        )
        actual_answerable = bool(payload.get("answerable"))

        expected_answerable = case.get("expected_answerable", True)
        checks = {
            "answerable": actual_answerable == bool(expected_answerable),
            "law": matches(actual_law, case.get("expected_law")),
            "section": matches(actual_section, case.get("expected_section")),
        }
        ok = all(checks.values())
        passed += int(ok)

        print(f"[{index}] {'PASS' if ok else 'FAIL'} — {question}")
        print(f"    law: {actual_law or '—'}")
        print(f"    section: {actual_section or '—'}")
        print(f"    answerable: {actual_answerable}")
        if not ok:
            failed = ", ".join(name for name, result in checks.items() if not result)
            print(f"    failed checks: {failed}")

    print(f"\nResult: {passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
