# Phase 2 Evaluation

## Readiness

Phase 2 is ready to start. Phase 1 now has:

- Working OpenAI-compatible gateway on `43180`.
- Non-stream and stream capture.
- Local SQLite trace store.
- Raw archive files.
- Redacted API/UI by default.
- Run finalization for new calls.
- Maintenance backfill for old stale `running` rows.
- Readable UI response display and Taipei time display.

The main gap Phase 2 should close is correlation. Current traces can show what happened inside the gateway, but they do not yet reliably answer which external agent session, LiteLLM call, provider request, or channel conversation produced a trace.

## Value

Phase 2 directly supports the project priority:

> Collect enough information to analyze agent-system and model behavior, then use that information to adjust agent usage.

Correlation ids turn isolated LLM calls into analyzable agent runs. Without them, debugging requires manually matching timestamps across Hermes/OpenClaw/LiteLLM/provider logs. With them, the hub can become the local index for a whole agent interaction.

## Capability Impact

| Capability | Current | After Phase 2 |
| --- | --- | --- |
| Find trace by local trace id | Yes | Yes |
| Find trace by Hermes session id | No | Yes |
| Find trace by OpenClaw session id | No | Yes |
| Find trace by LiteLLM call id | Header visible in response, not persisted | Yes |
| Find trace by provider request id | Header visible in response, not persisted | Yes |
| Explain `agent unknown` | Partially | Mostly fixed when clients send headers |
| Cross-check gateway vs LiteLLM logs | Manual | Direct lookup |
| Cross-check provider errors | Manual | Direct lookup by provider request id |

## Evaluation Criteria

Phase 2 should be accepted only if these are true:

1. A Hermes request with metadata headers creates external id rows.
2. A LiteLLM response with `x-litellm-call-id` creates an external id row.
3. MiniMax provider ids from response headers create external id rows.
4. `/api/traces/{trace_id}/correlations` returns all ids for a trace.
5. `/api/correlations?source=hermes&key=session_id&value=...` finds the trace.
6. Trace UI shows correlations clearly.
7. Authorization/cookie/API key values are not saved as correlations.
8. Duplicate requests or retries do not create duplicate external id rows.
9. Existing Phase 1 tests still pass.

## Effort Estimate

Recommended estimate: 1 to 1.5 focused days.

Confidence: medium-high.

Reasons:

- SQLite/repository/API/UI patterns already exist.
- Header data is already available in gateway request/response objects.
- The feature is additive and does not require proxy behavior changes.
- The only uncertainty is exact Hermes/OpenClaw metadata header names in real traffic.

## Risks

Security risk:

- Correlation values may include user or channel identifiers.
- Mitigation: strict allowlist, no auth/cookie capture, prefer user hash, document local-only behavior.

Data quality risk:

- Hermes/OpenClaw may not send session headers yet.
- Mitigation: support both generic headers and client-specific headers; document recommended headers.

Provider variance risk:

- LiteLLM/provider header names can vary by upstream.
- Mitigation: persist known LiteLLM/MiniMax headers first; add observed mappings as needed.

UI scope risk:

- Correlation panel could grow into a dashboard too early.
- Mitigation: keep it as a compact key/value table on trace detail only.

## Recommendation

Proceed with Phase 2 next.

Build it in this order:

1. Migration and repository support for `external_ids`.
2. Gateway capture of inbound request metadata.
3. Gateway capture of LiteLLM/provider response headers.
4. Correlation APIs.
5. Trace UI correlation panel.
6. Manual Hermes/OpenClaw smoke test with real headers.

Do not start OpenInference/OTEL, importer enrichment, or tool call capture until Phase 2 correlation is working with real Hermes/OpenClaw traffic.
