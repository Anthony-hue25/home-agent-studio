"""Stdlib-only smoke test for the Gate J1 container: health, session bootstrap,
and one real Streamable HTTP MCP initialize + tools/call round trip through
the reverse proxy. Run against a container already listening on BASE_URL.
"""
import http.cookiejar
import json
import sys
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

failures = []


def get(path):
    with opener.open(f"{BASE_URL}{path}", timeout=10) as r:
        return r.status, json.loads(r.read())


def post_json(path, payload, extra_headers=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **(extra_headers or {})},
    )
    with opener.open(req, timeout=15) as r:
        return r.status, r.headers, r.read()


def parse_mcp_body(headers, raw):
    """The MCP Streamable HTTP transport may respond with a single JSON object
    (Content-Type: application/json) or with an SSE-framed stream
    (Content-Type: text/event-stream) containing one or more `data: {...}`
    lines. Handle both so this stdlib-only script doesn't need a full SSE client.
    """
    ctype = headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        text = raw.decode("utf-8", errors="replace")
        data_lines = [line[len("data:"):].strip() for line in text.splitlines() if line.startswith("data:")]
        if not data_lines:
            raise ValueError(f"no 'data:' lines found in SSE body: {text!r}")
        # Use the last event (the final JSON-RPC response), in case of interleaved frames.
        return json.loads(data_lines[-1])
    return json.loads(raw)


print(f"--- GET /health ---")
status, body = get("/health")
print(status, body)
if status != 200 or body.get("status") != "ok":
    failures.append("health endpoint did not report ok")

print(f"--- POST /session ---")
req = urllib.request.Request(f"{BASE_URL}/session", data=b"", method="POST")
with opener.open(req, timeout=10) as r:
    session_status = r.status
    session_body = json.loads(r.read())
print(session_status, session_body)
if session_status != 200 or "session_id" not in session_body:
    failures.append("session bootstrap failed")
if not any(c.name == "asp_session" for c in cj):
    failures.append("no asp_session cookie was set")

print(f"--- POST /mcp  method=initialize (real Streamable HTTP MCP handshake through the proxy) ---")
status, headers, body = post_json("/mcp", {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "container-verify", "version": "0.1"}},
})
mcp_session_id = headers.get("Mcp-Session-Id")
print(status, "Mcp-Session-Id:", mcp_session_id, "Content-Type:", headers.get("Content-Type"))
try:
    resp = parse_mcp_body(headers, body)
except Exception as e:
    resp = {}
    failures.append(f"initialize response body did not parse: {e}")
print(json.dumps(resp, indent=2)[:600])
if status != 200 or not mcp_session_id or "result" not in resp:
    failures.append("initialize did not return a valid MCP result + Mcp-Session-Id")

print(f"--- POST /mcp  notifications/initialized ---")
post_json("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"Mcp-Session-Id": mcp_session_id})

print(f"--- POST /mcp  tools/call get_stay ---")
status, headers, body = post_json("/mcp", {
    "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_stay", "arguments": {}},
}, {"Mcp-Session-Id": mcp_session_id})
try:
    resp = parse_mcp_body(headers, body)
except Exception as e:
    resp = {}
    failures.append(f"get_stay response body did not parse: {e}")
data = resp.get("result", {}).get("structuredContent", {}).get("data", {})
print(status, "status:", data.get("status"), "guests:", len(data.get("guests", [])))
if data.get("status") != "BOOKED" or len(data.get("guests", [])) != 5:
    failures.append(f"get_stay did not return the expected fixture stay: {data}")

print("\n=== RESULT ===")
if failures:
    print("FAIL:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("PASS: containerized app served /health, minted a session cookie, and completed a")
print("real Streamable HTTP MCP initialize + tools/call get_stay through the reverse proxy.")
