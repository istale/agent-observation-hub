-- MEU (Memory Editing UI): per-message soft overlay stored hub-side.
-- The user's session message history (Pi's ~/.pi/agent/sessions/*.jsonl) is
-- never modified. Marks + notes are stored here keyed by session_id and the
-- 0-based index of the message inside the rendered message list (filtered to
-- entries with type='message' from Pi's session tree).
--
-- mark semantics (matches the "soft focus layer" design):
--   'active'     default. message participates as normal.
--   'background' user has flagged this as not the current focus; UI dims it.
--                A future Pi-side integration may de-emphasise it in context.
--   'stale'      retained for audit but no longer relevant. UI strikes through.
--   'hidden'     UI collapses by default; full content still loadable on click.
--
-- note: optional free-form correction or context the user wants to remember
--       alongside this message. Doesn't modify the original message.
CREATE TABLE IF NOT EXISTS session_message_overlays (
  session_id TEXT NOT NULL,
  message_index INTEGER NOT NULL,
  mark TEXT NOT NULL DEFAULT 'active',
  note TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (session_id, message_index)
);

CREATE INDEX IF NOT EXISTS idx_session_message_overlays_session ON session_message_overlays(session_id);
