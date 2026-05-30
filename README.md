# Agent Observation Hub

Agent Observation Hub is a local-first OpenAI-compatible observation proxy. It sits between OpenClaw or Hermes Agent and a LiteLLM Proxy, captures LLM request and response data, and stores metadata in SQLite while archiving raw payloads on the local filesystem.

## Architecture

- FastAPI exposes OpenAI-compatible endpoints and local APIs.
- `app/gateway` forwards `/v1/chat/completions` and captures non-stream and stream payloads.
- `app/trace` owns IDs, timestamps, redaction, normalization, and raw archive I/O.
- `app/storage` owns SQLite migrations and repository queries.
- `app/api` exposes trace, run, LLM call, health, and raw payload APIs.
- `app/ui` provides a minimal server-rendered timeline UI.

Raw payloads are written under `data/raw/YYYY-MM-DD/trace_<trace_id>/`. SQLite stores metadata, indexes, payload refs, usage, latency, and status.

## Install

Use Python 3.12.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Configure

```sh
cp .env.example .env
export UPSTREAM_OPENAI_BASE_URL=http://127.0.0.1:4000
export UPSTREAM_OPENAI_API_KEY=dummy
export AOH_DATA_DIR=data
export AOH_DATABASE_PATH=data/hub.sqlite3
```

Point OpenClaw or Hermes to this gateway as the OpenAI base URL:

```text
http://127.0.0.1:43180/v1
```

Canonical local topology:

```text
OpenClaw / Hermes
  -> Agent Observation Gateway: http://127.0.0.1:43180/v1
  -> LiteLLM Proxy: http://127.0.0.1:4000/v1
  -> Model endpoint
```

Earlier local Hermes validation used `8080`. Keep that only as a temporary compatibility override:

```sh
PORT=8080 scripts/dev.sh
```

Point this gateway upstream to LiteLLM:

```sh
export UPSTREAM_OPENAI_BASE_URL=http://127.0.0.1:4000
```

## Start

```sh
scripts/init_db.sh
scripts/dev.sh
```

Open the UI at `http://127.0.0.1:43180/`.

## Maintenance

If older traces were created before run finalization existed, use the backfill command to repair stale `running` rows:

```sh
.venv312/bin/python scripts/backfill_running_runs.py --db data/hub.sqlite3 --stale-minutes 60
.venv312/bin/python scripts/backfill_running_runs.py --db data/hub.sqlite3 --stale-minutes 60 --apply
```

The first command is a dry-run. The second applies updates. Completed child LLM calls finalize their parent run as `ok` or `error`; stale running calls older than the threshold are marked `cancelled` and their parent run becomes `error`.

## Curl Non-Stream

```sh
curl http://127.0.0.1:43180/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer test-key' \
  -H 'X-Agent-Id: openclaw' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

## Curl Stream

```sh
curl -N http://127.0.0.1:43180/v1/chat/completions \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer test-key' \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"hello"}]}'
```

## APIs

- `GET /healthz`
- `GET /api/traces`
- `GET /api/traces/{trace_id}`
- `GET /api/traces/{trace_id}/events`
- `GET /api/traces/{trace_id}/llm-calls`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/llm-calls/{llm_call_id}`
- `GET /api/raw/{payload_ref}`

`/api/raw/{payload_ref}` returns redacted payloads by default. Raw payloads are only returned when `ALLOW_RAW_VIEW=true` and `raw=true` is passed.

## Security Notes

This is a local observation tool. Keep `ALLOW_RAW_VIEW=false` unless you are debugging locally. Raw archives can contain sensitive prompts, headers, tool inputs, and model outputs. The API protects against path traversal for raw refs, but the archive directory should still be treated as sensitive local data.

Retention settings are present for governance planning:

```sh
RAW_RETENTION_DAYS=14
REDACTED_RETENTION_DAYS=90
METRICS_RETENTION_DAYS=365
```

Retention cleanup is not fully implemented in the MVP.

## MVP Limits

- `/v1/responses` is pass-through only.
- Importers are skeletons for OpenClaw and Hermes logs.
- Exporters are no-op interfaces for future OTEL, Opik, and Langfuse integrations.
- Streaming capture records chunks as received by httpx and does not yet normalize provider-specific stream semantics.
