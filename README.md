# Sendox

AI-native multi-channel marketing platform for Shopify brands — Final Year Project,
COMSATS University Islamabad.

Multiple specialised AI agents (Strategy, Copywriting, Design, Optimization) handle the
email/SMS/WhatsApp marketing lifecycle end to end, grounded in each brand's own voice via a
RAG pipeline, with a closed feedback loop from real engagement data.

- **Scope (requirements):** `Sendox_Scope_Updated.docx` — 25 modules, FE-level requirements
- **Build plan (execution):** [`docs/BUILD-PLAN.md`](docs/BUILD-PLAN.md) — releases, phases, cut order, risks
- **Dev environment gotchas:** [`docs/DEV-ENVIRONMENT.md`](docs/DEV-ENVIRONMENT.md) — read this before debugging a machine setup problem

---

## Quick start

Prerequisites: **Node 22+** with pnpm, **uv**, and either **Docker Desktop** (preferred) or
Homebrew `postgresql@15` + `redis` for the no-Docker path.

```bash
make setup     # install Python + Node deps, create .env from .env.example
make up        # Docker: postgres, redis, chromadb, mailpit, mjml, api, worker, beat
make dev-web   # Next.js dev server on the host (faster HMR than in a container)
```

**Without Docker** — uses the Homebrew Postgres/Redis already on the machine, and runs ChromaDB
and the MJML sidecar as local processes:

```bash
make up-native   # postgres + redis + chromadb(8001) + mjml(7070)
make dev-api     # API on http://localhost:8000
make health      # expect all four checks "ok"
make down-native # stop chromadb + mjml
```

Docker remains the supported path because it pins exact service versions; `up-native` uses
Postgres 15 where compose pins 16. Mailpit has no native equivalent, so local mail capture needs
Docker (first required in phase 1.10).

| What | Where |
|---|---|
| Dev dashboard | http://localhost:3000 — live service health, capability checks, build status |
| API docs | http://localhost:8000/docs |
| Readiness report | http://localhost:8000/health/ready |
| Database + isolation state | http://localhost:8000/status/database |
| Vector store sandbox | `POST /dev/vectors/seed`, `POST /dev/vectors/query` |
| Local inbox (Mailpit) | http://localhost:8025 |
| ChromaDB | http://localhost:8001 |

`make help` lists every target. `make health` pretty-prints the readiness report —
the fastest way to see which backing service is unhappy.

## Verifying everything works

One command exercises every piece of phase 0.1 against live services — API, readiness probes,
the Redis/Celery round-trip, the API→MJML render path, ChromaDB, Mailpit and the dashboard:

```bash
make verify
```

It prints a PASS/FAIL/SKIP line per check and exits non-zero if anything required fails. Checks that
need an optional service (Mailpit under `up-native`, the web dev server) report SKIP rather than
failing. `make test` is the separate unit-test run.

## Testing the API by hand

```bash
make test-api                                    # 36 tests (integration ones need the stack up)
curl -s localhost:8000/health/live               # {"status":"ok","version":"0.1.0"}
curl -s localhost:8000/health/ready | jq         # per-dependency status + latency
open http://localhost:8000/docs                  # interactive Swagger UI
```

`/health/ready` returns **200** when every backing service answers and **503** with a per-service
reason when one does not — so it tells you *which* dependency is down, not just that something is.

The MJML sidecar is independently testable:

```bash
curl -s localhost:7070/health
curl -s -X POST localhost:7070/render -H 'content-type: application/json' \
  -d '{"mjml":"<mjml><mj-body><mj-section><mj-column><mj-text>Hi</mj-text></mj-column></mj-section></mj-body></mjml>"}' | jq
```

Invalid MJML comes back as a structured `errors` array with line numbers rather than an exception —
the Design Agent (phase 1.8) relies on that to self-correct.

## Repository layout

```
apps/
  api/                FastAPI app + Celery worker/beat (one package, two entrypoints)
    src/sendox_api/
      config.py       settings, loaded from the repo-root .env
      main.py         app factory
      health.py       dependency probes behind /health/ready
      worker.py       Celery app
      tasks.py        Celery tasks
      clients/         mjml (render sidecar), chroma (vector store), claude (LLM)
      data/           module_status.json — what is built, by release
      routers/        health, status, dev (dev is not mounted in production)
    tests/
  web/                Next.js 16 + React 19 + Tailwind dev dashboard
    src/lib/api.ts      typed API client — the one place that knows response shapes
    src/components/     service health, capability checks, build status panels
services/
  mjml/               MJML -> HTML sidecar (MJML is Node-only)
docs/
  BUILD-PLAN.md       the plan this repo is being built against
infra/                deployment config
```

**Why the worker shares the API package:** workers need the same models, settings and service
clients as the API. A separate package would mean duplicating all of it, so `worker.py` and
`main.py` are two entrypoints over one codebase.

**Why MJML is a sidecar:** MJML only runs on Node. Rather than shell out or reimplement it, the
Python API posts MJML to a tiny HTTP service and gets compiled, cross-client HTML back.

## Running things individually

```bash
make dev-api      # API on the host (needs `make up` for backing services)
make dev-worker   # Celery worker on the host
make test         # Python tests + web build
make lint         # ruff + mypy + eslint
make fmt          # auto-format
make down         # stop services, keep data
make nuke         # stop services and delete all local data
```

## Environment

Everything is configured through the repo-root `.env`; `.env.example` documents every key and
which phase first needs it. Keys left blank are not needed until their phase arrives — the API
boots fine without an Anthropic key or AWS credentials.

Secrets never go in git. `.env` is gitignored.

## The dev dashboard

`http://localhost:3000` answers "what actually works right now":

- **Backing services** — polls `/health/ready` every 10s, per-service status and latency
- **Capability checks** — buttons that run the real paths: a Celery round-trip through Redis, and an
  MJML compile through the sidecar with the resulting email previewed in an iframe
- **Build status** — all 25 scope modules plus the R0 foundation phases, grouped by release, each
  marked done / partial / planned

Status comes from `apps/api/src/sendox_api/data/module_status.json`, served at `/status/modules`.
**Update that file when a phase lands** — it is the single source of truth for progress, and a test
asserts it still covers all 25 modules.

## Tenant isolation

Every workspace's data is separated in **Postgres**, not in application code:

- tables carrying `tenant_id` have a `FORCE`'d RLS policy comparing it against the
  `app.current_tenant_id` session setting
- application sessions run as `sendox_app`, a `NOLOGIN NOSUPERUSER` role they `SET LOCAL ROLE` into —
  necessary because **Postgres skips RLS for superusers** (see `docs/DEV-ENVIRONMENT.md`)
- `db.tenant_session(settings, tenant_id)` is the only correct way to read or write tenant data;
  `global_session` is for `users` and `tenants` and deliberately sees no tenant-scoped rows

A query that forgets to filter by workspace returns nothing rather than another brand's data.
`tests/test_rls.py` proves it, including that inserting a row for another tenant is refused.

## Brand knowledge (vector store)

Each workspace gets its own Chroma collection, `brand-<tenant_id>`. **Chroma has no row-level
security**, so unlike Postgres the boundary is the collection name — and nothing in
`clients/chroma.py` accepts a collection name from a caller, it is always derived from a tenant id.

Embeddings are computed locally (all-MiniLM-L6-v2 via ONNX, 384 dims): no API key, no per-call cost.
The scope document permits this — M7 FE-2 reads "OpenAI text-embedding-3-small **or open-source
alternative**".

Try it from the dashboard, or:

```bash
curl -X POST localhost:8000/dev/vectors/seed
curl -X POST localhost:8000/dev/vectors/query -H 'content-type: application/json' \
  -d '{"query":"can I send something back?","top_k":2}'
```

The sample content mentions neither "send" nor "back" — matching happens by meaning, which is the
whole point of the RAG pipeline in M8.

## Conventions

- One phase of `docs/BUILD-PLAN.md` at a time, on a branch, CI green before merge.
- Python: ruff (lint + format) and mypy `strict`. No new `type: ignore` without a comment.
- Any dependency that is slow or large is an opt-in extra (`--extra ai`, `--extra ml`), so a
  plain install stays fast.
