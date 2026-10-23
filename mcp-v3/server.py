"""Honcho MCP server for the /v3 API.

Why this exists: every published Honcho MCP calls /v2. `@honcho-ai/mcp` tops out
at 2.2.0 and `@honcho-ai/sdk` 2.3.0 both target /v2; this server speaks /v3 only
(`/v2/workspaces/list` → 404, `/v3/workspaces/list` → 200). There is no v3 MCP
implementation published anywhere, so this is written directly against the
OpenAPI document the running server serves.

Design notes:
  * Every tool signature was derived from /openapi.json, not from memory. Where
    Honcho takes query parameters rather than a body (the `list` endpoints,
    both `context` endpoints) this passes query parameters.
  * A bearer token is required on every request except /health, and is checked
    here rather than at the proxy — so the requirement survives being published
    on a tailnet, the same way QMD's does. Refusing to start without a token is
    deliberate: the failure mode of a silently-open memory API is much worse
    than the failure mode of a container that will not boot.
"""

import os
import sys

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

HONCHO_API_URL = os.environ.get("HONCHO_API_URL", "http://api:8000").rstrip("/")
DEFAULT_WORKSPACE = os.environ.get("HONCHO_WORKSPACE_ID", "default")
BEARER_TOKEN = os.environ.get("HONCHO_MCP_BEARER_TOKEN", "").strip()
BIND_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("MCP_PORT", "8081"))

# The SDK's DNS-rebinding guard checks the Host header and answers
# "421 Invalid Host header" to anything it does not recognise. Behind the
# tailnet proxy the Host is the public name, not the container's, so it must be
# listed or every proxied request fails after passing auth.
#
# MCP_ALLOWED_HOSTS is a comma-separated list; "*" disables the check. Leaving
# rebinding protection ON with an explicit list is the safer default, and it
# costs one environment variable per deployment.
_allowed = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=("*" not in _allowed),
    allowed_hosts=_allowed or ["127.0.0.1:8081", "localhost:8081"],
    allowed_origins=["*"],
)

mcp = FastMCP("honcho-v3", transport_security=_security)
_http = httpx.Client(base_url=HONCHO_API_URL, timeout=120.0)


def _ws(workspace_id: str = "") -> str:
    return workspace_id or DEFAULT_WORKSPACE


def _call(method: str, path: str, **kw) -> dict:
    """One place where every upstream error becomes a readable tool result.

    Returning the error instead of raising keeps a 404 or a validation failure
    legible to the model, which can then correct itself, rather than surfacing
    as an opaque transport fault.
    """
    try:
        r = _http.request(method, path, **kw)
    except httpx.HTTPError as exc:
        return {"error": f"cannot reach honcho at {HONCHO_API_URL}: {exc}"}
    if r.status_code >= 400:
        return {"error": f"honcho {r.status_code} on {method} {path}", "detail": r.text[:600]}
    if not r.content:
        return {"ok": True}
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text[:2000]}


@mcp.tool()
def list_workspaces(page: int = 1, size: int = 50) -> dict:
    """List workspaces on this Honcho instance."""
    return _call("POST", "/v3/workspaces/list", params={"page": page, "size": size})


@mcp.tool()
def search(query: str, workspace_id: str = "", limit: int = 10) -> dict:
    """Semantic search across a whole workspace."""
    return _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/search",
        json={"query": query, "limit": limit},
    )


@mcp.tool()
def chat(
    peer_id: str,
    query: str,
    workspace_id: str = "",
    session_id: str = "",
    target: str = "",
) -> dict:
    """Ask *about* a peer — Honcho's dialectic endpoint.

    Answers from accumulated memory rather than returning stored rows, e.g.
    "what does this person care about?". `target` scopes the question to what
    `peer_id` understands about that other peer.
    """
    body: dict = {"query": query, "stream": False}
    if session_id:
        body["session_id"] = session_id
    if target:
        body["target"] = target
    return _call("POST", f"/v3/workspaces/{_ws(workspace_id)}/peers/{peer_id}/chat", json=body)


@mcp.tool()
def get_peer_context(
    peer_id: str,
    workspace_id: str = "",
    target: str = "",
    search_query: str = "",
    search_top_k: int = 0,
) -> dict:
    """Standing context Honcho holds for a peer."""
    params: dict = {}
    if target:
        params["target"] = target
    if search_query:
        params["search_query"] = search_query
    if search_top_k:
        params["search_top_k"] = search_top_k
    return _call(
        "GET", f"/v3/workspaces/{_ws(workspace_id)}/peers/{peer_id}/context",
        params=params or None,
    )


@mcp.tool()
def get_representation(
    peer_id: str,
    workspace_id: str = "",
    target: str = "",
    session_id: str = "",
    search_query: str = "",
    max_conclusions: int = 0,
) -> dict:
    """The model Honcho has built of a peer — inspectable, not a summary.

    POST with a body, unlike the neighbouring `context` endpoint which is a GET
    with query parameters. This was a GET here until it 405'd in real use: the
    shape was inferred from `context` instead of read from the OpenAPI document.
    """
    body: dict = {}
    if target:
        body["target"] = target
    if session_id:
        body["session_id"] = session_id
    if search_query:
        body["search_query"] = search_query
    if max_conclusions:
        body["max_conclusions"] = max_conclusions
    return _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/peers/{peer_id}/representation",
        json=body,
    )


@mcp.tool()
def list_peers(workspace_id: str = "", page: int = 1, size: int = 50) -> dict:
    """List peers (agents and humans) in a workspace."""
    return _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/peers/list",
        params={"page": page, "size": size},
    )


@mcp.tool()
def list_sessions(workspace_id: str = "", page: int = 1, size: int = 50) -> dict:
    """List sessions (conversations between peers) in a workspace."""
    return _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/sessions/list",
        params={"page": page, "size": size},
    )


@mcp.tool()
def get_session_context(
    session_id: str,
    workspace_id: str = "",
    tokens: int = 0,
    summary: bool = True,
    search_query: str = "",
) -> dict:
    """Conversation context for a session, summarised to a token budget."""
    params: dict = {"summary": summary}
    if tokens:
        params["tokens"] = tokens
    if search_query:
        params["search_query"] = search_query
    return _call(
        "GET", f"/v3/workspaces/{_ws(workspace_id)}/sessions/{session_id}/context",
        params=params,
    )


@mcp.tool()
def get_session_messages(session_id: str, workspace_id: str = "", page: int = 1, size: int = 50) -> dict:
    """Raw messages in a session."""
    return _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/sessions/{session_id}/messages/list",
        params={"page": page, "size": size},
    )


# ---------------------------------------------------------------------------
# Writes.
#
# These mutate shared memory that more than one agent reads. They live on this
# surface — behind the bearer — precisely so nobody has to reach for the REST
# API at `/`, which is currently open to the whole tailnet with no credential.
# An authenticated write path existing is what makes declining the unauthenticated
# one a real choice rather than an inconvenience.
#
# HONCHO_MCP_ALLOW_WRITES=false turns them into refusals without removing them,
# so a read-only deployment is one variable and the tool list stays honest about
# what the surface would otherwise do.
# ---------------------------------------------------------------------------

ALLOW_WRITES = os.environ.get("HONCHO_MCP_ALLOW_WRITES", "true").strip().lower() not in (
    "0", "false", "no", "off",
)


def _guard() -> dict | None:
    if ALLOW_WRITES:
        return None
    return {"error": "writes are disabled on this server (HONCHO_MCP_ALLOW_WRITES=false)"}


@mcp.tool()
def create_workspace(workspace_id: str, metadata: dict | None = None) -> dict:
    """Create a workspace. Idempotent in Honcho: an existing id is returned, not an error."""
    return _guard() or _call(
        "POST", "/v3/workspaces",
        json={"id": workspace_id, "metadata": metadata or {}},
    )


@mcp.tool()
def create_peer(peer_id: str, workspace_id: str = "", metadata: dict | None = None) -> dict:
    """Create a peer (an agent or a human) in a workspace."""
    return _guard() or _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/peers",
        json={"id": peer_id, "metadata": metadata or {}},
    )


@mcp.tool()
def set_peer_card(peer_id: str, peer_card: list[str], workspace_id: str = "") -> dict:
    """Set a peer's card — the standing self-description Honcho keeps for them."""
    return _guard() or _call(
        "PUT", f"/v3/workspaces/{_ws(workspace_id)}/peers/{peer_id}/card",
        json={"peer_card": peer_card},
    )


@mcp.tool()
def create_session(
    session_id: str,
    workspace_id: str = "",
    peers: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create a session and optionally seat peers in it.

    `peers` maps peer_id -> {"observe_me": bool, "observe_others": bool}. Setting
    observe_me here is the cheapest way to get it right, because it is a
    *session-scoped* property (see set_session_peer_config).
    """
    body: dict = {"id": session_id, "metadata": metadata or {}}
    if peers:
        body["peers"] = peers
    return _guard() or _call("POST", f"/v3/workspaces/{_ws(workspace_id)}/sessions", json=body)


@mcp.tool()
def add_peers_to_session(session_id: str, peers: dict, workspace_id: str = "") -> dict:
    """Seat additional peers in an existing session.

    `peers` maps peer_id -> {"observe_me": bool, "observe_others": bool}.
    """
    return _guard() or _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/sessions/{session_id}/peers",
        json=peers,
    )


@mcp.tool()
def set_session_peer_config(
    session_id: str,
    peer_id: str,
    workspace_id: str = "",
    observe_me: bool | None = None,
    observe_others: bool | None = None,
) -> dict:
    """Turn observation on or off for one peer in one session.

    `observe_me` is **session-scoped**: it exists only on SessionPeerConfig, not
    on the peer itself. There is no global "observe this peer everywhere" switch
    — it is set per session, here or at create_session time. A peer with
    observe_me false accrues no representation, which is why one reads as "".
    """
    body: dict = {}
    if observe_me is not None:
        body["observe_me"] = observe_me
    if observe_others is not None:
        body["observe_others"] = observe_others
    if not body:
        return {"error": "nothing to set: pass observe_me and/or observe_others"}
    return _guard() or _call(
        "PUT",
        f"/v3/workspaces/{_ws(workspace_id)}/sessions/{session_id}/peers/{peer_id}/config",
        json=body,
    )


@mcp.tool()
def add_messages_to_session(
    session_id: str,
    messages: list[dict],
    workspace_id: str = "",
) -> dict:
    """Append messages to a session. This is what the deriver learns from.

    Each message is {"content": str, "peer_id": str, "metadata": dict?}.
    Honcho accepts 1–100 per call.
    """
    if not messages:
        return {"error": "messages is empty"}
    if len(messages) > 100:
        return {"error": f"honcho accepts at most 100 messages per call, got {len(messages)}"}
    return _guard() or _call(
        "POST", f"/v3/workspaces/{_ws(workspace_id)}/sessions/{session_id}/messages",
        json={"messages": messages},
    )


@mcp.tool()
def set_metadata(
    metadata: dict,
    workspace_id: str = "",
    peer_id: str = "",
    session_id: str = "",
) -> dict:
    """Set metadata on a workspace, a peer, or a session.

    Scope is chosen by which id is supplied: peer_id wins, then session_id, then
    the workspace itself. Honcho replaces the metadata object rather than merging.
    """
    ws = _ws(workspace_id)
    if peer_id:
        path = f"/v3/workspaces/{ws}/peers/{peer_id}"
    elif session_id:
        path = f"/v3/workspaces/{ws}/sessions/{session_id}"
    else:
        path = f"/v3/workspaces/{ws}"
    return _guard() or _call("PUT", path, json={"metadata": metadata})


@mcp.tool()
def honcho_health() -> dict:
    """Upstream Honcho health, and which API this server is pointed at."""
    return {"honcho_api_url": HONCHO_API_URL, "upstream": _call("GET", "/health")}


class BearerAuth(BaseHTTPMiddleware):
    """Same contract QMD uses, so the two doors behave identically.

    /health stays open so a proxy or orchestrator can check liveness without
    holding the secret; everything else needs the token.
    """

    async def dispatch(self, request, call_next):
        if request.url.path.rstrip("/") == "/health":
            return await call_next(request)
        if request.headers.get("authorization", "") != f"Bearer {BEARER_TOKEN}":
            return JSONResponse(
                {"error": "Unauthorized: expected Authorization: Bearer <token>"},
                status_code=401,
            )
        return await call_next(request)


def main() -> None:
    if not BEARER_TOKEN:
        print(
            "refusing to start: HONCHO_MCP_BEARER_TOKEN is unset.\n"
            "This server fronts a memory API that has no auth of its own; starting "
            "without a token would publish it wide open.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    app = mcp.streamable_http_app()  # mounts the MCP endpoint at /mcp
    app.add_middleware(BearerAuth)

    @app.route("/health")
    async def _health(_request):
        return JSONResponse({"status": "ok", "honcho_api_url": HONCHO_API_URL})

    print(
        f"honcho-v3 MCP on http://{BIND_HOST}:{BIND_PORT}/mcp -> {HONCHO_API_URL} "
        f"(workspace default: {DEFAULT_WORKSPACE})\n"
        f"Auth: bearer token required ({len(BEARER_TOKEN)} chars); /health remains open",
        flush=True,
    )
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT, log_level="info")


if __name__ == "__main__":
    main()
