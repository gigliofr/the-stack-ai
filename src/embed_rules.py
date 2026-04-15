#!/usr/bin/env python3
"""Create multilingual embeddings for Comprehensive Rules documents."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed rules documents with a multilingual SentenceTransformer model."
    )
    parser.add_argument(
        "--input",
        default="data/rules_documents.jsonl",
        help="Path to the rules document JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        default="data/rules_embeddings",
        help="Directory where embeddings and metadata will be written",
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model to use",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Embedding batch size",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of documents to embed (0 means no limit)",
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


def load_documents(path: Path, limit: int) -> Tuple[list[Dict[str, Any]], list[str]]:
    metadata: list[Dict[str, Any]] = []
    texts: list[str] = []

    for row in read_jsonl(path):
        text = str(row.get("text") or "").strip()
        if not text:
            continue

        metadata.append(
            {
                "source_file": row.get("source_file"),
                "section": row.get("section"),
            }
        )
        texts.append(text)

        if 0 < limit <= len(texts):
            break

    return metadata, texts


def main() -> int:
    args = parse_args()
    source_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not source_path.exists():
        raise SystemExit(f"Input file not found: {source_path}")

    numpy = get_dependency("numpy")
    sentence_transformers = get_dependency("sentence_transformers")

    metadata, texts = load_documents(source_path, args.limit)
    if not texts:
        raise SystemExit("No rules documents found in the input file.")

    output_dir.mkdir(parents=True, exist_ok=True)
    embeddings_path = output_dir / "rules_embeddings.npy"
    metadata_path = output_dir / "rules_embeddings_metadata.jsonl"

    model = sentence_transformers.SentenceTransformer(args.model)
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    numpy.save(embeddings_path, embeddings)

    with metadata_path.open("w", encoding="utf-8") as destination:
        for row in metadata:
            destination.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Input: {source_path}")
    print(f"Documents: {len(texts):,}")
    print(f"Embeddings: {embeddings_path}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())