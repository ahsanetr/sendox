# Sendox — Prototype Build Plan

**Scope source of truth:** `Sendox_Scope_Updated.docx` (25 modules, ~180 FE requirements).
This document is the *execution* plan: what gets built, in what order, and what "done" means at each step.

- **Project:** Sendox — AI-native multi-channel marketing platform for Shopify brands
- **Today:** 8 Oct 2026 · **Final submission:** end of May 2027 · **~34 weeks**
- **Build mode:** one single stream, one phase at a time, built here. No work division.

---

## 1. The governing principle

The scope doc lists 25 modules. Built module-by-module, nothing works until almost everything works —
and in 34 weeks, "almost everything" never arrives.

So we build **vertical slices**, not horizontal layers. Every release is a system that actually runs
end-to-end against a real Shopify store. Each release makes the same path deeper and wider, never longer.

**The money path** — the one flow that must work before anything else matters:

```
Shopify store connected → contacts + products imported → brand voice learned
→ AI writes an email → renders to HTML → validated → human approves
→ SES sends it → open/click tracked → result shown in dashboard
```

Everything in the scope doc is either *on* that path (build early and shallow, then deepen) or *hangs off*
it (SMS, WhatsApp, copilot, predictive ML, billing, forms — build after the path is solid).

**Demo-grade first, FE-complete later.** In R1 the Design Agent ships 3 MJML layouts, not 15; the
Copywriting Agent ships one tone, not multi-tone. The full FE lists get satisfied by explicit deepening
passes in R2/R3. This is the method, and it should be presented to the supervisor as such — not hidden
as a shortfall.

---

## 2. Release map

| Release | Window | Weeks | What exists at the end |
|---|---|---|---|
| **R0 — Skeleton** | 8 Oct – 21 Oct | 2 | Repo, services, CI, auth, one request crossing every layer |
| **R1 — "It sends"** | 22 Oct – 24 Dec | 9 | The full money path, manually triggered, on a real Shopify dev store |
| **R2 — "It runs itself"** | 5 Jan – 28 Feb | 8 | Flows, campaigns, strategy agent, real analytics. Autonomous, not manual |
| **R3 — "It learns + multi-channel"** | 1 Mar – 25 Apr | 8 | Optimization loop, SMS, WhatsApp, cross-channel consent, predictions |
| **R4 — "It's a product"** | 26 Apr – 23 May | 4 | Billing, signup forms, copilot, beta with 3–5 brands, docs, defense prep |
| **Buffer** | 24 May – 31 May | 1 | Reserve. No work planned here. |

Winter break (25 Dec – 4 Jan) is left unplanned on purpose. If R1 slips, it slips into there.

---

## 3. Start these in week 1 — long-lead items that block later releases

These cost weeks of *waiting*, not weeks of work. Each one blocks a release if started late.

| Item | Blocks | Lead time |
|---|---|---|
| **AWS account + SES production access request** | R1 send to real inboxes | 1–3 weeks, can be rejected |
| Sending domain purchased + DNS access (Cloudflare) | R1 SPF/DKIM/DMARC | days |
| Shopify Partner account + dev store with seeded data | R1 everything | hours |
| Anthropic API key + spend cap agreed | R1 all agents | hours |
| **Beta brand recruitment — start conversations now** | R4 validation (needs 3–5 stores) | months |
| **SMS sender registration (10DLC / alphanumeric sender ID)** | R3 SMS | **4–8 weeks** |
| **Meta WhatsApp Business account + business verification** | R3 WhatsApp | **3–6 weeks** |
| Stripe account (test mode suffices until R4) | R4 billing | hours |

> SES stays in sandbox until approved — it can only send to addresses you verify. R1 is planned around
> sandbox + verified test inboxes, so an SES delay stalls the beta, not the prototype.

---

## 4. Locked technical decisions

Faithful to the scope doc's Tools & Technologies table except where noted.

| Layer | Choice | Note |
|---|---|---|
| Repo | Single monorepo: `apps/api`, `apps/web`, `services/mjml`, `infra/` | worker is a second entrypoint over `apps/api`, not its own package |
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind (+ shadcn/ui, Recharts in 0.3) | doc says 14.x; using current stable |
| Backend | FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic, deps via `uv` | |
| Jobs | Celery 5 + Redis 7 (worker + beat) | |
| DB | PostgreSQL 16; multi-tenancy via `tenant_id` + **Postgres Row-Level Security** | satisfies M1 FE-6 properly |
| Vector DB | ChromaDB, self-hosted | kept — named as a project contribution |
| Embeddings | local `sentence-transformers`, behind a swappable interface | doc says OpenAI; local = no vendor, no cost |
| LLM | Claude API — **`claude-sonnet-5`** | doc says `claude-sonnet-4-6`, not a real model id — **fix the doc** |
| Email render | MJML 4 in a small Node sidecar the API calls over HTTP | MJML is Node-only |
| Email send | Amazon SES v2 + SNS for bounce/complaint | |
| Local dev | `docker compose`: postgres, redis, chromadb, mailpit, mjml | one command boots everything |
| Deploy | API + worker + Postgres + Redis + Chroma on **Railway**; web on **Vercel** | |
| CI | GitHub Actions: lint, type-check, pytest, vitest on every PR | |
| Errors | Sentry wired from R0, not bolted on at the end | |

**Scope-doc corrections to make** (versions that have moved on, not scope changes):

| Table 2 row | Doc says | Should say |
|---|---|---|
| LLM / AI — Claude API | `claude-sonnet-4-6` | `claude-sonnet-5` (the doc's id does not exist) |
| Vector DB — ChromaDB | `0.5+` | `1.5+` (1.x removed the v1 API we'd have coded against) |
| Frontend — Next.js + React | `14.x` | `16.x` / React 19 |
| Authentication — NextAuth.js | `4.x` | `5.x` (Auth.js), required for Next 16 |
| E-commerce API — Shopify REST | `2024-01` | pick the current stable version at phase 1.2 |

Local embeddings need **no** sign-off: M7 FE-2 already reads "OpenAI text-embedding-3-small
**or open-source alternative**", so `sentence-transformers` is within the approved scope as written.

---

## 5. Phases

Each phase ends with a demo, not a checkbox. If the demo can't be shown, the phase isn't done.

### R0 — Skeleton · 8–21 Oct

Status: **R0 complete except 0.6** (the long-lead filings, which are not a coding task), and
**M1 done**. 0.6 is yours; the next code is phase 1.2, Shopify connect, which needs credentials. Live state is always at `/status/modules`, rendered on
the dev dashboard at `localhost:3000` — that, not this table, is the source of truth for progress.

| # | Phase | Exit criteria |
|---|---|---|
| 0.1 | ✅ Monorepo + docker-compose + CI | `docker compose up` boots all services; CI green |
| 0.2 | DB foundation: Alembic, `tenants`/`users`, RLS policies | a test proves cross-tenant reads fail |
| 0.3 | Next.js shell + API client + auth (NextAuth credentials → FastAPI, JWT verified server-side) | log in, see a page with tenant-scoped data from FastAPI |
| 0.4 | ✅ Celery worker + beat wired end to end | job enqueued from API, executed, result visible in UI |
| 0.5 | ✅ Anthropic + Chroma clients | vector store working end to end; Claude awaits an API key |
| 0.6 | Every §3 long-lead item filed | SES request submitted, dev store seeded, `.env.example` complete |

**0.1 verified in full.** `make up` boots all eight services healthy, `/health/ready` returns 200
with every backing service ok, Mailpit serves on 8025, and a Celery task round-trips through Redis
(`sendox.ping` → SUCCESS). Also green: ruff, mypy strict, 10 pytest tests, 3 MJML tests, Next build.
`make up-native` remains as a no-Docker fallback (Postgres 15 instead of 16, no Mailpit).

**Two dev-network constraints found while doing it**, both worked around in-repo — see
`docs/DEV-ENVIRONMENT.md`. They will bite again on any new machine, so they are written down.

### R1 — "It sends" · 22 Oct – 24 Dec

Modules: M1, M3, M4 (partial), M5, M6, M7, M8, M10, M11, M12, M16, M17, M18 (partial), M13 (minimal)

| # | Phase | Wks | Exit criteria |
|---|---|---|---|
| 1.1 | **M1** Auth, workspaces, roles, team invites, audit log | 2 | two users, two workspaces, role enforced at API *and* UI |
| 1.2 | **M3** Shopify OAuth + encrypted token store + bulk import (customers, orders, products) | 2 | dev store connected, 1k+ records imported, rate limits handled |
| 1.3 | **M5** Contact + behavioral event schema, timeline, tags, CSV import | 1.5 | contact detail page shows a real purchase timeline |
| 1.3b | ✅ **Product UI foundation** — app shell, design system, screens rebuilt | 1 | inserted on request: every later module lands in the real product rather than a dev panel |
| 1.4 | **M6** Onboarding wizard (5 questions + assets) + sitemap crawler + product/About parser → S3 | 2.5 | run against dev store; extracted text and images inspectable |
| 1.5 | **M7** Chunk → embed → Chroma with metadata + knowledge-base inspector UI | 1.5 | user can see what the AI "learned"; versioned |
| 1.6 | **M8** RAG retrieval + prompt template library + assembly + token budget + prompt logging | 1.5 | every generation has a stored, inspectable prompt |
| 1.7 | **M10** Copywriting Agent: 3 subject variants, preheader, body, CTA, personalization tokens | 2 | output is recognisably in the dev store's voice |
| 1.8 | **M11** Design Agent: **3** MJML layouts + brand styling + product blocks + preview pane | 2 | HTML renders correctly in Gmail and Apple Mail |
| 1.9 | **M12** Validation: product-claim check, spam words, brand-voice score, confidence → approval queue | 2 | a deliberately hallucinated claim gets blocked |
| 1.10 | **M16** Domain auth wizard (SPF/DKIM/DMARC + SES identity) + DNS validator + throttled send queue | 2 | real domain authenticates; batched send respects SES quota |
| 1.11 | **M17** Tracking: pixel endpoint, link rewriting, click redirect, event store | 1.5 | open and click on a real email land in the DB |
| 1.12 | **M18** SNS bounce/complaint receivers + hard-bounce suppression + RFC 8058 unsubscribe | 1.5 | SES simulator bounce suppresses the contact |
| 1.13 | **M13-min** "Send to this segment, now" + per-campaign KPI rollup | 1 | **the money path runs start to finish** |
| 1.14 | R1 hardening + demo script + rehearsal | 1 | 15-minute live demo, no mocks |

**R1 is deliberately shallow in places:** no incremental sync (1.2), no Playwright JS rendering unless a
theme demands it (1.4), no cross-encoder re-ranking (1.6), no multi-tone variants (1.7), 3 layouts not 15
(1.8), no auto-approve (1.9), no scheduling (1.13). All of it is R2 deepening work.

### R2 — "It runs itself" · 5 Jan – 28 Feb

Modules: M4 (full), M9, M13 (full), M14, M22 + deepening passes over R1

| # | Phase | Wks |
|---|---|---|
| 2.1 | **M4** full webhooks: HMAC, idempotency, retry, DLQ, health dashboard + **M3** 15-min incremental sync | 1.5 |
| 2.2 | **M14** Flow Engine: stateful runs, delays, conditions, the three pre-built flows, flow viewer | 3 |
| 2.3 | **M13** full Campaign Engine: audience builder, scheduler, lifecycle state machine, pre-send validation, pause/resume | 2 |
| 2.4 | **M9** Strategy Agent: flow recommendation, 4-week calendar, segment suggestions, send-time strategy, rationale panel, approval UI | 2.5 |
| 2.5 | **M22** Analytics: live campaign + per-flow dashboards, revenue attribution (last-touch first), weekly AI summary, export | 2.5 |
| 2.6 | Deepening: 15 MJML layouts, cross-encoder re-rank, multi-tone variants, regenerate-with-feedback, auto-approve toggle | 2 |

**Exit:** a cart abandoned on the dev store produces an AI-written recovery email one hour later with
nobody touching the app, and the dashboard attributes the resulting order to it.

### R3 — "It learns + multi-channel" · 1 Mar – 25 Apr

| # | Phase | Wks |
|---|---|---|
| 3.1 | **M19** Optimization Agent: metric ingestion, auto A/B, Thompson Sampling allocator, winning-pattern extractor → KB, insights dashboard | 3 |
| 3.2 | **M23** SMS: provider integration, E.164, GSM-7/UCS-2 segment counter, STOP/START/HELP, quiet hours, receipts, spend cap | 2.5 |
| 3.3 | **M24** WhatsApp: Cloud API, template composer + Meta approval tracking, 24-hour window state, message router, receipts | 2.5 |
| 3.4 | **M25** Cross-channel: per-channel consent ledger, AI channel selection, frequency cap, fallback rules, unified suppression, dedup | 2 |
| 3.5 | **M20** Predictive: CLV (XGBoost), churn risk, next-best-product, per-contact send time, predictive segments | 2.5 |
| 3.6 | **M22+** Markov multi-touch attribution + holdout-group causal lift testing | 1.5 |

**Risk:** 3.2 and 3.3 are hostage to registrations filed in week 1. If either is still pending in March,
build against the provider sandbox and swap credentials later — do not idle.

### R4 — "It's a product" · 26 Apr – 23 May

| # | Phase | Wks |
|---|---|---|
| 4.1 | **M2** Stripe billing: checkout, 3 tiers, usage metering, limits, webhooks, invoices | 1.5 |
| 4.2 | **M15** Signup forms: JS widget, designer, 4 form types, double opt-in, discount reward, form analytics | 1.5 |
| 4.3 | **M21** Conversational Copilot: chat, goal-to-execution, performance Q&A, tool-use, daily next-moves feed | 2 |
| 4.4 | **Beta:** onboard 3–5 real Shopify brands, measure, iterate | 2.5 |
| 4.5 | Production hardening, Sentry alerting, UAT, technical + user docs | 1.5 |
| 4.6 | FYP report, research paper draft, demo rehearsal, defense prep | 2 |

R4 is over-subscribed by design — 4.1/4.2/4.3 are the cut candidates if beta results demand attention.
Billing can ship Stripe test-mode only; the copilot can ship read-only (Q&A without tool-use).

---

## 6. Cut order, if we fall behind

Cut from the bottom. Never cut from the money path.

1. Copilot tool-use → read-only Q&A (M21 FE-5)
2. Signup form designer → one hardcoded popup template (M15 FE-2, FE-6)
3. Stripe → test mode only, no proration (M2 FE-5)
4. Markov attribution → last-touch only (M22 FE-3)
5. Predictive engine → CLV + churn only, drop next-best-product (M20 FE-3)
6. WhatsApp → one approved template, no free-form session routing (M24 FE-5)
7. **Floor — never cut:** M1, M3, M5, M6, M7, M8, M10, M11, M12, M13, M14, M16, M17, M18, M22-core.
   That floor is still a defensible FYP: an AI-native email platform that works end to end.

---

## 7. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| SES production access rejected or slow | Cannot send to beta brands | Filed week 1; demo runs in sandbox; Resend/Postmark documented as fallback |
| 10DLC / Meta verification not granted in time | M23/M24 undemonstrable | Filed week 1; build on sandbox; already stated as LI-7/LI-8 |
| Claude API cost overrun | Work stops | Hard spend cap; cache dev generations to disk; replay prompt logs instead of re-calling |
| Scraper breaks on JS-heavy themes | Weak brand profile | Playwright fallback budgeted in 1.4; manual brand-context override (M7 FE-7) |
| Beta brands don't materialise | BO-5 unmet | Recruiting from week 1; fallback = 2 brands + one dev store with realistic seeded data |
| Scope doc promises more than 34 weeks allows | Supervisor expectation gap | Show this plan and §6 cut order to the supervisor **now**, not in May |

## 8. Working cadence

- One phase at a time, in order. A phase is done when its demo runs.
- Branch per phase, CI green before merge.
- Each release ends with a tagged build and a short recorded demo — this becomes FYP report evidence.
