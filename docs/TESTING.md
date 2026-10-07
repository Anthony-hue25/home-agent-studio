# Adaptive Stay testing

Run from the repository root after installing `requirements.txt`. Python 3.12 was used for this reconciliation.

## Credential-free unit checks

```powershell
python test_home_state_gateway.py
python test_identity_gate.py
python test_live_planner_profile_fallback.py
```

These verify gateway apply/readback, identity rejection, and named-profile fallback with mocked AWS/Strands calls. All three passed on 2026-10-07.

## Local HTTP/MCP checks

Start the server using the README's Fixture configuration (`COOKIE_SECURE=false` for local HTTP), then run:

```powershell
python verify_container.py http://127.0.0.1:8080
python verify_gate_i_ui.py http://127.0.0.1:8080
python verify_dual_session_and_checkout.py http://127.0.0.1:8080
python verify_no_silent_fallback.py http://127.0.0.1:8080 fixture
```

All four passed on 2026-10-07. They exercise real MCP transport through the host, UI/API integration, visitor isolation, checkout/reset, deterministic verification, and simulated activation/readback. `verify_container.py` was run against the Python process; Docker was unavailable, so no container build is claimed.

`verify_scenarios_live.py` requires a Strands backend and intentionally fails its provenance check against Fixture mode. Its local run passed the combined-constraint, stale-refusal, and infeasible fail-closed assertions, but the overall result was FAIL because Fixture is not live inference. Do not use it as a passing local Fixture command.

## Live Bedrock checks

```powershell
python verify_no_silent_fallback.py https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws strands
python verify_scenarios_live.py https://ad-eaa7c5234e71450e9b279c154dc91a52.ecs.us-east-1.on.aws
```

These checks create isolated demo sessions and invoke real Bedrock inference. The anti-fallback check requires Bedrock call evidence, Strands grounding, independent deterministic verification, a Blueprint, and execution/readback evidence. The scenario check exercises combined constraints, stale activation rejection, and infeasible fail-closed behavior. Runtime diagnostics are not a promise that the browser presents a candidate menu.

## Validation limits

Physical device execution is simulated. No production Alexa hardware integration or independent security certification is claimed. `python -m pip check` found no broken dependencies. Application source, requirements, tests, verification scripts, Dockerfile, and license remain identical to baseline `65abd2b`; only documentation and repository/build-context exclusions change.

Both live Bedrock commands passed on 2026-10-07. Live UI HTML matched the baseline bundle after excluding session bootstrap state. Live health reported `Live` / `gate-j3-live-v1`.
