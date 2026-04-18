#!/usr/bin/env python3
"""Core gameplay utilities for legality, synergies and deck building."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.query_knowledge import read_jsonl


FORMAT_RULES: dict[str, dict[str, Any]] = {
    "standard": {"deck_min": 60, "max_copies": 4},
    "pioneer": {"deck_min": 60, "max_copies": 4},
    "historic": {"deck_min": 60, "max_copies": 4},
    "modern": {"deck_min": 60, "max_copies": 4},
    "legacy": {"deck_min": 60, "max_copies": 4},
    "vintage": {"deck_min": 60, "max_copies": 4},
    "pauper": {"deck_min": 60, "max_copies": 4},
    "commander": {
        "deck_exact": 100,
        "max_copies": 1,
        "requires_commander": True,
    },
}


def normalize_name(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\d+\s*x?\s*", "", text, flags=re.IGNORECASE)
    text = re.split(r"\s*[\[(]", text, maxsplit=1)[0].strip()
    return " ".join(text.lower().split())


def _words(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z\-']+", value.lower())


def _to_set(values: list[str], min_len: int = 3) -> set[str]:
    return {item for item in values if len(item) >= min_len}


def _is_basic_land(card: dict[str, Any]) -> bool:
    return "basic land" in str(card.get("type_line") or "").lower()


def _is_legendary_creature(card: dict[str, Any]) -> bool:
    type_line = str(card.get("type_line") or "").lower()
    if "legendary" in type_line and "creature" in type_line:
        return True

    oracle = str(card.get("oracle_text") or "").lower()
    return "can be your commander" in oracle


def _legal_status(card: dict[str, Any], fmt: str) -> str:
    legalities = card.get("legalities") or {}
    return str(legalities.get(fmt, "not_legal"))


def _card_tags(card: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    tags.update(_to_set(_words(str(card.get("type_line") or ""))))
    tags.update(_to_set(_words(str(card.get("oracle_text") or ""))))
    keywords = [str(item).lower() for item in (card.get("keywords") or [])]
    tags.update(_to_set(keywords, min_len=2))
    return set(list(tags)[:160])


def _prefer_card(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    # Prefer English printings, then those with more oracle text.
    current_lang = str(current.get("lang") or "")
    candidate_lang = str(candidate.get("lang") or "")
    if current_lang != "en" and candidate_lang == "en":
        return candidate
    if current_lang == "en" and candidate_lang != "en":
        return current

    current_len = len(str(current.get("oracle_text") or ""))
    candidate_len = len(str(candidate.get("oracle_text") or ""))
    return candidate if candidate_len > current_len else current


@lru_cache(maxsize=2)
def load_card_pool(path: str = "data/cards_light_en_it.jsonl") -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Card dataset not found: {source}")

    canonical_cards: dict[str, dict[str, Any]] = {}
    alias_index: dict[str, str] = {}

    for row in read_jsonl(source):
        name = str(row.get("name") or "").strip()
        if not name:
            continue

        key = normalize_name(name)
        card = {
            "id": row.get("id"),
            "name": name,
            "lang": row.get("lang"),
            "mana_cost": row.get("mana_cost"),
            "type_line": row.get("type_line"),
            "oracle_text": row.get("oracle_text"),
            "power": row.get("power"),
            "toughness": row.get("toughness"),
            "colors": row.get("colors") or [],
            "color_identity": row.get("color_identity") or [],
            "cmc": row.get("cmc"),
            "keywords": row.get("keywords") or [],
            "legalities": row.get("legalities") or {},
            "set": row.get("set"),
            "rarity": row.get("rarity"),
        }
        card["tags"] = _card_tags(card)

        if key in canonical_cards:
            canonical_cards[key] = _prefer_card(canonical_cards[key], card)
        else:
            canonical_cards[key] = card

        alias_index[normalize_name(name)] = key

    return {"cards": canonical_cards, "aliases": alias_index}


def resolve_card(name: str, dataset_path: str = "data/cards_light_en_it.jsonl") -> dict[str, Any] | None:
    pool = load_card_pool(dataset_path)
    aliases = pool["aliases"]
    cards = pool["cards"]
    alias = aliases.get(normalize_name(name))
    if not alias:
        return None
    return cards.get(alias)


def validate_deck(
    deck: list[dict[str, Any]],
    fmt: str,
    commander: str | None = None,
    dataset_path: str = "data/cards_light_en_it.jsonl",
) -> dict[str, Any]:
    fmt_norm = normalize_name(fmt)
    if fmt_norm not in FORMAT_RULES:
        return {
            "valid": False,
            "errors": [f"Formato non supportato: {fmt}"],
            "warnings": [],
            "stats": {},
        }

    rules = FORMAT_RULES[fmt_norm]
    errors: list[str] = []
    warnings: list[str] = []

    total_cards = 0
    deck_by_key: dict[str, dict[str, Any]] = {}
    unknown_cards: list[str] = []

    for item in deck:
        name = str(item.get("name") or "").strip()
        count = int(item.get("count") or 0)
        if not name or count <= 0:
            continue

        card = resolve_card(name, dataset_path)
        if card is None:
            unknown_cards.append(name)
            continue

        key = normalize_name(card["name"])
        if key not in deck_by_key:
            deck_by_key[key] = {"card": card, "count": 0}
        deck_by_key[key]["count"] += count
        total_cards += count

    if unknown_cards:
        errors.append(f"Carte non trovate: {', '.join(sorted(set(unknown_cards)))}")

    for key, entry in deck_by_key.items():
        card = entry["card"]
        count = entry["count"]
        status = _legal_status(card, fmt_norm)

        if status not in {"legal", "restricted"}:
            errors.append(f"{card['name']} non legale in {fmt_norm} ({status}).")

        max_copies = int(rules.get("max_copies", 4))
        if _is_basic_land(card):
            max_copies = 9999
        if status == "restricted":
            max_copies = min(max_copies, 1)

        if count > max_copies:
            errors.append(
                f"{card['name']} ha {count} copie ma il massimo in {fmt_norm} e {max_copies}."
            )

    commander_card = None
    if rules.get("requires_commander"):
        if not commander:
            errors.append("Il formato Commander richiede un comandante.")
        else:
            commander_card = resolve_card(commander, dataset_path)
            if commander_card is None:
                errors.append(f"Comandante non trovato: {commander}")
            else:
                status = _legal_status(commander_card, fmt_norm)
                if status not in {"legal", "restricted"}:
                    errors.append(
                        f"Comandante {commander_card['name']} non legale in commander ({status})."
                    )
                if not _is_legendary_creature(commander_card):
                    errors.append(
                        f"{commander_card['name']} non e una creatura leggendaria valida come comandante."
                    )

    deck_size = total_cards
    if commander_card is not None and normalize_name(commander_card["name"]) not in deck_by_key:
        deck_size += 1

    if "deck_exact" in rules and deck_size != int(rules["deck_exact"]):
        errors.append(f"Il mazzo deve avere esattamente {rules['deck_exact']} carte (attuale: {deck_size}).")

    if "deck_min" in rules and deck_size < int(rules["deck_min"]):
        errors.append(f"Il mazzo deve avere almeno {rules['deck_min']} carte (attuale: {deck_size}).")

    if fmt_norm == "commander" and commander_card is not None:
        commander_identity = set(commander_card.get("color_identity") or [])
        for entry in deck_by_key.values():
            card = entry["card"]
            identity = set(card.get("color_identity") or [])
            if not identity.issubset(commander_identity):
                errors.append(
                    f"{card['name']} viola la color identity del comandante ({''.join(sorted(commander_identity)) or 'colorless'})."
                )

    if total_cards == 0:
        warnings.append("Mazzo vuoto o non risolto: nessuna carta valida trovata.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "format": fmt_norm,
            "deck_size": deck_size,
            "resolved_cards": len(deck_by_key),
            "unknown_cards": len(unknown_cards),
        },
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _score_synergy(seed: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    tag_overlap = _jaccard(set(seed.get("tags") or set()), set(candidate.get("tags") or set()))
    if tag_overlap > 0:
        score += 0.55 * tag_overlap
        reasons.append(f"overlap meccaniche {tag_overlap:.2f}")

    seed_ci = set(seed.get("color_identity") or [])
    cand_ci = set(candidate.get("color_identity") or [])
    color_overlap = _jaccard(seed_ci, cand_ci)
    if color_overlap > 0:
        score += 0.25 * color_overlap
        reasons.append(f"coerenza colori {color_overlap:.2f}")

    seed_type = _to_set(_words(str(seed.get("type_line") or "")), min_len=4)
    cand_type = _to_set(_words(str(candidate.get("type_line") or "")), min_len=4)
    type_overlap = _jaccard(seed_type, cand_type)
    if type_overlap > 0:
        score += 0.20 * type_overlap
        reasons.append(f"sinergia tipo {type_overlap:.2f}")

    return score, reasons


def suggest_synergies(
    seed_cards: list[str],
    fmt: str,
    top_k: int = 20,
    dataset_path: str = "data/cards_light_en_it.jsonl",
) -> dict[str, Any]:
    fmt_norm = normalize_name(fmt)
    if fmt_norm not in FORMAT_RULES:
        return {"seed_cards": [], "results": [], "errors": [f"Formato non supportato: {fmt}"]}

    pool = load_card_pool(dataset_path)
    cards = pool["cards"]

    seeds: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in seed_cards:
        card = resolve_card(name, dataset_path)
        if card is None:
            missing.append(name)
            continue
        seeds.append(card)

    if not seeds:
        return {
            "seed_cards": [],
            "results": [],
            "errors": ["Nessuna seed card valida trovata.", *[f"Carta non trovata: {m}" for m in missing]],
        }

    seed_keys = {normalize_name(card["name"]) for card in seeds}
    candidates: list[dict[str, Any]] = []

    for key, candidate in cards.items():
        if key in seed_keys:
            continue

        status = _legal_status(candidate, fmt_norm)
        if status not in {"legal", "restricted"}:
            continue

        total_score = 0.0
        reasons: list[str] = []
        for seed in seeds:
            partial, partial_reasons = _score_synergy(seed, candidate)
            total_score += partial
            reasons.extend(partial_reasons)

        total_score /= max(1, len(seeds))
        if total_score <= 0.02:
            continue

        candidates.append(
            {
                "name": candidate.get("name"),
                "lang": candidate.get("lang"),
                "type_line": candidate.get("type_line"),
                "mana_cost": candidate.get("mana_cost"),
                "score": round(float(total_score), 4),
                "reasons": sorted(set(reasons))[:5],
                "status": status,
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "seed_cards": [card.get("name") for card in seeds],
        "missing_seed_cards": missing,
        "format": fmt_norm,
        "results": candidates[: max(1, top_k)],
    }


def build_deck(
    seed_cards: list[str],
    fmt: str,
    target_size: int | None = None,
    commander: str | None = None,
    dataset_path: str = "data/cards_light_en_it.jsonl",
) -> dict[str, Any]:
    fmt_norm = normalize_name(fmt)
    if fmt_norm not in FORMAT_RULES:
        return {"errors": [f"Formato non supportato: {fmt}"], "deck": []}

    rules = FORMAT_RULES[fmt_norm]
    desired_size = int(target_size or rules.get("deck_exact") or rules.get("deck_min") or 60)

    seeds_resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in seed_cards:
        card = resolve_card(name, dataset_path)
        if card is None:
            missing.append(name)
            continue
        seeds_resolved.append(card)

    if not seeds_resolved:
        return {"errors": ["Nessuna seed card valida trovata."], "deck": []}

    deck: dict[str, dict[str, Any]] = {}
    for card in seeds_resolved:
        key = normalize_name(card["name"])
        deck[key] = {"name": card["name"], "count": 1, "card": card}

    synergy = suggest_synergies([card["name"] for card in seeds_resolved], fmt_norm, top_k=150, dataset_path=dataset_path)
    max_copies = int(rules.get("max_copies", 4))

    for item in synergy.get("results", []):
        card = resolve_card(str(item.get("name") or ""), dataset_path)
        if card is None:
            continue

        status = _legal_status(card, fmt_norm)
        if status not in {"legal", "restricted"}:
            continue

        key = normalize_name(card["name"])
        if key not in deck:
            deck[key] = {"name": card["name"], "count": 0, "card": card}

        cap = max_copies
        if fmt_norm == "commander":
            cap = 1
        if _is_basic_land(card):
            cap = 9999
        if status == "restricted":
            cap = min(cap, 1)

        while deck[key]["count"] < cap and sum(entry["count"] for entry in deck.values()) < desired_size:
            deck[key]["count"] += 1

        if sum(entry["count"] for entry in deck.values()) >= desired_size:
            break

    built_list = [
        {"name": entry["name"], "count": entry["count"]}
        for entry in deck.values()
        if entry["count"] > 0
    ]
    built_list.sort(key=lambda item: (-item["count"], item["name"]))

    validation = validate_deck(built_list, fmt_norm, commander=commander, dataset_path=dataset_path)
    return {
        "format": fmt_norm,
        "target_size": desired_size,
        "seed_cards": [card["name"] for card in seeds_resolved],
        "missing_seed_cards": missing,
        "deck": built_list,
        "validation": validation,
    }
