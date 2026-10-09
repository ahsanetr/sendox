# Dev environment notes

Things that are not obvious from the code and will cost an hour if rediscovered from scratch.

## The dev network has no IPv6 route

`route -n get -inet6 default` returns "not in table" and no interface has a global IPv6 address.
Docker Desktop still resolved `registry-1.docker.io` to its AAAA records and tried IPv6 anyway,
failing every pull with:

```
dial tcp [2600:1f18:...]:443: connect: no route to host
```

It does **not** fall back to IPv4 on its own. Fix — in `~/.docker/daemon.json`:

```json
{ "ipv6": false }
```

then restart Docker Desktop (`docker desktop restart`). Pulls work immediately afterwards.

This file is per-machine and not in the repo, so **every new dev machine on this network needs it.**

## `ghcr.io` is unreachable

Both `brew` (installing uv) and `docker build` (`COPY --from=ghcr.io/astral-sh/uv`) failed against
GitHub Container Registry — DNS failure from the shell, connection timeout from the Docker daemon
(`dial tcp 20.207.73.86:443: i/o timeout`). `docker.io` and `pypi.org` are both fine.

Consequences, already handled in-repo:

- `apps/api/Dockerfile` installs uv with `pip install uv` from PyPI instead of copying it from the
  ghcr.io image. **Do not "optimise" this back to `COPY --from=ghcr.io/astral-sh/uv`** — it will
  build in CI and fail on this network.
- uv was installed locally into a dedicated venv symlinked onto `PATH`:
  `~/.local/share/sendox-tools/uv-venv/bin/uv` → `~/.local/bin/uv`, with `~/.local/bin` prepended
  to `PATH` in `~/.zshrc`.

If you later need a ghcr.io image, mirror it through Docker Hub rather than fighting the network.

## apt inside the API image is slow and occasionally flaky

The first build failed with `E: Unable to locate package curl` because `apt-get update` had not
completed cleanly. Retrying worked. The image now installs **only `curl`** (for the container
healthcheck) — `build-essential` was dropped because `psycopg[binary]` and `chromadb` both ship
wheels for linux/arm64, which cut the build substantially and removed most of the flakiness.

## ChromaDB 1.x removed the v1 API

`/api/v1/heartbeat` returns `410 Gone`. Health probes and the compose healthcheck both use
`/api/v2/heartbeat`. The scope document says "ChromaDB 0.5+" — that is a different API generation
from the 1.5.9 client we actually run. `tests/test_health_probe_paths.py` pins the probe paths so
this cannot silently regress.

## Postgres superusers silently bypass row-level security

This one cost real time and is easy to get wrong without noticing.

The official postgres image makes `POSTGRES_USER` (our `sendox`) the **bootstrap superuser**, and
Postgres skips RLS policies entirely for superusers — even with `FORCE ROW LEVEL SECURITY`. The
policies existed, `pg_policy` listed them, and a cross-tenant read still returned another tenant's
rows. Only a behavioural test caught it; a "does a policy exist?" check passed happily.

Demoting the role does not work either: `ALTER ROLE sendox NOSUPERUSER` fails with *"the bootstrap
user must have the SUPERUSER attribute"*.

The fix, in the initial migration and `db.py`:

- a `sendox_app` role — `NOLOGIN NOSUPERUSER`, so nothing can connect as it directly and it needs no
  password — is granted DML on `public`, plus `ALTER DEFAULT PRIVILEGES` so future tables are covered
- every application session issues `SET LOCAL ROLE sendox_app` before touching data, making
  `current_user` a non-superuser so policies apply
- migrations keep running as the owner, which still needs full rights

`tests/test_rls.py::test_application_sessions_are_not_superuser` is the guard. If it ever fails, the
isolation tests after it are passing vacuously. `/status/database` reports the same thing at runtime
via its `enforced` field, and the dashboard shows it.

## The embedding model is baked into the API image

Embeddings run locally through Chroma's default model (all-MiniLM-L6-v2 via ONNX, 384 dimensions) —
no API key, no per-call cost, no torch. The model is ~79MB and Chroma downloads it from S3 on first
use.

On this connection that download takes about two minutes, so a container that fetched it at startup
never became healthy in time. The Dockerfile now warms the model at **build** time so it lives in an
image layer, and the app's startup warmup is fired as a background task rather than awaited — a cold
cache must never block readiness.

If you see `onnx.tar.gz` progress bars in `docker compose logs api`, the bake step did not run and
the image needs rebuilding.

## Keep slow synchronous work off the event loop

Chroma's client is synchronous and embedding a batch takes seconds. Calling it straight from an async
FastAPI handler blocked the event loop and made a concurrent 10-second health check time out.

`clients/chroma.py` therefore exposes async wrappers (`aupsert_chunks`, `aquery`, `astats`, `adrop`)
that run the sync functions via `asyncio.to_thread`. **Request handlers use those**; Celery tasks can
call the sync versions directly. The same applies to SQLAlchemy, which is synchronous here too.

`tests/test_event_loop.py` pins it: a health check must answer in under three seconds while a seed
is in flight.

## Celery's prefork pool does not work on the macOS host

A worker started with the default pool accepts tasks and fails every one of them with:

```
ValueError: not enough values to unpack (expected 3, got 0)
```

...from inside Celery's `fast_trace_task`. The forked child never gets the worker-optimisation state
set up — a macOS fork-safety problem, not a bug in our code. The identical worker is fine inside the
Docker image, which is Linux.

So `make dev-worker` runs `--pool=threads --concurrency=4`. Our work is I/O bound (SMTP, HTTP to
Shopify and Anthropic, database), so threads are a good fit anyway. **Compose keeps the default
prefork pool**, because that is what production will run and we want CI exercising it.

If you start a worker by hand, pass `--pool=threads` or tasks will fail in a confusing way.

## Local service versions differ from compose

`make up-native` uses the machine's Homebrew Postgres **15**; compose pins **16**. Everything we use
works on both, including row-level security. Compose is the parity reference — if something behaves
oddly under `up-native`, check it under `make up` before debugging further.
