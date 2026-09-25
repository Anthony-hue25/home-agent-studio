#!/usr/bin/env python3
"""
Gate J2 -- automated runtime anti-silent-fallback verification.

Drives one real Dream through the *actual* Streamable HTTP MCP endpoint
(no source/config inspection) and asserts, from the bounded
`planner_provenance` the server recorded for that specific Dream job, that
the technology chain the deployment is *supposed* to be running actually
ran:

    Public MCP tools/call -> dream_stay -> LiveStayPlanner -> Strands
    -> Amazon Bedrock -> deterministic Dream verifier -> Blueprint

Usage:
    python3 verify_no_silent_fallback.py <BASE_URL> <EXPECTED_BACKEND>

    EXPECTED_BACKEND is "strands" (Live path must have run) or "fixture"
    (deterministic Fixture path is expected -- e.g. pre-cutover checks).

Exit code is 0 only if every assertion for the *expected* backend holds.
If EXPECTED_BACKEND=strands but the observed provenance is fixture-shaped
(or missing required Strands/Bedrock evidence), this exits non-zero with
"SILENT FALLBACK DETECTED" -- this is the check the J2 exit criterion
requires so a config regression (PLANNER_KIND silently not "Live" in the
running container) cannot pass unnoticed.

Only bounded, non-sensitive fields are read or printed: backend/provider
labels, model id, Bedrock call http_status/request_id, grounding tool-call
names, content hashes, job/blueprint ids, and verification/execution
results. No prompts, chain-of-thought, credentials, or raw guest data are
ever in scope.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


def fail(msg):
    print(f"[FAIL] {msg}")
    global OK
    OK = False


def ok(msg):
    print(f"[PASS] {msg}")


OK = True


class McpClient:
    def __init__(self, base):
        self.base = base
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.sid = None
        self._id = 0

    def _next_id(self):
        self._id += 1
        return self._id

    def _raw(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()

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

    def initialize(self):
        self._raw("GET", "/")
        status, msg = self.mcp({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "gate-j2-anti-fallback", "version": "1"}},
        })
        if status != 200 or not self.sid:
            raise SystemExit(f"MCP initialize failed: status={status} sid={self.sid} msg={msg}")
        self.mcp({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        server_info = msg.get("result", {}).get("serverInfo", {})
        return server_info

    def call(self, name, args=None):
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
            raise RuntimeError(f"tool {name} returned isError: {text}")
        return result.get("structuredContent", {}).get("data", {})


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    base = sys.argv[1]
    expected = sys.argv[2].strip().lower()
    if expected not in ("strands", "fixture"):
        raise SystemExit("EXPECTED_BACKEND must be 'strands' or 'fixture'")

    client = McpClient(base)
    server_info = client.initialize()
    ok(f"real MCP initialize + Mcp-Session-Id issued (server={server_info.get('name')}, session={client.sid[:8]}...)")

    dream = client.call("dream_stay")
    job_id = dream.get("job_id")
    if not job_id:
        fail(f"dream_stay did not return a job_id: {dream}")
        raise SystemExit(1)
    ok(f"real tools/call dream_stay -> job_id={job_id}")

    status_data = None
    for _ in range(60):
        status_data = client.call("get_dream_status", {"job_id": job_id})
        if status_data.get("status") not in ("REQUESTED", "RUNNING", "IN_PROGRESS", "PENDING"):
            break
        time.sleep(0.5)
    else:
        fail("Dream never reached a terminal state (timed out)")
        raise SystemExit(1)
    ok(f"real tools/call get_dream_status -> terminal status={status_data.get('status')}")

    prov = status_data.get("planner_provenance")
    if not prov:
        fail("no planner_provenance recorded for this Dream job -- cannot prove any backend ran")
        raise SystemExit(1)

    backend = prov.get("planner_backend")
    provider = prov.get("provider")
    print(f"    observed planner_backend={backend!r} provider={provider!r}")

    # --- The anti-silent-fallback gate -------------------------------------
    if expected == "strands" and backend != "strands":
        fail(f"SILENT FALLBACK DETECTED: expected planner_backend='strands' "
             f"(Live/Strands/Bedrock path) but observed '{backend}'. The public "
             f"LIVE path did not use Strands/Bedrock for this Dream.")
        raise SystemExit(1)
    if expected == "fixture" and backend != "fixture":
        fail(f"unexpected backend: expected 'fixture' but observed '{backend}' "
             f"-- Live path ran when Fixture was expected")
        raise SystemExit(1)
    ok(f"planner_backend matches expected mode ({expected})")

    if backend == "strands":
        if provider != "bedrock":
            fail(f"backend is 'strands' but provider != 'bedrock' (got {provider!r})")
        else:
            ok("provider == 'bedrock'")

        model = prov.get("model")
        if not model:
            fail("no model/inference-profile id recorded for the Strands/Bedrock invocation")
        else:
            ok(f"model/inference-profile id recorded: {model}")

        calls = prov.get("bedrock_calls") or []
        if not calls:
            fail("no bedrock_calls recorded -- no runtime evidence of an actual Bedrock invocation")
        elif any(c.get("http_status") != 200 for c in calls):
            fail(f"a recorded Bedrock call did not return HTTP 200: {calls}")
        else:
            ok(f"real Bedrock invocation evidence present: {calls}")

        grounding = prov.get("grounding_calls") or []
        if not grounding:
            fail("no grounding_calls recorded -- Strands agent may not have used its tool-use loop")
        else:
            ok(f"Strands tool-use (grounding) evidence present: {grounding}")

        if not prov.get("strands_version"):
            fail("no strands_version recorded")
        else:
            ok(f"strands_version recorded: {prov.get('strands_version')}")

        if not (prov.get("input_hash") and prov.get("output_hash")):
            fail("missing input_hash/output_hash -- cannot bind this provenance to a specific Dream")
        else:
            ok("input_hash/output_hash present (bounded, non-reversible content binding)")
    else:
        if provider != "deterministic":
            fail(f"backend is 'fixture' but provider != 'deterministic' (got {provider!r})")
        else:
            ok("provider == 'deterministic' (Fixture path, as expected)")

    dver = prov.get("deterministic_verification")
    if not dver or dver.get("status") != "PASS":
        fail(f"no independent deterministic Dream verification recorded as PASS: {dver}")
        raise SystemExit(1)
    ok(f"independent deterministic Dream verification: PASS (option_ref={dver.get('option_ref')})")

    blueprint_id = prov.get("blueprint_id") or status_data.get("blueprint_id")
    if not blueprint_id:
        fail("no blueprint_id recorded -- Blueprint was not produced from the verified option")
        raise SystemExit(1)
    ok(f"Blueprint produced from independently-verified option: blueprint_id={blueprint_id}")

    bp_data = client.call("get_stay_blueprint", {"blueprint_id": blueprint_id})
    ok(f"real tools/call get_stay_blueprint -> is_current={bp_data.get('is_current')}")

    act_data = client.call("activate_stay", {"blueprint_id": blueprint_id})
    ok(f"real tools/call activate_stay -> status={act_data.get('status')}")

    final_prov = client.call("get_stay_blueprint", {"blueprint_id": blueprint_id}).get("planner_provenance", {})
    exec_result = final_prov.get("execution_result")
    if not exec_result:
        fail("no execution_result recorded after activation")
    else:
        ok(f"execution/readback result recorded: {exec_result}")

    print()
    print("BOUNDED PROVENANCE EVIDENCE (safe to paste into exit report):")
    print(json.dumps({
        "job_id": job_id,
        "blueprint_id": blueprint_id,
        "planner_backend": final_prov.get("planner_backend"),
        "provider": final_prov.get("provider"),
        "model": final_prov.get("model"),
        "bedrock_calls": final_prov.get("bedrock_calls"),
        "grounding_calls": final_prov.get("grounding_calls"),
        "strands_version": final_prov.get("strands_version"),
        "deterministic_verification": final_prov.get("deterministic_verification"),
        "execution_result": final_prov.get("execution_result"),
    }, indent=2))

    print()
    print("OVERALL:", "PASS" if OK else "FAIL")
    raise SystemExit(0 if OK else 1)


if __name__ == "__main__":
    main()
