CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  session_id TEXT,
  event_seq INTEGER,
  stage TEXT NOT NULL,
  source_module TEXT,
  ts TEXT NOT NULL,
  payload_ref TEXT,
  payload_inline TEXT,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_events_trace ON agent_events(trace_id, event_seq);
CREATE INDEX IF NOT EXISTS idx_agent_events_stage ON agent_events(stage, ts);
