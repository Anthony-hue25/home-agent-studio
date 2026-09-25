# Adaptive Stay

**Two guests can each be right about what they want, and still be wrong together.**

Adaptive Stay is an Alexa+-style, MCP-native assistant for a shared guest stay. A guest states a preference in natural language; the assistant *dreams* the stay forward with a real Amazon Bedrock (Nova Pro) call orchestrated by the Strands Agents SDK, looking for a plan that resolves every guest's constraints at once — including genuinely conflicting ones (two guests wanting different temperatures in a shared thermal zone, two guests wanting hot water from one limited system at the same time). It shows its work: options it tried and rejected, and why. Only a deterministically re-verified plan becomes a **Stay Blueprint**, and that Blueprint is re-checked for staleness on every read — if the world changed since it was made, activation is refused rather than silently proceeding on stale information. When a plan does activate, an independent **Home State Gateway** reads the result back rather than trusting the plan's own report of success.

Built for the **Alexa+ / MCP track** of the [Build, Ship, Shape: Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/), and entered in the **AWS Builder** mini-challenge.

**Live demo:** https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws — no login required. See [`docs/JUDGE_QUICKSTART.md`](docs/JUDGE_QUICKSTART.md) for a 60-second walkthrough.

## Why this exists

Most "AI for the home" demos handle the easy case: one person, one preference, one action. Real shared stays aren't like that. Guests disagree. Physical systems have shared limits. And by the time an AI has planned something, the world may have already changed underneath the plan. Adaptive Stay is built around a simple idea: an assistant should rather say "I can't verify that anymore" than quietly do the wrong thing.

## What it does

1. A guest expresses a preference (e.g. "I run cold, I want zone A cooler").
2. `dream_stay` asks a real Bedrock-backed Strands agent to propose a strategy, then **deterministically, independently re-verifies** every candidate before accepting it — the model proposes, it never grades its own homework.
3. If nothing verifiably resolves every constraint, the job fails closed (`NO_VERIFIED_STRATEGY`) with the genuinely rejected candidates shown — never a fabricated pass.
4. A verified plan becomes a **Stay Blueprint**. Every time it's read back (`get_stay_blueprint`), it's re-checked against current reality; if anything changed, it reports `is_current: false`.
5. `activate_stay` refuses to activate a stale Blueprint (`"stale Stay Blueprint"`), and on a successful activation, the **Home State Gateway** applies the change and independently reads the result back — activation only reports `VERIFIED_ACTIVE` if the readback actually confirms it.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full flow. In short:

```
Guest (natural language)
  -> Alexa+ simulated conversational surface (browser UI)
  -> MCP over Streamable HTTP, protocol version 2025-11-25
  -> adaptive-stay-alexa-product MCP server (official `mcp` SDK 1.27.0 / FastMCP, on AWS ECS Express Gateway)
  -> LiveStayPlanner: strands.Agent + Amazon Bedrock (Nova Pro)
  -> deterministic Dream verifier (fails closed, bounds rejected candidates)
  -> Stay Blueprint (re-checked for staleness on every read)
  -> Home State Gateway (apply + independent readback, not self-reported success)
```

## Running it

```bash
pip install -r requirements.txt
python app_server.py
```

The server listens on `PORT` (default `8080`) and serves the product UI at `/`, health at `/health`, and the MCP endpoint at `/mcp` (Streamable HTTP). Set `PLANNER_KIND=Live` with valid AWS credentials for real Bedrock/Strands planning, or leave it unset to use the deterministic fixture planner (no AWS credentials needed) for local development.

A `Dockerfile` is included; the live demo runs this exact image on AWS ECS Express Gateway.

## Tests and verification

All of the following are real, runnable, and part of this repository — see [`docs/TESTING_EVIDENCE.md`](docs/TESTING_EVIDENCE.md) for what each one proves and how to reproduce it:

- `test_identity_gate.py`, `test_home_state_gateway.py`, `test_live_planner_profile_fallback.py` — unit tests, no AWS credentials needed
- `verify_container.py`, `verify_gate_i_ui.py`, `verify_dual_session_and_checkout.py` — local regression suites
- `verify_no_silent_fallback.py <base-url> strands` — proves a live deployment is really calling Bedrock/Strands, not silently running on a canned fixture
- `verify_scenarios_live.py <base-url>` — replays the three hardest judge-facing scenarios (simultaneous conflicts, stale-Blueprint refusal, fail-closed on an infeasible ask) against a live deployment end to end

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — full component/data-flow diagram and description
- [`docs/JUDGE_QUICKSTART.md`](docs/JUDGE_QUICKSTART.md) — try the live demo in under 60 seconds
- [`docs/TESTING_EVIDENCE.md`](docs/TESTING_EVIDENCE.md) — what's proven, and exactly how to reproduce each proof
- [`docs/AWS_BUILDER_MINI_CHALLENGE.md`](docs/AWS_BUILDER_MINI_CHALLENGE.md) — AWS services used and how
- [`docs/FRICTION_LOG.md`](docs/FRICTION_LOG.md) — real friction encountered building and deploying this
- [`docs/PRODUCT_FEEDBACK.md`](docs/PRODUCT_FEEDBACK.md) — required hackathon product-feedback answers

## License

MIT — see [`LICENSE`](LICENSE).

## Author

Anthony Doodnath
