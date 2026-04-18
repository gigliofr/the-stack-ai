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
    "alchemy": {"deck_min": 60, "max_copies": 4},
    "pioneer": {"deck_min": 60, "max_copies": 4},
    "explorer": {"deck_min": 60, "max_copies": 4},
    "historic": {"deck_min": 60, "max_copies": 4},
    "timeless": {"deck_min": 60, "max_copies": 4},
    "modern": {"deck_min": 60, "max_copies": 4},
    "legacy": {"deck_min": 60, "max_copies": 4},
    "vintage": {"deck_min": 60, "max_copies": 4},
    "pauper": {"deck_min": 60, "max_copies": 4},
    "premodern": {"deck_min": 60, "max_copies": 4},
    "oldschool": {"deck_min": 60, "max_copies": 4},
    "brawl": {
        "deck_exact": 60,
        "max_copies": 1,
        "requires_commander": True,
    },
    "standardbrawl": {
        "deck_exact": 60,
        "max_copies": 1,
        "requires_commander": True,
    },
    "commander": {
        "deck_exact": 100,
        "max_copies": 1,
        "requires_commander": True,
        "allow_partner_pairs": True,
    },
    "duel": {
        "deck_exact": 100,
        "max_copies": 1,
        "requires_commander": True,
        "allow_partner_pairs": True,
    },
    "paupercommander": {
        "deck_exact": 100,
        "max_copies": 1,
        "requires_commander": True,
        "allow_partner_pairs": True,
    },
}

PARTNER_MARKERS = (
    "partner",
    "partner with",
    "friends forever",
    "doctor's companion",
)

FAST_MANA_CARDS = {
    "sol ring",
    "mana crypt",
    "mana vault",
    "jeweled lotus",
    "chrome mox",
    "mox diamond",
    "mox amber",
    "lotus petal",
    "arcane signet",
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
    type_line = str(card.get("type_line") or "").lower()
    return (
        "basic land" in type_line
        or "terra base" in type_line
        or ("basic" in type_line and "land" in type_line)
    )


def _is_legendary_creature(card: dict[str, Any]) -> bool:
    type_line = str(card.get("type_line") or "").lower()
    if "legendary" in type_line and "creature" in type_line:
        return True

    oracle = str(card.get("oracle_text") or "").lower()
    return "can be your commander" in oracle


def _is_planeswalker_commander(card: dict[str, Any]) -> bool:
    type_line = str(card.get("type_line") or "").lower()
    oracle = str(card.get("oracle_text") or "").lower()
    return "planeswalker" in type_line and "can be your commander" in oracle


def _has_partner_marker(card: dict[str, Any]) -> bool:
    oracle = str(card.get("oracle_text") or "").lower()
    return any(marker in oracle for marker in PARTNER_MARKERS)


def _can_choose_background(card: dict[str, Any]) -> bool:
    oracle = str(card.get("oracle_text") or "").lower()
    return "choose a background" in oracle


def _is_background(card: dict[str, Any]) -> bool:
    type_line = str(card.get("type_line") or "").lower()
    return "background" in type_line and "enchantment" in type_line


def _is_commander_candidate(card: dict[str, Any]) -> bool:
    return _is_legendary_creature(card) or _is_planeswalker_commander(card)


def _parse_commander_list(commander: str | None) -> list[str]:
    if not commander:
        return []

    def _clean(raw: str) -> str:
        text = str(raw or "").strip()
        text = re.sub(r"^\d+\s*x?\s*", "", text, flags=re.IGNORECASE)
        text = re.split(r"\s*[\[(]", text, maxsplit=1)[0].strip()
        return " ".join(text.split())

    names: list[str] = []
    for part in re.split(r"[;\n]+", commander):
        # Keep commas because many card names include commas (e.g., "Terra, Herald of Hope").
        split_candidates = re.split(r"\s*(?:/|\+|\|)\s*", part)
        for candidate in split_candidates:
            cleaned = _clean(candidate)
            if cleaned:
                names.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)

    return deduped


def _classify_commander_role(card: dict[str, Any]) -> dict[str, bool]:
    type_line = str(card.get("type_line") or "").lower()
    oracle = str(card.get("oracle_text") or "").lower()
    name_key = normalize_name(str(card.get("name") or ""))

    is_land = "land" in type_line
    is_ramp = (
        name_key in FAST_MANA_CARDS
        or "add {" in oracle
        or "search your library for" in oracle and "land" in oracle
        or "treasure token" in oracle
    )
    is_draw = "draw a card" in oracle or "draw two cards" in oracle or "draw three cards" in oracle
    is_removal = (
        "destroy target" in oracle
        or "exile target" in oracle
        or "counter target" in oracle
        or "return target" in oracle and "to its owner's hand" in oracle
    )
    is_wipe = (
        "destroy all" in oracle
        or "exile all" in oracle
        or "each creature" in oracle and "sacrifice" in oracle
    )

    return {
        "land": is_land,
        "ramp": is_ramp,
        "draw": is_draw,
        "removal": is_removal,
        "wipe": is_wipe,
    }


def _estimate_power_level(deck_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fast_mana = 0
    tutors = 0
    combo_markers = 0
    avg_cmc_sum = 0.0
    avg_cmc_count = 0

    for entry in deck_by_key.values():
        card = entry["card"]
        count = int(entry["count"])
        oracle = str(card.get("oracle_text") or "").lower()
        name_key = normalize_name(str(card.get("name") or ""))

        if name_key in FAST_MANA_CARDS:
            fast_mana += count
        if "search your library for" in oracle:
            tutors += count
        if "you win the game" in oracle or "take an extra turn" in oracle:
            combo_markers += count

        cmc = card.get("cmc")
        if isinstance(cmc, (int, float)):
            avg_cmc_sum += float(cmc) * count
            avg_cmc_count += count

    avg_cmc = (avg_cmc_sum / avg_cmc_count) if avg_cmc_count else 0.0
    score = (fast_mana * 0.8) + (tutors * 0.6) + (combo_markers * 0.8)
    if avg_cmc and avg_cmc <= 2.3:
        score += 1.5
    elif avg_cmc and avg_cmc <= 2.8:
        score += 0.8

    if score >= 8:
        tier = "cEDH (Competitive EDH)"
    elif score >= 4:
        tier = "High Power/Optimized"
    else:
        tier = "Precon/Casual"

    return {
        "tier": tier,
        "score": round(score, 2),
        "signals": {
            "fast_mana": fast_mana,
            "tutors": tutors,
            "combo_markers": combo_markers,
            "avg_cmc": round(avg_cmc, 2),
        },
    }


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

        if status == "banned":
            errors.append(f"{card['name']} presente nella banlist di {fmt_norm}.")
        elif status not in {"legal", "restricted"}:
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

    commander_cards: list[dict[str, Any]] = []
    if rules.get("requires_commander"):
        commander_names = _parse_commander_list(commander)
        if not commander_names:
            errors.append("Il formato Commander richiede un comandante.")
        else:
            if len(commander_names) > 2:
                errors.append("Puoi specificare al massimo due comandanti.")
            for name in commander_names[:2]:
                resolved = resolve_card(name, dataset_path)
                if resolved is None:
                    errors.append(f"Comandante non trovato: {name}")
                    continue
                commander_cards.append(resolved)

            for cmd in commander_cards:
                status = _legal_status(cmd, fmt_norm)
                if status == "banned":
                    errors.append(f"Comandante {cmd['name']} presente nella banlist di {fmt_norm}.")
                elif status not in {"legal", "restricted"}:
                    errors.append(f"Comandante {cmd['name']} non legale in {fmt_norm} ({status}).")

                if not _is_commander_candidate(cmd) and not _is_background(cmd):
                    errors.append(
                        f"{cmd['name']} non e un comandante valido (creatura leggendaria o planeswalker con testo dedicato)."
                    )

            if len(commander_cards) == 2:
                first, second = commander_cards
                partner_ok = _has_partner_marker(first) and _has_partner_marker(second)
                background_ok = (
                    (_can_choose_background(first) and _is_background(second))
                    or (_can_choose_background(second) and _is_background(first))
                )
                if not (rules.get("allow_partner_pairs") and (partner_ok or background_ok)):
                    errors.append(
                        "Due comandanti sono consentiti solo con Partner/Friends Forever/Doctor's Companion o con Choose a Background + Background."
                    )

    deck_size = total_cards
    for cmd in commander_cards:
        if normalize_name(cmd["name"]) not in deck_by_key:
            deck_size += 1

    if "deck_exact" in rules and deck_size != int(rules["deck_exact"]):
        errors.append(f"Il mazzo deve avere esattamente {rules['deck_exact']} carte (attuale: {deck_size}).")

    if "deck_min" in rules and deck_size < int(rules["deck_min"]):
        errors.append(f"Il mazzo deve avere almeno {rules['deck_min']} carte (attuale: {deck_size}).")

    if rules.get("requires_commander") and commander_cards:
        commander_identity: set[str] = set()
        for cmd in commander_cards:
            commander_identity |= set(cmd.get("color_identity") or [])
        for entry in deck_by_key.values():
            card = entry["card"]
            identity = set(card.get("color_identity") or [])
            if not identity.issubset(commander_identity):
                errors.append(
                    f"{card['name']} viola la color identity del comandante ({''.join(sorted(commander_identity)) or 'colorless'})."
                )

    composition: dict[str, int] = {"lands": 0, "ramp": 0, "draw": 0, "removal": 0, "board_wipes": 0}
    if fmt_norm in {"commander", "duel", "paupercommander", "brawl", "standardbrawl"}:
        for entry in deck_by_key.values():
            card = entry["card"]
            count = int(entry["count"])
            role = _classify_commander_role(card)
            composition["lands"] += count if role["land"] else 0
            composition["ramp"] += count if role["ramp"] else 0
            composition["draw"] += count if role["draw"] else 0
            composition["removal"] += count if role["removal"] else 0
            composition["board_wipes"] += count if role["wipe"] else 0

        if fmt_norm in {"commander", "duel", "paupercommander"}:
            if composition["lands"] < 35 or composition["lands"] > 40:
                warnings.append(
                    f"Base terre consigliata 35-40 (attuale: {composition['lands']})."
                )
            if composition["ramp"] < 8:
                warnings.append(f"Ramp basso: consigliato >= 8 (attuale: {composition['ramp']}).")
            if composition["draw"] < 8:
                warnings.append(f"Draw power basso: consigliato >= 8 (attuale: {composition['draw']}).")
            if composition["removal"] < 8:
                warnings.append(f"Removal basso: consigliato >= 8 (attuale: {composition['removal']}).")
            if composition["board_wipes"] < 2:
                warnings.append(
                    f"Board wipes bassi: consigliato >= 2 (attuale: {composition['board_wipes']})."
                )

    if total_cards == 0:
        warnings.append("Mazzo vuoto o non risolto: nessuna carta valida trovata.")

    power_level = _estimate_power_level(deck_by_key)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "format": fmt_norm,
            "deck_size": deck_size,
            "resolved_cards": len(deck_by_key),
            "unknown_cards": len(unknown_cards),
            "commanders": [card.get("name") for card in commander_cards],
            "composition": composition,
            "power_level": power_level,
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
