#!/usr/bin/env python3
"""Streamlit UI for The Stack local retrieval API."""

from __future__ import annotations

import json
from urllib import error, request

import streamlit as st


API_DEFAULT = "http://127.0.0.1:8000"
MODEL_DEFAULT = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


st.set_page_config(page_title="The Stack", page_icon="🃏", layout="wide")


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

if only_cards and only_rules:
    st.error("Select only one scope: cards only or rules only.")
    st.stop()

left, right = st.columns([1.2, 1])

with left:
    st.subheader("Results")

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
    with left:
        st.metric("Results", len(results))
        for index, result in enumerate(results, start=1):
            with st.container(border=True):
                st.markdown(f"### {index}. {result.get('source', 'unknown')} | score {float(result.get('score', 0.0)):.4f}")
                if result.get("source") == "card":
                    st.write(result.get("summary"))
                else:
                    st.write(f"{result.get('source_file')} | section {result.get('section')}")
                    if result.get("snippet"):
                        st.code(result.get("snippet"), language="text")
                    if show_source_text and result.get("text"):
                        st.text_area("Full text", value=str(result.get("text")), height=180, key=f"rules-{index}")

    with right:
        st.subheader("Raw JSON")
        st.code(json.dumps(response_data, ensure_ascii=False, indent=2), language="json")
else:
    with left:
        st.info("Configure the query in the sidebar and click Run query.")

    with right:
        st.subheader("Sample payload")
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