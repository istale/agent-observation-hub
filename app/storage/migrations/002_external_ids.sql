CREATE TABLE IF NOT EXISTS external_ids (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  llm_call_id TEXT,
  source TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  value_hash TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_ids_trace_id ON external_ids(trace_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_run_id ON external_ids(run_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_llm_call_id ON external_ids(llm_call_id);
CREATE INDEX IF NOT EXISTS idx_external_ids_lookup ON external_ids(source, key, value);
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_ids_unique
  ON external_ids(trace_id, COALESCE(run_id, ''), COALESCE(llm_call_id, ''), source, key, value);
