# Phase 2.1 Ingress Route Mapping Spec

## Purpose

Phase 2 correlation captures explicit metadata headers from Hermes, OpenClaw, LiteLLM, and providers. In real deployments, however, there may be 10-20 users or agents running through different local gateway ports, and some clients may not send Hub metadata headers yet.

Ingress Route Mapping provides a controlled fallback:

- If a request has explicit metadata headers, trust the headers.
- If headers are missing, infer default user/agent/channel labels from the inbound port/path.
- If neither exists, keep `unknown`.

This improves UI usefulness without pretending that port-based inference is perfect.

## Non-Goals

This feature does not replace explicit metadata headers.

It should not infer Discord user id, Discord channel id, Hermes session id, or OpenClaw session id unless the route table explicitly contains those values.

It should not use arbitrary request headers as identity.

It should not perform agent optimization or routing decisions.

## Resolution Priority

Identity resolution should follow this order:

1. Explicit request headers
   - `X-Agent-Id`
   - `X-Session-Id`
   - `X-Channel`
   - `X-Channel-Id`
   - `X-Conversation-Id`
   - `X-Hermes-Session-Id`
   - `X-OpenClaw-Session-Id`
   - Discord/OpenWebUI-specific headers

2. Ingress route lookup
   - inbound host
   - inbound port
   - optional path prefix

3. Heuristic fallback
   - future only
   - disabled by default

4. Unknown

Headers always override ingress route defaults. Ingress routes fill only missing or `unknown` fields.

## Proposed Schema

Add `003_ingress_routes.sql`:

```sql
CREATE TABLE IF NOT EXISTS ingress_routes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listen_host TEXT,
  listen_port INTEGER,
  path_prefix TEXT,
  tenant_id TEXT,
  user_id TEXT,
  user_hash TEXT,
  agent_id TEXT,
  session_id TEXT,
  channel TEXT,
  channel_id TEXT,
  conversation_id TEXT,
  source TEXT NOT NULL DEFAULT 'ingress_route',
  note TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ingress_routes_lookup
  ON ingress_routes(listen_host, listen_port, path_prefix, enabled);
```

Optional uniqueness:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingress_routes_unique
  ON ingress_routes(COALESCE(listen_host, ''), COALESCE(listen_port, -1), COALESCE(path_prefix, ''));
```

## Example Route Table

```text
listen_host | listen_port | path_prefix | tenant_id | user_hash | agent_id | channel | note
127.0.0.1   | 43180       | /v1         | local     | istale    | hermes   | discord | main Hermes gateway
127.0.0.1   | 43181       | /v1         | local     | alice     | openclaw | cli     | Alice OpenClaw
127.0.0.1   | 43182       | /v1         | local     | bob       | hermes   | discord | Bob Hermes
```

Current confirmed first route:

```text
127.0.0.1:43180 /v1 -> tenant_id=local, user_hash=istale, agent_id=hermes, channel=discord
```

Confirmed deployment assumptions:

- One user/agent per port.
- All ports share `data/hub.sqlite3`.
- Use `user_hash`, not raw `user_id`.
- `channel=discord` is sufficient for the first route; no `channel_id` is required.
- Do not map `session_id` or `conversation_id` from port. Those should come from future Hermes/OpenClaw headers.
- Route management is CLI-only in the first implementation.
- Path prefix is `/v1` for all current routes.

## Context Fields

Current request context fields:

- `tenant_id`
- `user_id`
- `user_hash`
- `agent_id`
- `session_id`
- `channel`
- `channel_id`
- `conversation_id`
- `trigger_type`

Phase 2.1 should add:

- `identity_source`

Suggested values:

- `headers`
- `ingress_route`
- `mixed`
- `unknown`

If at least one field comes from headers and at least one field comes from ingress route, use `mixed`.

## Data Flow

For each incoming OpenAI-compatible request:

1. Parse explicit metadata headers as today.
2. If any identity field is missing or equals `unknown`, query `ingress_routes`.
3. Match by:
   - `request.url.hostname`
   - `request.url.port`
   - path prefix, if configured
   - `enabled=1`
4. Fill missing fields from the matched route.
5. Preserve explicit header values.
6. Store the final context in `trace_runs` and `llm_calls`.
7. Insert an `external_ids` row for the route match:
   - `source=ingress_route`
   - `key=route_id`
   - `value=<id>`
8. Insert additional `external_ids` rows for route-derived fields:
   - `source=ingress_route`
   - `key=agent_id/channel/user_hash/etc`
   - `value=<resolved value>`

## API

Add:

- `GET /api/ingress-routes`
- `POST /api/ingress-routes`
- `PATCH /api/ingress-routes/{id}`
- `DELETE /api/ingress-routes/{id}` or soft-disable with `enabled=0`

First implementation can skip public mutation APIs and provide a CLI/script if faster:

```sh
.venv312/bin/python scripts/add_ingress_route.py \
  --host 127.0.0.1 \
  --port 43180 \
  --path-prefix /v1 \
  --tenant-id local \
  --user-hash istale \
  --agent-id hermes \
  --channel discord \
  --note "main Hermes gateway"
```

## UI

Trace list should display resolved fields as it does today:

- Agent
- Channel

Trace detail should show resolution source:

```text
Identity Source: ingress_route
Route: 127.0.0.1:43180 /v1
```

Correlation panel should include ingress route rows so the operator can tell which mapping was used.

## Safety

Ingress route mapping is operational metadata, not authentication.

Do not use it for access control.

Do not assume a port proves a human identity unless the deployment model guarantees one user per port.

Prefer `user_hash` over `user_id`.

Do not store API keys, authorization headers, cookies, or tokens in route notes.

## Acceptance Tests

### Test 1: Header Wins

Given route:

```text
43180 -> agent_id=hermes, channel=discord
```

Request includes:

```text
X-Agent-Id: openclaw
X-Channel: cli
```

Expected:

- `trace_runs.agent_id=openclaw`
- `trace_runs.channel=cli`
- `identity_source=headers`

### Test 2: Route Fills Missing Values

Given route:

```text
43180 -> agent_id=hermes, channel=discord, user_hash=istale
```

Request has no metadata headers.

Expected:

- `trace_runs.agent_id=hermes`
- `trace_runs.channel=discord`
- `trace_runs.user_hash=istale`
- `identity_source=ingress_route`
- `external_ids` includes route id and route-derived values.

### Test 3: Mixed Resolution

Given route:

```text
43180 -> agent_id=hermes, channel=discord
```

Request includes:

```text
X-Session-Id: hermes-session-123
```

Expected:

- `session_id=hermes-session-123`
- `agent_id=hermes`
- `channel=discord`
- `identity_source=mixed`

### Test 4: Disabled Route

Given route is `enabled=0`.

Expected:

- route is ignored
- missing fields remain `unknown`

### Test 5: No Sensitive Values

Route note or values must not include raw API tokens. If a token-like value is submitted through future APIs/scripts, reject it or redact it.

## Implementation Effort

Estimated effort: 0.5 to 1 focused day.

Breakdown:

- Migration and repository methods: 1-2 hours.
- Request context resolver: 1-2 hours.
- External id insertion for route-derived values: 1 hour.
- Minimal CLI/script or API for route management: 1-2 hours.
- Tests and manual verification: 1-2 hours.

## Recommendation

Implement Phase 2.1 after Phase 2 correlation has been exercised with real Hermes/OpenClaw traffic.

This should be treated as a fallback layer:

```text
headers > ingress route mapping > unknown
```

The long-term target remains explicit metadata headers from Hermes/OpenClaw. Ingress route mapping helps the system become useful immediately for multi-user, multi-port deployments.
