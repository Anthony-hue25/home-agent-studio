# AWS Builder mini-challenge

Entered alongside this project's primary-track submission to the **Alexa+ / MCP track** (see the repository root `README.md`, "Track eligibility"). This document describes the AWS integration specifically for the AWS Builder mini-challenge.

## AWS services used, and for what

- **Amazon Bedrock** (Nova Pro, `amazon.nova-pro-v1:0`) -- the actual model behind the Dream planner. Given the current guests, their preferences, and the simulated property's physical constraints, it proposes candidate strategies for resolving the stay. It never gets the final word: every candidate it proposes is independently, deterministically re-verified before it can become a Stay Blueprint (see `docs/ARCHITECTURE.md`).
- **Strands Agents SDK** (`strands-agents==1.56.0`) -- orchestrates the agent loop that calls Bedrock, including two read-only grounding tools the model can call to discover the simulated property's current capabilities before proposing a strategy.
- **boto3 / botocore** -- the AWS SDK layer underneath Strands and the identity/credential resolution used by `LiveStayPlanner`, including its ECS-task-role fallback path (see `test_live_planner_profile_fallback.py`).
- **AWS ECS (Express Gateway)** -- hosts the live, public deployment. The exact `Dockerfile` in this repository is what's running at the live demo URL.

No AgentCore, SageMaker, or Kiro usage is claimed -- only what's listed above is actually wired into the running product.

## How this is documented, not just asserted

`verify_no_silent_fallback.py`, run against the live endpoint, captures bounded, real runtime provenance from an actual Dream job: the planner backend (`strands`), the provider (`bedrock`), the exact model ID, the HTTP status and request ID of each real Bedrock call, and the Strands SDK version -- proving the AWS integration is live at runtime, not configured-but-unused. See `docs/TESTING_EVIDENCE.md` for the full evidence table and how to reproduce it yourself.

## Why this design

The core product bet is that an LLM should *propose*, never *verify*. Bedrock/Strands are given real, bounded read-only tools to ground their proposal in the actual (simulated) property state, but the result only becomes real (a Stay Blueprint, an activated change in the simulation) after it passes a separate, deterministic verification step that doesn't trust the model's own account of whether its plan works.
