#!/usr/bin/env python3
"""Preview and sanity-check the cleaned Scryfall JSONL dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a short preview and summary of a JSONL card dataset."
    )
    parser.add_argument(
        "--input",
        default="data/cards_light_en_it.jsonl",
        help="Path to the JSONL dataset to inspect",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="How many sample rows to print",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    args = parse_args()
    source_path = Path(args.input)

    if not source_path.exists():
        raise SystemExit(f"Input file not found: {source_path}")

    rows = 0
    sample_rows: list[Dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    set_counts: Counter[str] = Counter()

    for row in read_jsonl(source_path):
        rows += 1
        if len(sample_rows) < args.sample_size:
            sample_rows.append(row)

        type_line = str(row.get("type_line") or "unknown")
        set_code = str(row.get("set") or "unknown")
        type_counts[type_line] += 1
        set_counts[set_code] += 1

    print(f"File: {source_path}")
    print(f"Rows: {rows:,}")
    print("\nSamples:")
    for index, row in enumerate(sample_rows, start=1):
        print(f"[{index}] {row.get('name')} | {row.get('type_line')} | {row.get('mana_cost')}")

    print("\nTop type lines:")
    for value, count in type_counts.most_common(10):
        print(f"{count:>8,}  {value}")

    print("\nTop sets:")
    for value, count in set_counts.most_common(10):
        print(f"{count:>8,}  {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())