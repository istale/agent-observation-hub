# LiteLLM Optional Upstream Spec

## Purpose

Agent Observation Hub must work in production environments where LiteLLM is not installed, not approved, or explicitly banned. AOH's required upstream contract is OpenAI-compatible HTTP, not LiteLLM.

## Decision

LiteLLM is optional.

AOH does not require:

```text
pip install litellm
```

AOH does not import the LiteLLM Python package at runtime. Existing `x-litellm-*` handling is only optional response-header correlation capture when an upstream gateway happens to return those headers.

## Supported Topologies

Direct provider mode:

```text
Hermes / OpenClaw
  -> Agent Observation Hub: http://127.0.0.1:43180/v1
  -> OpenAI-compatible provider: https://api.minimax.io/v1
```

Optional LiteLLM mode:

```text
Hermes / OpenClaw
  -> Agent Observation Hub: http://127.0.0.1:43180/v1
  -> LiteLLM Proxy: http://127.0.0.1:4000/v1
  -> OpenAI-compatible provider
```

## Production Requirement

Production deployments may ban LiteLLM. In that case:

- do not install LiteLLM
- point `UPSTREAM_OPENAI_BASE_URL` directly at the approved OpenAI-compatible provider
- keep using `ingress_routes` for user/agent/channel lookup
- use subject and trace analysis bundles as usual

## Observation Invariants

Direct provider mode must still capture:

- trace/run/LLM call IDs
- user/agent/channel identity from `ingress_routes`
- raw request payload
- raw response payload or stream chunks
- usage tokens when present
- latency
- HTTP status
- analysis bundle data

LiteLLM-specific correlations are best-effort only. Missing LiteLLM headers must never be treated as an error.

## Test Guard

The repository contains tests that prevent accidental introduction of a LiteLLM package/runtime dependency:

```text
tests/test_no_litellm_dependency.py
```
