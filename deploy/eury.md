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
on eury use `HONCHO_URL=http://localhost:8133`.

## Environment deltas from `.env.template`

- `LLM_OPENAI_API_KEY` — set (deriver + dialectic + embeddings).
- `DERIVER_FLUSH_ENABLED=true` — **testing convenience only**: makes the
  deriver claim representation work immediately instead of batching
  (default batches until a token target or 30 min age). Remove for
  production economics.
- Auth stays off (`AUTH_USE_AUTH=false`); the API is loopback-bound.

## Consumers

- Miadi-18 worktree dev server (`/a/ws/mightyeagle`, port 3345) with
  `HONCHO_URL=http://localhost:8133 HONCHO_WORKSPACE_ID=miadi-dev`.
- Workspace `miadi-dev`: 11 bootstrapped persona/human peers plus the
  `chronicle-registry` session (miadi-chronicle episode census).

A machine-readable receipt of the live state at documentation time sits
beside this note: `eury.receipt.json`.
