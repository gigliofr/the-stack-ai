#!/usr/bin/env python3
"""Run local semantic search over precomputed card embeddings."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query card embeddings with a multilingual SentenceTransformer model."
    )
    parser.add_argument("--query", required=True, help="User query text")
    parser.add_argument(
        "--embeddings",
        default="data/embeddings/card_embeddings.npy",
        help="Path to .npy embeddings file",
    )
    parser.add_argument(
        "--metadata",
        default="data/embeddings/card_embeddings_metadata.jsonl",
        help="Path to metadata JSONL file",
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model to use",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top results to print")
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


def main() -> int:
    args = parse_args()
    embeddings_path = Path(args.embeddings)
    metadata_path = Path(args.metadata)

    if not embeddings_path.exists():
        raise SystemExit(f"Embeddings file not found: {embeddings_path}")
    if not metadata_path.exists():
        raise SystemExit(f"Metadata file not found: {metadata_path}")

    numpy = get_dependency("numpy")
    sentence_transformers = get_dependency("sentence_transformers")

    embeddings = numpy.load(embeddings_path, mmap_mode="r")
    metadata = list(read_jsonl(metadata_path))
    if len(metadata) != len(embeddings):
        raise SystemExit(
            "Metadata and embeddings length mismatch. Rebuild embeddings to fix."
        )

    model = sentence_transformers.SentenceTransformer(args.model)
    query_vector = model.encode(
        [args.query], convert_to_numpy=True, normalize_embeddings=True
    )[0]

    scores = embeddings @ query_vector
    top_k = max(1, min(args.top_k, len(scores)))
    top_indices = numpy.argpartition(scores, -top_k)[-top_k:]
    top_indices = top_indices[numpy.argsort(scores[top_indices])[::-1]]

    print(f"Query: {args.query}")
    print(f"Results: {top_k}")
    for rank, idx in enumerate(top_indices, start=1):
        row = metadata[int(idx)]
        print(
            f"[{rank}] score={float(scores[idx]):.4f} | "
            f"name={row.get('name')} | lang={row.get('lang')} | "
            f"type={row.get('type_line')} | set={row.get('set')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())