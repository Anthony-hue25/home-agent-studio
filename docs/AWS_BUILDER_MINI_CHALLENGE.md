# AWS Builder mini-challenge

Adaptive Stay is built for Build, Ship, Shape: Amazon Developer Hackathon, primary track Alexa+ / MCP, with the AWS Builder mini-challenge.

- Amazon Bedrock Nova Pro (`amazon.nova-pro-v1:0`) supplies live planning inference.
- Strands Agents SDK orchestrates the agent and bounded read-only grounding tool.
- boto3 / botocore handle AWS identity, credential resolution, and Bedrock transport.
- AWS ECS Express Gateway hosts the public application using the included Docker recipe.

Adaptive Stay's deterministic verifier decides whether a proposed configuration resolves constraints. A verified, current Blueprint can be applied through the simulated gateway; independent readback must match before the stay is reported active.

The browser and physical execution are simulated. See [architecture](ARCHITECTURE.md), [testing](TESTING.md), the existing [friction log](FRICTION_LOG.md), and [product feedback](PRODUCT_FEEDBACK.md).
