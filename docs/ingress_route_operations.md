# Ingress Route Operations

Use ingress routes when Hermes/OpenClaw clients do not yet send Agent Observation Hub metadata headers.

Resolution order:

```text
explicit headers > ingress route mapping > unknown
```

For the current deployment, use one local port per user/agent and one shared SQLite database.

## Current Route

```text
43180 = istale / hermes / discord
```

Add it with:

```sh
.venv312/bin/python scripts/add_ingress_route.py \
  --db data/hub.sqlite3 \
  --host 127.0.0.1 \
  --port 43180 \
  --path-prefix /v1 \
  --tenant-id local \
  --user-hash istale \
  --agent-id hermes \
  --channel discord \
  --note "istale main Hermes Discord gateway"
```

## Agent Guidance

When helping operate this project:

- Prefer explicit Hermes/OpenClaw headers when available.
- Use ingress routes only as fallback.
- Do not store raw Discord user ids unless the user explicitly asks.
- Prefer `user_hash`.
- Do not store API keys, bearer tokens, cookies, or secrets in route notes.
- Keep `path_prefix=/v1` unless the deployment changes.
- Keep all local ports writing to `data/hub.sqlite3` unless the user asks for per-user DB isolation.

## Verification

After adding a route, send a request through the mapped port without metadata headers. The run should show:

```text
agent_id=hermes
channel=discord
user_hash=istale
identity_source=ingress_route
```

The trace correlation panel should include:

```text
source=ingress_route
key=route_id
key=agent_id
key=channel
key=user_hash
```
