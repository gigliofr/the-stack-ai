#!/usr/bin/env python3
"""Streamlit UI for The Stack local retrieval API."""

from __future__ import annotations

import json
import csv
import io
from pathlib import Path
from urllib import error, request

import streamlit as st


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


def render_result_item(result: dict[str, object], show_source_text: bool, index: int) -> None:
    with st.container(border=True):
        st.markdown(
            f"### {index}. {result.get('source', 'unknown')} | score {float(result.get('score', 0.0)):.4f}"
        )
        if result.get("source") == "card":
            st.markdown(f"**{result.get('name')}**")
            st.caption(result.get("summary"))
            return

        st.write(f"{result.get('source_file')} | section {result.get('section')}")
        if result.get("snippet"):
            st.code(result.get("snippet"), language="text")
        if show_source_text and result.get("text"):
            st.text_area(
                "Full text",
                value=str(result.get("text")),
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


st.title("The Stack")
st.caption("Local Magic: The Gathering retrieval UI powered by cards and Comprehensive Rules.")

st.session_state.setdefault("base_url", API_DEFAULT)
st.session_state.setdefault("query_text", "When does summoning sickness apply?")
st.session_state.setdefault("top_k", 5)
st.session_state.setdefault("model_name", MODEL_DEFAULT)
st.session_state.setdefault("only_cards", False)
st.session_state.setdefault("only_rules", False)
st.session_state.setdefault("show_source_text", True)
st.session_state.setdefault("query_text", "When does summoning sickness apply?")
st.session_state.setdefault("favorite_choice", "")
get_favorites()

with st.sidebar:
    st.header("Connection")
    base_url = st.text_input("API base URL", key="base_url")

    st.header("Query")
    query_text = st.text_area("Question", key="query_text", height=100)
    top_k = st.slider("Top results", min_value=1, max_value=10, key="top_k")
    model_name = st.text_input("Embedding model", key="model_name")

    st.header("Scope")
    only_cards = st.checkbox("Cards only", key="only_cards")
    only_rules = st.checkbox("Rules only", key="only_rules")
    show_source_text = st.checkbox("Show full rules text", key="show_source_text")
    submit = st.button("Run query", type="primary")

    favorites = get_favorites()
    if favorites:
        st.divider()
        st.subheader("Favorites")
        favorite_labels = [item["query"] for item in favorites]
        st.selectbox(
            "Saved query",
            options=["", *favorite_labels],
            key="favorite_choice",
            label_visibility="collapsed",
        )
        load_favorite = st.button("Load favorite")
        save_favorite = st.button("Save current query")
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
        st.subheader("Compare favorites")
        compare_left = st.selectbox(
            "Left favorite",
            options=[""] + favorite_labels,
            key="compare_left",
        )
        compare_right = st.selectbox(
            "Right favorite",
            options=[""] + favorite_labels,
            key="compare_right",
        )
        compare_button = st.button("Compare selected favorites")

    history = get_history()
    if history:
        st.divider()
        st.subheader("Recent queries")
        selected_history = st.selectbox(
            "Reuse a query",
            options=["", *[item["query"] for item in history]],
            label_visibility="collapsed",
        )
        if selected_history:
            query_text = selected_history

if only_cards and only_rules:
    st.error("Select only one scope: cards only or rules only.")
    st.stop()

left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="stack-panel"><div class="stack-kicker">Retrieval</div><h2 style="margin:0;">Results</h2></div>', unsafe_allow_html=True)


def run_query_payload(payload: dict[str, object]) -> dict[str, object]:
    try:
        return post_query(base_url, payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        st.error(f"HTTP {exc.code}: {detail}")
        st.stop()
    except error.URLError as exc:
        st.error(f"Could not reach API at {base_url}: {exc}")
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
        st.metric("Results", len(results))
        for index, result in enumerate(results, start=1):
            render_result_item(result, show_source_text, index)

    with right:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Payload</div><h2 style="margin:0;">Raw JSON</h2></div>', unsafe_allow_html=True)
        st.code(json.dumps(response_data, ensure_ascii=False, indent=2), language="json")
        st.download_button(
            "Download JSON",
            data=export_json_bytes(response_data),
            file_name="the-stack-query.json",
            mime="application/json",
        )
        st.download_button(
            "Download CSV",
            data=export_csv_text(response_data),
            file_name="the-stack-query.csv",
            mime="text/csv",
        )
elif favorites and compare_button:
    selected_favorites = [compare_left, compare_right]
    if "" in selected_favorites or compare_left == compare_right:
        st.error("Select two different saved queries to compare.")
        st.stop()

    left_config = next((item for item in favorites if item["query"] == compare_left), None)
    right_config = next((item for item in favorites if item["query"] == compare_right), None)
    if not left_config or not right_config:
        st.error("Could not find one of the selected favorites.")
        st.stop()

    left_data = run_query_payload(make_payload(left_config))
    right_data = run_query_payload(make_payload(right_config))

    left_results = left_data.get("results", [])
    right_results = right_data.get("results", [])
    with left:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Comparison</div><h2 style="margin:0;">Left favorite</h2></div>', unsafe_allow_html=True)
        st.caption(left_config["query"])
        st.metric("Results", len(left_results))
        for index, result in enumerate(left_results, start=1):
            render_result_item(result, bool(left_config.get("show_source_text", True)), index)
        st.download_button(
            "Download left JSON",
            data=export_json_bytes(left_data),
            file_name="the-stack-left-query.json",
            mime="application/json",
        )
        st.download_button(
            "Download left CSV",
            data=export_csv_text(left_data),
            file_name="the-stack-left-query.csv",
            mime="text/csv",
        )

    with right:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Comparison</div><h2 style="margin:0;">Right favorite</h2></div>', unsafe_allow_html=True)
        st.caption(right_config["query"])
        st.metric("Results", len(right_results))
        for index, result in enumerate(right_results, start=1):
            render_result_item(result, bool(right_config.get("show_source_text", True)), index)
        st.download_button(
            "Download right JSON",
            data=export_json_bytes(right_data),
            file_name="the-stack-right-query.json",
            mime="application/json",
        )
        st.download_button(
            "Download right CSV",
            data=export_csv_text(right_data),
            file_name="the-stack-right-query.csv",
            mime="text/csv",
        )
else:
    with left:
        st.info("Configure the query in the sidebar and click Run query.")

        if history:
            st.subheader("Query history")
            for item in history:
                st.markdown(
                    f"- **{item['query']}** · top_k={item['top_k']} · cards={item['only_cards']} · rules={item['only_rules']}"
                )

        favorites = get_favorites()
        if favorites:
            st.subheader("Saved favorites")
            for item in favorites[:5]:
                st.markdown(
                    f"- **{item['query']}** · top_k={item['top_k']} · cards={item['only_cards']} · rules={item['only_rules']}"
                )

    with right:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Preview</div><h2 style="margin:0;">Sample payload</h2></div>', unsafe_allow_html=True)
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