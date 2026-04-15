#!/usr/bin/env python3
"""Streamlit UI for The Stack local retrieval API."""

from __future__ import annotations

import json
import csv
import io
from functools import lru_cache
from pathlib import Path
from urllib import error, request

import streamlit as st

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None


API_DEFAULT = "http://127.0.0.1:8000"
MODEL_DEFAULT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FAVORITES_PATH = Path("data/query_favorites.json")


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


def post_query(base_url: str, payload: dict[str, object]) -> dict[str, object]:
    endpoint = f"{base_url.rstrip('/')}/query"
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(http_request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


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
    return f"rules:{result.get('source_file')}:{result.get('section')}"


def result_label(result: dict[str, object]) -> str:
    if result.get("source") == "card":
        return str(result.get("summary") or result.get("name") or "unknown card")
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


st.title("The Stack")
st.caption("Interfaccia locale per interrogare carte e Comprehensive Rules di Magic in modo semantico.")

st.session_state.setdefault("base_url", API_DEFAULT)
st.session_state.setdefault("query_text", "When does summoning sickness apply?")
st.session_state.setdefault("top_k", 5)
st.session_state.setdefault("model_name", MODEL_DEFAULT)
st.session_state.setdefault("only_cards", False)
st.session_state.setdefault("only_rules", False)
st.session_state.setdefault("show_source_text", True)
st.session_state.setdefault("query_text", "When does summoning sickness apply?")
st.session_state.setdefault("favorite_choice", "")
st.session_state.setdefault("compare_left", "")
st.session_state.setdefault("compare_right", "")
st.session_state.setdefault("stability_high_threshold", 0.70)
st.session_state.setdefault("stability_medium_threshold", 0.40)
st.session_state.setdefault("translate_to_italian", True)
get_favorites()

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
        load_favorite = st.button("Carica preferito")
        save_favorite = st.button("Salva query corrente")
        if load_favorite and st.session_state.get("favorite_choice"):
            selected_query = st.session_state["favorite_choice"]
            matched = next(
                (item for item in favorites if item["query"] == selected_query),
                None,
            )
            if matched:
                st.session_state["query_text"] = str(matched["query"])
                st.session_state["top_k"] = int(matched.get("top_k", st.session_state["top_k"]))
                st.session_state["only_cards"] = bool(
                    matched.get("only_cards", st.session_state["only_cards"])
                )
                st.session_state["only_rules"] = bool(
                    matched.get("only_rules", st.session_state["only_rules"])
                )
                st.session_state["show_source_text"] = bool(
                    matched.get("show_source_text", st.session_state["show_source_text"])
                )
                st.rerun()
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
            value=float(st.session_state["stability_high_threshold"]),
            step=0.01,
            key="stability_high_threshold",
        )
        max_medium = max(0.49, stability_high_threshold - 0.01)
        stability_medium_threshold = st.slider(
            "Soglia media",
            min_value=0.05,
            max_value=float(max_medium),
            value=min(float(st.session_state["stability_medium_threshold"]), float(max_medium)),
            step=0.01,
            key="stability_medium_threshold",
        )

        if swap_button and st.session_state.get("compare_left") and st.session_state.get("compare_right"):
            st.session_state["compare_left"], st.session_state["compare_right"] = (
                st.session_state["compare_right"],
                st.session_state["compare_left"],
            )
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

left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="stack-panel"><div class="stack-kicker">Retrieval</div><h2 style="margin:0;">Risultati</h2></div>', unsafe_allow_html=True)


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

    results = response_data.get("results", [])
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
    with left:
        st.metric("Risultati", len(results))
        for index, result in enumerate(results, start=1):
            render_result_item(result, show_source_text, index, translate_output)

    with right:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Payload</div><h2 style="margin:0;">JSON grezzo</h2></div>', unsafe_allow_html=True)
        st.code(json.dumps(response_data, ensure_ascii=False, indent=2), language="json")
        st.download_button(
            "Scarica JSON",
            data=export_json_bytes(response_data),
            file_name="the-stack-query.json",
            mime="application/json",
        )
        st.download_button(
            "Scarica CSV",
            data=export_csv_text(response_data),
            file_name="the-stack-query.csv",
            mime="text/csv",
        )
elif favorites and compare_button:
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