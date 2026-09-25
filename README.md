# Adaptive Stay

**Two guests can each be right about what they want, and still be wrong together.**

Adaptive Stay is an MCP-native assistant for a shared guest stay, built for the **Alexa+ / MCP track** of the [Build, Ship, Shape: Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/) and demonstrated through a **simulated Alexa+-style conversational surface** (a browser UI standing in for an Alexa+ device, exactly as the track's own rules permit — see "Track eligibility" below). In the simulator, a guest picks a preference from a small set of labeled choices (each captioned with the words a real Alexa+ session would use for the same request, e.g. "Dream this stay"); the assistant then *dreams* the stay forward with a real Amazon Bedrock (Nova Pro) call orchestrated by the Strands Agents SDK, looking for a plan that resolves every guest's constraints at once — including genuinely conflicting ones (two guests wanting different temperatures in a shared thermal zone, two guests wanting hot water from one limited system at the same time). It shows its work: options it tried and rejected, and why. Only a deterministically re-verified plan becomes a **Stay Blueprint**, and that Blueprint is re-checked for staleness on every read — if the world changed since it was made, activation is refused rather than silently proceeding on stale information. When a plan does activate, an independent **simulated Home State Gateway** reads the result back rather than trusting the plan's own report of success — no physical hardware is involved at any point; the property, its rooms, and its systems are a deterministic simulated model.

Also entered in the **AWS Builder** mini-challenge (Amazon Bedrock, Strands Agents SDK, and AWS ECS Express Gateway — see [`docs/AWS_BUILDER_MINI_CHALLENGE.md`](docs/AWS_BUILDER_MINI_CHALLENGE.md)).

**The real technical chain, end to end:** Browser (simulated Alexa+ / multimodal surface) → MCP → Strands → Bedrock → deterministic Dream → Blueprint → simulated Home State Gateway → readback verification.

```
Browser (simulated Alexa+ / multimodal surface)
  -> MCP (Streamable HTTP, protocol 2025-11-25)
  -> Strands (agent orchestration)
  -> Bedrock (Nova Pro inference)
  -> deterministic Dream (independent re-verification, fails closed)
  -> Stay Blueprint (staleness re-checked on every read)
  -> simulated Home State Gateway (apply + independent readback)
  -> readback verification (VERIFIED_ACTIVE only if the readback actually matches)
```

**Live demo:** https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws — no login required. See [`docs/JUDGE_QUICKSTART.md`](docs/JUDGE_QUICKSTART.md) for a 60-second walkthrough.

## Track eligibility

The Alexa+ / MCP track's own rules state that a submission may "simulate Alexa+ experience using any AI/agentic tool without specific framework requirements." This project takes the stronger path available under that allowance: the conversational surface is a browser-based simulation (no production Alexa+ device SDK or certification is claimed — see `docs/TESTING_EVIDENCE.md`), but behind it sits a real MCP server built on the official `mcp` Python SDK, negotiating Streamable HTTP transport at **protocol version 2025-11-25** — the track's own stated minimum — against a live public deployment. That negotiation was verified directly against the running server, not assumed:

```json
{"protocolVersion":"2025-11-25","serverInfo":{"name":"adaptive-stay-alexa-product","version":"1.27.0"}}
```

## Why this exists

Most "AI for the home" demos handle the easy case: one person, one preference, one action. Real shared stays aren't like that. Guests disagree. Physical systems have shared limits. And by the time an AI has planned something, the world may have already changed underneath the plan. Adaptive Stay is built around a simple idea: an assistant should rather say "I can't verify that anymore" than quietly do the wrong thing.

## Impact: why a property operator, not just a guest, would want this

The guest-facing story is the demo, but the harder problem it solves is the property operator's: two guests submitting conflicting climate or hot-water requests today usually means either a manual staff intervention, an unresolved complaint, or — worse — both requests get applied naively and a shared system (one hot-water tank, one thermal-zone controller) gets pushed past what it can actually deliver. Adaptive Stay's deterministic Dream layer exists specifically to catch that *before* anything is sent to a physical system, and its independent readback exists so an operator has a real, checkable record of what was verified and actually applied — not just what an assistant claims it did. For a property operator, that's fewer incompatible demands applied to shared systems, fewer staff escalations, and an audit trail (Blueprint + readback result) that can settle a guest dispute after the fact. None of this requires trusting the model's own account of success: every activation this system reports is independently re-checked, which is exactly the property of a system worth putting in front of hundreds of stays rather than one demo.

## What it does

1. A guest picks a preference from the simulator's labeled choices (e.g. a button labeled "Cooler" for a thermal preference) -- not by typing or speaking an open-ended request.
2. `dream_stay` asks a real Bedrock-backed Strands agent to propose a strategy, then **deterministically, independently re-verifies** every candidate before accepting it — the model proposes, it never grades its own homework.
3. If nothing verifiably resolves every constraint, the job fails closed (`NO_VERIFIED_STRATEGY`) with the genuinely rejected candidates shown — never a fabricated pass.
4. A verified plan becomes a **Stay Blueprint**. Every time it's read back (`get_stay_blueprint`), it's re-checked against current (simulated) reality; if anything changed, it reports `is_current: false`.
5. `activate_stay` refuses to activate a stale Blueprint (`"stale Stay Blueprint"`), and on a successful activation, the **simulated Home State Gateway** applies the change to the simulated property state and independently reads the result back — activation only reports `VERIFIED_ACTIVE` if the readback actually confirms it.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full flow, including the Experience Lab demo side-channel and the identity gate. In short:

```
Guest (picks from the simulator's labeled choices)
  -> simulated Alexa+ / multimodal surface (browser UI)
  -> MCP over Streamable HTTP, protocol version 2025-11-25
  -> adaptive-stay-alexa-product MCP server (official `mcp` SDK 1.27.0 / FastMCP, on AWS ECS Express Gateway)
  -> LiveStayPlanner: strands.Agent + Amazon Bedrock (Nova Pro)
  -> deterministic Dream verifier (fails closed, bounds rejected candidates)
  -> Stay Blueprint (re-checked for staleness on every read)
  -> simulated Home State Gateway (`SimulatedHomeStateGateway`: apply + independent readback, not self-reported success)
  -> simulated property state (rooms, thermal zones, hot water — no physical hardware)
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
- [`docs/TESTING_EVIDENCE.md`](docs/TESTING_EVIDENCE.md) — what's proven, and exactly how to reproduce each proof, plus what's explicitly not claimed
- [`docs/AWS_BUILDER_MINI_CHALLENGE.md`](docs/AWS_BUILDER_MINI_CHALLENGE.md) — AWS services used and how
- [`docs/FRICTION_LOG.md`](docs/FRICTION_LOG.md) — real friction encountered building and deploying this
- [`docs/PRODUCT_FEEDBACK.md`](docs/PRODUCT_FEEDBACK.md) — required hackathon product-feedback answers

## License

MIT — see [`LICENSE`](LICENSE).

## Author

Anthony Doodnath
