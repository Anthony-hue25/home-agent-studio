# Judge quick-start (about 60 seconds)

**Live URL:** https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws — no login, no credentials, nothing to install.

1. Open the URL. You'll land on the Adaptive Stay browser experience — the **simulated Alexa+ conversational surface** described in `docs/ARCHITECTURE.md` (a browser UI standing in for an Alexa+ device; no production Alexa+ deployment is involved). Session bootstrap happens automatically on load.
2. Use the **Experience Lab** toggle (floating button) to load one of the six judge-facing scenarios (A–F). The two most interesting for judging in one minute:
   - **Scenario C — multiple simultaneous shared constraints.** Two guests want conflicting thermal-zone temperatures *and* two guests want hot water from a shared, limited (simulated) system, at the same time. Ask the assistant to plan the stay: it will show you real options it tried and rejected before landing on the one plan that resolves both conflicts at once.
   - **Scenario D — reality changed after the plan was made.** A verified plan exists; then a guest's preference genuinely changes underneath it. Try to activate anyway: the assistant refuses, correctly, because the plan is now stale — it does not silently activate an outdated plan.
3. To see the fail-closed path directly: **Scenario E — truly infeasible.** A required capability is removed from the simulated property. Planning correctly ends in "no verified strategy" instead of fabricating a plan that looks fine but wouldn't actually work.
4. Look for the **"why can I trust this?"** panel after any activation — it shows the real chain: Bedrock model + call evidence, deterministic verification result, and the independent simulated Home State Gateway readback that confirmed the change actually took effect in the simulated property.

## If you want to verify it's not a canned demo

From a machine with network access, run:

```bash
python3 verify_no_silent_fallback.py https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws strands
```

This drives a real `dream_stay` job against the live endpoint and asserts the returned provenance shows a genuine Bedrock/Strands call chain (model ID, HTTP 200 responses, request IDs) rather than a fixture/canned response. See `docs/TESTING_EVIDENCE.md` for what every check in this repository proves, and what is explicitly not claimed.

## If you want to run it yourself

```bash
pip install -r requirements.txt
python app_server.py
```

Runs the deterministic fixture planner by default (no AWS credentials needed) so you can exercise the full MCP tool surface and UI locally. Real Bedrock/Strands planning requires `PLANNER_KIND=Live` plus AWS credentials for one of the two identities the identity gate accepts (see `docs/ARCHITECTURE.md`) — the hosted live demo already runs this mode.
