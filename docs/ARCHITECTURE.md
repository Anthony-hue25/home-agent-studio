# Adaptive Stay architecture

The [README diagram](../README.md#architecture) shows the submission flow. The browser is a simulated Alexa+-style surface. `app_server.py` creates visitor-specific product services and proxies MCP Streamable HTTP to a FastMCP server per visitor. Starlette and uvicorn host the HTTP routes.

`studio/alexa_product_mcp.py` exposes the product tools. `studio/stay_planner.py` supplies a deterministic Fixture planner and a Live planner using Strands `Agent`, the bounded read-only `discover_stay_strategies` grounding tool, and Amazon Bedrock Nova Pro. The model proposes a strategy grounded in the simulated property's capabilities.

`studio/stay_dream.py` verifies proposals deterministically. A failed proposal cannot create a passing Blueprint; an infeasible stay ends in `NO_VERIFIED_STRATEGY`. Candidate diagnostics are bounded and are not an alternative-candidate menu in the browser.

`studio/stay_blueprint.py` binds the verified configuration to state. `studio/product_service.py` checks freshness on Blueprint reads and activation. A stale Blueprint is refused. `studio/home_state_gateway.py` applies a current configuration to simulated property state and independently reads it back. Success requires a matching readback (`VERIFIED_ACTIVE`). No physical devices are connected.

Experience Lab prepares scenario starting states through simulator-only HTTP routes. Planning and activation use the MCP product tools. Scenario D deliberately creates a Blueprint and then changes a preference, making the existing Blueprint stale.

## Runtime configuration and identity

Local default: Fixture mode. Live mode uses the `agent-factory` AWS profile if present, otherwise the default credential chain, including ECS task-role credentials. The identity gate pins the development IAM identity and deployed task role; unrelated AWS credentials fail closed. This account-specific boundary is intentional runtime policy, not a credential. Reproducing inference in another AWS account requires a separately reviewed policy change; local Fixture reproduction requires none.

## Deployment provenance

AWS ECS Express Gateway hosts the demo. The root Dockerfile uses Python 3.12 and copies pinned requirements, `studio/`, and `app_server.py`. Baseline `65abd2b` matches the historical `gate_j1_container` application source, Dockerfile, requirements, and HTTP verifiers. Historical tag `adaptive-stay-gate-j3` points to `0422ac0` in the earlier local repository.

During reconciliation, live health reported `planner: Live` and `build: gate-j3-live-v1`, matching historical deployment evidence. A health label does not expose a source or image hash. This reconciliation preserves production source and does not redeploy AWS. Later uncommitted provider experiments are excluded.
