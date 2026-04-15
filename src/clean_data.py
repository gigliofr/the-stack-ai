#!/usr/bin/env python3
"""Create a lightweight JSONL dataset from Scryfall Default Cards."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def get_ijson() -> Any:
    try:
        return importlib.import_module("ijson")
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency 'ijson'. Install it with: pip install ijson"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Scryfall default-cards JSON and write a slim JSONL file."
    )
    parser.add_argument(
        "--input",
        default="data/default-cards.json",
        help="Path to Scryfall Default Cards JSON file",
    )
    parser.add_argument(
        "--output",
        default="data/cards_light.jsonl",
        help="Path for generated JSONL file",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="Keep only cards with this language code (default: en)",
    )
    return parser.parse_args()


def compact_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.split())


def merge_faces(card: Dict[str, Any], field: str) -> Optional[str]:
    faces = card.get("card_faces")
    if not faces:
        return None

    chunks = []
    for face in faces:
        value = face.get(field)
        if value:
            chunks.append(str(value).strip())

    if not chunks:
        return None
    return " // ".join(chunks)


def extract_card(card: Dict[str, Any], lang: str) -> Optional[Dict[str, Any]]:
    if card.get("lang") != lang:
        return None
    if card.get("layout") == "token":
        return None

    oracle_text = card.get("oracle_text") or merge_faces(card, "oracle_text")
    mana_cost = card.get("mana_cost") or merge_faces(card, "mana_cost")
    power = card.get("power") or merge_faces(card, "power")
    toughness = card.get("toughness") or merge_faces(card, "toughness")

    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "mana_cost": mana_cost,
        "type_line": card.get("type_line") or merge_faces(card, "type_line"),
        "oracle_text": compact_text(oracle_text),
        "power": power,
        "toughness": toughness,
        "loyalty": card.get("loyalty"),
        "colors": card.get("colors") or [],
        "color_identity": card.get("color_identity") or [],
        "cmc": card.get("cmc"),
        "keywords": card.get("keywords") or [],
        "legalities": card.get("legalities") or {},
        "set": card.get("set"),
        "rarity": card.get("rarity"),
    }


def iter_cards(path: Path) -> Iterable[Dict[str, Any]]:
    ijson = get_ijson()
    with path.open("rb") as source:
        for card in ijson.items(source, "item"):
            yield card


def main() -> int:
    args = parse_args()
    source_path = Path(args.input)
    output_path = Path(args.output)

    if not source_path.exists():
        raise SystemExit(f"Input file not found: {source_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    scanned = 0

    with output_path.open("w", encoding="utf-8") as out_file:
        for card in iter_cards(source_path):
            scanned += 1
            row = extract_card(card, args.lang)
            if row is None:
                continue
            out_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            kept += 1

    print(f"Scanned: {scanned:,}")
    print(f"Written: {kept:,}")
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
