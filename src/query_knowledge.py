#!/usr/bin/env python3
"""Query card and rules embeddings together with one command."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query both card and rules embeddings with multilingual semantic search."
    )
    parser.add_argument("--query", required=True, help="User query text")
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model to use",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top results to print")

    parser.add_argument(
        "--card-embeddings",
        default="data/embeddings/card_embeddings.npy",
        help="Path to card embeddings .npy",
    )
    parser.add_argument(
        "--card-metadata",
        default="data/embeddings/card_embeddings_metadata.jsonl",
        help="Path to card metadata JSONL",
    )

    parser.add_argument(
        "--rules-embeddings",
        default="data/rules_embeddings/rules_embeddings.npy",
        help="Path to rules embeddings .npy",
    )
    parser.add_argument(
        "--rules-metadata",
        default="data/rules_embeddings/rules_embeddings_metadata.jsonl",
        help="Path to rules metadata JSONL",
    )
    parser.add_argument(
        "--skip-rules",
        action="store_true",
        help="Skip rules embeddings even if files exist",
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
        help="Print full rules section text for rule results",
    )
    parser.add_argument(
        "--rules-documents",
        default="data/rules_documents.jsonl",
        help="Path to rules documents JSONL (used with --show-source-text)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text output",
    )
    return parser.parse_args()


def get_dependency(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            f"Missing dependency '{name}'. Install it with: pip install -r requirements.txt"
        ) from exc


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_index(numpy: Any, embeddings_path: Path, metadata_path: Path) -> tuple[Any, list[Dict[str, Any]]]:
    embeddings = numpy.load(embeddings_path, mmap_mode="r")
    metadata = list(read_jsonl(metadata_path))
    if len(embeddings) != len(metadata):
        raise SystemExit(
            f"Length mismatch for {embeddings_path.name} and {metadata_path.name}."
        )
    return embeddings, metadata


def score_block(
    numpy: Any,
    embeddings: Any,
    metadata: list[Dict[str, Any]],
    query_vector: Any,
    source: str,
    top_k: int,
) -> list[Dict[str, Any]]:
    scores = embeddings @ query_vector
    block_k = max(1, min(top_k, len(scores)))
    indices = numpy.argpartition(scores, -block_k)[-block_k:]
    indices = indices[numpy.argsort(scores[indices])[::-1]]

    rows: list[Dict[str, Any]] = []
    for idx in indices:
        row = metadata[int(idx)].copy()
        row["_source"] = source
        row["_score"] = float(scores[idx])
        rows.append(row)
    return rows


def format_result(row: Dict[str, Any]) -> str:
    if row.get("_source") == "card":
        return (
            f"name={row.get('name')} | lang={row.get('lang')} | "
            f"type={row.get('type_line')} | set={row.get('set')}"
        )
    snippet = row.get("snippet")
    if snippet:
        return (
            f"source_file={row.get('source_file')} | section={row.get('section')} | "
            f"snippet={snippet}"
        )
    return f"source_file={row.get('source_file')} | section={row.get('section')}"


def result_payload(row: Dict[str, Any], include_source_text: bool, rules_text_index: dict[tuple[str, int], str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source": row.get("_source"),
        "score": row.get("_score"),
    }

    if row.get("_source") == "card":
        payload.update(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "lang": row.get("lang"),
                "type_line": row.get("type_line"),
                "set": row.get("set"),
                "summary": format_result(row),
            }
        )
        return payload

    source_file = row.get("source_file")
    section = row.get("section")
    payload.update(
        {
            "source_file": source_file,
            "section": section,
            "snippet": row.get("snippet"),
        }
    )

    if include_source_text and source_file is not None and section is not None:
        try:
            payload["text"] = rules_text_index.get((str(source_file), int(section)))
        except (TypeError, ValueError):
            payload["text"] = None
    return payload


def load_rules_text_index(path: Path) -> dict[tuple[str, int], str]:
    index: dict[tuple[str, int], str] = {}
    for row in read_jsonl(path):
        source_file = str(row.get("source_file") or "")
        section = row.get("section")
        text = str(row.get("text") or "").strip()
        if not source_file or section is None or not text:
            continue
        try:
            section_int = int(section)
        except (TypeError, ValueError):
            continue
        index[(source_file, section_int)] = text
    return index


def main() -> int:
    args = parse_args()
    if args.only_cards and args.only_rules:
        raise SystemExit("Use only one of --only-cards or --only-rules.")
    if args.only_rules and args.skip_rules:
        raise SystemExit("--only-rules cannot be combined with --skip-rules.")

    numpy = get_dependency("numpy")
    sentence_transformers = get_dependency("sentence_transformers")

    card_embeddings_path = Path(args.card_embeddings)
    card_metadata_path = Path(args.card_metadata)
    if not card_embeddings_path.exists() or not card_metadata_path.exists():
        raise SystemExit("Card embeddings are required. Build them first with embed_documents.py")

    card_embeddings, card_metadata = load_index(
        numpy, card_embeddings_path, card_metadata_path
    )

    include_rules = (
        not args.skip_rules
        and Path(args.rules_embeddings).exists()
        and Path(args.rules_metadata).exists()
    )

    rules_embeddings = None
    rules_metadata: list[Dict[str, Any]] = []
    if include_rules:
        rules_embeddings, rules_metadata = load_index(
            numpy, Path(args.rules_embeddings), Path(args.rules_metadata)
        )

    rules_text_index: dict[tuple[str, int], str] = {}
    if args.show_source_text and include_rules:
        rules_documents_path = Path(args.rules_documents)
        if not rules_documents_path.exists():
            raise SystemExit(
                "Rules documents file not found. Build it first with build_rules_documents.py "
                "or provide --rules-documents."
            )
        rules_text_index = load_rules_text_index(rules_documents_path)

    model = sentence_transformers.SentenceTransformer(args.model)
    query_vector = model.encode(
        [args.query], convert_to_numpy=True, normalize_embeddings=True
    )[0]

    block_k = max(args.top_k * 3, 10)
    all_rows: list[Dict[str, Any]] = []

    if not args.only_rules:
        all_rows.extend(
            score_block(
                numpy,
                card_embeddings,
                card_metadata,
                query_vector,
                source="card",
                top_k=block_k,
            )
        )

    if not args.only_cards and include_rules and rules_embeddings is not None:
        all_rows.extend(
            score_block(
                numpy,
                rules_embeddings,
                rules_metadata,
                query_vector,
                source="rules",
                top_k=block_k,
            )
        )

    if not all_rows:
        raise SystemExit(
            "No eligible indexes available for the selected mode. "
            "Check source flags and embedding files."
        )

    all_rows.sort(key=lambda item: item["_score"], reverse=True)
    top_rows = all_rows[: max(1, args.top_k)]

    if args.json:
        output = {
            "query": args.query,
            "rules_included": include_rules,
            "results": [
                result_payload(row, args.show_source_text, rules_text_index)
                for row in top_rows
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    print(f"Query: {args.query}")
    print(f"Rules included: {include_rules}")
    print(f"Results: {len(top_rows)}")
    for rank, row in enumerate(top_rows, start=1):
        print(
            f"[{rank}] source={row.get('_source')} "
            f"score={row.get('_score'):.4f} | {format_result(row)}"
        )
        if args.show_source_text and row.get("_source") == "rules":
            source_file = str(row.get("source_file") or "")
            section = row.get("section")
            text = None
            if source_file and section is not None:
                try:
                    text = rules_text_index.get((source_file, int(section)))
                except (TypeError, ValueError):
                    text = None
            if text:
                print(f"    text={text}")
            else:
                print("    text=<not found in rules documents index>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())