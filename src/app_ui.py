#!/usr/bin/env python3
"""Streamlit UI for The Stack local retrieval API."""

from __future__ import annotations

import json
import csv
import os
import io
import re
from functools import lru_cache
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

import streamlit as st

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None


API_DEFAULT = os.environ.get("THE_STACK_API_URL", "http://127.0.0.1:18000")
API_FALLBACK_PORTS = (18000, 8000)
MODEL_DEFAULT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FAVORITES_PATH = Path("data/query_favorites.json")
AGENT_FORMAT_OPTIONS = [
    "alchemy",
    "brawl",
    "commander",
    "duel",
    "explorer",
    "historic",
    "legacy",
    "modern",
    "oldschool",
    "pauper",
    "paupercommander",
    "pioneer",
    "premodern",
    "standard",
    "standardbrawl",
    "timeless",
    "vintage",
]


st.set_page_config(page_title="The Stack", page_icon="🃏", layout="wide")

st.markdown(
    """
    <style>
        .stApp {
            background: radial-gradient(circle at top, rgba(18, 24, 38, 0.96), rgba(8, 10, 18, 1));
            color: #f4f1ea;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .stack-panel {
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            background: rgba(255, 255, 255, 0.03);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.22);
            margin-bottom: 0.8rem;
        }
        .stack-kicker {
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: rgba(244, 241, 234, 0.68);
            font-size: 0.74rem;
            margin-bottom: 0.35rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_candidates(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    candidates = [normalized]
    parsed = urlparse(normalized)
    hostname = parsed.hostname

    if hostname in {None, "127.0.0.1", "localhost"}:
        scheme = parsed.scheme or "http"
        host_variants = ["127.0.0.1", "localhost"]
        if hostname and hostname not in host_variants:
            host_variants.insert(0, hostname)
        for port in API_FALLBACK_PORTS:
            for host in host_variants:
                candidate = f"{scheme}://{host}:{port}"
                if candidate not in candidates:
                    candidates.append(candidate)

    return candidates


def post_api(base_url: str, path: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None

    for candidate in api_candidates(base_url):
        endpoint = f"{candidate.rstrip('/')}/{path.lstrip('/')}"
        http_request = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=120) as response:
                if candidate != base_url:
                    st.session_state["base_url"] = candidate
                return json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error

    raise RuntimeError("Impossibile raggiungere l'API")


def post_query(base_url: str, payload: dict[str, object]) -> dict[str, object]:
    return post_api(base_url, "/query", payload)


def translation_available() -> bool:
    return GoogleTranslator is not None


@lru_cache(maxsize=2048)
def translate_short_to_italian(text: str) -> str:
    if not text or not translation_available():
        return text
    try:
        return GoogleTranslator(source="auto", target="it").translate(text)
    except Exception:
        return text


def translate_to_italian(text: str) -> str:
    if not text:
        return text
    if len(text) <= 3500:
        return translate_short_to_italian(text)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        piece_len = len(line) + 1
        if current and current_len + piece_len > 3500:
            chunks.append("\n".join(current))
            current = [line]
            current_len = piece_len
            continue
        current.append(line)
        current_len += piece_len
    if current:
        chunks.append("\n".join(current))

    translated = [translate_short_to_italian(chunk) for chunk in chunks]
    return "\n".join(translated)


def get_history() -> list[dict[str, object]]:
    return st.session_state.setdefault("query_history", [])


def add_history_entry(entry: dict[str, object]) -> None:
    history = get_history()
    history.insert(0, entry)
    del history[10:]


def load_favorites() -> list[dict[str, object]]:
    if not FAVORITES_PATH.exists():
        return []
    try:
        data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    favorites: list[dict[str, object]] = []
    for item in data:
        if isinstance(item, dict) and item.get("query"):
            favorites.append(item)
    return favorites


def save_favorites(favorites: list[dict[str, object]]) -> None:
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_PATH.write_text(
        json.dumps(favorites, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_favorites() -> list[dict[str, object]]:
    return st.session_state.setdefault("query_favorites", load_favorites())


def persist_favorites() -> None:
    save_favorites(get_favorites())


def add_favorite(entry: dict[str, object]) -> None:
    favorites = get_favorites()
    if any(item.get("query") == entry.get("query") for item in favorites):
        return
    favorites.insert(0, entry)
    del favorites[20:]
    persist_favorites()


def make_payload(config: dict[str, object]) -> dict[str, object]:
    return {
        "query": config.get("query", ""),
        "top_k": int(config.get("top_k", 5)),
        "model": config.get("model", MODEL_DEFAULT),
        "only_cards": bool(config.get("only_cards", False)),
        "only_rules": bool(config.get("only_rules", False)),
        "show_source_text": bool(config.get("show_source_text", True)),
    }


def clean_archidekt_card_name(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\d+\s*x?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.split(r"\s*[\[(]", cleaned, maxsplit=1)[0].strip()
    return " ".join(cleaned.split())


def looks_like_decklist(text: str) -> bool:
    for line in str(text or "").splitlines():
        if re.match(r"^\s*\d+\s*x?\s+", line):
            return True
    return False


def render_result_item(
    result: dict[str, object],
    show_source_text: bool,
    index: int,
    translate_output: bool,
) -> None:
    with st.container(border=True):
        st.markdown(
            f"### {index}. {result.get('source', 'sconosciuto')} | punteggio {float(result.get('score', 0.0)):.4f}"
        )
        if result.get("source") == "card":
            st.markdown(f"**{result.get('name')}**")
            summary = str(result.get("summary") or "")
            st.caption(translate_to_italian(summary) if translate_output else summary)
            return

        if result.get("source") == "set":
            st.markdown(f"**{result.get('name')}**")
            summary = str(result.get("summary") or "")
            st.caption(translate_to_italian(summary) if translate_output else summary)
            return

        st.write(f"{result.get('source_file')} | sezione {result.get('section')}")
        if result.get("snippet"):
            snippet = str(result.get("snippet"))
            st.code(translate_to_italian(snippet) if translate_output else snippet, language="text")
        if show_source_text and result.get("text"):
            full_text = str(result.get("text"))
            st.text_area(
                "Testo completo",
                value=translate_to_italian(full_text) if translate_output else full_text,
                height=180,
                key=f"rules-{index}-{result.get('section')}",
            )


def export_json_bytes(data: dict[str, object]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def export_csv_text(data: dict[str, object]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["source", "score", "name", "lang", "type_line", "set", "source_file", "section", "snippet"],
    )
    writer.writeheader()
    for result in data.get("results", []):
        writer.writerow(
            {
                "source": result.get("source"),
                "score": result.get("score"),
                "name": result.get("name"),
                "lang": result.get("lang"),
                "type_line": result.get("type_line"),
                "set": result.get("set"),
                "source_file": result.get("source_file"),
                "section": result.get("section"),
                "snippet": result.get("snippet") or result.get("summary"),
            }
        )
    return buffer.getvalue()


def result_key(result: dict[str, object]) -> str:
    source = str(result.get("source") or "")
    if source == "card":
        return f"card:{result.get('id') or result.get('name')}"
    if source == "set":
        return f"set:{result.get('name')}"
    return f"rules:{result.get('source_file')}:{result.get('section')}"


def result_label(result: dict[str, object]) -> str:
    if result.get("source") == "card":
        return str(result.get("summary") or result.get("name") or "unknown card")
    if result.get("source") == "set":
        return str(result.get("summary") or result.get("name") or "unknown set")
    return (
        f"{result.get('source_file')}#section-{result.get('section')} | "
        f"{result.get('snippet') or ''}"
    )


def compare_result_sets(
    left_results: list[dict[str, object]], right_results: list[dict[str, object]]
) -> tuple[list[tuple[dict[str, object], dict[str, object]]], list[dict[str, object]], list[dict[str, object]]]:
    right_index = {result_key(item): item for item in right_results}
    overlap: list[tuple[dict[str, object], dict[str, object]]] = []
    left_only: list[dict[str, object]] = []

    for left_item in left_results:
        key = result_key(left_item)
        right_item = right_index.get(key)
        if right_item is None:
            left_only.append(left_item)
            continue
        overlap.append((left_item, right_item))

    left_index = {result_key(item): item for item in left_results}
    right_only = [item for item in right_results if result_key(item) not in left_index]
    return overlap, left_only, right_only


def stability_status(
    overlap_count: int,
    left_count: int,
    right_count: int,
    high_threshold: float,
    medium_threshold: float,
) -> tuple[float, str, str]:
    union_count = max(1, left_count + right_count - overlap_count)
    score = overlap_count / union_count
    if score >= high_threshold:
        return score, "High", "#3CB371"
    if score >= medium_threshold:
        return score, "Medium", "#F0AD4E"
    return score, "Low", "#E57373"


def ensure_agent_state() -> None:
    st.session_state.setdefault("agent_messages", [])
    st.session_state.setdefault("agent_format", "modern")
    st.session_state.setdefault("agent_seed_cards", "")
    st.session_state.setdefault("agent_decklist", "")
    st.session_state.setdefault("agent_commander", "")
    st.session_state.setdefault("agent_archidekt_import", "")
    st.session_state.setdefault("agent_import_feedback", "")
    st.session_state.setdefault("agent_target_size", 60)
    st.session_state.setdefault("agent_show_source_text", True)


def parse_decklist(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+x?\s*(.+)$", line)
        if match:
            rows.append({"name": clean_archidekt_card_name(match.group(2)), "count": int(match.group(1))})
            continue
        rows.append({"name": clean_archidekt_card_name(line), "count": 1})
    return rows


def parse_archidekt_import(text: str) -> dict[str, object]:
    headers = {
        "commander": "commander",
        "commander(s)": "commander",
        "mainboard": "mainboard",
        "deck": "mainboard",
        "cards": "mainboard",
        "sideboard": "sideboard",
        "maybeboard": "maybeboard",
    }

    section = "mainboard"
    sections: dict[str, list[tuple[int, str]]] = {
        "commander": [],
        "mainboard": [],
        "sideboard": [],
        "maybeboard": [],
    }

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized_header = re.sub(r"\s*[:\-]+\s*$", "", line).strip().lower()
        if normalized_header in headers:
            section = headers[normalized_header]
            continue

        match = re.match(r"^(\d+)\s+x?\s*(.+)$", line)
        if match:
            count = int(match.group(1))
            name = clean_archidekt_card_name(match.group(2))
            if name:
                sections[section].append((count, name))
            continue

        # Fallback for plain card-name lines under a known section.
        name = clean_archidekt_card_name(line)
        if name:
            sections[section].append((1, name))

    commander_name = ""
    if sections["commander"]:
        commander_name = sections["commander"][0][1]

    # Keep mainboard as decklist input for validation.
    deck_rows = sections["mainboard"]
    deck_text = "\n".join([f"{count} {name}" for count, name in deck_rows])

    return {
        "commander": commander_name,
        "deck_text": deck_text,
        "counts": {
            "commander": len(sections["commander"]),
            "mainboard": len(sections["mainboard"]),
            "sideboard": len(sections["sideboard"]),
            "maybeboard": len(sections["maybeboard"]),
        },
    }


def apply_archidekt_import() -> None:
    payload = parse_archidekt_import(str(st.session_state.get("agent_archidekt_import") or ""))
    commander = str(payload.get("commander") or "")
    deck_text = str(payload.get("deck_text") or "")
    counts = payload.get("counts") or {}

    if commander:
        st.session_state["agent_commander"] = commander
        st.session_state["agent_format"] = "commander"
    if deck_text:
        st.session_state["agent_decklist"] = deck_text

    st.session_state["agent_import_feedback"] = (
        "Import completato: "
        f"commander={counts.get('commander', 0)}, "
        f"mainboard={counts.get('mainboard', 0)}, "
        f"sideboard={counts.get('sideboard', 0)}, "
        f"maybeboard={counts.get('maybeboard', 0)}"
    )


def detect_agent_intent(message: str) -> str:
    text = message.lower()
    if any(token in text for token in ["valid", "valida", "verifica", "controlla", "legal", "legalità", "legale", "bann", "restricted", "bandita"]):
        return "validate-deck"
    if any(token in text for token in ["sinerg", "synergy", "sinergie", "combo", "combo"]):
        return "suggest-synergies"
    if any(token in text for token in ["costruisci", "build", "genera", "crea"]):
        return "build-deck"
    if any(token in text for token in ["mazzo", "deck", "lista"]):
        return "validate-deck"
    return "query"


def extract_seed_cards(message: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', message)
    if quoted:
        return [item.strip() for item in quoted if item.strip()]

    deck_style: list[str] = []
    for line in str(message or "").splitlines():
        if re.match(r"^\s*\d+\s*x?\s+", line):
            cleaned = clean_archidekt_card_name(re.sub(r"^\s*\d+\s*x?\s+", "", line))
            if cleaned:
                deck_style.append(cleaned)
    if deck_style:
        return deck_style

    # split on commas or semicolons for quick prompts like: "Bolt, Snapcaster Mage"
    parts = re.split(r"[,;\n]+", message)
    seeds: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if 2 <= len(cleaned.split()) <= 4 and not any(word in cleaned.lower() for word in ["legal", "mazzo", "deck", "formato", "sinerg"]):
            seeds.append(cleaned)
    return seeds


def agent_system_response(base_url: str, user_message: str) -> dict[str, object]:
    intent = detect_agent_intent(user_message)
    fmt = str(st.session_state.get("agent_format") or "modern")
    show_text = bool(st.session_state.get("agent_show_source_text", True))

    if intent == "validate-deck":
        deck_text = str(st.session_state.get("agent_decklist") or "")
        if not deck_text and looks_like_decklist(str(st.session_state.get("agent_seed_cards") or "")):
            deck_text = str(st.session_state.get("agent_seed_cards") or "")
        if not deck_text and looks_like_decklist(user_message):
            deck_text = user_message

        deck_rows = parse_decklist(deck_text)
        commander_text = str(st.session_state.get("agent_commander") or "").strip()
        commander = clean_archidekt_card_name(commander_text) or None
        if not deck_rows:
            deck_rows = parse_decklist(user_message) if looks_like_decklist(user_message) else []
        if not deck_rows:
            raise ValueError("Per la validazione serve una lista carte. Inseriscila nel campo mazzo o nel messaggio.")
        return post_api(
            base_url,
            "/validate-deck",
            {
                "format": fmt,
                "deck": deck_rows,
                "commander": commander,
                "dataset_path": "data/cards_light_en_it.jsonl",
            },
        )

    if intent == "suggest-synergies":
        seeds = extract_seed_cards(user_message)
        if not seeds and st.session_state.get("agent_seed_cards"):
            seeds = [item.strip() for item in str(st.session_state["agent_seed_cards"]).splitlines() if item.strip()]
        if not seeds:
            raise ValueError("Per suggerire sinergie devi indicare almeno una carta seed.")
        return post_api(
            base_url,
            "/suggest-synergies",
            {
                "format": fmt,
                "seed_cards": seeds,
                "top_k": 10,
                "dataset_path": "data/cards_light_en_it.jsonl",
            },
        )

    if intent == "build-deck":
        seeds = extract_seed_cards(user_message)
        if not seeds and st.session_state.get("agent_seed_cards"):
            seeds = [item.strip() for item in str(st.session_state["agent_seed_cards"]).splitlines() if item.strip()]
        if not seeds:
            raise ValueError("Per costruire un mazzo devi indicare almeno una carta seed.")
        target_size = int(st.session_state.get("agent_target_size") or 60)
        commander = str(st.session_state.get("agent_commander") or "").strip() or None
        return post_api(
            base_url,
            "/build-deck",
            {
                "format": fmt,
                "seed_cards": seeds,
                "target_size": target_size,
                "commander": commander,
                "dataset_path": "data/cards_light_en_it.jsonl",
            },
        )

    return post_query(
        base_url,
        {
            "query": user_message,
            "top_k": 5,
            "model": MODEL_DEFAULT,
            "only_cards": False,
            "only_rules": False,
            "show_source_text": show_text,
        },
    )


def summarize_agent_response(response: dict[str, object]) -> str:
    if "errors" in response and response.get("errors"):
        return "\n".join([f"- {item}" for item in response.get("errors", [])])

    if "valid" in response:
        lines = ["Mazzo valido: sì" if response.get("valid") else "Mazzo valido: no"]
        for item in response.get("errors", []):
            lines.append(f"- Errore: {item}")
        for item in response.get("warnings", []):
            lines.append(f"- Avviso: {item}")
        stats = response.get("stats", {})
        if isinstance(stats, dict):
            lines.append(f"- Formato: {stats.get('format')}")
            lines.append(f"- Dimensione mazzo: {stats.get('deck_size')}")
            commanders = stats.get("commanders") or []
            if commanders:
                lines.append(f"- Comandante/i: {', '.join([str(c) for c in commanders])}")
            composition = stats.get("composition") or {}
            if isinstance(composition, dict) and any(int(composition.get(key, 0)) > 0 for key in ["lands", "ramp", "draw", "removal", "board_wipes"]):
                lines.append(
                    "- Struttura: "
                    f"terre={composition.get('lands', 0)}, "
                    f"ramp={composition.get('ramp', 0)}, "
                    f"draw={composition.get('draw', 0)}, "
                    f"removal={composition.get('removal', 0)}, "
                    f"wipe={composition.get('board_wipes', 0)}"
                )
            power_level = stats.get("power_level") or {}
            if isinstance(power_level, dict) and power_level.get("tier"):
                lines.append(
                    f"- Power level stimato: {power_level.get('tier')} (score {power_level.get('score')})"
                )
        return "\n".join(lines)

    if "deck" in response:
        deck_rows = response.get("deck", [])
        lines = [f"Mazzo costruito per {response.get('format')} con target {response.get('target_size')} carte."]
        validation = response.get("validation", {})
        if isinstance(validation, dict):
            lines.append("Validazione finale: " + ("ok" if validation.get("valid") else "non ok"))
        lines.append("Carte principali:")
        for item in deck_rows[:10]:
            lines.append(f"- {item.get('count')}x {item.get('name')}")
        return "\n".join(lines)

    if response.get("seed_cards") and response.get("results"):
        lines = [
            "Sinergie trovate:",
            f"Seed: {', '.join([str(item) for item in response.get('seed_cards', [])])}",
        ]
        missing = response.get("missing_seed_cards") or []
        if missing:
            lines.append("Seed mancanti: " + ", ".join([str(item) for item in missing]))
        for item in response.get("results", [])[:8]:
            if not isinstance(item, dict):
                continue
            reasons = item.get("reasons") or []
            reason_text = f" ({'; '.join([str(reason) for reason in reasons[:3]])})" if reasons else ""
            lines.append(f"- {item.get('name')} [{item.get('score')}] {reason_text}".rstrip())
        return "\n".join(lines)

    if "results" in response and response.get("results"):
        first = response.get("results", [])[0]
        if response.get("query_mode") == "set_lookup":
            lines = [str(response.get("query_note") or "Ricerca sul set." )]
            for item in response.get("results", [])[:5]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('name')}: {item.get('summary') or item.get('snippet') or ''}")
            return "\n".join(lines)
        if isinstance(first, dict) and first.get("source") == "rules":
            return translate_to_italian(str(first.get("text") or first.get("snippet") or ""))
        if isinstance(first, dict):
            lines = [translate_to_italian(str(first.get("summary") or first.get("name") or ""))]
            for item in response.get("results", [])[1:4]:
                if isinstance(item, dict) and item.get("source") == "card":
                    lines.append(f"- {item.get('name')} | {item.get('type_line')} | {item.get('set')}")
            return "\n".join([line for line in lines if line])

    return json.dumps(response, ensure_ascii=False, indent=2)


st.title("The Stack")
st.caption("Interfaccia locale per interrogare carte e Comprehensive Rules di Magic in modo semantico.")

st.session_state.setdefault("base_url", API_DEFAULT)
st.session_state.setdefault("query_text", "When does summoning sickness apply?")
st.session_state.setdefault("top_k", 5)
st.session_state.setdefault("model_name", MODEL_DEFAULT)
st.session_state.setdefault("only_cards", False)
st.session_state.setdefault("only_rules", False)
st.session_state.setdefault("show_source_text", True)
st.session_state.setdefault("favorite_choice", "")
st.session_state.setdefault("compare_left", "")
st.session_state.setdefault("compare_right", "")
st.session_state.setdefault("translate_to_italian", True)
get_favorites()

ensure_agent_state()
if str(st.session_state.get("agent_format") or "") not in AGENT_FORMAT_OPTIONS:
    st.session_state["agent_format"] = "modern"

if not st.session_state["agent_messages"]:
    st.session_state["agent_messages"].append(
        {
            "role": "assistant",
            "content": (
                "Sono pronto. Scrivimi, per esempio:\n"
                "- Valida questo mazzo per Commander\n"
                "- Suggerisci sinergie per \"Lightning Bolt\" e \"Snapcaster Mage\"\n"
                "- Costruisci un mazzo Modern intorno a una carta seed"
            ),
        }
    )


def load_selected_favorite() -> None:
    favorites = get_favorites()
    selected_query = str(st.session_state.get("favorite_choice") or "")
    if not selected_query:
        return
    matched = next((item for item in favorites if item.get("query") == selected_query), None)
    if not matched:
        return
    st.session_state["query_text"] = str(matched.get("query", st.session_state.get("query_text", "")))
    st.session_state["top_k"] = int(matched.get("top_k", st.session_state.get("top_k", 5)))
    st.session_state["only_cards"] = bool(matched.get("only_cards", st.session_state.get("only_cards", False)))
    st.session_state["only_rules"] = bool(matched.get("only_rules", st.session_state.get("only_rules", False)))
    st.session_state["show_source_text"] = bool(
        matched.get("show_source_text", st.session_state.get("show_source_text", True))
    )


def swap_compare_selection() -> None:
    current_left = st.session_state.get("compare_left", "")
    current_right = st.session_state.get("compare_right", "")
    st.session_state["compare_left"] = current_right
    st.session_state["compare_right"] = current_left

with st.sidebar:
    st.header("Connessione")
    base_url = st.text_input("URL API", key="base_url")

    st.header("Query")
    query_text = st.text_area("Domanda", key="query_text", height=100)
    top_k = st.slider("Numero risultati", min_value=1, max_value=10, key="top_k")
    model_name = st.text_input("Modello embeddings", key="model_name")

    st.header("Ambito")
    only_cards = st.checkbox("Solo carte", key="only_cards")
    only_rules = st.checkbox("Solo regole", key="only_rules")
    show_source_text = st.checkbox("Mostra testo completo regole", key="show_source_text")
    translate_output = st.checkbox("Traduci risultati in italiano", key="translate_to_italian")
    submit = st.button("Esegui query", type="primary")

    if translate_output and not translation_available():
        st.warning("Per la traduzione automatica installa 'deep-translator'.")

    favorites = get_favorites()
    if favorites:
        st.divider()
        st.subheader("Preferiti")
        favorite_labels = [item["query"] for item in favorites]
        st.selectbox(
            "Query salvata",
            options=["", *favorite_labels],
            key="favorite_choice",
            label_visibility="collapsed",
        )
        load_favorite = st.button("Carica preferito", on_click=load_selected_favorite)
        save_favorite = st.button("Salva query corrente")
        if save_favorite:
            add_favorite(
                {
                    "query": st.session_state["query_text"],
                    "top_k": st.session_state["top_k"],
                    "only_cards": st.session_state["only_cards"],
                    "only_rules": st.session_state["only_rules"],
                    "show_source_text": st.session_state["show_source_text"],
                }
            )
            st.rerun()

        st.divider()
        st.subheader("Confronta preferiti")
        compare_left = st.selectbox(
            "Preferito sinistra",
            options=[""] + favorite_labels,
            key="compare_left",
        )
        compare_right = st.selectbox(
            "Preferito destra",
            options=[""] + favorite_labels,
            key="compare_right",
        )
        compare_button = st.button("Confronta preferiti selezionati")
        swap_button = st.button("Inverti preferiti")
        show_only_differences = st.checkbox("Mostra solo differenze", key="show_only_differences")

        st.caption("Soglie stabilita")
        stability_high_threshold = st.slider(
            "Soglia alta",
            min_value=0.50,
            max_value=0.95,
            step=0.01,
            key="stability_high_threshold",
        )
        max_medium = max(0.49, stability_high_threshold - 0.01)
        stability_medium_threshold = st.slider(
            "Soglia media",
            min_value=0.05,
            max_value=float(max_medium),
            step=0.01,
            key="stability_medium_threshold",
        )

        if swap_button and st.session_state.get("compare_left") and st.session_state.get("compare_right"):
            swap_compare_selection()
            st.rerun()

    history = get_history()
    if history:
        st.divider()
        st.subheader("Query recenti")
        selected_history = st.selectbox(
            "Riusa una query",
            options=["", *[item["query"] for item in history]],
            label_visibility="collapsed",
        )
        if selected_history:
            query_text = selected_history

if only_cards and only_rules:
    st.error("Seleziona un solo ambito: solo carte oppure solo regole.")
    st.stop()

tabs = st.tabs(["Agente", "Ricerca", "Confronto"])

agent_tab, search_tab, compare_tab = tabs

with agent_tab:
    st.markdown('<div class="stack-panel"><div class="stack-kicker">Agente</div><h2 style="margin:0;">Interfaccia conversazionale</h2></div>', unsafe_allow_html=True)
    st.caption("Scrivi in italiano cosa vuoi ottenere: legalità, sinergie o costruzione mazzo. L’agente instrada la richiesta al motore giusto.")

    agent_left, agent_right = st.columns([1.05, 0.95])
    with agent_left:
        for message in st.session_state.get("agent_messages", []):
            role = str(message.get("role") or "assistant")
            with st.chat_message(role, avatar="🧙" if role == "assistant" else "🧑"):
                st.markdown(str(message.get("content") or ""))

        agent_prompt = st.chat_input("Chiedimi di validare un mazzo, suggerire sinergie o costruire una lista", key="agent_chat_input")

    with agent_right:
        st.subheader("Controlli agente")
        st.selectbox(
            "Formato",
            options=AGENT_FORMAT_OPTIONS,
            key="agent_format",
            help="Seleziona il formato del mazzo.",
        )
        st.text_area(
            "Import Archidekt (opzionale)",
            key="agent_archidekt_import",
            height=140,
            help="Incolla export Archidekt con sezioni Commander/Mainboard/Sideboard e premi Importa.",
        )
        st.button("Importa Archidekt", on_click=apply_archidekt_import)
        if st.session_state.get("agent_import_feedback"):
            st.caption(str(st.session_state.get("agent_import_feedback")))
        st.text_input("Comandante (opzionale)", key="agent_commander")
        st.text_area("Seed cards", key="agent_seed_cards", height=120, help="Una carta per riga, oppure carte separate da virgola.")
        st.text_area("Lista mazzo", key="agent_decklist", height=180, help="Usata per la validazione. Formato: 4 Lightning Bolt\n2 Snapcaster Mage")
        st.number_input("Dimensione mazzo target", min_value=1, max_value=250, key="agent_target_size")
        st.checkbox("Mostra testo completo regole nelle risposte", key="agent_show_source_text")

    if agent_prompt:
        st.session_state["agent_messages"].append({"role": "user", "content": agent_prompt})
        try:
            agent_response = agent_system_response(base_url, agent_prompt)
            agent_summary = summarize_agent_response(agent_response)
            st.session_state["agent_messages"].append({"role": "assistant", "content": agent_summary})
        except Exception as exc:
            st.session_state["agent_messages"].append({"role": "assistant", "content": f"Errore: {exc}"})
        st.rerun()


def run_query_payload(payload: dict[str, object]) -> dict[str, object]:
    try:
        return post_query(base_url, payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        st.error(f"HTTP {exc.code}: {detail}")
        st.stop()
    except error.URLError as exc:
        st.error(f"Impossibile raggiungere API su {base_url}: {exc}")
        st.stop()

left, right = st.columns([1.2, 1])

if submit:
    payload = make_payload(
        {
            "query": query_text,
            "top_k": top_k,
            "model": model_name,
            "only_cards": only_cards,
            "only_rules": only_rules,
            "show_source_text": show_source_text,
        }
    )

    response_data = run_query_payload(payload)

    add_history_entry(
        {
            "query": query_text,
            "top_k": top_k,
            "only_cards": only_cards,
            "only_rules": only_rules,
            "show_source_text": show_source_text,
        }
    )
    add_favorite(
        {
            "query": query_text,
            "top_k": top_k,
            "only_cards": only_cards,
            "only_rules": only_rules,
            "show_source_text": show_source_text,
        }
    )
    st.session_state["last_query_response"] = response_data
    st.session_state["last_query_query_text"] = query_text
    st.session_state["last_query_show_source_text"] = show_source_text
    st.session_state["last_query_translate_output"] = translate_output

with compare_tab:
    left, right = st.columns([1.2, 1])

    if favorites and compare_button:
        selected_favorites = [compare_left, compare_right]
        if "" in selected_favorites or compare_left == compare_right:
            st.error("Seleziona due query salvate diverse per il confronto.")
            st.stop()

        left_config = next((item for item in favorites if item["query"] == compare_left), None)
        right_config = next((item for item in favorites if item["query"] == compare_right), None)
        if not left_config or not right_config:
            st.error("Non riesco a trovare uno dei preferiti selezionati.")
            st.stop()

        left_data = run_query_payload(make_payload(left_config))
        right_data = run_query_payload(make_payload(right_config))

        left_results = left_data.get("results", [])
        right_results = right_data.get("results", [])
        overlap, left_only, right_only = compare_result_sets(left_results, right_results)
        stability, stability_label, stability_color = stability_status(
            len(overlap),
            len(left_results),
            len(right_results),
            float(st.session_state.get("stability_high_threshold", 0.70)),
            float(st.session_state.get("stability_medium_threshold", 0.40)),
        )

        st.markdown('<div class="stack-panel"><div class="stack-kicker">Analisi</div><h2 style="margin:0;">Sintesi confronto</h2></div>', unsafe_allow_html=True)
        metric_a, metric_b, metric_c, metric_d = st.columns(4)
        metric_a.metric("Overlap", len(overlap))
        metric_b.metric("Solo sinistra", len(left_only))
        metric_c.metric("Solo destra", len(right_only))
        metric_d.metric("Stabilita", f"{stability * 100:.1f}%")
        st.markdown(
            (
                f"<div class=\"stack-panel\" style=\"padding:0.6rem 0.9rem; border-color:{stability_color};\">"
                f"<strong>Stato stabilita:</strong> <span style=\"color:{stability_color};\">{stability_label}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        if not show_only_differences:
            with st.expander("Mostra dettaglio overlap"):
                if not overlap:
                    st.caption("Nessun risultato condiviso tra le due query.")
                else:
                    for index, (left_item, right_item) in enumerate(overlap, start=1):
                        left_score = float(left_item.get("score", 0.0))
                        right_score = float(right_item.get("score", 0.0))
                        delta = left_score - right_score
                        st.markdown(
                            f"{index}. **{result_label(left_item)}**  \n"
                            f"sinistra={left_score:.4f} | destra={right_score:.4f} | delta={delta:+.4f}"
                        )

        with st.expander("Mostra risultati unici"):
            if left_only:
                st.markdown("**Solo nella query di sinistra**")
                for item in left_only:
                    st.markdown(f"- {result_label(item)}")
            else:
                st.caption("Nessun risultato solo-sinistra.")

            if right_only:
                st.markdown("**Solo nella query di destra**")
                for item in right_only:
                    st.markdown(f"- {result_label(item)}")
            else:
                st.caption("Nessun risultato solo-destra.")

        with left:
            st.markdown('<div class="stack-panel"><div class="stack-kicker">Confronto</div><h2 style="margin:0;">Preferito sinistra</h2></div>', unsafe_allow_html=True)
            st.caption(left_config["query"])
            left_display = left_only if show_only_differences else left_results
            st.metric("Risultati", len(left_display))
            for index, result in enumerate(left_display, start=1):
                render_result_item(
                    result,
                    bool(left_config.get("show_source_text", True)),
                    index,
                    translate_output,
                )
            st.download_button(
                "Scarica JSON sinistra",
                data=export_json_bytes(left_data),
                file_name="the-stack-left-query.json",
                mime="application/json",
            )
            st.download_button(
                "Scarica CSV sinistra",
                data=export_csv_text(left_data),
                file_name="the-stack-left-query.csv",
                mime="text/csv",
            )

        with right:
            st.markdown('<div class="stack-panel"><div class="stack-kicker">Confronto</div><h2 style="margin:0;">Preferito destra</h2></div>', unsafe_allow_html=True)
            st.caption(right_config["query"])
            right_display = right_only if show_only_differences else right_results
            st.metric("Risultati", len(right_display))
            for index, result in enumerate(right_display, start=1):
                render_result_item(
                    result,
                    bool(right_config.get("show_source_text", True)),
                    index,
                    translate_output,
                )
            st.download_button(
                "Scarica JSON destra",
                data=export_json_bytes(right_data),
                file_name="the-stack-right-query.json",
                mime="application/json",
            )
            st.download_button(
                "Scarica CSV destra",
                data=export_csv_text(right_data),
                file_name="the-stack-right-query.csv",
                mime="text/csv",
            )

    elif not favorites:
        st.info("Non ci sono ancora preferiti salvati per il confronto.")

with search_tab:
    cached_response = st.session_state.get("last_query_response")
    if cached_response:
        cached_query = str(st.session_state.get("last_query_query_text") or query_text)
        cached_show_source_text = bool(st.session_state.get("last_query_show_source_text", show_source_text))
        cached_translate_output = bool(st.session_state.get("last_query_translate_output", translate_output))
        cached_results = cached_response.get("results", [])

        with left:
            if cached_response.get("query_note"):
                st.info(str(cached_response.get("query_note")))
            st.info(f"Ultima query eseguita: {cached_query}")
            st.metric("Risultati", len(cached_results))
            for index, result in enumerate(cached_results, start=1):
                render_result_item(result, cached_show_source_text, index, cached_translate_output)

        with right:
            st.markdown('<div class="stack-panel"><div class="stack-kicker">Payload</div><h2 style="margin:0;">JSON grezzo</h2></div>', unsafe_allow_html=True)
            st.code(json.dumps(cached_response, ensure_ascii=False, indent=2), language="json")
            st.download_button(
                "Scarica JSON",
                data=export_json_bytes(cached_response),
                file_name="the-stack-query.json",
                mime="application/json",
            )
            st.download_button(
                "Scarica CSV",
                data=export_csv_text(cached_response),
                file_name="the-stack-query.csv",
                mime="text/csv",
            )
    else:
        with left:
            st.info("Configura la query nel pannello laterale e premi Esegui query.")

            if history:
                st.subheader("Storico query")
                for item in history:
                    st.markdown(
                        f"- **{item['query']}** · top_k={item['top_k']} · cards={item['only_cards']} · rules={item['only_rules']}"
                    )

            favorites = get_favorites()
            if favorites:
                st.subheader("Preferiti salvati")
                for item in favorites[:5]:
                    st.markdown(
                        f"- **{item['query']}** · top_k={item['top_k']} · cards={item['only_cards']} · rules={item['only_rules']}"
                    )

        with right:
            st.markdown('<div class="stack-panel"><div class="stack-kicker">Anteprima</div><h2 style="margin:0;">Payload di esempio</h2></div>', unsafe_allow_html=True)
            st.code(
                json.dumps(
                    {
                        "query": query_text,
                        "top_k": top_k,
                        "model": model_name,
                        "only_cards": only_cards,
                        "only_rules": only_rules,
                        "show_source_text": show_source_text,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                language="json",
            )