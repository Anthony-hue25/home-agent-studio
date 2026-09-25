"""Standalone simulator for the same Gate I Alexa+ MCP App bundle.

Scenario data lives here on purpose. Product/runtime modules remain property-agnostic.

This file also hosts the local-only "Experience Lab": a repeatable scenario launcher
and a "create a new demo stay from scratch" wizard. Both are simulator conveniences
served by the same local HTTP handler as the standalone browser page. Neither is an
Alexa-facing MCP tool, neither changes the frozen public tool surface in
alexa_product_mcp.py, and every scenario runs the real AdaptiveStayProductService --
the same deterministic Dream, shared-resource and Blueprint code the Alexa+ MCP App
uses. Nothing here is faked to make a scenario "pass".
"""
import argparse
import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from .alexa_product_mcp import PUBLIC_PRODUCT_TOOLS, build_alexa_product_server
from .alexa_product_ui import standalone_html
from .capability_topology import CapabilityPlacement, PropertyCapabilityMap
from .product_service import AdaptiveStayProductService, CompleteCatalogPlanner
from .shared_resources import HotWaterRequest, HotWaterState
from .stay import Guest, PropertyProfile, PropertyTwin, RoomAssignment, ScopedPreference, StayProfile, StayStore
from .stay_blueprint import DreamJobStore
from .stay_planner import LiveStayPlanner

PROPERTY_ID = "coral-house"


def _base_topology():
    """The one physical property every Experience Lab scenario shares.

    Scenarios differ only in who is staying, what they ask for, and the shared-
    resource state at the moment they ask -- never in the rooms, zones or devices
    the property actually has. This is what keeps "create a new demo stay from
    scratch" and every lettered scenario honest: none of them can invent capacity
    the property does not have.
    """
    twin = PropertyTwin(
        PROPERTY_ID,
        ("bedroom-1", "bedroom-2", "bedroom-3"),
        ("zone-a", "zone-b"),
        (("bedroom-1", "zone-a"), ("bedroom-2", "zone-a"), ("bedroom-3", "zone-b")),
        ("hvac-a", "hvac-b", "fan-1", "fan-3", "blind-1", "lights"),
        ("climate", "fan", "blind", "lighting"),
    )
    topology = PropertyCapabilityMap(
        PROPERTY_ID,
        1,
        (
            CapabilityPlacement("cp-1", "hvac-a", "climate", "ZONE", "zone-a", True),
            CapabilityPlacement("cp-2", "hvac-b", "climate", "ZONE", "zone-b", True),
            CapabilityPlacement("cp-3", "fan-1", "fan", "ROOM", "bedroom-1", True),
            CapabilityPlacement("cp-4", "fan-3", "fan", "ROOM", "bedroom-3", True),
        ),
    )
    profile = PropertyProfile(PROPERTY_ID, "Coral House")
    return profile, twin, topology


def _thermal_preference(preference_id, guest_id, value_ref):
    return ScopedPreference(preference_id, "PERSON", guest_id, "pref.thermal.feel", value_ref, "GUEST")


def demo_service(planner_kind="Fixture"):
    """The default landing stay: five guests, three rooms, nothing decided yet."""
    profile, twin, topology = _base_topology()
    stay = StayProfile(
        "stay-coral-01", PROPERTY_ID, "2026-10-05", "2026-10-10",
        (
            Guest("maya", "Maya", "group-a"),
            Guest("luis", "Luis", "group-a"),
            Guest("james", "James", "group-b"),
            Guest("priya", "Priya", "group-b"),
            Guest("zoe", "Zoe", "group-c"),
        ),
        (
            RoomAssignment("maya", "bedroom-1"),
            RoomAssignment("luis", "bedroom-1"),
            RoomAssignment("james", "bedroom-2"),
            RoomAssignment("priya", "bedroom-2"),
            RoomAssignment("zoe", "bedroom-3"),
        ),
    )
    store = StayStore(profile, twin)
    store.create(stay)
    planner = LiveStayPlanner() if planner_kind.lower() == "live" else CompleteCatalogPlanner()
    return AdaptiveStayProductService(store, topology, planner)


def load_next_demo_stay(service):
    """Local simulator convenience only; never exposed as an Alexa MCP tool."""
    if service.store.current is not None:
        raise ValueError("checkout current stay before loading the next demo stay")
    next_stay = StayProfile(
        "stay-coral-02", PROPERTY_ID, "2026-10-12", "2026-10-16",
        (
            Guest("elena", "Elena", "group-d"),
            Guest("marcus", "Marcus", "group-e"),
            Guest("nia", "Nia", "group-e"),
        ),
        (
            RoomAssignment("elena", "bedroom-1"),
            RoomAssignment("marcus", "bedroom-2"),
            RoomAssignment("nia", "bedroom-3"),
        ),
    )
    service.store.create(next_stay)
    return service.get_stay()


def dispatch(service, name, args, *, authorized):
    if name not in PUBLIC_PRODUCT_TOOLS:
        raise ValueError("unsupported product tool")
    if name == "get_stay" and not args:
        return service.get_stay()
    if name == "get_preference_options" and set(args) == {"scope", "subject_id"}:
        return service.get_preference_options(args["scope"], args["subject_id"])
    if name == "propose_preference" and set(args) == {"preference_ref", "value_ref", "scope", "subject_id", "catalog_hash"}:
        return service.propose_preference(args["preference_ref"], args["value_ref"], args["scope"], args["subject_id"], args["catalog_hash"])
    if name == "dream_stay" and not args:
        return service.dream_stay()
    if name == "get_dream_status" and set(args) == {"job_id"}:
        return service.get_dream_status(args["job_id"])
    if name == "get_stay_blueprint" and set(args).issubset({"blueprint_id"}):
        return service.get_stay_blueprint(args.get("blueprint_id", ""))
    if name == "activate_stay" and set(args) == {"blueprint_id"}:
        return service.activate_stay(args["blueprint_id"], authorized=authorized)
    if name == "change_stay" and set(args) == {"proposal_id"}:
        return service.change_stay(args["proposal_id"], authorized=authorized)
    if name == "checkout_stay" and not args:
        return service.checkout_stay(authorized=authorized)
    raise ValueError("invalid product tool arguments")


# ---------------------------------------------------------------------------
# Experience Lab: named, repeatable scenarios. Local simulator only.
#
# Every scenario resets and reconfigures the SAME AdaptiveStayProductService
# instance the running demo already has -- the one the Alexa+ MCP tools are
# bound to -- so the Alexa+ surface and the standalone browser never diverge.
# No scenario invents a room, zone or device the base topology does not have,
# and no scenario hand-writes a Dream result: every one calls the real
# dream_stay()/get_dream_status()/get_stay_blueprint() pipeline.
# ---------------------------------------------------------------------------

def _reset_to(service, stay, *, hot_water_state=None, hot_water_requests=()):
    if service.store.current is not None:
        service.store.checkout()
    service.hot_water_state = hot_water_state
    service.hot_water_requests = hot_water_requests
    service._pending.clear()
    service._blueprints.clear()
    service._job_blueprints.clear()
    service._dream_provenance.clear()
    # Dream job identity is deterministic (derived only from a content hash
    # of the stay/preference/resource context), so an Experience Lab scenario
    # that reproduces an earlier scenario's exact configuration (e.g. loading
    # D, which Dreams a "Maya wants it cooler" stay before its reality
    # change, then loading F, which Dreams that identical stay) would have
    # dream_stay() rediscover the OLD job here -- still sitting in
    # service.jobs with a terminal READY status even after _blueprints/
    # _job_blueprints above were just cleared -- and report it READY with no
    # blueprint bookkeeping get_stay_blueprint can ever resolve. This mirrors
    # the exact same cross-stay-leakage fix product_service.py's own
    # checkout_stay() already applies for the same reason.
    service.jobs = DreamJobStore()
    service._latest_job_id = ""
    service._latest_blueprint_id = ""
    service._active_blueprint_id = ""
    service._active_profile_hash = ""
    service._active_resource_hash = ""
    service.store.create(stay)


def _base_five_guest_stay(preferences=()):
    return StayProfile(
        "stay-lab-01", PROPERTY_ID, "2026-11-01", "2026-11-05",
        (
            Guest("maya", "Maya", "group-a"),
            Guest("luis", "Luis", "group-a"),
            Guest("james", "James", "group-b"),
            Guest("priya", "Priya", "group-b"),
            Guest("zoe", "Zoe", "group-c"),
        ),
        (
            RoomAssignment("maya", "bedroom-1"),
            RoomAssignment("luis", "bedroom-1"),
            RoomAssignment("james", "bedroom-2"),
            RoomAssignment("priya", "bedroom-2"),
            RoomAssignment("zoe", "bedroom-3"),
        ),
        preferences,
    )


def _restore_full_topology(service):
    _, _, topology = _base_topology()
    service.topology = topology


def _scenario_a(service):
    """Smooth personalization: nothing pre-decided, no shared-resource tension."""
    _restore_full_topology(service)
    _reset_to(service, _base_five_guest_stay())
    return service.get_stay()


def _scenario_b(service):
    """One shared climate conflict: two rooms on zone-a want opposite temperatures."""
    _restore_full_topology(service)
    prefs = (
        _thermal_preference("pref-lab-maya-thermal", "maya", "thermal.cooler"),
        _thermal_preference("pref-lab-james-thermal", "james", "thermal.warmer"),
    )
    _reset_to(service, _base_five_guest_stay(prefs))
    return service.get_stay()


def _scenario_c(service):
    """Multiple simultaneous shared constraints: the zone-a climate conflict AND
    a genuine hot-water capacity conflict, at the same time, both real."""
    _restore_full_topology(service)
    prefs = (
        _thermal_preference("pref-lab-maya-thermal", "maya", "thermal.cooler"),
        _thermal_preference("pref-lab-james-thermal", "james", "thermal.warmer"),
    )
    _reset_to(
        service,
        _base_five_guest_stay(prefs),
        hot_water_state=HotWaterState("MEDIUM"),
        hot_water_requests=(
            HotWaterRequest("shower-maya", "maya"),
            HotWaterRequest("shower-zoe", "zoe"),
        ),
    )
    return service.get_stay()


def _scenario_d(service):
    """Reality changed after Dream: a stay Dreams cleanly to a real verified
    Blueprint, then a guest's preference changes through the same
    propose_preference -> change_stay path production uses. The existing
    Blueprint must go stale immediately and refuse activation -- not because
    a flag was hand-set, but because the stay it was verified against no
    longer exists. This is the same mechanism Gate J2's stale-Blueprint
    trust/control proof exercised; the Experience Lab just gives it a
    guided, repeatable moment."""
    _restore_full_topology(service)
    prefs = (_thermal_preference("pref-lab-maya-thermal", "maya", "thermal.cooler"),)
    _reset_to(service, _base_five_guest_stay(prefs))
    job = service.dream_stay()
    ready = service.wait_for_job(job["data"]["job_id"], timeout=20)
    if ready.status != "READY":
        raise RuntimeError("Experience Lab scenario D requires a Dream pass before the reality change")
    blueprint_id = service.get_stay_blueprint()["data"]["blueprint"]["blueprint_id"]
    # The reality change: James now also wants his (shared zone-a) room
    # warmer. Real propose/change calls, exactly as a guest would trigger
    # from the product UI -- nothing here writes stay state directly.
    catalog = service._preference_catalog()
    proposal = service.propose_preference(
        "pref.thermal.feel", "thermal.warmer", "PERSON", "james", catalog.catalog_hash,
    )
    service.change_stay(proposal["data"]["proposal_id"], authorized=True)
    # change_stay() correctly clears the service's own "latest job/blueprint"
    # pointers (a stale job should not keep looking like the current one) --
    # but that also means a plain get_stay() no longer surfaces the Blueprint
    # that just went stale, so the Experience Lab would land on what looks
    # like an unconfigured stay instead of a visibly stale one. lab_stale_
    # blueprint_id is a local-simulator-only hint (never part of any MCP tool
    # response) telling the browser which specific Blueprint to re-fetch via
    # the real get_stay_blueprint tool so it can show, honestly, that this
    # exact Blueprint is now stale.
    result = dict(service.get_stay())
    result["lab_stale_blueprint_id"] = blueprint_id
    return result


def _scenario_e(service):
    """Truly infeasible: the same zone-a conflict as scenario B, but with the
    one local escape hatch (bedroom-1's fan) removed, so no bounded strategy
    can satisfy both rooms. Dream must fail closed, not fabricate a pass."""
    _restore_full_topology(service)
    disabled = PropertyCapabilityMap(
        service.topology.property_id,
        service.topology.version + 1,
        tuple(
            CapabilityPlacement(
                p.placement_id, p.device_id, p.capability_ref, p.scope, p.subject_id,
                False if p.subject_id == "bedroom-1" and p.capability_ref == "fan" else p.available,
            )
            for p in service.topology.placements
        ),
    )
    prefs = (
        _thermal_preference("pref-lab-maya-thermal", "maya", "thermal.cooler"),
        _thermal_preference("pref-lab-james-thermal", "james", "thermal.warmer"),
    )
    _reset_to(service, _base_five_guest_stay(prefs))
    service.topology = disabled
    return service.get_stay()


def _scenario_f(service):
    """Checkout -> next stay: a stay that is already Dream-verified and active,
    one click from checkout, so the between-stays and next-stay/create-from-
    scratch lifecycle can be demonstrated immediately."""
    _restore_full_topology(service)
    prefs = (_thermal_preference("pref-lab-maya-thermal", "maya", "thermal.cooler"),)
    _reset_to(service, _base_five_guest_stay(prefs))
    job = service.dream_stay()
    ready = service.wait_for_job(job["data"]["job_id"], timeout=20)
    if ready.status != "READY":
        raise RuntimeError("Experience Lab scenario F requires a Dream pass")
    blueprint_id = service.get_stay_blueprint()["data"]["blueprint"]["blueprint_id"]
    service.activate_stay(blueprint_id, authorized=True)
    return service.get_stay()


LAB_SCENARIOS = (
    ("A", _scenario_a, "Smooth personalization", "No conflicts yet -- pick a guest and personalize their room."),
    ("B", _scenario_b, "One shared climate conflict", "Maya wants it cooler, James wants it warmer -- same shared zone."),
    ("C", _scenario_c, "Multiple simultaneous shared constraints", "A climate conflict and a hot-water conflict, both real, at once."),
    ("D", _scenario_d, "Reality changed", "A verified Blueprint exists -- then a guest changes a preference. It goes stale immediately."),
    ("E", _scenario_e, "Truly infeasible", "Dream must fail closed -- no bounded configuration can satisfy this stay."),
    ("F", _scenario_f, "Checkout -> next stay", "An already-active, verified stay -- one click from checkout and the next booking."),
)
_LAB_SCENARIO_INDEX = {key: fn for key, fn, _, _ in LAB_SCENARIOS}


def load_lab_scenario(service, key):
    fn = _LAB_SCENARIO_INDEX.get(key)
    if fn is None:
        raise ValueError("unknown Experience Lab scenario")
    return fn(service)


def create_demo_stay_from_scratch(service, guest_assignments):
    """Local simulator wizard only. Uses only this property's existing topology:
    no room, zone or device is invented, and no new Alexa-facing tool is added.

    guest_assignments is a list of {"name": <str>, "room_id": <str>} objects --
    one existing room chosen independently per guest. Nothing here assumes the
    whole party shares a single room. Every room is validated against this
    property's own Property Twin before ANY guest is created: a bad room for
    one guest fails the whole request closed rather than dropping that guest
    or defaulting them into someone else's room.
    """
    if service.store.current is not None:
        raise ValueError("checkout current stay before creating another demo stay")
    if type(guest_assignments) is not list or not 1 <= len(guest_assignments) <= 6:
        raise ValueError("between 1 and 6 guest assignments required")
    cleaned = []
    for raw in guest_assignments:
        if type(raw) is not dict or set(raw) != {"name", "room_id"}:
            raise ValueError("each guest assignment needs exactly name and room_id")
        name, room_id = raw["name"], raw["room_id"]
        if type(name) is not str or not name.strip() or len(name) > 60:
            raise ValueError("bounded guest name required")
        if type(room_id) is not str or room_id not in service.store.property_twin.room_ids:
            raise ValueError("room must belong to this property")
        cleaned.append((name.strip(), room_id))
    if len(cleaned) != len(set(n.lower() for n, _ in cleaned)):
        raise ValueError("duplicate guest name")

    def _slug(name, index):
        base = "".join(c for c in name.lower() if c.isalnum()) or "guest"
        return f"{base}-{index}"

    guests = tuple(Guest(_slug(name, i), name, "group-lab") for i, (name, _room) in enumerate(cleaned))
    assignments = tuple(RoomAssignment(g.guest_id, room_id) for g, (_name, room_id) in zip(guests, cleaned))
    stay = StayProfile("stay-lab-scratch", PROPERTY_ID, "2026-12-01", "2026-12-05", guests, assignments)
    _reset_to(service, stay)
    return service.get_stay()


class _Handler(BaseHTTPRequestHandler):
    server_version = "AdaptiveStayProduct/1.0"

    def log_message(self, *_):
        pass

    def _local(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host:
            raise PermissionError("local host required")
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise PermissionError("local origin required")

    def _json(self, payload, status=200):
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, max_bytes):
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("json required")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= max_bytes:
            raise ValueError("bounded input required")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        try:
            self._local()
            if self.path in ("/", "/adaptive-stay"):
                body = standalone_html(self.server.service.get_stay()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; img-src data:; font-src 'none'; frame-src 'none'; "
                    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                )
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/lab/scenarios":
                # Local-only metadata for the Experience Lab drawer. Never registered
                # as an MCP tool or resource; not reachable from the Alexa+ surface.
                self._json({
                    "scenarios": [
                        {"key": key, "label": f"{key} — {label}", "description": description}
                        for key, _, label, description in LAB_SCENARIOS
                    ],
                    "property_rooms": list(self.server.service.store.property_twin.room_ids),
                })
                return
            self.send_error(404)
        except PermissionError:
            self.send_error(403)

    def do_POST(self):
        try:
            self._local()
            if self.path == "/api/demo-next-stay":
                request = self._read_json(200)
                if request != {}:
                    raise ValueError("empty object required")
                self._json(load_next_demo_stay(self.server.service))
                return
            if self.path == "/api/lab/load":
                request = self._read_json(200)
                if type(request) is not dict or set(request) != {"scenario"}:
                    raise ValueError("exact scenario request required")
                self._json(load_lab_scenario(self.server.service, request["scenario"]))
                return
            if self.path == "/api/lab/create-stay":
                request = self._read_json(2000)
                if type(request) is not dict or set(request) != {"guests"}:
                    raise ValueError("exact create-stay request required")
                self._json(create_demo_stay_from_scratch(self.server.service, request["guests"]))
                return
            if self.path not in ("/api/tool", "/api/local-action"):
                self.send_error(404)
                return
            request = self._read_json(24000)
            if type(request) is not dict or set(request) != {"name", "arguments"}:
                raise ValueError("exact tool request required")
            args = request["arguments"]
            if type(args) is not dict:
                raise ValueError("arguments object required")
            result = dispatch(
                self.server.service,
                request["name"],
                args,
                authorized=self.path == "/api/local-action",
            )
            self._json(result)
        except (ValueError, PermissionError, KeyError, TypeError, RuntimeError) as exc:
            self._json({"error": str(exc)[:400]}, 400)


class AdaptiveProductDemo:
    def __init__(self, service=None, browser_port=8800, *, mcp_write_authorized=False):
        import uvicorn
        self.service = service or demo_service("Fixture")

        self.mcp_socket = socket.socket()
        self.mcp_socket.bind(("127.0.0.1", 0))
        self.mcp_socket.listen(64)
        mcp_port = self.mcp_socket.getsockname()[1]
        mcp = build_alexa_product_server(self.service, mcp_port, write_authorized=mcp_write_authorized)
        self.mcp_server = uvicorn.Server(
            uvicorn.Config(mcp.streamable_http_app(), log_level="error", access_log=False)
        )
        self.mcp_thread = Thread(target=lambda: self.mcp_server.run(sockets=[self.mcp_socket]), daemon=True)
        self.mcp_thread.start()
        deadline = time.monotonic() + 10
        while not self.mcp_server.started and self.mcp_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        if not self.mcp_server.started:
            self.close(); raise RuntimeError("ALEXA_PRODUCT_MCP_START_FAILED")
        self.mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"

        self.http = ThreadingHTTPServer(("127.0.0.1", browser_port), _Handler)
        self.http.service = self.service
        self.browser_thread = Thread(target=self.http.serve_forever, daemon=True)
        self.browser_thread.start()
        self.url = f"http://127.0.0.1:{self.http.server_port}/adaptive-stay"

    def close(self):
        if getattr(self, "http", None) is not None:
            self.http.shutdown(); self.http.server_close(); self.browser_thread.join(timeout=5); self.http = None
        if getattr(self, "mcp_server", None) is not None:
            self.mcp_server.should_exit = True; self.mcp_thread.join(timeout=5); self.mcp_server = None
        if getattr(self, "mcp_socket", None) is not None:
            self.mcp_socket.close(); self.mcp_socket = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--planner", choices=("Live", "Fixture"), default="Live")
    args = parser.parse_args()
    demo = AdaptiveProductDemo(demo_service(args.planner), browser_port=args.port)
    print("Adaptive Stay Alexa+ product: " + demo.url, flush=True)
    print("Alexa+ MCP endpoint:          " + demo.mcp_url, flush=True)
    print("Planner:                      " + args.planner, flush=True)
    print("Public MCP writes:            AUTH_REQUIRED (production OAuth deferred to Gate J)", flush=True)
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        demo.close()


if __name__ == "__main__":
    main()
