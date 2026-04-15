#!/usr/bin/env python3
"""Command-line client for the local The Stack retrieval API."""

from __future__ import annotations

import argparse
import json
from urllib import error, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the local The Stack API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--query", required=True, help="User query text")
    parser.add_argument("--top-k", type=int, default=5, help="Top results to request")
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model to use",
    )
    parser.add_argument(
        "--only-cards",
        action="store_true",
        help="Return only card results",
    )
    parser.add_argument(
        "--only-rules",
        action="store_true",
        help="Return only rules results",
    )
    parser.add_argument(
        "--show-source-text",
        action="store_true",
        help="Request full rules section text when rules are returned",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON response")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.only_cards and args.only_rules:
        raise SystemExit("Use only one of --only-cards or --only-rules.")

    body = {
        "query": args.query,
        "top_k": args.top_k,
        "model": args.model,
        "only_cards": args.only_cards,
        "only_rules": args.only_rules,
        "show_source_text": args.show_source_text,
    }

    payload = json.dumps(body).encode("utf-8")
    endpoint = f"{args.base_url.rstrip('/')}/query"
    http_request = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=120) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SystemExit(f"Failed to connect to API at {endpoint}: {exc}") from exc

    if args.json:
        print(json.dumps(response_data, ensure_ascii=False, indent=2))
        return 0

    print(f"Query: {response_data.get('query')}")
    print(f"Rules included: {response_data.get('rules_included')}")
    print(f"Results: {len(response_data.get('results', []))}")
    for index, result in enumerate(response_data.get("results", []), start=1):
        if result.get("source") == "card":
            summary = result.get("summary") or f"name={result.get('name')}"
            print(f"[{index}] source=card score={result.get('score'):.4f} | {summary}")
            continue

        line = (
            f"[{index}] source=rules score={result.get('score'):.4f} | "
            f"source_file={result.get('source_file')} | section={result.get('section')}"
        )
        print(line)
        if args.show_source_text and result.get("text"):
            print(f"    text={result.get('text')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())