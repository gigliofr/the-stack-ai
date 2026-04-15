#!/usr/bin/env python3
"""Convert cleaned card rows into retrieval-ready text documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build plain-text documents from the cleaned card JSONL file."
    )
    parser.add_argument(
        "--input",
        default="data/cards_light_en_it.jsonl",
        help="Path to the cleaned JSONL dataset",
    )
    parser.add_argument(
        "--output",
        default="data/cards_documents.jsonl",
        help="Path for the generated document JSONL",
    )
    return parser.parse_args()


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def compact_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.split())


def build_document(card: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        f"Name: {card.get('name')}",
        f"Language: {card.get('lang')}",
    ]

    if card.get("mana_cost"):
        lines.append(f"Mana Cost: {card.get('mana_cost')}")
    if card.get("type_line"):
        lines.append(f"Type Line: {card.get('type_line')}")
    if card.get("oracle_text"):
        lines.append(f"Oracle Text: {card.get('oracle_text')}")
    if card.get("power") is not None:
        lines.append(f"Power: {card.get('power')}")
    if card.get("toughness") is not None:
        lines.append(f"Toughness: {card.get('toughness')}")
    if card.get("loyalty") is not None:
        lines.append(f"Loyalty: {card.get('loyalty')}")
    if card.get("set"):
        lines.append(f"Set: {card.get('set')}")
    if card.get("rarity"):
        lines.append(f"Rarity: {card.get('rarity')}")

    text = compact_text("\n".join(lines))

    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "lang": card.get("lang"),
        "set": card.get("set"),
        "type_line": card.get("type_line"),
        "text": text,
    }


def main() -> int:
    args = parse_args()
    source_path = Path(args.input)
    output_path = Path(args.output)

    if not source_path.exists():
        raise SystemExit(f"Input file not found: {source_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with output_path.open("w", encoding="utf-8") as destination:
        for card in read_jsonl(source_path):
            document = build_document(card)
            destination.write(json.dumps(document, ensure_ascii=False) + "\n")
            written += 1

    print(f"Input: {source_path}")
    print(f"Written: {written:,}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())