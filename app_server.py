"""Gate J1 public container entrypoint.

Wraps the UNMODIFIED alexa_product_mcp.py Streamable HTTP MCP server with:
  - GET  /health              -- health endpoint
  - POST /session             -- mint a per-visitor session (simulator
                                  convenience; NOT an MCP tool, NOT part of
                                  the frozen nine-tool surface)
  - GET  /                    -- landing page (session-aware MCP browser demo)
  - ANY  /mcp                 -- opaque byte-for-byte reverse proxy into that
                                  visitor's own build_alexa_product_server()
                                  instance, selected by session cookie

Every visitor gets their own AdaptiveStayProductService and their own
build_alexa_product_server(...) FastMCP instance bound to a loopback port
inside this one container -- exactly the mechanism already falsified locally
in public_session_shim.py. This file adds only hosting/session-boundary code;
alexa_product_mcp.py and the studio product/domain modules are untouched.
"""
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock, Thread

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from studio.adaptive_product_demo import (
    LAB_SCENARIOS,
    create_demo_stay_from_scratch,
    demo_service,
    load_lab_scenario,
    load_next_demo_stay,
)
from studio.alexa_product_mcp import build_alexa_product_server
from studio.alexa_product_ui import standalone_html

COOKIE_NAME = "asp_session"
MAX_CONCURRENT_SESSIONS = int(os.environ.get("MAX_CONCURRENT_SESSIONS", "25"))
SESSION_IDLE_TTL_SECONDS = int(os.environ.get("SESSION_IDLE_TTL_SECONDS", "1800"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
PLANNER_KIND = os.environ.get("PLANNER_KIND", "Fixture")  # Fixture until the
# LiveStayPlanner credential-resolution fix is applied and explicitly approved
# for this deployment; flipping to "Live" needs no other code change here.
BUILD_LABEL = os.environ.get("BUILD_LABEL", "dev")


@dataclass
class VisitorSession:
    session_id: str
    service: object
    port: int
    _socket: socket.socket = field(repr=False)
    _server: uvicorn.Server = field(repr=False)
    _thread: Thread = field(repr=False)
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self):
        self.last_seen = time.monotonic()

    def close(self):
        self._server.should_exit = True
        self._thread.join(timeout=5)
        self._socket.close()


class SessionRegistry:
    def __init__(self, planner_kind=PLANNER_KIND, max_sessions=MAX_CONCURRENT_SESSIONS,
                 idle_ttl=SESSION_IDLE_TTL_SECONDS):
        self.planner_kind = planner_kind
        self.max_sessions = max_sessions
        self.idle_ttl = idle_ttl
        self._sessions: dict[str, VisitorSession] = {}
        self._lock = Lock()

    def _evict_idle(self):
        now = time.monotonic()
        stale = [sid for sid, s in self._sessions.items() if now - s.last_seen > self.idle_ttl]
        for sid in stale:
            self._sessions.pop(sid).close()

    def create(self) -> VisitorSession:
        with self._lock:
            self._evict_idle()
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError("SESSION_CAPACITY_REACHED")
            session_id = uuid.uuid4().hex
            service = demo_service(self.planner_kind)

            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sock.listen(64)
            port = sock.getsockname()[1]

            mcp = build_alexa_product_server(service, port, write_authorized=True)
            server = uvicorn.Server(
                uvicorn.Config(mcp.streamable_http_app(), log_level="warning", access_log=False)
            )
            thread = Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
            thread.start()
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.02)
            if not server.started:
                sock.close()
                raise RuntimeError("VISITOR_MCP_START_FAILED")

            session = VisitorSession(session_id, service, port, sock, server, thread)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> VisitorSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                if time.monotonic() - session.last_seen > self.idle_ttl:
                    self._sessions.pop(session_id).close()
                    return None
                session.touch()
            return session

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


registry = SessionRegistry()
_http_client = httpx.AsyncClient()

_LANDING_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Adaptive Stay -- Gate J1 public demo</title>
<style>body{font-family:system-ui,sans-serif;background:#0b0f14;color:#e7edf3;padding:32px;max-width:760px;margin:0 auto}
button{padding:10px 18px;font-size:15px;border-radius:6px;border:none;background:#3b82f6;color:#fff;cursor:pointer;margin:6px 6px 6px 0}
pre{white-space:pre-wrap;background:#11161d;padding:14px;border-radius:8px;border:1px solid #223;min-height:120px}
.note{color:#9db;font-size:13px}</style></head>
<body>
<h1>Adaptive Stay -- public demo (Gate J1)</h1>
<p class="note">Physical device execution is simulated in this build. This container speaks the same nine-tool Streamable HTTP MCP contract Alexa+ uses.</p>
<button id="start">Start a new stay session</button>
<button id="get_stay" disabled>get_stay</button>
<pre id="log">(no session yet)</pre>
<script>
const log = (...a) => { document.getElementById('log').textContent += a.join(' ') + '\\n'; };
class McpClient {
  constructor(url){ this.url=url; this.sessionId=null; this.nextId=1; }
  async _post(body, expectResponse=true){
    const headers = {'Content-Type':'application/json','Accept':'application/json, text/event-stream'};
    if (this.sessionId) headers['Mcp-Session-Id']=this.sessionId;
    const res = await fetch(this.url,{method:'POST',headers,body:JSON.stringify(body),credentials:'same-origin'});
    const sid = res.headers.get('Mcp-Session-Id'); if (sid) this.sessionId=sid;
    if (!expectResponse) return null;
    const ct = res.headers.get('Content-Type')||'';
    if (ct.includes('application/json')) return await res.json();
    if (ct.includes('text/event-stream')){
      const text = await res.text();
      for (const block of text.split('\\n\\n')){
        const line = block.split('\\n').find(l=>l.startsWith('data:'));
        if (line){ const p=JSON.parse(line.slice(5).trim()); if (p.id!==undefined||p.method) return p; }
      }
      throw new Error('no JSON-RPC message in SSE body');
    }
    throw new Error('unexpected content-type '+ct);
  }
  async initialize(){
    const r = await this._post({jsonrpc:'2.0',id:this.nextId++,method:'initialize',
      params:{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'adaptive-stay-public-browser',version:'0.1'}}});
    await this._post({jsonrpc:'2.0',method:'notifications/initialized'}, false);
    return r;
  }
  async callTool(name,args){
    const r = await this._post({jsonrpc:'2.0',id:this.nextId++,method:'tools/call',params:{name,arguments:args||{}}});
    if (r.error) throw new Error(name+' -> '+JSON.stringify(r.error));
    return r.result.structuredContent.data;
  }
}
const mcp = new McpClient('/mcp');
document.getElementById('start').onclick = async () => {
  const res = await fetch('/session', {method:'POST', credentials:'same-origin'});
  const body = await res.json();
  log('session started:', body.session_id.slice(0,8));
  await mcp.initialize();
  log('MCP initialize OK, Mcp-Session-Id =', mcp.sessionId);
  document.getElementById('get_stay').disabled = false;
};
document.getElementById('get_stay').onclick = async () => {
  const data = await mcp.callTool('get_stay');
  log('get_stay ->', JSON.stringify({status:data.status, guests:data.guests.length}));
};
</script>
</body></html>"""


async def health(request):
    return JSONResponse({
        "status": "ok",
        "planner": PLANNER_KIND,
        "build": BUILD_LABEL,
        "active_sessions": registry.count(),
    })


async def landing(request):
    """Judge-facing root: the real Gate I Adaptive Stay product UI
    (mcp_app_html()'s bundle, via standalone_html(mcp=True)), talking real
    Streamable HTTP MCP to this visitor's own /mcp endpoint. A session is
    minted here -- reusing one already on the cookie, if still valid -- so
    the page never shows the raw "start a session" debug step judges saw
    before; the /session endpoint itself is untouched for anything that
    still wants to call it directly.
    """
    session_id = request.cookies.get(COOKIE_NAME)
    session = registry.get(session_id) if session_id else None
    needs_cookie = session is None
    if session is None:
        try:
            session = registry.create()
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
    response = HTMLResponse(standalone_html(mcp=True))
    if needs_cookie:
        response.set_cookie(
            COOKIE_NAME, session.session_id, httponly=True, samesite="strict",
            secure=COOKIE_SECURE, path="/", max_age=SESSION_IDLE_TTL_SECONDS,
        )
    return response


async def debug_shell(request):
    """Temporary Gate J1 engineering shell, moved off the default route so
    judges land in the real product UI. Kept as a non-default diagnostic
    route only.
    """
    return HTMLResponse(_LANDING_PAGE)


def _visitor_session(request):
    """Resolve the requesting visitor's own session for the local Experience
    Lab convenience endpoints below. These are plain REST -- never MCP tools
    -- and always operate on that one visitor's own service instance, never
    a shared singleton.
    """
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return None
    return registry.get(session_id)


async def lab_scenarios(request):
    session = _visitor_session(request)
    if session is None:
        return JSONResponse({"error": "NO_SESSION", "hint": "GET / first"}, status_code=400)
    return JSONResponse({
        "scenarios": [
            {"key": key, "label": f"{key} — {label}", "description": description}
            for key, _, label, description in LAB_SCENARIOS
        ],
        "property_rooms": list(session.service.store.property_twin.room_ids),
    })


async def lab_load(request):
    session = _visitor_session(request)
    if session is None:
        return JSONResponse({"error": "NO_SESSION", "hint": "GET / first"}, status_code=400)
    try:
        payload = await request.json()
        if type(payload) is not dict or set(payload) != {"scenario"}:
            raise ValueError("exact scenario request required")
        return JSONResponse(load_lab_scenario(session.service, payload["scenario"]))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def lab_create_stay(request):
    session = _visitor_session(request)
    if session is None:
        return JSONResponse({"error": "NO_SESSION", "hint": "GET / first"}, status_code=400)
    try:
        payload = await request.json()
        if type(payload) is not dict or set(payload) != {"guests"}:
            raise ValueError("exact create-stay request required")
        return JSONResponse(create_demo_stay_from_scratch(session.service, payload["guests"]))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def demo_next_stay(request):
    session = _visitor_session(request)
    if session is None:
        return JSONResponse({"error": "NO_SESSION", "hint": "GET / first"}, status_code=400)
    try:
        return JSONResponse(load_next_demo_stay(session.service))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def start_session(request):
    try:
        session = registry.create()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    response = JSONResponse({"session_id": session.session_id})
    response.set_cookie(
        COOKIE_NAME, session.session_id, httponly=True, samesite="strict",
        secure=COOKIE_SECURE, path="/", max_age=SESSION_IDLE_TTL_SECONDS,
    )
    return response


_HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "upgrade", "content-length"}


async def mcp_proxy(request):
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return JSONResponse({"error": "NO_SESSION", "hint": "POST /session first"}, status_code=400)
    session = registry.get(session_id)
    if session is None:
        return JSONResponse({"error": "UNKNOWN_OR_EXPIRED_SESSION"}, status_code=400)

    target = f"http://127.0.0.1:{session.port}/mcp"
    body = await request.body()
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP and k.lower() not in ("host", "origin")
    }
    # The frozen inner per-visitor MCP server (alexa_product_mcp.py's
    # build_alexa_product_server) enforces its own DNS-rebinding protection,
    # allowlisting only its own loopback host:port as a valid Origin -- exactly
    # right for a server that should never be reached except through this
    # proxy. A real public browser sends its own Origin (the public ECS
    # domain), which that allowlist correctly rejects with 403 "Invalid
    # Origin header" -- this proxy IS the trusted boundary that Origin
    # crosses, so it presents this hop as the loopback-local caller the inner
    # server expects, rather than forwarding the browser's own Origin through
    # unchanged. (Host is already dropped above for the same reason --
    # httpx sets the correct loopback Host itself.)
    forward_headers["Origin"] = f"http://127.0.0.1:{session.port}"

    upstream_req = _http_client.build_request(request.method, target, headers=forward_headers, content=body)
    upstream_resp = await _http_client.send(upstream_req, stream=True)

    resp_headers = {k: v for k, v in upstream_resp.headers.items() if k.lower() not in _HOP_BY_HOP}

    async def stream():
        async for chunk in upstream_resp.aiter_raw():
            yield chunk
        await upstream_resp.aclose()

    return StreamingResponse(stream(), status_code=upstream_resp.status_code, headers=resp_headers)


app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/", landing, methods=["GET"]),
    Route("/debug", debug_shell, methods=["GET"]),
    Route("/session", start_session, methods=["POST"]),
    Route("/mcp", mcp_proxy, methods=["GET", "POST", "DELETE"]),
    Route("/api/lab/scenarios", lab_scenarios, methods=["GET"]),
    Route("/api/lab/load", lab_load, methods=["POST"]),
    Route("/api/lab/create-stay", lab_create_stay, methods=["POST"]),
    Route("/api/demo-next-stay", demo_next_stay, methods=["POST"]),
])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
