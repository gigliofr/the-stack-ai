#!/usr/bin/env python3
"""Local HTTP API for The Stack retrieval pipeline."""

from __future__ import annotations

import argparse
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.query_knowledge import run_query


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


app = FastAPI(title="The Stack API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
def query(payload: QueryRequest) -> dict[str, Any]:
    args = argparse.Namespace(
        query=payload.query,
        top_k=payload.top_k,
        model=payload.model,
        card_embeddings=payload.card_embeddings,
        card_metadata=payload.card_metadata,
        rules_embeddings=payload.rules_embeddings,
        rules_metadata=payload.rules_metadata,
        rules_documents=payload.rules_documents,
        skip_rules=payload.skip_rules,
        only_cards=payload.only_cards,
        only_rules=payload.only_rules,
        show_source_text=payload.show_source_text,
        json=True,
    )
    return run_query(args)