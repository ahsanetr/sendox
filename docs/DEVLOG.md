# Sendox — development log

What was built, why it was built that way, and what broke along the way. Written to be read
alongside the code: each entry names the files involved so you can go and look.

- **Scope (requirements):** `Sendox_Scope_Updated.docx` — 25 modules
- **Plan (sequencing):** `docs/BUILD-PLAN.md`
- **Environment gotchas:** `docs/DEV-ENVIRONMENT.md`
- **Live status:** http://localhost:3000 · progress data at `/status/modules`

Newest entry last, so the file reads as a history.

---

## Phase 0.1 + 0.4 — the walking skeleton · 8 Oct 2026

**Goal:** one request that crosses every layer, so later phases have somewhere to land.

### What was built

A monorepo with four runnable pieces:

| Piece | Where | Why it exists |
|---|---|---|
| FastAPI app | `apps/api/src/sendox_api/main.py` | the HTTP API |
| Celery worker + beat | `apps/api/src/sendox_api/worker.py`, `tasks.py` | background jobs (email sending, syncs, AI generation later) |
| Next.js dashboard | `apps/web` | the UI, and our own window into what works |
| MJML sidecar | `services/mjml/server.js` | compiles email markup to cross-client HTML |

Plus `docker-compose.yml` wiring in Postgres, Redis, ChromaDB and Mailpit.

### Concepts worth understanding

**Why the worker shares the API's Python package.** `worker.py` and `main.py` are two *entrypoints*
over one codebase. A worker needs the same database models, settings and service clients as the API.
A separate package would mean duplicating all of it and keeping two copies in sync. The compose file
runs the same image with different commands.

**Why MJML is a separate HTTP service.** MJML is a Node library and our backend is Python. Three
options existed: shell out to the `mjml` CLI per render (slow, fragile), reimplement it (absurd), or
run it as a tiny HTTP service the API posts to. The third is what `services/mjml` is — about 80
lines, no state, no database. `clients/mjml.py` is the Python side.

**The readiness endpoint is the centrepiece.** `GET /health/ready` (`health.py`) probes Postgres,
Redis, ChromaDB and MJML *concurrently*, each time-boxed to 3 seconds, and returns a per-service
status with latency:

```json
{"status": "degraded", "checks": {"postgres": {"status": "error", "detail": "connection refused"}}}
```

This matters more than it looks. "Is the stack wired up?" becomes a testable claim rather than a
hope, and when something breaks you learn *which* dependency died instead of staring at a generic
500. Note that no probe is allowed to raise — a dead dependency is *reported*, never propagated.

**Liveness vs readiness** is a standard distinction worth knowing: *liveness* asks "is this process
alive?" (restart me if not), *readiness* asks "can I serve traffic?" (stop sending me requests if
not). They have different endpoints because they have different consequences.

### What we hit

1. **`ghcr.io` is unreachable on this network.** Both `brew install uv` and the Dockerfile's
   `COPY --from=ghcr.io/astral-sh/uv` failed. The Dockerfile now does `pip install uv` from PyPI.
   *Do not "optimise" that back* — it will build in CI and fail here.
2. **No IPv6 route, but Docker tried IPv6 anyway.** Docker resolved Docker Hub's AAAA records and
   failed with `no route to host`, never falling back to IPv4. Fixed with `{"ipv6": false}` in
   `~/.docker/daemon.json`.
3. **A test found a real bug.** The readiness route resolved settings through a cached
   `get_settings()`, so it ignored the settings `create_app(settings)` was handed — a test pointing
   probes at dead ports still hit the live services and passed for the wrong reason. Fixed by adding
   `dependencies.py`, which reads settings off `app.state` per request. Worth internalising: a test
   that passes for the wrong reason is worse than no test.

### Verified

`make verify` — 15 checks against live services. 17 API tests, 3 MJML tests, ruff + mypy strict +
eslint clean.

---

## Phase 0.2 — schema and tenant isolation · 8 Oct 2026

**Goal:** a database schema, migrations, and the guarantee that one brand can never read another's
data.

### What was built

Alembic migrations and four tables (`apps/api/src/sendox_api/models/`): `tenants` (workspaces),
`users`, `memberships` (who may do what, where) and `audit_logs`.

`db.py` exposes the only correct ways to reach the database:

- `tenant_session(settings, tenant_id)` — can see exactly one workspace's rows
- `user_session(settings, user_id)` — can see which workspaces one person belongs to
- `global_session(settings)` — for `users` and `tenants`; sees **no** tenant-scoped rows at all

### The central idea: isolation belongs in the database

The naive approach is `WHERE tenant_id = ?` in every query. It works until the one query somebody
forgets, and then one customer sees another's data. That is the classic multi-tenant SaaS failure.

Instead we use **Postgres row-level security (RLS)**. Each tenant-scoped table carries a policy:

```sql
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_logs
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

`USING` filters what you can *read*; `WITH CHECK` constrains what you can *write*. The session
announces its context with `set_config('app.current_tenant_id', '<uuid>', true)` — the `true` makes
it **transaction-local**, which is what stops a pooled connection from carrying one request's
identity into the next.

The result: a query that forgets to filter by workspace returns **nothing**, and an insert labelled
with the wrong tenant is **refused**. The mistake becomes a bug you notice immediately rather than a
breach you notice never.

### The bug that made this real

The policies existed. `pg_policy` listed them. A cross-tenant read **still returned the other
tenant's rows.**

Cause: **Postgres skips RLS entirely for superusers**, even with `FORCE`. The official Postgres
Docker image makes `POSTGRES_USER` the bootstrap superuser. And that user cannot be demoted —
`ALTER ROLE sendox NOSUPERUSER` fails with *"the bootstrap user must have the SUPERUSER attribute"*.

The fix (in the initial migration and `db.py`):

- a `sendox_app` role — `NOLOGIN NOSUPERUSER`, so nothing can connect as it and it needs no password
- it holds DML on `public`, with `ALTER DEFAULT PRIVILEGES` so future tables are covered automatically
- every application session runs `SET LOCAL ROLE sendox_app` before touching data, making
  `current_user` a non-superuser so policies apply
- migrations keep running as the owner, which still needs full rights

`tests/test_rls.py::test_application_sessions_are_not_superuser` guards the precondition. Without it,
every isolation test after it could pass vacuously. **The lesson: a structural check ("does a policy
exist?") passed happily while the behaviour was broken. Only a behavioural test caught it.**

### Verified

7 isolation tests, including that inserting a row for another tenant is refused. `/status/database`
reports the same facts at runtime with a single `enforced` flag, shown on the dashboard.

---

## Phase 0.5 — brand knowledge vector store · 8 Oct 2026

**Goal:** the retrieval half of the RAG pipeline (scope M7/M8), plus the LLM transport.

### What RAG is, briefly

Retrieval-Augmented Generation. Instead of fine-tuning a model on each brand, you keep the brand's
own text in a searchable store, fetch the most relevant pieces at generation time, and paste them
into the prompt. The model stays generic; the *context* is brand-specific. Far cheaper than training,
and updating the brand's knowledge is just re-indexing text.

### How search by meaning works

Text is converted to an **embedding** — a vector of 384 numbers positioned so that text with similar
meaning lands nearby. A query becomes a vector the same way, and retrieval is "find the nearest
stored vectors", measured by cosine distance.

That is why this works:

```
query: "can I send something back if it does not fit"
top hit: "Returns accepted within 60 days, worn or unworn."   (similarity 0.60)
```

The stored sentence contains neither "send" nor "back". Keyword search finds nothing; meaning-based
search finds the right answer. This is the mechanism the Copywriting Agent will rely on in M10.

### What was built

`apps/api/src/sendox_api/clients/chroma.py`:

- **one Chroma collection per workspace**, named `brand-<tenant_id>`
- embeddings computed **locally** — all-MiniLM-L6-v2 via ONNX, 384 dimensions, no API key, no
  per-call cost (the scope allows this: M7 FE-2 says "OpenAI text-embedding-3-small **or open-source
  alternative**")
- `upsert` replaces by id rather than appending, so re-crawling a storefront does not multiply the
  knowledge base (M7 FE-5)

**Isolation here is a different mechanism from Postgres, and that is worth noticing.** Chroma has no
row-level security. The boundary is the collection name — so no function in that module accepts a
collection name from a caller; it is always *derived* from a tenant id. Same guarantee, enforced a
different way, because the tool is different.

`clients/claude.py` is the LLM transport: model choice, and a clear "is it configured?" answer so a
missing API key produces a readable message rather than a stack trace mid-request.

### Two bugs worth learning from

**1. Embedding blocked the event loop.** Chroma's client is synchronous and embedding takes seconds.
Called directly from an `async def` handler, it blocked the entire event loop — a concurrent
10-second health check timed out, which is how we noticed.

Why: an async server runs one thread handling many requests by switching whenever a request `await`s.
Synchronous CPU or blocking I/O never yields, so *every other request waits*. The fix is
`asyncio.to_thread`, which moves the blocking call to a thread pool:

```python
async def aquery(settings, tenant_id, text, top_k=DEFAULT_TOP_K):
    return await asyncio.to_thread(query, settings, tenant_id, text, top_k)
```

Request handlers use the `a`-prefixed wrappers; Celery tasks can call the sync versions directly
because a worker process is not serving other requests. `tests/test_event_loop.py` pins it: a health
check must answer within 3 seconds while a seed is in flight. **The same caution applies to
SQLAlchemy, which is synchronous here too.**

**2. The 79MB model was re-downloaded on every container start**, taking ~2 minutes on this
connection, so the API never became healthy. Now baked into the image at build time, and the startup
warmup is a *background task* rather than awaited — a cold cache must never block readiness.

### Verified

7 vector-store tests including that one workspace cannot retrieve another's chunks. Dashboard panel
with seed / semantic search / drop.

---

## Phase 0.3 + 1.1 (M1) — accounts, workspaces and roles · 9 Oct 2026

**Goal:** real authentication, workspaces people can switch between, and roles that are actually
enforced. This is the prerequisite for connecting a Shopify store, because a store connects *to* a
workspace.

### What was built

| Area | Files |
|---|---|
| Password hashing, JWTs, one-time tokens | `security.py` |
| Transactional email | `email.py`, `tasks.py` |
| Registration, verification, login, reset | `services/auth.py`, `routers/auth.py` |
| Workspaces, roles, invitations | `services/workspaces.py`, `routers/workspaces.py` |
| Accepting an invitation | `routers/invitations.py` |
| Who-is-this / what-may-they-do | `dependencies.py` |
| Web UI | `apps/web/src/app/account/`, `components/auth-panel.tsx`, `components/workspace-panel.tsx` |

### Security decisions, and the reasoning

**Passwords use Argon2id** (`pwdlib`), not SHA-256. General-purpose hashes are *fast*, which is
exactly wrong for passwords — fast means an attacker with the database can try billions of guesses.
Argon2id is deliberately slow and memory-hard. It won the Password Hashing Competition and is the
current default recommendation.

**Email tokens are stored hashed, never in plaintext.** `generate_email_token()` returns
`(token_for_the_link, sha256_to_store)`. The plaintext exists only long enough to build the email.
If the database leaks, nobody can replay a verification or reset link.

Note SHA-256 is correct *here* while being wrong for passwords. The reason: the token already has 256
bits of entropy, so there is nothing to brute-force — and unlike Argon2 it stays fast and indexable.
Choice of hash follows the threat, not habit.

**Sessions are JWTs in httpOnly cookies.** `httponly` means page scripts cannot read the cookie, so
an XSS bug cannot steal the session. `samesite=lax` limits cross-site sending. `secure` is set in
production so it never travels over plain HTTP. A `Bearer` header is also accepted, for scripts and
the API docs.

**The signing key is validated at startup.** HS256 needs ≥32 bytes of key material (RFC 7518 §3.2);
PyJWT warned that our 18-byte dev default was too short. `config.py` now *refuses to start a
production app* with a short or default secret. Failing at boot beats discovering a forged token
later.

**Timing attacks and enumeration.** Three places deliberately give away nothing:

- login hashes a dummy password when the account does not exist, so response time does not reveal
  which addresses are registered
- `forgot-password` answers identically for known and unknown addresses
- a non-member asking for a workspace gets **404, not 403** — 403 would confirm it exists

### Roles

Four roles ranked `viewer < editor < admin < owner`, so "does this role suffice?" is one comparison
(`services/workspaces.ROLE_RANK`). Two rules deserve attention:

- **only an owner may create or unmake another owner** — an admin must not be able to hand out
  ownership of a brand
- **a workspace can never lose its last owner** — both demotion and removal check the owner count and
  return 409, otherwise a workspace becomes permanently unmanageable

### Three design problems and how they were solved

**1. Creating a workspace is a chicken-and-egg under RLS.** The owner's `memberships` row cannot be
inserted without tenant context (`WITH CHECK` rejects it), but there is no context until the
workspace exists. Solution: `db.adopt_tenant()` switches the *open transaction* into the new
workspace's context between the two inserts. Safe because the setting is transaction-local.

**2. "List my workspaces" is legitimately cross-tenant.** `memberships` is RLS-protected, so neither
a tenant session nor a global session can answer "which workspaces does this person belong to?".
Rather than exempt the query, a **second policy** expresses the permission in the database:

```sql
CREATE POLICY own_memberships ON memberships
  FOR SELECT USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
```

Multiple permissive policies are OR'ed, so a tenant session sees that workspace's rows and a
`user_session` sees its own rows across all workspaces. It is **SELECT-only on purpose** — a
permissive `WITH CHECK` would let anyone insert themselves into any workspace.

**3. Invitations cannot be RLS-protected.** An invitation must be readable by its token *before* the
recipient belongs to the workspace, so there is no tenant context to set and a policy would hide the
row from the only request that needs it. It is therefore the one table carrying a `tenant_id` without
a policy; the boundary is the token (256 bits, stored hashed) and every listing query filters by
tenant explicitly. The exception is documented in `models/invitation.py` — **an undocumented
exception is how a system quietly stops being secure.**

### Deviation from the scope document: NextAuth.js

The scope names NextAuth.js. We did not use it, and this needs your supervisor's awareness.

NextAuth's value is third-party identity providers (Google, GitHub). Sendox does not need them —
Shopify OAuth is *app installation*, not user login. Using NextAuth purely to wrap our own
credentials endpoint would add a dependency and a second session representation for no gain.

Instead `apps/web/src/lib/session.tsx` holds a small session context over the API's httpOnly cookie.
If social login is ever wanted, that one module is what changes. **Tell your supervisor; if they
want NextAuth specifically, it is a contained swap.**

### GDPR account deletion (FE-3)

`services/auth.delete_account()` spans three session scopes, because none of them may see everything:
a `user_session` to find the workspaces, a `tenant_session` per workspace to check whether anyone
else remains, and a `global_session` to delete. Workspaces with other members survive and lose the
member; workspaces nobody else belongs to are deleted, cascading to all their data.

### Testing notes

The suite creates real accounts in the development database. `tests/conftest.py` has a
session-scoped fixture that purges everything at `@example.com` afterwards, so repeated runs do not
accumulate junk. One early test asserted an exact workspace slug and broke once a workspace of that
name already existed — relaxed to assert the prefix, with uniqueness covered by its own test.
**Assert the contract, not an accident of your database.**

### Verified

- **71 API tests** (16 auth, 16 workspaces/roles, 7 isolation, plus earlier phases)
- 12 new end-to-end checks in `make verify`, covering confirmation gating, single-use links, httpOnly
  cookies, 404-for-non-members, role enforcement and the last-owner rule
- the browser path verified with a cookie jar: register → confirm → `/auth/me` with **no bearer
  token** → logout clears it
- ruff + mypy strict + eslint clean

### One more environment trap

A worker started with Celery's default **prefork** pool accepted tasks and failed every one with
`ValueError: not enough values to unpack (expected 3, got 0)` from inside `fast_trace_task`. The
forked child never receives the worker-optimisation state — a macOS fork-safety problem, not a bug in
our code. The same worker is fine inside the Linux Docker image.

`make dev-worker` therefore uses `--pool=threads`. Our work is I/O bound (SMTP, HTTP to Shopify and
Anthropic, database queries), so threads suit it regardless. Compose keeps prefork, because that is
what production runs and CI should exercise it. **If you ever start a worker by hand, pass
`--pool=threads`** or tasks fail in a way that looks like your code is broken.

### Deferred from M1

TOTP two-factor authentication (FE-2 marks it optional) and notification preferences. Everything else
in M1 is done.

---

## Anthropic key setup · 9 Oct 2026

The first key supplied was an **unscoped user key** (`sk-ant-usr-…`). The API rejected every call:

> This API key is not scoped to a workspace, so this request must include the
> `anthropic-workspace-id` header.

Two ways forward, both now supported: create a **workspace-scoped key** in the Console (`sk-ant-api03-…`,
which carries its own workspace and needs nothing else), or set `ANTHROPIC_WORKSPACE_ID` alongside the
user key — `clients/claude.py` sends it as a default header when present.

Two related fixes while reading the current API guidance:

- **`max_tokens` was far too small.** The health-check call used `max_tokens=16`. On current models
  thinking is on by default and **thinking tokens count against `max_tokens`**, so a tight ceiling gets
  consumed by reasoning and returns empty text — a failure that looks like the model ignoring you. The
  client default is now 16,000.
- A latent bug surfaced here: `config.py` resolved the repo root with `parents[3]`, which is `apps/`,
  not the repository root — so **`.env` was never being read**. Nothing failed loudly because Docker
  passes environment variables directly and an unset API key just looks like "not configured yet".
  Fixed to `parents[4]`, with a test asserting `.env.example` and `docker-compose.yml` sit beside it.

**The model stays `claude-sonnet-5`**, matching the scope document's choice of a Sonnet-tier model.
Opus is roughly 2.5× the price; Sonnet is the right default for generating marketing copy at volume.

## First CI run — three failures, all real · 9 Oct 2026

The GitHub token finally had the `workflow` scope, so `ci.yml` could be pushed and ran for the first
time. All four jobs failed, and every failure was a genuine defect rather than CI noise. This is the
argument for CI in one run: each of these passed locally.

**1. The container could not start at all — caused by the previous fix.** Resolving the repository
root as `Path(__file__).parents[4]` is correct inside the repository
(`apps/api/src/sendox_api/config.py`) but the container image flattens the tree to
`/app/src/sendox_api/config.py`, where there is no fourth parent:

```
File "/app/src/sendox_api/config.py", line 10
  _REPO_ROOT = Path(__file__).resolve().parents[4]
IndexError: 4
```

Counting parents encodes an assumption about directory depth that differs per environment. Replaced
with an upward search for a marker file (`docker-compose.yml`, chosen because it is committed, unlike
`.env`), falling back harmlessly when no repository is present — which is exactly the container's
situation, where configuration comes from the environment anyway.

**2. The API job never ran migrations**, so 32 tests failed with `role "sendox_app" does not exist`.
Obvious in hindsight: the test database is created fresh by the GitHub service container, and the
schema *and* that non-superuser role both come from a migration. Added an `alembic upgrade head` step
before the test step.

**3. `pnpm install --frozen-lockfile` failed both Node jobs** with
`ERR_PNPM_IGNORED_BUILDS: unrs-resolver`. The fix locally had been `pnpm rebuild`, which papered over
the real cause: pnpm 11 gates dependency install scripts on an `allowBuilds` block in
`pnpm-workspace.yaml`, and it had written a **placeholder** there —
`unrs-resolver: set this to true or false` — which is not a boolean, so the package stayed unapproved.
The `onlyBuiltDependencies` list that was also present is read by `pnpm config` but is not the gate.
`pnpm approve-builds --all` writes the correct block. Verified by deleting every `node_modules` and
installing from scratch, which is what CI does every run.

The lesson worth keeping: **"it works on my machine" was true in all three cases.** A local
environment accumulates state — an already-migrated database, an already-rebuilt native module, a
source tree that happens to be the right depth — and CI has none of it.

## Anthropic API, working · 9 Oct 2026

Three attempts to get a usable key, each failing differently and each worth knowing:

1. **Unscoped key** — `This API key is not scoped to a workspace`. The `sk-ant-usr-` prefix does *not*
   determine this; a user key can be scoped to a workspace in the Console, and the third key was.
2. **Scoped, but no credits** — `Your credit balance is too low to access the Anthropic API`. A
   different 400, and a useful reminder that a working key is not a working account.
3. **Working.** `/dev/ai/ping` returns 200, model `claude-sonnet-5`, 34 input / 4 output tokens.

Every AI feature from here (M9 Strategy, M10 Copywriting, M12 Validation, M19 Optimization) runs
through `clients/claude.py`, so this unblocks all of them.

## Phase 1.2 (M3) — Shopify connect · 9 Oct 2026

**Goal:** a merchant installs Sendox on their own store and approves what it may read — the same
flow Klaviyo uses.

### Custom app vs Partner app — the decision that shaped this

Shopify offers two app types and they are not interchangeable:

| | Custom app | Partner app |
|---|---|---|
| Created in | one store's admin | partners.shopify.com |
| Installs on | **that store only, ever** | any store that approves it |
| Auth | a token the owner copies | OAuth |
| Needs a public URL | no | **yes** |

A custom app can never become a product merchants sign up for — every merchant would have to create
their own app and paste a token in. **Partner app**, therefore, which is what the scope document
already implies (M3 FE-1 OAuth, FE-3 multi-store).

The cost is that Shopify will not redirect to `localhost`, so development needs a public HTTPS URL.
`cloudflared tunnel --url http://localhost:8000` provides one.

### How OAuth works here

1. The merchant types their store handle. We validate it and build an authorize URL pointing at
   **their own admin**, carrying our client id, the scopes we want, our redirect URL, and a `state`.
2. They approve. Shopify redirects back to our callback with `code`, `hmac`, `shop`, `state`.
3. We verify everything (below), then POST the code to `https://{shop}/admin/oauth/access_token`
   with our client secret and receive a token for **that store**.

### The callback is unauthenticated, so everything it trusts is proven

The browser returning from Shopify may carry no session cookie, so the callback cannot be behind
auth. Three checks replace it, and the **order matters**:

- **The shop domain**, validated against `^[a-z0-9][a-z0-9-]*\.myshopify\.com$` — anchored at both
  ends. This runs first because the domain is used to build the URL we redirect to *and* the URL we
  post our client secret to. `store.myshopify.com.attacker.example` passes a naive "contains
  myshopify.com" check and would send our secret to the attacker.
- **The HMAC**, computed over every query parameter except `hmac` itself, sorted and joined, keyed
  with the client secret, compared with `hmac.compare_digest` so a wrong digest cannot be discovered
  byte by byte.
- **The state**, a short-lived JWT carrying the workspace that started the install. Signed rather
  than stored in a table — it already has to survive a round trip through Shopify, and a signature
  carries the workspace without a lookup. This is what stops a CSRF-driven install landing in
  someone else's workspace.

### Storing the token

Unlike a password, the token must be **recoverable** — we send it to Shopify on every request — so
hashing is not an option. AES-256-GCM with a key derived per workspace from one master secret
(`crypto.py`). One leaked key exposes one workspace. The tenant id is authenticated alongside the
ciphertext, so a token row copied into another workspace fails to decrypt. `shopify_stores` is also
row-level-security protected like every other tenant-scoped table.

### The Admin API client

Two things make Shopify awkward, both handled in `clients/shopify.py`:

- **Rate limits** are a leaky bucket — 40 burst, refilling 2/second — and Shopify reports how full it
  is in `X-Shopify-Shop-Api-Call-Limit`. Rather than sprinting into a 429 and backing off, the client
  *slows down as the bucket fills*, so a bulk import runs at a steady pace instead of bursts
  punctuated by failures. A real 429 is still honoured via `Retry-After`.
- **Pagination is cursor-based** through an opaque `Link` header, not page numbers. `paginate()`
  follows it so callers write an ordinary loop. Note the cursor URL carries its own query string, so
  follow-up requests must not re-send the original params — doing so returns the first page forever.

### A routing mistake worth recording

The endpoints were first written as `/shopify/status` and `/shopify/install`, but the workspace
dependency resolves `workspace_id` from the **path** — so every request failed with
`Field required: path.workspace_id`. Split into two routers: the authenticated work lives under
`/workspaces/{workspace_id}/shopify/...` alongside members and invitations, and only the callback
stays at `/shopify/callback`, because the merchant returning from Shopify has no workspace in hand.

### Also fixed

Alembic autogenerate emits `postgresql.JSONB` / `postgresql.ENUM` without importing the dialect,
which fails at runtime rather than at review time — it had bitten three migrations. The import is now
in `alembic/script.py.mako`, so every generated migration has it, with ruff's unused-import rule
waived for that directory.

### Verified

25 OAuth tests covering domain normalisation, five hostile domain shapes, HMAC tampering (edited,
added and missing parameters), state forgery and uniqueness. 5 new end-to-end checks in `make verify`.

### The data layer it feeds (M5)

Three tenant-scoped tables, all with the same FORCE'd row-level security policy — a brand's customer
list is the most sensitive thing this platform will ever hold:

- **`contacts`** — identity, per-channel consent, and denormalised order totals. Consent is tracked
  **per channel** because the law treats email and SMS separately, and it defaults to `unknown`
  rather than `subscribed`: emailing people who never opted in is precisely how a sending domain's
  reputation is destroyed. Order counts are denormalised so segmentation and the predictive models in
  M20 do not aggregate the event table on every query.
- **`events`** — one row per thing a contact did, with `occurred_at` and a JSONB payload. This is the
  timeline the Copywriting Agent reads to personalise.
- **`products`** — needed twice later: the Design Agent fills product blocks from it (M11 FE-4), and
  the validation layer checks AI claims against it (M12 FE-1), which is what stops an invented
  discount reaching a customer.

### Import design: idempotent by construction

A 40,000-record import **will** be interrupted, so re-running it must be free. Everything is
upsert-by-external-id: contacts keyed on `(tenant, email)`, products on `(tenant, shopify_product_id)`,
events on `(tenant, type, external_id)`. Running the import twice produces identical state, and a
test asserts exactly that — second pass, zero new events.

Shopify is treated as the **source of truth**: a re-sync overwrites local values rather than merging,
so a merchant correcting a name in Shopify sees it corrected here rather than silently diverging.

Email addresses are lower-cased on the way in, so `Buyer@Example.com` and `buyer@example.com` are one
person rather than two contacts who each get their own copy of every campaign.

The import runs as a Celery task, not in a request — it makes hundreds of rate-limited calls and can
take minutes. A `ShopifyAuthError` is **not** retried, because a revoked token will not come back;
other errors retry with a delay.

Tests use a fake client returning canned pages rather than a live store, so the logic that matters is
testable with no network, no credentials, and no dependence on one store's contents.

Still to do in M3: the 15-minute incremental sync (FE-5) and the webhook pipeline (M4).

## Known environment problems

- **Disk pressure.** The Mac ran down to 1.2 GB free of 228 GB, which forced Docker's filesystem
  read-only mid-build. ~8.7 GB was reclaimed inside Docker (`Docker.raw` does not shrink, so that did
  not return to the host). Space has since been freed — **23 GB free as of 9 Oct**, enough for Docker
  builds again.
- Development currently runs on the **native path** (`make up-native`): Homebrew Postgres 15 and
  Redis, with ChromaDB and the MJML sidecar as host processes. Mailpit is Docker-only, which is why
  the API returns verification tokens directly in development.
- `.github/workflows/ci.yml` exists and works locally but is **not on GitHub** — the `gh` token lacks
  the `workflow` scope. Run `gh auth refresh -h github.com -s workflow` to fix.
