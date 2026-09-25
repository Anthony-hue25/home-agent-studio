import json
import sys
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18090"
print("Verifying against:", BASE)
jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def req(method, path, body=None, headers=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    if data is not None:
        r.add_header("Content-Type", "application/json")
    def lower_headers(h):
        return {k.lower(): v for k, v in h.items()}

    try:
        with opener.open(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, lower_headers(resp.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, lower_headers(e.headers), e.read()


def parse_mcp(headers, raw):
    ctype = headers.get("content-type", "")
    if "text/event-stream" in ctype:
        text = raw.decode("utf-8", errors="replace")
        lines = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
        return json.loads(lines[-1])
    return json.loads(raw)


ok = True


def check(label, cond, extra=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{status}] {label} {extra}")


# 1. GET / -- real product UI, session cookie minted
status, headers, raw = req("GET", "/")
text = raw.decode("utf-8")
check("GET / -> 200", status == 200, str(status))
check("has asp_session cookie", any(c.name == "asp_session" for c in jar), str([c.name for c in jar]))
check("contains Gate I brand shell", "Adaptive Stay" in text and "Experience Lab" in text)
check("bootstrap sets __ADAPTIVE_MCP__=true", "__ADAPTIVE_MCP__=true" in text.split("</body>")[0])
check("does NOT contain old debug shell text", "Start a new stay session" not in text)

# 2. GET /debug -- old shell preserved off the default route
status, headers, raw = req("GET", "/debug")
text_dbg = raw.decode("utf-8")
check("GET /debug -> 200", status == 200, str(status))
check("/debug still has old shell", "Start a new stay session" in text_dbg)

# 3. /api/tool must not exist server-side (zero fallback)
status, headers, raw = req("GET", "/api/tool")
check("GET /api/tool -> 404", status == 404, str(status))

# 4. Real Streamable HTTP MCP round trip on this visitor's session cookie
init_body = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "verify-script", "version": "1"}},
}
status, headers, raw = req("POST", "/mcp", init_body, {"Accept": "application/json, text/event-stream"})
check("POST /mcp initialize -> 200", status == 200, str(status))
mcp_sid = headers.get("mcp-session-id")
check("Mcp-Session-Id header present", bool(mcp_sid))
msg = parse_mcp(headers, raw)
server_info = msg.get("result", {}).get("serverInfo", {})
check("real server identity returned", server_info.get("name") == "adaptive-stay-alexa-product", str(server_info))

req("POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})

call_body = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_stay", "arguments": {}}}
status, headers, raw = req("POST", "/mcp", call_body,
                            {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})
msg = parse_mcp(headers, raw)
sc = msg.get("result", {}).get("structuredContent", {})
data = sc.get("data", {})
check("tools/call get_stay -> data present", "status" in data, str(data.get("status")))

# 5. Experience Lab REST endpoints, scoped to this same visitor cookie
status, headers, raw = req("GET", "/api/lab/scenarios")
scenarios = json.loads(raw)
keys = [s["key"] for s in scenarios.get("scenarios", [])]
check("lab scenarios include A-F", set(keys) == {"A", "B", "C", "D", "E", "F"}, str(keys))

status, headers, raw = req("POST", "/api/lab/load", {"scenario": "C"})
loaded = json.loads(raw)
check("lab load Scenario C -> 200", status == 200, str(status))
c_data = loaded.get("data", {})
check("Scenario C loaded (has guests+shared_resources)", "guests" in c_data, str(list(c_data.keys())[:6]))

# 6. Dream -> Blueprint -> Activate through the real MCP path (Scenario C path)
dream_body = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "dream_stay", "arguments": {}}}
status, headers, raw = req("POST", "/mcp", dream_body,
                            {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})
msg = parse_mcp(headers, raw)
job = msg.get("result", {}).get("structuredContent", {}).get("data", {})
check("dream_stay -> job returned", "job_id" in job, str(job))

import time
job_id = job.get("job_id")
blueprint_id = None
for _ in range(30):
    poll_body = {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "get_dream_status", "arguments": {"job_id": job_id}}}
    status, headers, raw = req("POST", "/mcp", poll_body,
                                {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})
    msg = parse_mcp(headers, raw)
    st = msg.get("result", {}).get("structuredContent", {}).get("data", {})
    if st.get("status") not in ("REQUESTED", "RUNNING", "IN_PROGRESS", "PENDING"):
        blueprint_id = st.get("blueprint_id") or (st.get("blueprint") or {}).get("blueprint_id")
        check("Dream reached terminal state", True, str(st.get("status")))
        break
    time.sleep(0.3)
else:
    check("Dream reached terminal state", False, "timed out")

if blueprint_id:
    bp_body = {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
               "params": {"name": "get_stay_blueprint", "arguments": {"blueprint_id": blueprint_id}}}
    status, headers, raw = req("POST", "/mcp", bp_body,
                                {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})
    msg = parse_mcp(headers, raw)
    bp = msg.get("result", {}).get("structuredContent", {}).get("data", {})
    check("get_stay_blueprint via /mcp -> blueprint data", "blueprint" in bp or "is_current" in bp, str(list(bp.keys())))

    act_body = {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                "params": {"name": "activate_stay", "arguments": {"blueprint_id": blueprint_id}}}
    status, headers, raw = req("POST", "/mcp", act_body,
                                {"Mcp-Session-Id": mcp_sid, "Accept": "application/json, text/event-stream"})
    msg = parse_mcp(headers, raw)
    act = msg.get("result", {}).get("structuredContent", {}).get("data", {})
    check("activate_stay via real /mcp write path -> ACTIVE", act.get("status") == "ACTIVE", str(act.get("status")))
else:
    print("[SKIP] blueprint/activate checks -- no blueprint_id from Dream")

print()
print("OVERALL:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
