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

## 8) Build rules embeddings

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/embed_rules.py --input data/rules_documents.jsonl --output-dir data/rules_embeddings --batch-size 64
```

## 9) Query cards + rules together

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_knowledge.py --query "When does summoning sickness apply?" --top-k 8
```

To print the full text of matching rules sections:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_knowledge.py --query "When does summoning sickness apply?" --top-k 5 --show-source-text
```

Cards only:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_knowledge.py --query "counter target spell" --top-k 5 --only-cards
```

Rules only:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_knowledge.py --query "When does summoning sickness apply?" --top-k 5 --only-rules --show-source-text
```

Machine-readable JSON output:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/query_knowledge.py --query "counter target spell" --top-k 5 --json --only-cards
```

## 10) Run local API (FastAPI)

Start server:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m uvicorn src.api_server:app --host 127.0.0.1 --port 8000
```

If port `8000` is already in use, run the API on a high port (example `18000`):

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m uvicorn src.api_server:app --host 127.0.0.1 --port 18000
```

The API caches the model and loaded vectors after the first request, so the second and later queries should be noticeably faster.

Health check:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

Query endpoint:

```powershell
$body = @{
	query = "When does summoning sickness apply?"
	top_k = 5
	only_rules = $true
	show_source_text = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/query" -ContentType "application/json" -Body $body
```

CLI client:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe src/api_client.py --query "counter target spell" --top-k 5 --only-cards
```

Web UI:

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m streamlit run src/app_ui.py
```

If port `8501` is already in use, start Streamlit on another port (example `8601`):

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m streamlit run src/app_ui.py --server.headless true --server.port 8601
```

When using a non-default API port, set `URL API` in the sidebar (example `http://127.0.0.1:18000`).

Quick smoke checks:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:18000/health"
Invoke-WebRequest -Uri "http://127.0.0.1:8601" -UseBasicParsing | Select-Object -ExpandProperty StatusCode
```

## 11) Gameplay endpoints (MVP)

Validate deck legality:

```powershell
$body = @{
	format = "modern"
	deck = @(
		@{ name = "Lightning Bolt"; count = 4 },
		@{ name = "Snapcaster Mage"; count = 2 }
	)
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/validate-deck" -ContentType "application/json" -Body $body
```

Suggest synergies:

```powershell
$body = @{
	format = "modern"
	seed_cards = @("Lightning Bolt", "Snapcaster Mage")
	top_k = 10
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/suggest-synergies" -ContentType "application/json" -Body $body
```

Build deck:

```powershell
$body = @{
	format = "modern"
	seed_cards = @("Lightning Bolt", "Snapcaster Mage")
	target_size = 60
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/build-deck" -ContentType "application/json" -Body $body
```

## 12) Release notes (latest)

What was improved in the latest release:

- Agent tab now returns richer summaries for gameplay intents.
- Synergy responses include more than one candidate, with score and reasons.
- Set-aware lookup for Bloomburrow was added to reduce rules noise.
- Search rendering in the UI now shows last query results reliably.
- Startup runbook now includes fallback ports for API/UI.

## 13) Smoke test in 3 commands

Use these commands to validate the full local flow quickly.

1) Start API (fallback high port)

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m uvicorn src.api_server:app --host 127.0.0.1 --port 18000
```

2) Start UI (fallback high port)

```powershell
c:/Users/gigli/GoWs/the-stack-ai/.venv/Scripts/python.exe -m streamlit run src/app_ui.py --server.headless true --server.port 8601
```

3) Run API checks (health + gameplay)

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:18000/health"

$body = @{
	format = "modern"
	seed_cards = @("Llanowar Elves", "Cultivate")
	top_k = 3
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:18000/suggest-synergies" -ContentType "application/json" -Body $body
```

If the API is not running on default port 8000, set URL API in the Streamlit sidebar to:

http://127.0.0.1:18000

One-command smoke test (API already running):

```powershell
./scripts/smoke_test.ps1
```

Custom API URL:

```powershell
./scripts/smoke_test.ps1 -BaseUrl "http://127.0.0.1:18000"
```

## 14) One-command startup (auto port fallback)

Start API + UI together on free local ports:

```powershell
./scripts/start_stack.ps1 -Headless
```

The script prints:

- API URL
- UI URL
- process IDs to stop both services

Stop command example (printed by the script):

```powershell
Stop-Process -Id <API_PID>,<UI_PID>
```
