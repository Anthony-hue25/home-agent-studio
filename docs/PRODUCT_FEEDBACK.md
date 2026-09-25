# Product feedback

## Which developer tools, APIs and SDKs did you use and for what?

Amazon Bedrock (Nova Pro) for the actual planning inference behind the Dream engine. The Strands Agents SDK (1.56.0) to orchestrate the model/tool loop, including a bounded read-only grounding tool (`discover_stay_strategies`) the model calls to discover the current simulated property state before proposing a strategy. boto3/botocore for AWS SDK access and credential resolution, including a fallback from a named local CLI profile to the default credential chain (the normal case for an ECS task authenticating via its task role). The official MCP Python SDK (`mcp` 1.27.0, FastMCP) for the Streamable HTTP MCP server itself. AWS ECS Express Gateway to host the live public deployment, plus the AWS CLI (including its custom `login` subcommand) for authentication and deployment.

## What worked well? (setup, docs, testing, performance, reliability)

Bedrock and Strands were straightforward to wire together once the identity/credential path was right -- the Strands agent loop with a bounded read-only grounding tool and structured output worked reliably and produced genuinely useful, groundable proposals. The MCP Python SDK's Streamable HTTP transport worked correctly out of the box, including session-id handling and protocol version negotiation (it correctly negotiates protocol version 2025-11-25 when a client proposes it). ECS Express Gateway deployment, once the correct CLI flags were found, produced a stable rolling deployment with a working health check.

## What needs work? (system errors, docs sections, missing features, compatibility issues, tool limitations, required workarounds)

Three concrete points, detailed with full repro steps in `docs/FRICTION_LOG.md`: (1) the custom `aws login --remote` command's authorization codes are invocation-scoped and not reusable, which isn't documented next to the flag; (2) `describe-express-gateway-service` and `update-express-gateway-service` use differently-named identifying flags (`--service-arn` vs. others) for the same resource, which cost time to discover; (3) `ecs:DescribeServiceDeployments` is a separate, not-obviously-required IAM permission that a reasonably-scoped developer policy didn't include, and its absence produced a generic `AccessDeniedException` rather than a hint about which specific permission was missing.

## How was your onboarding experience (getting from zero to hello world)?

Getting a first real Bedrock call working through Strands was fast once the IAM identity was correctly scoped. Getting that same call running reliably from a *deployed* ECS task (rather than a local developer identity) took longer, mainly because of the CLI/IAM friction above rather than anything about Bedrock or Strands themselves -- the model/agent layer was the easy part; the deployment plumbing around it was where the real friction was.

## Would you build with these devices and services again? Yes/No and why?

Yes. Bedrock and Strands are a good fit for "propose, don't decide" style AI features -- letting the model suggest strategies while a separate deterministic layer verifies them before anything real happens. MCP's Streamable HTTP transport is a clean, standard way to expose exactly the tool surface a conversational client needs, without inventing a bespoke protocol. The friction we hit was entirely in CLI/IAM ergonomics around ECS deployment, not in the AI services themselves, and all of it had a workaround.
