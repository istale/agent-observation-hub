# Agent Observation Hub

Agent Observation Hub is a local-first OpenAI-compatible observation proxy. It sits between OpenClaw or Hermes Agent and any OpenAI-compatible upstream, captures LLM request and response data, and stores metadata in SQLite while archiving raw payloads on the local filesystem.

LiteLLM is optional. AOH does not require, install, or import the LiteLLM Python package. If production policy bans LiteLLM, point AOH directly at an approved OpenAI-compatible provider.

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
export UPSTREAM_OPENAI_BASE_URL=https://api.minimax.io/v1
export UPSTREAM_OPENAI_API_KEY=replace-me
export AOH_DATA_DIR=data
export AOH_DATABASE_PATH=data/hub.sqlite3
```

Point OpenClaw or Hermes to this gateway as the OpenAI base URL:

```text
http://127.0.0.1:43180/v1
```

Direct provider topology:

```text
OpenClaw / Hermes
  -> Agent Observation Gateway: http://127.0.0.1:43180/v1
  -> OpenAI-compatible provider: https://api.minimax.io/v1
```

Optional LiteLLM topology:

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

Point this gateway upstream directly to a provider:

```sh
export UPSTREAM_OPENAI_BASE_URL=https://api.minimax.io/v1
```

Or optionally point this gateway upstream to LiteLLM:

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
- `GET /api/traces/{trace_id}/analysis-bundle`
- `GET /api/traces/{trace_id}/events`
- `GET /api/traces/{trace_id}/llm-calls`
- `GET /api/subjects/users`
- `GET /api/subjects/users/{user_hash}/traces`
- `GET /api/subjects/users/{user_hash}/analysis-bundle`
- `GET /api/subjects/users/{user_hash}/agents`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/llm-calls/{llm_call_id}`
- `GET /api/raw/{payload_ref}`

Payload rendering is controlled by `AOH_PAYLOAD_MODE`:

- `AOH_PAYLOAD_MODE=raw`: UI pages and `/api/raw/{payload_ref}` return raw local payloads.
- `AOH_PAYLOAD_MODE=redacted`: UI pages and `/api/raw/{payload_ref}` return redacted payloads.

Raw mode is intended for trusted local/company-internal debugging and local LLM agents that need complete payloads to analyze agent and model behavior. `ALLOW_RAW_VIEW` is deprecated and is no longer the primary payload access switch.

`/api/traces/{trace_id}/analysis-bundle` packages run metadata, identity, timeline events, LLM call metadata, payloads, readable response text, correlations, and diagnostics for local LLM analysis. See [docs/analysis_bundle_api.md](docs/analysis_bundle_api.md).

Subject query APIs list observed users, user-specific trace IDs, and user agent/channel combinations before choosing a trace for deep analysis. See [docs/subject_query_api.md](docs/subject_query_api.md).

`/api/subjects/users/{user_hash}/analysis-bundle` packages recent traces for one user into a summary-first bundle for local LLM analysis. It omits payload bodies by default and can include them with `include_payloads=true`. See [docs/user_analysis_bundle_api.md](docs/user_analysis_bundle_api.md).

## Security Notes

This is a local observation tool. Use `AOH_PAYLOAD_MODE=raw` only when every client that can reach the hub is trusted. Raw mode can expose Authorization headers, cookies, API keys, private prompts, user messages, agent memory, tool inputs, tool outputs, and file contents to the UI and `/api/raw/{payload_ref}`. Use `AOH_PAYLOAD_MODE=redacted` before sharing the hub, opening it to a network, or enabling cloud/exporter integrations. The API still protects against path traversal for raw refs, and the archive directory should always be treated as sensitive local data.

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
