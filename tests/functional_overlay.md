# Functional regression test: Memory Editing UI / Overlay injection

This document describes 8 user-level scenarios for the overlay feature
(混合方案: system-prepend annotation + hidden tombstone). Each scenario
is **AI-agent-runnable**: every assertion maps to a hub HTTP endpoint
so no SQLite or filesystem access is needed.

If you are an AI agent picking this up later: read this top-to-bottom,
run the scenarios in order, and gate each one on the documented API
response.

## Prerequisites

- Hub running at `http://127.0.0.1:43180`
- Pi CLI built: `node /Users/istale/Documents/pi-agent-obervation/repos/pi/packages/coding-agent/dist/cli.js`
- An LLM endpoint reachable (default MiniMax via the hub)
- Pi run from the SAME cwd it was created in (otherwise pi prompts
  "Fork into current directory? [y/N]" and blocks)

## Constants used below

| Variable | Value |
|---|---|
| `HUB` | `http://127.0.0.1:43180` |
| `PI_JS` | `/Users/istale/Documents/pi-agent-obervation/repos/pi/packages/coding-agent/dist/cli.js` |
| `MODEL` | `minimax-via-hub/MiniMax-M2.7` |

## Conventions

- "ISO_NOW" = `python3 -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())"`
- Always `sleep 2` after running pi so the hub tailer ingests events
- Always run pi from the same cwd a session was created in

## API endpoints used for assertions

| Endpoint | Purpose |
|---|---|
| `GET /api/assertions/overlay/{sid}` | DB + snapshot file state for session |
| `GET /api/assertions/overlay-applied/{sid}?since=ISO` | list overlay_applied events (latest N) |
| `GET /api/assertions/payload-inspect/{tid}` | structured analysis of the LLM HTTP payload |
| `GET /api/assertions/session-summary/{sid}?since=ISO` | composite: overlay + per-model-call inspection |

---

## Scenario 1 — Baseline (no marks → no overhead)

**Goal**: a fresh session with no marks does not trigger any overlay machinery.

**Setup**:
1. Generate a unique session id `S1_SID` (Pi will create the file).
2. Record `SINCE = ISO_NOW`.

**Action**:
```
cd /any/dir
node $PI_JS -p "say baseline_one" --session-id $S1_SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$S1_SID?since=$SINCE`:
- `overlay.snapshot.exists` == `false`
- `overlay.db.non_active_count` == `0`
- All `model_calls[].overlay_applied.fired` == `false`

---

## Scenario 2 — Mark stale → annotation appears in system prompt

**Goal**: marking a message as stale causes the next resume to include a STALE annotation in the system prompt.

**Setup**:
1. Use the S1 session id (or create a new one).
2. Mark message at index 0 stale.

**Action**:
```
curl -X POST $HUB/api/sessions/$SID/messages/0/mark \
  -H 'Content-Type: application/json' \
  -d '{"mark":"stale"}'

SINCE=ISO_NOW
sleep 1
cd <original-cwd>
node $PI_JS -p "What did I just say?" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$SID?since=$SINCE`:
- `overlay.snapshot.exists` == `true`
- `overlay.consistent` == `true`
- Latest `model_calls[-1].overlay_applied.fired` == `true`
- Latest `model_calls[-1].overlay_applied.stale_count` >= 1
- Latest `model_calls[-1].payload_inspection.annotation_in_system_prompt` == `true`
- `"STALE"` in `model_calls[-1].payload_inspection.annotation_mentions`

---

## Scenario 3 — Hidden mark → tombstone in payload + tool pairing intact

**Goal**: marking a toolResult as hidden replaces its content with a tombstone but keeps tool_call_id so the conversation history doesn't break.

**Setup**:
1. Create a session with a tool call:
   ```
   cd /Users/istale/Documents/pi-agent-obervation/repos/pi
   node $PI_JS -p "Run 'echo hi_for_s3' in bash and tell me the output." --model $MODEL
   ```
2. Find the resulting `session_id` by reading the latest jsonl in `~/.pi/agent/sessions/`.
3. Use `GET /api/sessions/$SID/messages` to find the index `i` where `role == "toolResult"`.
4. Mark that index hidden.

**Action**:
```
curl -X POST $HUB/api/sessions/$SID/messages/$i/mark \
  -H 'Content-Type: application/json' \
  -d '{"mark":"hidden"}'

SINCE=ISO_NOW
sleep 1
cd /Users/istale/Documents/pi-agent-obervation/repos/pi   # SAME cwd
node $PI_JS -p "summarize what tool ran" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$SID?since=$SINCE`:
- Latest `model_calls[-1].overlay_applied.hidden_count` >= 1
- Latest `model_calls[-1].payload_inspection.tombstoned_count` >= 1
- `model_calls[-1].payload_inspection.tool_pairing_intact` == `true`
- For each entry in `model_calls[-1].payload_inspection.tombstoned`, if `role == "tool"` then `tool_call_id != null`.

---

## Scenario 4 — Revert to active deletes the snapshot

**Goal**: changing the last non-active mark back to active deletes the snapshot file and stops emitting overlay events.

**Setup**: use the S2 session (or any session with exactly one non-active mark).

**Action**:
```
curl -X POST $HUB/api/sessions/$SID/messages/0/mark -d '{"mark":"active"}'
sleep 1
SINCE=ISO_NOW
cd <original-cwd>
node $PI_JS -p "say final" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$SID?since=$SINCE`:
- `overlay.snapshot.exists` == `false`
- All `model_calls[].overlay_applied.fired` == `false`

---

## Scenario 5 — Multi-mark (stale + background coexist)

**Goal**: multiple marks of different kinds appear correctly in the snapshot and annotation.

**Setup**:
1. Create a fresh session via `pi -p ...`.
2. Use `GET /api/sessions/$SID/messages` to confirm `>= 2` messages.
3. Mark index 0 stale, index 1 background.

**Action**:
```
SINCE=ISO_NOW
sleep 1
cd <original-cwd>
node $PI_JS -p "what now" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$SID?since=$SINCE`:
- `overlay.snapshot.content.overlays` contains both `{mark:"stale", index:0}` and `{mark:"background", index:1}`
- Latest `model_calls[-1].overlay_applied.stale_count` >= 1
- Latest `model_calls[-1].overlay_applied.background_count` >= 1
- Latest `payload_inspection.annotation_mentions` contains both `"STALE"` and `"BACKGROUND"`

---

## Scenario 6 — Note attached to a mark surfaces in annotation

**Goal**: a user-typed note on a marked message is included in the system-prompt annotation.

**Setup**: from S5 (any marked message exists). Pick a unique sentinel string for the note, e.g. `FUNCTEST_NOTE_MARKER_XYZ`.

**Action**:
```
curl -X POST $HUB/api/sessions/$SID/messages/0/note \
  -d '{"note":"FUNCTEST_NOTE_MARKER_XYZ"}'

SINCE=ISO_NOW
sleep 1
cd <original-cwd>
node $PI_JS -p "what now" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/payload-inspect/$LATEST_TRACE_ID`
(get latest trace from `session-summary.model_calls[-1].trace_id`):
- Fetch the actual payload by re-querying the trace; expect `FUNCTEST_NOTE_MARKER_XYZ` to appear in the first system message.

Or simpler — fetch the snapshot JSON and confirm the note round-trips:
- `GET /api/assertions/overlay/$SID` → `db.overlays[0].note == "FUNCTEST_NOTE_MARKER_XYZ"`

---

## Scenario 7 — Kill switch (`AOH_OVERLAY_DISABLE=1`)

**Goal**: setting `AOH_OVERLAY_DISABLE=1` on the Pi process disables the entire overlay mechanism even with marks present.

**Setup**: any session with at least one non-active mark.

**Action**:
```
SINCE=ISO_NOW
sleep 1
cd <original-cwd>
AOH_OVERLAY_DISABLE=1 node $PI_JS -p "kill switch test" --session $SID --model $MODEL
sleep 2
```

**Assert** via `GET /api/assertions/session-summary/$SID?since=$SINCE`:
- All `model_calls[].overlay_applied.fired` == `false`
- (`overlay.snapshot.exists` is still `true` — the marks are kept; we just didn't read them this turn.)

---

## Scenario 8 — Trace page renders overlay_applied card

**Goal**: when overlay fires, the trace detail page shows an `overlay_applied` card with the right counts and a link to Memory Editing.

**Setup**: any trace where overlay fired (e.g. from S2/S3/S5).

**Action**:
```
TID = session-summary.model_calls[-1].trace_id
```

**Assert** by fetching `GET /traces/$TID` (HTML) and inspecting:
- substring `class="agent-event agent-event-overlay_applied"` appears
- substring `🗂 Overlay 已套用` appears
- substring `🗂 Memory Editing ↗` appears
- the mark badges from `model_calls[-1].overlay_applied` (e.g. `mark-stale`, `mark-hidden`) appear

This is the only scenario that touches HTML (because the assertion is
"the page renders"). For full structural checks, prefer the
`session-summary` endpoint.

---

## Running this whole battery

There is no automated runner committed yet — the scenarios are
imperative steps an AI agent walks through. Future work: emit a
`POST /api/regression/run` endpoint that orchestrates everything
internally if pi can be invoked from inside the hub process.

## What this catches

- Snapshot file write / delete on mark changes
- Overlay reaches Pi at convertToLlm time
- Annotation enters system prompt correctly
- Hidden replaces content WITHOUT breaking tool pairing
- Multiple marks of different kinds coexist
- Notes propagate end-to-end
- Kill switch works
- UI surfaces the result

## What this does NOT catch

- Conversation flow correctness (model's answer quality)
- Pi resume edge cases (cross-cwd, forked branches)
- Mid-stream mark changes (race conditions while pi is generating)
- Snapshot corruption recovery
- Pi without hub running (offline mode behaviour)

If you want regression coverage on those, add new scenarios + new
`/api/assertions/*` endpoints as needed.
