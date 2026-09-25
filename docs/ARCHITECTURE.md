# Architecture

Three lanes: **Amazon-run services**, the **open MCP standard**, and **Adaptive Stay's own logic**.

```
[Guest, natural language]
      |
      v
[Alexa+ simulated conversational surface]
   (browser UI; stands in for an Alexa+ device per the track's documented
    "simulate via any agentic tool" allowance)
      |
      |  MCP over Streamable HTTP, protocol version 2025-11-25, session-scoped
      v
[adaptive-stay-alexa-product MCP server]
   (official `mcp` Python SDK 1.27.0 / FastMCP, served by uvicorn/Starlette,
    running on AWS ECS Express Gateway)
      |
      +--> dream_stay / get_dream_status --> [LiveStayPlanner]
      |                                           |
      |                                    strands.Agent + read-only grounding tools
      |                                           v
      |                                   [Amazon Bedrock -- Nova Pro]
      |                                           |
      |                                    structured option proposals
      |                                           v
      |                              [Deterministic Dream verifier]
      |                    (evaluate_option; bounded rejected-candidate list;
      |                     fails closed to NO_VERIFIED_STRATEGY if nothing passes --
      |                     never fabricates a pass)
      |                                           |
      |                                           v
      +--> get_stay_blueprint  <-----------  [Stay Blueprint]
      |            (is_blueprint_current() re-checked against current
      |             reality on every read, not cached as "still good")
      |
      +--> activate_stay  --refuses if stale-->  [Home State Gateway]
      |                                             (apply_and_verify: independent
      |                                              readback of what actually
      |                                              happened, not the plan's own
      |                                              self-report)
      |                                                     |
      |                                                     v
      +--> checkout_stay                          [Simulated property state]
                                                    (rooms, thermal zones, hot
                                                     water, guest/preference
                                                     bindings)

  Side channel (demo-only, judge-visible, non-authoritative):
  [Experience Lab: POST /api/lab/load] --sets starting state for Scenarios A-F-->
      (same MCP tool surface above; never mutates Dream/Blueprint state directly)
```

## Component notes

**Identity gate.** `LiveStayPlanner` will only drive a real, billable Bedrock call from two pinned AWS identities (a named local development IAM user, or the deployed ECS task role's assumed-role identity). Both are literal in source, not environment- or config-supplied, so a misconfigured deploy cannot silently widen who can trigger real model calls from the public deployment.

**Fail-closed by construction.** The Dream verifier's job is to prove a candidate plan actually resolves the current constraints, deterministically, independent of what the model claimed. If no candidate verifies, the job ends in `NO_VERIFIED_STRATEGY` with the genuinely-tried-and-rejected candidates recorded (bounded to a fixed limit) — there is no code path that fabricates a passing Blueprint when verification fails.

**Staleness is re-checked, not cached.** A Stay Blueprint isn't "verified once, trusted forever." `get_stay_blueprint` recomputes `is_blueprint_current()` against the live property state, topology, and preference catalog on every call. `activate_stay` calls the same check and raises `"stale Stay Blueprint"` rather than activating a plan that no longer matches reality.

**Independent readback, not self-reported success.** `activate_stay` doesn't consider a Blueprint "active" because the code that applied it says so. The Home State Gateway's `apply_and_verify` performs the write and then independently reads the resulting state back; `activate_stay` only reports `VERIFIED_ACTIVE` if that readback actually matches.

**Experience Lab is a demo convenience, not a hidden authority path.** `/api/lab/load` sets up the starting stay/constraint state for each judge-facing scenario (A–F) so a scenario can be demonstrated on demand. It never touches Dream or Blueprint state directly — every planner-facing step still goes through the same MCP tool surface a real Alexa+ client would use, so the scenario is a genuine exercise of the product, not a scripted fake.

## Deployment

The exact `Dockerfile` in this repository builds the image running at the live demo URL, deployed to AWS ECS via the Express Gateway service type, fronted by its own managed HTTPS endpoint. `PLANNER_KIND=Live` is set on the live deployment so it runs the real Bedrock/Strands path; `verify_no_silent_fallback.py` (see `docs/TESTING_EVIDENCE.md`) is how that claim is checked, not just asserted.
