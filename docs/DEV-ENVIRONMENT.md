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

## Local service versions differ from compose

`make up-native` uses the machine's Homebrew Postgres **15**; compose pins **16**. Everything we use
works on both, including row-level security. Compose is the parity reference — if something behaves
oddly under `up-native`, check it under `make up` before debugging further.
