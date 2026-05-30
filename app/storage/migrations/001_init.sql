CREATE TABLE IF NOT EXISTS trace_runs (
  run_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  tenant_id TEXT,
  user_id TEXT,
  user_hash TEXT,
  agent_id TEXT,
  session_id TEXT,
  channel TEXT,
  channel_id TEXT,
  conversation_id TEXT,
  trigger_type TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  input_summary TEXT,
  output_summary TEXT,
  failure_type TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trace_events (
  event_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  parent_event_id TEXT,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ok',
  severity TEXT NOT NULL DEFAULT 'info',
  payload_json TEXT,
  payload_ref TEXT,
  redaction_level TEXT NOT NULL DEFAULT 'redacted',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llm_calls (
  llm_call_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  tenant_id TEXT,
  user_id TEXT,
  user_hash TEXT,
  agent_id TEXT,
  session_id TEXT,
  channel TEXT,
  conversation_id TEXT,
  provider TEXT,
  upstream_base_url TEXT,
  model TEXT,
  endpoint TEXT NOT NULL,
  is_stream INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'running',
  http_status INTEGER,
  error_type TEXT,
  error_message TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  total_tokens INTEGER,
  request_ref TEXT,
  response_ref TEXT,
  response_chunks_ref TEXT,
  redaction_level TEXT NOT NULL DEFAULT 'raw_local',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tool_calls (
  tool_call_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  run_id TEXT,
  parent_llm_call_id TEXT,
  tool_name TEXT NOT NULL,
  tool_kind TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'running',
  error_type TEXT,
  error_message TEXT,
  input_ref TEXT,
  output_ref TEXT,
  output_summary TEXT,
  sensitivity_level TEXT NOT NULL DEFAULT 'unknown',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trace_runs_trace_id ON trace_runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id ON trace_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_trace_id ON llm_calls(trace_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_run_id ON llm_calls(run_id);
