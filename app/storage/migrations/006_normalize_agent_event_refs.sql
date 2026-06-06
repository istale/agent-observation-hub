-- Strip leading "raw/" from agent_events.payload_ref written by earlier
-- versions of the ingester. /api/raw/{ref} expects paths relative to
-- data_dir/raw (matching the convention used by llm_calls.request_ref).
UPDATE agent_events
SET payload_ref = SUBSTR(payload_ref, 5)
WHERE payload_ref LIKE 'raw/%';
