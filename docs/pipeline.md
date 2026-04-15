# The Stack Pipeline

## 1) Clean Scryfall data (EN + IT)

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/clean_data.py --input data/default-cards.json --output data/cards_light_en_it.jsonl --langs en,it
```

## 2) Preview and sanity check

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/preview_data.py --input data/cards_light_en_it.jsonl --sample-size 5
```

## 3) Build retrieval documents

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/build_card_documents.py --input data/cards_light_en_it.jsonl --output data/cards_documents.jsonl
```

## 4) Build embeddings (smoke test)

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/embed_documents.py --input data/cards_documents.jsonl --output-dir data/embeddings_smoke --limit 500 --batch-size 32
```

## 5) Build embeddings (full)

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/embed_documents.py --input data/cards_documents.jsonl --output-dir data/embeddings --batch-size 64
```

## 6) Query embeddings locally

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_embeddings.py --query "creatura volante che pesca carte" --embeddings data/embeddings_smoke/card_embeddings.npy --metadata data/embeddings_smoke/card_embeddings_metadata.jsonl --top-k 5
```

## 7) Build rules documents (when files are available in docs)

Put .txt or .md Comprehensive Rules files in docs, then run:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/build_rules_documents.py --input-dir docs --output data/rules_documents.jsonl
```
