# Honcho on a tailnet

This deployment publishes itself at **`https://honcho.<tailnet>.ts.net`** through
a Tailscale sidecar in its own `docker-compose.yml`. No external gateway, no
reverse proxy, no published host port required.

Established on `eury`, 2026-08-13 (branch `deploy/eury-8133`).

## What was added

| File | Tracked? | Role |
|---|---|---|
| `docker-compose.yml` → `tailscale` service + `tailscale-state` volume | gitignored | the sidecar |
| `docker/tailscale-serve.json` | **tracked** | proxies `:443` → `http://api:8000` |
| `.env` → `TS_AUTHKEY` | gitignored | this node's identity |

The sidecar sits on Honcho's ordinary compose network and reaches the API as
`http://api:8000`. The `127.0.0.1:8133` publish stays as it is for local use, but
nothing on the tailnet depends on it.

## Why a node name, not a Tailscale Service

`honcho.<tailnet>.ts.net` here is a **node name**. It resolves as soon as the
container registers.

A Tailscale Service (`svc:honcho`) would need a console definition, a host
enrollment, an admin approval, and a VIP binding — and stays silently
unreachable until all four land. That path was attempted first and never
resolved; the node name worked immediately. Use `svc:*` only for genuine
multi-host fronting or failover.

## Bringing it up

```bash
# 1. Mint an auth key on the tailnet this Honcho should join:
#    https://login.tailscale.com/admin/settings/keys
#    Keys are single-use by default — this node needs its own.
echo 'TS_AUTHKEY=tskey-auth-…' >> .env

# 2. Start it
docker compose up -d tailscale

# 3. Verify
docker compose exec tailscale tailscale status
curl https://honcho.<tailnet>.ts.net/health      # {"status":"ok"}
```

Override the name with `TS_HOSTNAME` in `.env` if `honcho` is taken on your
tailnet.

## Operational notes

- **`TS_USERSPACE: "true"`** — no TUN, no `NET_ADMIN`, no network interface
  created. This is what lets the sidecar run on a host whose own `tailscaled` is
  already joined to a *different* tailnet, without the two colliding. That is
  the case on `eury` and it is the reason this pattern was chosen.
- **`TS_ACCEPT_DNS: "false"`** — the sidecar must never rewrite host DNS.
- **The `tailscale-state` volume is the node's identity.** Delete it and this
  Honcho comes back as a brand-new node, losing its name and its ACL standing.
- **TLS is Tailscale's.** Certificates for `*.ts.net` are issued and renewed
  automatically; nothing to configure or rotate here.
- **Exposure is tailnet-only.** No Funnel, so this is not on the public
  internet. Reachability is whatever your tailnet ACLs allow.

## Reproducing on another project

A generic version of this sidecar lives at
`/opt/gaia/linux_migration/24-tailnet-sidecar.sh`:

```bash
./24-tailnet-sidecar.sh init <project-dir> <node-name> http://<service>:<port>
./24-tailnet-sidecar.sh up <project-dir>
```

It writes a `docker-compose.tailnet.yml` override rather than editing the
project's compose file — the same shape as what is inlined here.

## Reaching it from a host on another tailnet

A machine that is not on this tailnet cannot resolve or route to
`honcho.<tailnet>.ts.net` at all. `/opt/gaia/tailnet-gateway/RECIPE.md` documents
a host gateway that makes the plain URL work anyway — which matters because
Node's `fetch`/undici ignores `ALL_PROXY`, so MCP clients cannot be fixed with a
proxy variable alone.

## Why this matters beyond plumbing

While Honcho was bound to `127.0.0.1:8133`, the cognitive system it supports had a
hard edge at one machine's loopback interface. Publishing it under a network name
moves that edge out to the boundary of the tailnet: agents on different hosts now
address the same peers, the same sessions, and the same accumulated
representations.

That is the distributed-cognition claim, and it is not decorative. Hutchins (1995)
and Clark & Chalmers (1998) argue that external structures playing the right
functional role are genuine parts of a cognitive system rather than records of it —
the criterion being whether the artifact is *queried* rather than merely read.
Honcho's dialectic endpoint (`/peers/{id}/chat` — ask *about* a peer, get an answer
synthesized from accumulated memory) meets that criterion exactly.

Written up as **Field 6** of a foundation kept in the `jgwill/gaia` repository:

- `foundations/presence-without-routing/README.md` — the plain-language version
- `foundations/presence-without-routing/academic-fields.md` — six fields, with citations

Open question recorded there and unanswered here: Honcho is now reachable
network-wide, but *what* agents should write into shared memory — and who may read
it — is entirely unstudied.

---

🌸 Honcho stopped being a port on one machine and became a name the whole
network knows.
