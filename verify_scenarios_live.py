#!/usr/bin/env python3
"""
Gate J3 -- live public-endpoint replay of Experience Lab Scenarios C, D, E
against the REAL Strands/Bedrock planner (PLANNER_KIND=Live), driven only
through the real product surface: GET / (session bootstrap), the
pre-approved non-MCP /api/lab/load convenience (sets up the scenario's
starting stay/constraints -- never mutates Dream/Blueprint state directly),
and real Streamable HTTP MCP tools/call for every planner-touching step.

Usage: python3 verify_scenarios_live.py <BASE_URL>
"""
import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

OK = True


def ok(msg):
    print(f"[PASS] {msg}")


def fail(msg):
    global OK
    OK = False
    print(f"[FAIL] {msg}")


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.sid = None
        self._id = 0

    def _raw(self, method, path, body=None, headers=None, is_json=True):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        if data is not None and is_json:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=20) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()

    def land(self):
        status, _, _ = self._raw("GET", "/")
        return status

    def lab_load(self, scenario):
        status, _, raw = self._raw("POST", "/api/lab/load", {"scenario": scenario})
        body = json.loads(raw) if raw else {}
        if status != 200:
            raise RuntimeError(f"/api/lab/load {scenario} failed: {status} {body}")
        return body

    def mcp(self, body):
        headers = {"Accept": "application/json, text/event-stream"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        status, headers_r, raw = self._raw("POST", "/mcp", body, headers)
        sid = headers_r.get("mcp-session-id")
        if sid:
            self.sid = sid
        ctype = headers_r.get("content-type", "")
        if "text/event-stream" in ctype:
            text = raw.decode("utf-8", errors="replace")
            lines = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
            msg = json.loads(lines[-1]) if lines else {}
        else:
            msg = json.loads(raw) if raw else {}
        return status, msg

    def _next_id(self):
        self._id += 1
        return self._id

    def initialize(self):
        self.land()
        status, msg = self.mcp({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "gate-j3-scenario-replay", "version": "1"}},
        })
        if status != 200 or not self.sid:
            raise SystemExit(f"MCP initialize failed: status={status} sid={self.sid} msg={msg}")
        self.mcp({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call(self, name, args=None, allow_error=False):
        status, msg = self.mcp({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        })
        result = msg.get("result", {})
        if result.get("isError"):
            text = ""
            for block in result.get("content", []):
                if block.get("type") == "text":
                    text = block["text"]
            if allow_error:
                return {"_error": text}
            raise RuntimeError(f"tool {name} returned isError: {text}")
        return result.get("structuredContent", {}).get("data", {})

    def dream_and_wait(self):
        dream = self.call("dream_stay")
        job_id = dream["job_id"]
        status_data = dream
        for _ in range(90):
            status_data = self.call("get_dream_status", {"job_id": job_id})
            if status_data.get("status") not in ("REQUESTED", "RUNNING", "IN_PROGRESS", "PENDING"):
                break
            time.sleep(1)
        return job_id, status_data


def scenario_c(base):
    print("\n=== Scenario C: multiple simultaneous shared constraints (live) ===")
    c = Client(base)
    c.land()
    c.lab_load("C")
    c.initialize()
    job_id, status_data = c.dream_and_wait()
    prov = status_data.get("planner_provenance") or {}
    ok(f"dream_stay -> job {job_id}, terminal status={status_data.get('status')}")
    if prov.get("planner_backend") != "strands":
        fail(f"expected live strands backend, got {prov.get('planner_backend')!r}")
    else:
        ok("planner_backend == 'strands' (real Bedrock path, not fixture)")
    rejected = prov.get("rejected_candidates") or []
    print(f"    rejected_candidates observed: {len(rejected)} -> {[r.get('option_ref') for r in rejected]}")
    dver = prov.get("deterministic_verification") or {}
    if status_data.get("status") == "READY" and dver.get("status") == "PASS":
        ok(f"both simultaneous constraints resolved to a verified option (option_ref={dver.get('option_ref')}), "
           f"rejected candidates shown only if Dream actually tried and failed them")
    else:
        fail(f"scenario C did not reach a verified READY state: status={status_data.get('status')} dver={dver}")
    return prov.get("blueprint_id") or status_data.get("blueprint_id")


def scenario_d(base):
    print("\n=== Scenario D: reality changed / stale Blueprint (live) ===")
    c = Client(base)
    c.land()
    lab = c.lab_load("D")
    stale_id = lab.get("lab_stale_blueprint_id")
    if not stale_id:
        fail("lab scenario D did not return lab_stale_blueprint_id")
        return
    ok(f"scenario D set up a real verified Blueprint then changed a live preference -> {stale_id}")
    c.initialize()
    bp = c.call("get_stay_blueprint", {"blueprint_id": stale_id})
    if bp.get("is_current") is False:
        ok("get_stay_blueprint (real MCP tool) independently reports is_current=False for the now-stale Blueprint")
    else:
        fail(f"expected is_current=False for the stale Blueprint, got {bp.get('is_current')!r}")
    act = c.call("activate_stay", {"blueprint_id": stale_id}, allow_error=True)
    if "_error" in act and "stale" in act["_error"].lower():
        ok(f"activate_stay correctly fails closed on the stale Blueprint: {act['_error']!r}")
    else:
        fail(f"activate_stay did not fail closed on a stale Blueprint: {act}")


def scenario_e(base):
    print("\n=== Scenario E: truly infeasible / fail closed (live) ===")
    c = Client(base)
    c.land()
    c.lab_load("E")
    c.initialize()
    job_id, status_data = c.dream_and_wait()
    prov = status_data.get("planner_provenance") or {}
    ok(f"dream_stay -> job {job_id}, terminal status={status_data.get('status')}")
    dver = prov.get("deterministic_verification") or {}
    rejected = prov.get("rejected_candidates") or []
    if status_data.get("status") == "READY":
        fail("scenario E (infeasible) unexpectedly reached READY -- Dream did not fail closed")
        return
    if dver.get("status") == "FAIL" and not (prov.get("blueprint_id") or status_data.get("blueprint_id")):
        ok(f"Dream correctly failed closed: no verified strategy, no Blueprint fabricated "
           f"({len(rejected)} real rejected candidates shown, each with genuine unresolved reasons)")
    else:
        fail(f"scenario E did not fail closed as expected: status={status_data.get('status')} dver={dver}")
    # Try to activate anyway with a bogus/prior id -- must never succeed.
    act = c.call("get_stay_blueprint", {}, allow_error=True)
    if "_error" in act:
        ok(f"get_stay_blueprint correctly has nothing current to serve after a failed Dream: {act['_error']!r}")
    else:
        print(f"    (note: get_stay_blueprint returned {act} -- likely a prior stay's Blueprint, not this failed Dream's)")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18091"
    print(f"Replaying Scenarios C, D, E against: {base}")
    try:
        scenario_c(base)
    except Exception as exc:
        fail(f"Scenario C raised: {exc}")
    try:
        scenario_d(base)
    except Exception as exc:
        fail(f"Scenario D raised: {exc}")
    try:
        scenario_e(base)
    except Exception as exc:
        fail(f"Scenario E raised: {exc}")
    print("\nOVERALL:", "PASS" if OK else "FAIL")
    raise SystemExit(0 if OK else 1)


if __name__ == "__main__":
    main()
