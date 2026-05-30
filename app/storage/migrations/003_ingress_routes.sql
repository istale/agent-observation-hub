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

CREATE UNIQUE INDEX IF NOT EXISTS idx_ingress_routes_unique
  ON ingress_routes(COALESCE(listen_host, ''), COALESCE(listen_port, -1), COALESCE(path_prefix, ''));
