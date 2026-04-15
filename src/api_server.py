#!/usr/bin/env python3
"""Local HTTP API for The Stack retrieval pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

from src.game_engine import build_deck, suggest_synergies, validate_deck
from src.query_knowledge import read_jsonl, result_payload, load_rules_text_index, score_block


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    card_embeddings: str = "data/embeddings/card_embeddings.npy"
    card_metadata: str = "data/embeddings/card_embeddings_metadata.jsonl"

    rules_embeddings: str = "data/rules_embeddings/rules_embeddings.npy"
    rules_metadata: str = "data/rules_embeddings/rules_embeddings_metadata.jsonl"
    rules_documents: str = "data/rules_documents.jsonl"

    skip_rules: bool = False
    only_cards: bool = False
    only_rules: bool = False
    show_source_text: bool = False


class DeckCardEntry(BaseModel):
    name: str = Field(..., min_length=1)
    count: int = Field(default=1, ge=1)


class ValidateDeckRequest(BaseModel):
    format: str = Field(..., min_length=1)
    deck: list[DeckCardEntry]
    commander: str | None = None
    dataset_path: str = "data/cards_light_en_it.jsonl"


class SynergyRequest(BaseModel):
    format: str = Field(..., min_length=1)
    seed_cards: list[str] = Field(default_factory=list)
    top_k: int = Field(default=20, ge=1, le=100)
    dataset_path: str = "data/cards_light_en_it.jsonl"


class BuildDeckRequest(BaseModel):
    format: str = Field(..., min_length=1)
    seed_cards: list[str] = Field(default_factory=list)
    target_size: int | None = Field(default=None, ge=1, le=250)
    commander: str | None = None
    dataset_path: str = "data/cards_light_en_it.jsonl"


app = FastAPI(title="The Stack API", version="0.1.0")


@lru_cache(maxsize=8)
def get_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


@lru_cache(maxsize=8)
def get_index(embeddings_path: str, metadata_path: str) -> tuple[Any, list[dict[str, Any]]]:
    embeddings = np.load(embeddings_path, mmap_mode="r")
    metadata = list(read_jsonl(Path(metadata_path)))
    if len(embeddings) != len(metadata):
        raise RuntimeError(
            f"Length mismatch for {Path(embeddings_path).name} and {Path(metadata_path).name}."
        )
    return embeddings, metadata


@lru_cache(maxsize=4)
def get_rules_text_index(rules_documents_path: str) -> dict[tuple[str, int], str]:
    return load_rules_text_index(Path(rules_documents_path))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/validate-deck")
def validate_deck_endpoint(payload: ValidateDeckRequest) -> dict[str, Any]:
    deck_rows = [{"name": item.name, "count": item.count} for item in payload.deck]
    return validate_deck(
        deck_rows,
        fmt=payload.format,
        commander=payload.commander,
        dataset_path=payload.dataset_path,
    )


@app.post("/suggest-synergies")
def suggest_synergies_endpoint(payload: SynergyRequest) -> dict[str, Any]:
    if not payload.seed_cards:
        raise HTTPException(status_code=400, detail="seed_cards non puo essere vuoto.")
    return suggest_synergies(
        seed_cards=payload.seed_cards,
        fmt=payload.format,
        top_k=payload.top_k,
        dataset_path=payload.dataset_path,
    )


@app.post("/build-deck")
def build_deck_endpoint(payload: BuildDeckRequest) -> dict[str, Any]:
    if not payload.seed_cards:
        raise HTTPException(status_code=400, detail="seed_cards non puo essere vuoto.")
    return build_deck(
        seed_cards=payload.seed_cards,
        fmt=payload.format,
        target_size=payload.target_size,
        commander=payload.commander,
        dataset_path=payload.dataset_path,
    )


@app.post("/query")
def query(payload: QueryRequest) -> dict[str, Any]:
    if payload.only_cards and payload.only_rules:
        raise HTTPException(status_code=400, detail="Use only one of only_cards or only_rules.")
    if payload.only_rules and payload.skip_rules:
        raise HTTPException(status_code=400, detail="only_rules cannot be combined with skip_rules.")

    card_embeddings, card_metadata = get_index(
        payload.card_embeddings, payload.card_metadata
    )

    include_rules = (
        not payload.skip_rules
        and Path(payload.rules_embeddings).exists()
        and Path(payload.rules_metadata).exists()
    )

    rules_embeddings = None
    rules_metadata: list[dict[str, Any]] = []
    if include_rules:
        rules_embeddings, rules_metadata = get_index(
            payload.rules_embeddings, payload.rules_metadata
        )

    rules_text_index: dict[tuple[str, int], str] = {}
    if payload.show_source_text and include_rules:
        rules_documents_path = Path(payload.rules_documents)
        if not rules_documents_path.exists():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Rules documents file not found. Build it first with build_rules_documents.py "
                    "or provide rules_documents."
                ),
            )
        rules_text_index = get_rules_text_index(payload.rules_documents)

    model = get_model(payload.model)
    query_vector = model.encode(
        [payload.query], convert_to_numpy=True, normalize_embeddings=True
    )[0]

    block_k = max(payload.top_k * 3, 10)
    all_rows: list[dict[str, Any]] = []

    if not payload.only_rules:
        all_rows.extend(
            score_block(
                np,
                card_embeddings,
                card_metadata,
                query_vector,
                source="card",
                top_k=block_k,
            )
        )

    if not payload.only_cards and include_rules and rules_embeddings is not None:
        all_rows.extend(
            score_block(
                np,
                rules_embeddings,
                rules_metadata,
                query_vector,
                source="rules",
                top_k=block_k,
            )
        )

    if not all_rows:
        raise HTTPException(
            status_code=400,
            detail=(
                "No eligible indexes available for the selected mode. "
                "Check source flags and embedding files."
            ),
        )

    all_rows.sort(key=lambda item: item["_score"], reverse=True)
    top_rows = all_rows[: max(1, payload.top_k)]

    return {
        "query": payload.query,
        "rules_included": include_rules,
        "results": [
            result_payload(row, payload.show_source_text, rules_text_index)
            for row in top_rows
        ],
    }
