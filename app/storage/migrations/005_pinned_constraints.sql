CREATE TABLE IF NOT EXISTS pinned_constraints (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pinned_constraints_scope ON pinned_constraints(scope, created_at);
