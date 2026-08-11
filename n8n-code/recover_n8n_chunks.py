"""Recover chunk items from an n8n flatted execution-data CSV export."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "workflows" / "legal-rag-execution-52.csv"
OUTPUT = ROOT / "workflows" / "legal_chunks_for_colab.json"
EXPECTED_COUNT = 557


def decode_flatted(payload: str):
    values = json.loads(payload)
    memo: dict[int, object] = {}

    def resolve_index(index: int):
        if index in memo:
            return memo[index]

        raw = values[index]
        if isinstance(raw, dict):
            decoded: dict[str, object] = {}
            memo[index] = decoded
            decoded.update({key: resolve_value(value) for key, value in raw.items()})
            return decoded

        if isinstance(raw, list):
            decoded_list: list[object] = []
            memo[index] = decoded_list
            decoded_list.extend(resolve_value(value) for value in raw)
            return decoded_list

        memo[index] = raw
        return raw

    def resolve_value(value):
        if isinstance(value, str) and value.isdigit() and int(value) < len(values):
            return resolve_index(int(value))
        if isinstance(value, dict):
            return {key: resolve_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve_value(item) for item in value]
        return value

    return resolve_index(0)


def main() -> None:
    csv.field_size_limit(2**31 - 1)
    with INPUT.open("r", encoding="utf-8", newline="") as handle:
        payload = next(csv.reader(handle))[0]

    execution = decode_flatted(payload)
    items = execution["resultData"]["runData"]["Code in JavaScript"][0]["data"]["main"][0]
    chunks = [item["json"] for item in items]

    if len(chunks) != EXPECTED_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_COUNT} chunks, recovered {len(chunks)}")

    indexes = [chunk["chunk_index"] for chunk in chunks]
    if sorted(indexes) != list(range(EXPECTED_COUNT)):
        raise RuntimeError("Chunk indexes are not exactly 0 through 556")

    OUTPUT.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(chunks)} chunks to {OUTPUT}")


if __name__ == "__main__":
    main()
