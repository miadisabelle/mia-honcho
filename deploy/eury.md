# Honcho deployment — eury (gaia.jgwill.com network)

Live self-hosted Honcho backing the Miadi-18 integration
(jgwill/Miadi#502). `docker-compose.yml` and `.env` are gitignored — this
note is the durable record of how the eury deployment differs from the
defaults, so the mapping cannot be lost with the working tree.

## Port mapping (host → container)

| Service  | Host binding        | Why |
|----------|---------------------|-----|
| api      | `127.0.0.1:8133`    | **Standing rule (jgwill): local honcho must NOT occupy host :8000.** `docker-compose.yml.example` on this branch carries the same default. |
| database | `127.0.0.1:5433`    | Host :5432 already serves another Postgres. |
| redis    | `127.0.0.1:6380`    | Host :6379 already serves another Redis. |

Container-internal ports are unchanged; only host bindings differ. Clients
on eury use `HONCHO_URL=http://localhost:8133`; clients elsewhere on the
tailnet use `HONCHO_URL=https://honcho.tail3b11eb.ts.net` (see *Exposure*).

## Exposure — read this before trusting the port table

**As of 2026-08-13 this deployment is no longer loopback-only.** A Tailscale
sidecar in `docker-compose.yml` publishes the API at
**`https://honcho.tail3b11eb.ts.net`**, reachable by every device on the tailnet.
See `../TAILNET.md`.

The port table above still describes the *host* bindings accurately. It no longer
describes who can reach the API, because the sidecar proxies to `api:8000` on the
compose network and never touches the host binding at all.

**Consequence, stated plainly:** `AUTH_USE_AUTH=false` means every `/v3` endpoint
is open — **read and write** — to anything on the tailnet, with no credential.
Verified from another machine (gaia): `POST /v3/workspaces/list` returns `200`
unauthenticated and enumerates every workspace, including `miadi-dev`. Writes are
not separately gated; auth is a single global switch.

This is contained to the tailnet — there is no Funnel, so nothing is on the public
internet — but "on the tailnet" now includes every phone, laptop and container
holding a key to it, not just processes on eury.

**Held for a decision, deliberately not changed here.** Turning auth on requires a
JWT secret and updating every consumer listed below; doing that unannounced would
break the Miadi-18 dev server mid-experiment. The options, in increasing order of
cost:

1. **Tailscale ACLs** — restrict which tailnet nodes may reach the honcho node.
   No change to Honcho, no consumer breakage. Cheapest real boundary.
2. **`AUTH_USE_AUTH=true`** + `AUTH_JWT_SECRET`, then reissue tokens to consumers.
   The actual fix; costs a coordinated consumer update.
3. **Unpublish** — stop the `tailscale` sidecar and return to loopback-only,
   which restores the original justification and gives up network-wide memory.

Until one is chosen, treat every workspace on this instance as readable and
writable by anything on the tailnet.

## Environment deltas from `.env.template`

- `LLM_OPENAI_API_KEY` — set (deriver + dialectic + embeddings).
- `DERIVER_FLUSH_ENABLED=true` — **testing convenience only**: makes the
  deriver claim representation work immediately instead of batching
  (default batches until a token target or 30 min age). Remove for
  production economics.
- `AUTH_USE_AUTH=false` — auth is off. **The justification that used to sit here
  ("the API is loopback-bound") is no longer true.** See *Exposure* below.

## Consumers

- Miadi-18 worktree dev server (`/a/ws/mightyeagle`, port 3345) with
  `HONCHO_URL=http://localhost:8133 HONCHO_WORKSPACE_ID=miadi-dev`.
- Workspace `miadi-dev`: 11 bootstrapped persona/human peers plus the
  `chronicle-registry` session (miadi-chronicle episode census).

A machine-readable receipt of the live state at documentation time sits
beside this note: `eury.receipt.json`.
