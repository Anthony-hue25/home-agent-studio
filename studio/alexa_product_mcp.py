"""Final Gate I Alexa+ MCP-native customer-intent surface."""
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .alexa_product_ui import UI_MIME_TYPE, UI_URI, mcp_app_html
from .product_service import AdaptiveStayProductService

PUBLIC_PRODUCT_TOOLS = (
    "get_stay",
    "get_preference_options",
    "propose_preference",
    "dream_stay",
    "get_dream_status",
    "get_stay_blueprint",
    "activate_stay",
    "change_stay",
    "checkout_stay",
)


def _local_transport_security(port):
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"],
        allowed_origins=[f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
    )


def build_alexa_product_server(service, port, *, write_authorized=False):
    if type(service) is not AdaptiveStayProductService:
        raise ValueError("typed AdaptiveStayProductService required")
    if type(port) is not int or port < 1 or port > 65535:
        raise ValueError("valid TCP port required")
    if type(write_authorized) is not bool:
        raise ValueError("write_authorized boolean required")

    mcp = FastMCP(
        name="adaptive-stay-alexa-product",
        instructions=(
            "Adaptive Stay is an Alexa+ MCP-native experience for a temporary guest stay. "
            "Use customer-intent tools only. Alexa+ owns natural-language interaction. "
            "The service owns stay state, physical constraints, Dream and Stay Blueprints. "
            "Dream runs asynchronously; poll get_dream_status after dream_stay. "
            "Authenticated write authority is required for change_stay, activate_stay and checkout_stay."
        ),
        host="127.0.0.1",
        port=port,
        streamable_http_path="/mcp",
        transport_security=_local_transport_security(port),
    )
    ui_meta = {"ui": {"resourceUri": UI_URI, "visibility": ["model", "app"]}}

    @mcp.tool(name="get_stay", structured_output=True, meta=ui_meta,
              description="Read the current property, stay, people, preferences, shared-resource state, Dream status and active Blueprint state. No mutation.")
    def get_stay() -> dict[str, Any]:
        return service.get_stay()

    @mcp.tool(name="get_preference_options", structured_output=True, meta=ui_meta,
              description="Get the complete closed preference/value choices currently supported for one guest or space. Call before propose_preference. No mutation.")
    def get_preference_options(scope: str, subject_id: str) -> dict[str, Any]:
        return service.get_preference_options(scope, subject_id)

    @mcp.tool(name="propose_preference", structured_output=True, meta=ui_meta,
              description="Propose exactly one preference/value pair returned by get_preference_options for the same scope, subject and catalog hash. Review only; no mutation.")
    def propose_preference(preference_ref: str, value_ref: str, scope: str, subject_id: str, catalog_hash: str) -> dict[str, Any]:
        return service.propose_preference(preference_ref, value_ref, scope, subject_id, catalog_hash)

    @mcp.tool(name="dream_stay", structured_output=True, meta=ui_meta,
              description="Request asynchronous Dream for the current stay. Returns quickly with a job id; Strands/Bedrock candidate generation and deterministic Dream continue behind the application boundary.")
    def dream_stay() -> dict[str, Any]:
        return service.dream_stay()

    @mcp.tool(name="get_dream_status", structured_output=True, meta=ui_meta,
              description="Read one Dream job state: REQUESTED, RUNNING, READY or FAILED. No mutation.")
    def get_dream_status(job_id: str) -> dict[str, Any]:
        return service.get_dream_status(job_id)

    @mcp.tool(name="get_stay_blueprint", structured_output=True, meta=ui_meta,
              description="Read the latest or requested verified Stay Blueprint and whether it is still current. No activation.")
    def get_stay_blueprint(blueprint_id: str = "") -> dict[str, Any]:
        return service.get_stay_blueprint(blueprint_id)

    @mcp.tool(name="activate_stay", structured_output=True, meta=ui_meta,
              description="Activate a current verified Stay Blueprint. This is an authenticated write action; unauthenticated callers receive AUTH_REQUIRED.")
    def activate_stay(blueprint_id: str) -> dict[str, Any]:
        return service.activate_stay(blueprint_id, authorized=write_authorized)

    @mcp.tool(name="change_stay", structured_output=True, meta=ui_meta,
              description="Apply a reviewed preference proposal to the current stay. This is an authenticated write action and makes prior Dream/Blueprint context stale.")
    def change_stay(proposal_id: str) -> dict[str, Any]:
        return service.change_stay(proposal_id, authorized=write_authorized)

    @mcp.tool(name="checkout_stay", structured_output=True, meta=ui_meta,
              description="Checkout the current stay and expire temporary guest state. This is an authenticated write action.")
    def checkout_stay() -> dict[str, Any]:
        return service.checkout_stay(authorized=write_authorized)

    @mcp.resource(
        UI_URI,
        name="Adaptive Stay Alexa+ Product",
        description="Complete Alexa+ MCP App for personalization, shared-resource coordination, Dream, Stay Blueprint, activation, mid-stay change and checkout.",
        mime_type=UI_MIME_TYPE,
    )
    def adaptive_stay_product_resource() -> str:
        return mcp_app_html()

    return mcp
