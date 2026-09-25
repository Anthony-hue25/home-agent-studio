# Testing and evidence summary

Every check below is real and runnable from this repository. Nothing here is asserted without a corresponding script or a live HTTP response.

## Unit tests (no AWS credentials, no network)

| File | What it proves |
|---|---|
| `test_identity_gate.py` | `is_authorized_runtime_identity` accepts exactly the two pinned identities (the named dev IAM user, the deployed ECS task role) and rejects everything else -- wrong account, wrong/renamed role, root user, malformed input |
| `test_home_state_gateway.py` | The Home State Gateway's `apply_and_verify` genuinely performs an independent readback and only reports success when that readback confirms it |
| `test_live_planner_profile_fallback.py` | When no local named AWS CLI profile is available (the normal case for an ECS task, which authenticates via its task role), `LiveStayPlanner` falls back to the default credential chain instead of hard-failing -- and the identity gate still runs, unchanged, against whatever identity that resolves to |

Run any of them directly: `python3 test_identity_gate.py` (etc.) -- each prints PASS/FAIL per assertion and exits non-zero on any failure.

## Local regression suites

| File | What it proves |
|---|---|
| `verify_container.py` | The container starts, serves `/health`, and completes a full MCP `initialize` / `tools/call` round trip |
| `verify_gate_i_ui.py` | The product UI renders correctly and without layout defects across desktop, 768px tablet, and 375px mobile widths |
| `verify_dual_session_and_checkout.py` | Two independent guest sessions do not leak state into each other, and checkout correctly resets stay state for the next guest |

## Live-deployment verification

| File | What it proves | How to run |
|---|---|---|
| `verify_no_silent_fallback.py` | The live deployment is genuinely calling Amazon Bedrock through Strands -- not silently running on a canned/fixture backend. Asserts real provenance: `planner_backend: strands`, `provider: bedrock`, a real model ID, real Bedrock call HTTP status/request IDs, and a real deterministic-verification result | `python3 verify_no_silent_fallback.py <base-url> strands` |
| `verify_scenarios_live.py` | Replays the three hardest judge-facing behaviors end to end against a live deployment: (C) multiple simultaneous shared constraints resolved in one verified plan, with genuine rejected candidates shown; (D) a plan that goes stale when reality changes is correctly refused at activation; (E) a truly infeasible ask fails closed with no fabricated Blueprint | `python3 verify_scenarios_live.py <base-url>` |

Both were run against the live production URL as part of this submission's own verification and passed. Representative captured evidence from that run:

```
planner_backend: strands
provider: bedrock
model: amazon.nova-pro-v1:0
bedrock_calls: 2 real invocations, both HTTP 200
grounding_calls: ["discover_stay_strategies"]
strands_version: 1.56.0
deterministic_verification: PASS
```

## Live protocol compliance

A direct, read-only MCP `initialize` handshake against the live endpoint returns:

```json
{"protocolVersion":"2025-11-25","serverInfo":{"name":"adaptive-stay-alexa-product","version":"1.27.0"}}
```

confirming the deployed server negotiates the Alexa+/MCP track's stated minimum acceptable protocol version (2025-11-25) over Streamable HTTP (`Content-Type: text/event-stream`, `Mcp-Session-Id` header present).

## What is explicitly *not* claimed

- No production Alexa+ device SDK integration or certification. The Alexa+ experience here is the browser-based simulation the track's own rules describe as acceptable ("simulate Alexa+ experience using any AI/agentic tool").
- No physical home hardware is connected; property/room state (thermal zones, hot water capacity, guest bindings) is a deterministic simulated model, not measured physical behavior.
- No independent third-party security audit or formal verification has been performed; "fail-closed" and "independent readback" describe this codebase's own tested logic, not an externally certified guarantee.
