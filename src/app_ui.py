#!/usr/bin/env python3
"""Streamlit UI for The Stack local retrieval API."""

from __future__ import annotations

import json
from urllib import error, request

import streamlit as st


API_DEFAULT = "http://127.0.0.1:8000"
MODEL_DEFAULT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


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


st.title("The Stack")
st.caption("Local Magic: The Gathering retrieval UI powered by cards and Comprehensive Rules.")

with st.sidebar:
    st.header("Connection")
    base_url = st.text_input("API base URL", API_DEFAULT)

    st.header("Query")
    query_text = st.text_area("Question", "When does summoning sickness apply?", height=100)
    top_k = st.slider("Top results", min_value=1, max_value=10, value=5)
    model_name = st.text_input("Embedding model", MODEL_DEFAULT)

    st.header("Scope")
    only_cards = st.checkbox("Cards only", value=False)
    only_rules = st.checkbox("Rules only", value=False)
    show_source_text = st.checkbox("Show full rules text", value=True)
    submit = st.button("Run query", type="primary")

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

if submit:
    payload = {
        "query": query_text,
        "top_k": top_k,
        "model": model_name,
        "only_cards": only_cards,
        "only_rules": only_rules,
        "show_source_text": show_source_text,
    }

    try:
        response_data = post_query(base_url, payload)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        st.error(f"HTTP {exc.code}: {detail}")
        st.stop()
    except error.URLError as exc:
        st.error(f"Could not reach API at {base_url}: {exc}")
        st.stop()

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
    with left:
        st.metric("Results", len(results))
        for index, result in enumerate(results, start=1):
            with st.container(border=True):
                st.markdown(
                    f"### {index}. {result.get('source', 'unknown')} | score {float(result.get('score', 0.0)):.4f}"
                )
                if result.get("source") == "card":
                    st.markdown(f"**{result.get('name')}**")
                    st.caption(result.get("summary"))
                else:
                    st.write(f"{result.get('source_file')} | section {result.get('section')}")
                    if result.get("snippet"):
                        st.code(result.get("snippet"), language="text")
                    if show_source_text and result.get("text"):
                        st.text_area("Full text", value=str(result.get("text")), height=180, key=f"rules-{index}")

    with right:
        st.markdown('<div class="stack-panel"><div class="stack-kicker">Payload</div><h2 style="margin:0;">Raw JSON</h2></div>', unsafe_allow_html=True)
        st.code(json.dumps(response_data, ensure_ascii=False, indent=2), language="json")
else:
    with left:
        st.info("Configure the query in the sidebar and click Run query.")

        if history:
            st.subheader("Query history")
            for item in history:
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