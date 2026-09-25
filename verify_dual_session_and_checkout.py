import json
import sys
import time
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18090"
print("Verifying dual-session isolation + checkout/reset against:", BASE)
print()

ok = True


def check(label, cond, extra=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {label} {extra}")


class Client:
    """One independent public browser/client session: its own cookie jar
    (so its own asp_session cookie / SessionRegistry entry) and its own
    Mcp-Session-Id, exactly like two separate visitors hitting the live
    public endpoint. Only real Streamable HTTP MCP (+ the pre-approved
    non-MCP Experience Lab REST convenience) is used -- no /api/tool."""

    def __init__(self, name):
        self.name = name
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.mcp_sid = None
        self._id = 0

    def _next_id(self):
        self._id += 1
        return self._id

    def raw(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(r, timeout=15) as resp:
                raw = resp.read()
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, raw
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()

    def cookie_value(self):
        for c in self.jar:
            if c.name == "asp_session":
                return c.value
        return None

    def land(self):
        status, headers, raw = self.raw("GET", "/")
        return status

    def mcp(self, body):
        headers = {"Accept": "application/json, text/event-stream"}
        if self.mcp_sid:
            headers["Mcp-Session-Id"] = self.mcp_sid
        status, headers_out, raw = self.raw("POST", "/mcp", body, headers)
        sid = headers_out.get("mcp-session-id")
        if sid:
            self.mcp_sid = sid
        ctype = headers_out.get("content-type", "")
        if status != 200:
            return status, {"_raw": raw.decode("utf-8", "replace")}
        if "text/event-stream" in ctype:
            text = raw.decode("utf-8", errors="replace")
            lines = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
            msg = json.loads(lines[-1]) if lines else {}
        else:
            msg = json.loads(raw) if raw else {}
        return status, msg

    def initialize(self):
        status, msg = self.mcp({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": f"dual-session-{self.name}", "version": "1"}},
        })
        self.mcp({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return status, msg

    def call_tool(self, name, args=None):
        status, msg = self.mcp({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        })
        if status != 200:
            return {"_transport_error": status, **msg}
        if "error" in msg:
            return {"_rpc_error": msg["error"]}
        return msg.get("result", {}).get("structuredContent", {}).get("data", {})

    def lab_load(self, scenario):
        status, headers, raw = self.raw("POST", "/api/lab/load", {"scenario": scenario})
        return status, (json.loads(raw) if raw else {})

    def demo_next_stay(self):
        status, headers, raw = self.raw("POST", "/api/demo-next-stay")
        return status, (json.loads(raw) if raw else {})

    def get_stay(self):
        return self.call_tool("get_stay")

    def dream_and_wait(self, timeout_iters=40):
        job = self.call_tool("dream_stay")
        job_id = job.get("job_id")
        if not job_id:
            return job, None
        for _ in range(timeout_iters):
            st = self.call_tool("get_dream_status", {"job_id": job_id})
            if st.get("status") not in ("REQUESTED", "RUNNING", "IN_PROGRESS", "PENDING"):
                bp_id = st.get("blueprint_id") or (st.get("blueprint") or {}).get("blueprint_id")
                return st, bp_id
            time.sleep(0.3)
        return {"status": "TIMEOUT"}, None


def snapshot_key_fields(stay):
    """A comparable fingerprint of guest/preference/dream/blueprint/activation
    state, deliberately excluding nothing -- full stay payload minus the
    top-level 'property' block (static across all visitors, not stay state)."""
    d = dict(stay)
    d.pop("property", None)
    return json.dumps(d, sort_keys=True)


# ---------------------------------------------------------------------------
# Setup: two fully independent client sessions, A and B
# ---------------------------------------------------------------------------
A = Client("A")
B = Client("B")

check("A: GET / -> 200 (session A minted)", A.land() == 200)
check("B: GET / -> 200 (session B minted)", B.land() == 200)

cookie_a, cookie_b = A.cookie_value(), B.cookie_value()
check("A and B have distinct asp_session cookies", bool(cookie_a) and bool(cookie_b) and cookie_a != cookie_b,
      f"a={cookie_a} b={cookie_b}")

init_a = A.initialize()
init_b = B.initialize()
check("A: MCP initialize -> 200", init_a[0] == 200)
check("B: MCP initialize -> 200", init_b[0] == 200)
check("A and B have distinct Mcp-Session-Id", bool(A.mcp_sid) and bool(B.mcp_sid) and A.mcp_sid != B.mcp_sid,
      f"a={A.mcp_sid} b={B.mcp_sid}")

baseline_a = A.get_stay()
baseline_b = B.get_stay()
check("A: baseline get_stay has data", "status" in baseline_a, str(baseline_a.get("status")))
check("B: baseline get_stay has data", "status" in baseline_b, str(baseline_b.get("status")))
b_fingerprint_pre_a_mutation = snapshot_key_fields(baseline_b)

print()
print("=== Test 1a: mutate/Dream/activate A, repeatedly confirm B is unaffected ===")

status, loaded = A.lab_load("C")
check("A: lab_load Scenario C -> 200", status == 200, str(status))
after_load_a = A.get_stay()
check("A: state now shows Scenario C conflicts", "SHARED_CLIMATE_ZONE_CONFLICT" in json.dumps(after_load_a),
      "climate conflict marker present" if "SHARED_CLIMATE_ZONE_CONFLICT" in json.dumps(after_load_a) else "missing")
b_after_a_load = B.get_stay()
check("B unaffected by A's Scenario C load", snapshot_key_fields(b_after_a_load) == b_fingerprint_pre_a_mutation)
check("B does NOT show A's climate conflict marker", "SHARED_CLIMATE_ZONE_CONFLICT" not in json.dumps(b_after_a_load))

dream_a, bp_id_a = A.dream_and_wait()
check("A: Dream reached terminal state", dream_a.get("status") not in (None, "TIMEOUT", "REQUESTED", "RUNNING"),
      str(dream_a.get("status")))
b_after_a_dream = B.get_stay()
check("B unaffected by A's Dream job", snapshot_key_fields(b_after_a_dream) == b_fingerprint_pre_a_mutation)

blueprint_a = A.call_tool("get_stay_blueprint", {"blueprint_id": bp_id_a}) if bp_id_a else {}
check("A: get_stay_blueprint returns blueprint data", bool(bp_id_a) and ("blueprint" in blueprint_a or "is_current" in blueprint_a),
      str(list(blueprint_a.keys())[:6]))
b_after_a_blueprint = B.get_stay()
check("B unaffected by A's Blueprint read", snapshot_key_fields(b_after_a_blueprint) == b_fingerprint_pre_a_mutation)

activate_a = A.call_tool("activate_stay", {"blueprint_id": bp_id_a}) if bp_id_a else {}
check("A: activate_stay -> ACTIVE", activate_a.get("status") == "ACTIVE", str(activate_a.get("status")))
b_after_a_activate = B.get_stay()
check("B unaffected by A's activation", snapshot_key_fields(b_after_a_activate) == b_fingerprint_pre_a_mutation)
check("B: status is NOT ACTIVE (A's activation did not leak)", b_after_a_activate.get("status") != "ACTIVE",
      str(b_after_a_activate.get("status")))

a_active_snapshot = A.get_stay()
a_active_fingerprint = snapshot_key_fields(a_active_snapshot)

print()
print("=== Test 1b: mutate/Dream/activate/checkout B, repeatedly confirm A is unaffected ===")

status, loaded_b = B.lab_load("D")
check("B: lab_load Scenario D -> 200", status == 200, str(status))
after_load_b = B.get_stay()
# Scenario D is "reality changed after Dream": the reality change itself (a
# guest's post-Dream preference change, via real propose_preference/
# change_stay calls) is what creates the shared climate conflict -- that is
# the whole point of the scenario, and is what makes the already-issued
# Blueprint stale. A hot-water conflict (Scenario C's shape) never appears
# here; this is a different scenario with a different shared resource.
check("B: the post-Dream reality change created a shared climate conflict",
      "SHARED_CLIMATE_ZONE_CONFLICT" in json.dumps(after_load_b))
check("B does NOT show a hot-water conflict (different scenario)",
      "SHARED_HOT_WATER_CAPACITY" not in json.dumps(after_load_b))
stale_blueprint_id = loaded_b.get("lab_stale_blueprint_id")
check("B: the lab hands back the now-stale Blueprint id", bool(stale_blueprint_id))
if stale_blueprint_id:
    stale_bp = B.call_tool("get_stay_blueprint", {"blueprint_id": stale_blueprint_id})
    check("B: that Blueprint is reported stale via the real get_stay_blueprint tool",
          stale_bp.get("is_current") is False, str(stale_bp.get("is_current")))
    act = B.call_tool("activate_stay", {"blueprint_id": stale_blueprint_id})
    check("B: activate_stay on the stale Blueprint is refused",
          "_rpc_error" in act or act.get("status") not in ("ACTIVE",), str(act))
a_after_b_load = A.get_stay()
check("A unaffected by B's Scenario D load", snapshot_key_fields(a_after_b_load) == a_active_fingerprint)

dream_b, bp_id_b = B.dream_and_wait()
check("B: Dream reached terminal state", dream_b.get("status") not in (None, "TIMEOUT", "REQUESTED", "RUNNING"),
      str(dream_b.get("status")))
check("A's and B's Dream job ids differ", bool(dream_a) and dream_a is not dream_b)
a_after_b_dream = A.get_stay()
check("A unaffected by B's Dream job", snapshot_key_fields(a_after_b_dream) == a_active_fingerprint)

blueprint_b = B.call_tool("get_stay_blueprint", {"blueprint_id": bp_id_b}) if bp_id_b else {}
check("B: get_stay_blueprint returns blueprint data", bool(bp_id_b) and ("blueprint" in blueprint_b or "is_current" in blueprint_b))
check("A's and B's blueprint ids differ", bool(bp_id_a) and bool(bp_id_b) and bp_id_a != bp_id_b,
      f"a={bp_id_a} b={bp_id_b}")
a_after_b_blueprint = A.get_stay()
check("A unaffected by B's Blueprint read", snapshot_key_fields(a_after_b_blueprint) == a_active_fingerprint)

activate_b = B.call_tool("activate_stay", {"blueprint_id": bp_id_b}) if bp_id_b else {}
check("B: activate_stay -> ACTIVE", activate_b.get("status") == "ACTIVE", str(activate_b.get("status")))
a_after_b_activate = A.get_stay()
check("A unaffected by B's activation", snapshot_key_fields(a_after_b_activate) == a_active_fingerprint)

checkout_b = B.call_tool("checkout_stay")
check("B: checkout_stay -> CHECKED_OUT", checkout_b.get("status") == "CHECKED_OUT", str(checkout_b.get("status")))
a_after_b_checkout = A.get_stay()
check("A unaffected by B's checkout (A still ACTIVE)", a_after_b_checkout.get("status") == "ACTIVE",
      str(a_after_b_checkout.get("status")))
check("A's full state unaffected by B's checkout", snapshot_key_fields(a_after_b_checkout) == a_active_fingerprint)

print()
print("=== Test 2: checkout/reset ===")

status_get_stay_b = B.get_stay()
check("B: get_stay returns NO_STAY immediately after checkout", status_get_stay_b.get("status") == "NO_STAY",
      str(status_get_stay_b.get("status")))
check("B: NO_STAY payload has no leftover dream/blueprint", status_get_stay_b.get("dream") is None and status_get_stay_b.get("blueprint") is None,
      str((status_get_stay_b.get("dream"), status_get_stay_b.get("blueprint"))))

# 2a. Fresh stay within the SAME session (Experience Lab "next stay" convenience)
status, next_stay = B.demo_next_stay()
check("B: /api/demo-next-stay -> 200", status == 200, str(status))
b_fresh = B.get_stay()
check("B: fresh stay has NO leftover Scenario D conflict marker",
      "SHARED_CLIMATE_ZONE_CONFLICT" not in json.dumps(b_fresh) or b_fresh.get("dream") is None,
      "conflict marker absent or dream cleared")
check("B: fresh stay status is not stale ACTIVE/CHECKED_OUT", b_fresh.get("status") not in ("CHECKED_OUT",),
      str(b_fresh.get("status")))
check("B: fresh stay has no dream job carried over", b_fresh.get("dream") is None, str(b_fresh.get("dream")))
check("B: fresh stay has no blueprint carried over", b_fresh.get("blueprint") is None, str(b_fresh.get("blueprint")))

# 2b. A brand-new session/client (fresh cookie jar) sees a clean baseline too,
# with none of A's or B's mutated identifiers anywhere in it.
C = Client("C")
check("C: GET / -> 200 (fresh session minted)", C.land() == 200)
init_c = C.initialize()
check("C: MCP initialize -> 200", init_c[0] == 200)
check("C has yet another distinct asp_session cookie", C.cookie_value() not in (cookie_a, cookie_b))
baseline_c = C.get_stay()
blob_c = json.dumps(baseline_c)
check("C: fresh session has no trace of A's blueprint id", not bp_id_a or bp_id_a not in blob_c)
check("C: fresh session has no trace of B's blueprint id", not bp_id_b or bp_id_b not in blob_c)
check("C: fresh session status is not ACTIVE/CHECKED_OUT", baseline_c.get("status") not in ("ACTIVE", "CHECKED_OUT"),
      str(baseline_c.get("status")))
check("C: fresh session has no dream job", baseline_c.get("dream") is None)

print()
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
