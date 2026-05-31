# Agent Event Importers Spec

## Purpose

Agent Observation Hub already captures gateway-level LLM requests, responses, stream chunks, correlations, subject queries, and analysis bundles. The next gap is agent-level behavior. Hermes and OpenClaw logs/sessions should become timeline events so local LLM analysis can explain not only what the model saw, but what the agent system did around the model call.

This feature is developed on an independent branch:

```text
codex/agent-event-importers
```

The implementation should be isolated under:

```text
app/importers/agent_events/
```

Existing importer entrypoints remain as compatibility wrappers:

```text
python -m app.importers.hermes_importer --path ...
python -m app.importers.openclaw_importer --path ...
```

## Scope

First implementation slice:

1. Normalize Hermes/OpenClaw log lines into a common event model.
2. Import normalized events into `trace_events`.
3. Support `--source hermes|openclaw`, `--path`, `--follow`, `--dry-run`.
4. Support Hermes root discovery configured per user.
5. Integrate with `ingress_routes` so each user/agent/channel can have a local path root.
6. Join imported events to existing traces conservatively.
7. Fall back to synthetic external traces when no safe join exists.
8. Preserve malformed/unrecognized lines as `external_log` without crashing.

Out of scope for the first slice:

- Deep OpenClaw native session semantics.
- Tool call table writes.
- Automatic failure classification.
- Automatic prompt/workflow optimization.
- Cloud exporters.

## User Root Mapping

Real deployments may have one local OS user or directory root per observed user. Importers need to know where each user's Hermes/OpenClaw data lives.

Initial config shape:

```yaml
hermes_roots:
  - user_hash: istale
    path: /Users/istale/.hermes
  - user_hash: alice
    path: /Users/alice/.hermes

openclaw_roots:
  - user_hash: istale
    path: /Users/istale/.openclaw
```

Because the project has no YAML dependency today, the first implementation may use JSON with the same shape:

```json
{
  "hermes_roots": [
    {"user_hash": "istale", "path": "/Users/istale/.hermes"},
    {"user_hash": "alice", "path": "/Users/alice/.hermes"}
  ],
  "openclaw_roots": [
    {"user_hash": "istale", "path": "/Users/istale/.openclaw"}
  ]
}
```

Suggested default path:

```text
config/agent_event_roots.json
```

CLI override:

```text
--roots-config config/agent_event_roots.json
```

## Ingress Route Integration

`ingress_routes` already maps listening ports and path prefixes to:

- `tenant_id`
- `user_hash`
- `agent_id`
- `channel`
- optional session/channel/conversation ids

Importers should use this table as identity context. For example:

```text
listen_host=127.0.0.1
listen_port=43180
path_prefix=/v1
tenant_id=local
user_hash=istale
agent_id=hermes
channel=discord
```

Root config and ingress routes work together:

1. Root config says where a user's agent files live.
2. `ingress_routes` says what identity should be attached to that user's gateway traffic.
3. Importers use `user_hash` to merge these identities.

If the imported event has no explicit `tenant_id`, `agent_id`, or `channel`, importer may fill missing fields from the enabled `ingress_routes` row matching `user_hash` and source:

- `source=hermes` prefers routes with `agent_id=hermes`
- `source=openclaw` prefers routes with `agent_id=openclaw`

If multiple routes match, importer should prefer the most recently created enabled route, or leave ambiguous fields unset and add a warning.

## Input Sources

Hermes:

```text
<hermes_root>/logs/*.log
<hermes_root>/sessions/
<hermes_root>/state.db
```

OpenClaw:

```text
/tmp/openclaw/openclaw-*.log
<openclaw_root>/agents/*/sessions/*.jsonl
```

First implementation only needs line-oriented file importing. `state.db` can remain documented but deferred unless a stable schema is available.

## Normalized Event Model

Parser output:

```json
{
  "source": "hermes",
  "event_type": "tool_call",
  "timestamp": "2026-05-31T10:00:00Z",
  "trace_id": null,
  "run_id": null,
  "tenant_id": "local",
  "user_hash": "istale",
  "agent_id": "hermes",
  "session_id": "session_123",
  "channel": "discord",
  "conversation_id": null,
  "severity": "info",
  "status": "ok",
  "message": "tool started",
  "payload": {},
  "raw_line": "..."
}
```

Allowed first-slice event types:

```text
agent_run_start
agent_run_end
agent_message
context_build
routing_decision
llm_prepare
tool_call
tool_result
tool_error
channel_delivery
agent_error
external_log
```

Unrecognized lines become:

```text
event_type=external_log
payload.message=<raw line>
```

## Join Strategy

Importer should join conservatively:

1. Exact `trace_id`, if present.
2. Exact `run_id`, if present.
3. `session_id + agent_id + timestamp window`.
4. `user_hash + agent_id + channel + timestamp window`.
5. Fallback synthetic external trace.

Initial timestamp window:

```text
10 minutes
```

Wrong joins are worse than missing joins. If a join is ambiguous, use a synthetic trace and insert enough metadata for later manual analysis.

## Synthetic Trace Behavior

If no existing trace is found:

- create a new `trace_runs` row
- `status=external`
- `trigger_type=importer`
- `input_summary=<source> external event`
- identity fields copied from normalized event when available
- insert the event into `trace_events`

## Safety

Importer payloads may include secrets. First slice should:

- store parsed payload in `trace_events.payload_json`
- avoid writing raw log files into raw archive
- avoid sending data to exporters
- keep malformed raw lines as local DB payload only
- rely on local/private deployment assumptions

## CLI

New canonical CLI:

```sh
python -m app.importers.agent_events.cli \
  --source hermes \
  --path /Users/istale/.hermes/logs/hermes.log
```

Dry run:

```sh
python -m app.importers.agent_events.cli \
  --source hermes \
  --path sample.log \
  --dry-run
```

Root discovery:

```sh
python -m app.importers.agent_events.cli \
  --source hermes \
  --roots-config config/agent_event_roots.json
```

## Analysis Bundle Integration

No schema change is required for analysis bundles. Once imported events are written to `trace_events`, existing endpoints naturally include them:

```text
/api/traces/{trace_id}/analysis-bundle
/api/subjects/users/{user_hash}/analysis-bundle
```

## Acceptance Criteria

1. Hermes JSON line parses into normalized event.
2. Hermes plain text line becomes `external_log`.
3. OpenClaw JSON line parses into normalized event.
4. Imported event writes to `trace_events`.
5. `--dry-run` returns parsed events without writing DB rows.
6. Existing trace can be joined by `session_id + agent_id + timestamp`.
7. Existing trace can be joined by `user_hash + agent_id + channel + timestamp`.
8. No safe join creates synthetic external trace.
9. Root config can discover Hermes paths by `user_hash`.
10. Ingress route identity fills missing `tenant_id`, `agent_id`, and `channel`.
11. Existing wrapper CLIs still work.
12. Analysis bundle timeline includes imported events.
