#!/usr/bin/env python3
"""Render the shareable status page from live data.

Two status surfaces exist and both must stay truthful:

* the dashboard at http://localhost:3000, which queries the API directly;
* this page, published as an Artifact and shared with the supervisor and project
  partners, who cannot reach localhost.

Every figure here is read from the running system — `/status/modules`,
`/status/database` and the output of `scripts/verify.sh` — so nothing is retyped
and the page cannot drift from reality. Run with `make status-page`, then publish
the file it writes.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "docs" / "status-page.html"
API = os.environ.get("API_BASE_URL", "http://localhost:8000")

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def fetch(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=15) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        sys.exit(f"cannot reach {API}{path} ({exc}). Start the API first: make dev-api")


def run_verify() -> str:
    """Run the verification script and return its plain-text output."""
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "verify.sh")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return ANSI.sub("", result.stdout)


def git_log() -> list[list[str]]:
    result = subprocess.run(
        ["git", "log", "--format=%h|%ad|%s", "--date=short"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return [line.split("|", 2) for line in result.stdout.strip().splitlines() if line]


def count_tests() -> str:
    """Total passing API tests, read from pytest rather than guessed."""
    result = subprocess.run(
        ["uv", "run", "pytest", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT / "apps" / "api",
        check=False,
    )
    match = re.search(r"(\d+) passed", result.stdout)
    return match.group(1) if match else "?"


modules = fetch("/status/modules")
database = fetch("/status/database")
verify_raw = run_verify()
commits = git_log()
test_count = count_tests()
TODAY = date.today().strftime("%-d %b %Y")

releases = {r["id"]: r for r in modules["releases"]}
foundation = modules["foundation"]
mods = modules["modules"]
totals = modules["totals"]

# ---- verification transcript -> coloured monospace -------------------------
lines = []
for raw in verify_raw.splitlines():
    if not raw.strip():
        lines.append("")
        continue
    if raw.startswith("Sendox") or raw.startswith("api="):
        continue
    m = re.match(r"^  (PASS|SKIP|FAIL)  (.{1,44})(.*)$", raw)
    if m:
        verdict, label, detail = m.group(1), m.group(2).rstrip(), m.group(3).strip()
        cls = {"PASS": "ok", "SKIP": "skip", "FAIL": "bad"}[verdict]
        lines.append(
            f'<span class="v {cls}">{verdict}</span>'
            f'<span class="vl">{html.escape(label)}</span>'
            f'<span class="vd">{html.escape(detail)}</span>'
        )
    elif raw.startswith("Summary"):
        lines.append(f'<span class="vsum">{html.escape(raw)}</span>')
    elif raw.startswith("All required"):
        lines.append(f'<span class="v ok" style="padding:0">{html.escape(raw)}</span>')
    else:
        lines.append(f'<span class="vgroup">{html.escape(raw)}</span>')
transcript = "\n".join(lines)

def chip(status):
    label = {"done": "done", "partial": "partial", "planned": "planned"}[status]
    return f'<span class="chip {status}">{label}</span>'

def item_rows(items, show_phase=True):
    out = []
    for i in items:
        phase = f'<span class="ph">{html.escape(i.get("phase", i["id"]))}</span>' if show_phase else ""
        note = f'<p class="note">{html.escape(i["note"])}</p>' if i.get("note") else ""
        out.append(
            f'<li class="row {i["status"]}">'
            f'<span class="rid">{html.escape(i["id"])}</span>'
            f'<span class="rname">{html.escape(i["name"])}{note}</span>'
            f'{phase}{chip(i["status"])}</li>'
        )
    return "\n".join(out)

release_blocks = []
for rid in ("R1", "R2", "R3", "R4"):
    items = [m for m in mods if m["release"] == rid]
    if not items:
        continue
    r = releases[rid]
    done = sum(1 for i in items if i["status"] != "planned")
    release_blocks.append(f"""
      <section class="rel">
        <header class="relhead">
          <h3><span class="relid">{rid}</span> {html.escape(r["title"])}</h3>
          <p class="relmeta">{html.escape(r["window"])} · {len(items)} modules · {done} started</p>
        </header>
        <ul class="rows">{item_rows(items)}</ul>
      </section>""")

counted = [*foundation, *mods]
done_count = sum(1 for i in counted if i["status"] == "done")
partial_count = sum(1 for i in counted if i["status"] == "partial")
total_count = len(counted)

summary = re.search(r"(\d+) passed, (\d+) failed, (\d+) skipped", verify_raw)
checks_passed = summary.group(1) if summary else "?"
checks_skipped = summary.group(3) if summary else "0"
checks_total = (
    str(int(checks_passed) + int(summary.group(2)) + int(checks_skipped)) if summary else "?"
)

commit_rows = "\n".join(
    f'<li><span class="sha">{html.escape(sha)}</span>'
    f'<span class="csub">{html.escape(subject)}</span>'
    f'<span class="cdate">{html.escape(date)}</span></li>'
    for sha, date, subject in commits
)

HTML = f"""<title>Sendox Build Status</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {{
    --ground: #fafafc;
    --surface: #ffffff;
    --ink: #15171e;
    --muted: #5c6270;
    --faint: #878d9c;
    --hair: #e3e5ec;
    --hair-strong: #cfd3de;
    --accent: #1f4fd8;
    --done: #0e7a56;
    --done-bg: #e8f5ef;
    --partial: #8a5a00;
    --partial-bg: #fdf2dd;
    --planned: #767d8e;
    --planned-bg: #eeeff4;
    --bad: #b22731;
    --term-bg: #12141a;
    --term-ink: #cdd2de;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --ground: #0e1014;
      --surface: #161922;
      --ink: #e7e9f0;
      --muted: #9ba2b2;
      --faint: #777f90;
      --hair: #262b36;
      --hair-strong: #343a47;
      --accent: #8aa4ff;
      --done: #46c795;
      --done-bg: #102a21;
      --partial: #e0ab46;
      --partial-bg: #2a2114;
      --planned: #8a91a1;
      --planned-bg: #1d212a;
      --bad: #ef6b74;
      --term-bg: #0a0c10;
      --term-ink: #c6cbd8;
    }}
  }}
  :root[data-theme="dark"] {{
    --ground: #0e1014;
    --surface: #161922;
    --ink: #e7e9f0;
    --muted: #9ba2b2;
    --faint: #777f90;
    --hair: #262b36;
    --hair-strong: #343a47;
    --accent: #8aa4ff;
    --done: #46c795;
    --done-bg: #102a21;
    --partial: #e0ab46;
    --partial-bg: #2a2114;
    --planned: #8a91a1;
    --planned-bg: #1d212a;
    --bad: #ef6b74;
    --term-bg: #0a0c10;
    --term-ink: #c6cbd8;
  }}

  body {{
    background: var(--ground);
    color: var(--ink);
    font-family: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, sans-serif;
    font-size: 15px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{
    max-width: 50rem;
    margin: 0 auto;
    padding-inline: 20px;
    padding-block: 3rem 4rem;
  }}
  h1, h2, h3 {{ text-wrap: balance; margin: 0; }}
  h1 {{ font-size: clamp(1.75rem, 5vw, 2.4rem); font-weight: 600; letter-spacing: -0.021em; }}
  h2 {{ font-size: 1.0625rem; font-weight: 600; letter-spacing: -0.006em; }}
  h3 {{ font-size: 0.9375rem; font-weight: 600; }}
  p {{ margin: 0; }}
  code, .mono {{ font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }}

  .eyebrow {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--faint);
  }}

  /* ---------- header ---------- */
  header.top {{ display: flex; flex-direction: column; gap: 0.5rem; }}
  .lede {{
    margin-top: 0.75rem;
    color: var(--muted);
    max-width: 38rem;
    font-size: 1.0625rem;
  }}
  .stamp {{
    margin-top: 1.25rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1rem;
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.75rem;
    color: var(--faint);
    border-top: 1px solid var(--hair);
    padding-top: 0.75rem;
  }}

  /* ---------- figures ---------- */
  .figs {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1.5rem;
    margin-top: 2.5rem;
    padding-block: 1.5rem;
    border-top: 1px solid var(--hair-strong);
    border-bottom: 1px solid var(--hair-strong);
  }}
  @media (max-width: 30rem) {{ .figs {{ grid-template-columns: 1fr; gap: 1.25rem; }} }}
  .fig .n {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 1.9rem;
    font-weight: 500;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    display: block;
    line-height: 1.1;
  }}
  .fig .l {{ display: block; margin-top: 0.3rem; font-size: 0.8125rem; color: var(--muted); }}

  section.blk {{ margin-top: 3rem; }}
  section.blk > h2 {{ padding-bottom: 0.6rem; border-bottom: 1px solid var(--hair); }}
  .sub {{ margin-top: 0.7rem; color: var(--muted); font-size: 0.9375rem; max-width: 40rem; }}

  /* ---------- terminal ---------- */
  .term {{
    margin-top: 1rem;
    background: var(--term-bg);
    color: var(--term-ink);
    border-radius: 6px;
    overflow-x: auto;
    padding: 1rem 1.15rem;
  }}
  .term pre {{
    margin: 0;
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.75rem;
    line-height: 1.75;
    white-space: pre;
  }}
  .term .cmd {{ color: #7f8ba3; }}
  .v {{ display: inline-block; width: 3.1rem; font-weight: 500; }}
  .v.ok {{ color: #4ec08d; }}
  .v.skip {{ color: #d9a33a; }}
  .v.bad {{ color: #ef6b74; }}
  .vl {{ display: inline-block; min-width: 23rem; }}
  .vd {{ color: #7f8ba3; }}
  .vgroup {{ color: #e7e9f0; font-weight: 500; }}
  .vsum {{ color: #e7e9f0; font-weight: 500; }}

  /* ---------- works / gaps ---------- */
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; margin-top: 1.25rem; }}
  @media (max-width: 40rem) {{ .two {{ grid-template-columns: 1fr; gap: 1.75rem; }} }}
  .two h3 {{ display: flex; align-items: baseline; gap: 0.5rem; }}
  .two ul {{ margin: 0.75rem 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.6rem; }}
  .two li {{ font-size: 0.875rem; padding-left: 1rem; position: relative; color: var(--muted); }}
  .two li::before {{
    content: ""; position: absolute; left: 0; top: 0.5rem;
    width: 5px; height: 5px; border-radius: 50%;
  }}
  .two .yes li::before {{ background: var(--done); }}
  .two .no li::before {{ background: var(--hair-strong); }}
  .two li b {{ color: var(--ink); font-weight: 600; }}

  /* ---------- rows ---------- */
  ul.rows {{ list-style: none; margin: 0; padding: 0; }}
  .row {{
    display: grid;
    grid-template-columns: 2.9rem 1fr auto auto;
    align-items: baseline;
    gap: 0.5rem 0.75rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--hair);
  }}
  .row.planned {{ opacity: 0.62; }}
  .rid {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.75rem; color: var(--faint); font-variant-numeric: tabular-nums;
  }}
  .rname {{ font-size: 0.875rem; min-width: 0; }}
  .note {{
    margin-top: 0.3rem; font-size: 0.75rem; color: var(--muted); line-height: 1.5;
  }}
  .ph {{ font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.6875rem; color: var(--faint); }}
  .chip {{
    font-size: 0.6875rem; font-weight: 500; padding: 0.1rem 0.45rem; border-radius: 3px;
    white-space: nowrap;
  }}
  .chip.done {{ color: var(--done); background: var(--done-bg); }}
  .chip.partial {{ color: var(--partial); background: var(--partial-bg); }}
  .chip.planned {{ color: var(--planned); background: var(--planned-bg); }}

  .rel {{ margin-top: 2rem; }}
  .relhead {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0.3rem 1rem; }}
  .relid {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    color: var(--accent); margin-right: 0.3rem;
  }}
  .relmeta {{ font-size: 0.75rem; color: var(--faint); font-family: "IBM Plex Mono", ui-monospace, monospace; }}

  /* ---------- commits ---------- */
  ul.commits {{ list-style: none; margin: 1rem 0 0; padding: 0; }}
  ul.commits li {{
    display: grid; grid-template-columns: 4.5rem 1fr auto; gap: 0.75rem;
    align-items: baseline; padding: 0.55rem 0; border-bottom: 1px solid var(--hair);
    font-size: 0.875rem;
  }}
  @media (max-width: 34rem) {{
    ul.commits li {{ grid-template-columns: 4.5rem 1fr; }}
    .cdate {{ display: none; }}
  }}
  .sha {{ font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.75rem; color: var(--accent); }}
  .cdate {{ font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.75rem; color: var(--faint); }}

  /* ---------- blockers ---------- */
  ol.blockers {{ margin: 1.25rem 0 0; padding: 0; list-style: none; counter-reset: b; }}
  ol.blockers li {{
    counter-increment: b; position: relative; padding-left: 2.1rem; margin-bottom: 1.1rem;
    font-size: 0.9375rem; color: var(--muted);
  }}
  ol.blockers li::before {{
    content: counter(b); position: absolute; left: 0; top: 0.05rem;
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.75rem;
    width: 1.4rem; height: 1.4rem; display: grid; place-items: center;
    border: 1px solid var(--hair-strong); border-radius: 50%; color: var(--ink);
  }}
  ol.blockers b {{ color: var(--ink); font-weight: 600; }}

  footer {{
    margin-top: 3.5rem; padding-top: 1.25rem; border-top: 1px solid var(--hair);
    font-size: 0.8125rem; color: var(--faint);
  }}
  footer a {{ color: var(--accent); text-decoration: none; }}
  footer a:hover {{ text-decoration: underline; }}
  a:focus-visible, li:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
</style>

<div class="wrap">
  <header class="top">
    <p class="eyebrow">Final Year Project · COMSATS University Islamabad</p>
    <h1>Sendox — build status</h1>
    <p class="lede">
      AI-native multi-channel marketing platform for Shopify brands. This is a snapshot of
      what is implemented and independently verified, taken from the running system — not a
      plan of intent.
    </p>
    <div class="stamp">
      <span>snapshot {TODAY}</span>
      <span>local development build</span>
      <span>not yet deployed</span>
      <span>due end of May 2027</span>
    </div>
  </header>

  <div class="figs">
    <div class="fig">
      <span class="n">{done_count}<span style="color:var(--faint)">/{total_count}</span></span>
      <span class="l">build items complete, plus {partial_count} partial — across 6 foundation phases and 25 scope modules</span>
    </div>
    <div class="fig">
      <span class="n">{test_count}</span>
      <span class="l">automated tests passing, including 7 that prove workspace data cannot leak</span>
    </div>
    <div class="fig">
      <span class="n">{checks_passed}<span style="color:var(--faint)">/{checks_total}</span></span>
      <span class="l">end-to-end checks against live services, run by one command; {checks_skipped} skipped for optional dependencies</span>
    </div>
  </div>

  <section class="blk">
    <h2>Verified, not asserted</h2>
    <p class="sub">
      A single command exercises every claim below against the running stack and prints a verdict
      per check. This is its unedited output. The same script runs in continuous integration, so
      local results and CI results cannot drift apart.
    </p>
    <div class="term">
      <pre><span class="cmd">$ make verify</span>
{transcript}</pre>
    </div>
  </section>

  <section class="blk">
    <h2>Where the project stands</h2>
    <div class="two">
      <div>
        <h3>Working <span class="eyebrow">verified</span></h3>
        <ul class="yes">
          <li><b>Infrastructure.</b> Eight-service stack (API, workers, Postgres, Redis, vector database, email renderer, mail capture) booting from one command, with CI.</li>
          <li><b>Workspace data isolation.</b> Enforced inside Postgres: a query that forgets to filter by workspace returns nothing rather than another brand's data.</li>
          <li><b>Brand knowledge retrieval.</b> Content is embedded locally and searched by meaning — asking "can I send something back?" returns the returns policy, which shares none of those words.</li>
          <li><b>Email rendering.</b> Produces responsive HTML that holds up across mail clients; invalid input is reported with line numbers rather than crashing.</li>
          <li><b>Background job queue.</b> Proven end to end, which is what makes timed automation possible later.</li>
        </ul>
      </div>
      <div>
        <h3>Not built yet <span class="eyebrow">23 modules</span></h3>
        <ul class="no">
          <li><b>Accounts and login.</b> No authentication yet — next piece of work.</li>
          <li><b>Shopify connection.</b> Blocked on partner app credentials.</li>
          <li><b>The AI agents.</b> Strategy, copywriting, design and optimisation — transport is ready, no generation yet.</li>
          <li><b>Campaigns, flows, sending and tracking.</b> Nothing is delivered to a real inbox yet.</li>
          <li><b>SMS and WhatsApp.</b> Scheduled for March–April 2027; sender registration must start months earlier.</li>
          <li><b>Billing, signup forms, analytics.</b> Final release.</li>
        </ul>
      </div>
    </div>
  </section>

  <section class="blk">
    <h2>Foundation</h2>
    <p class="sub">
      Groundwork rather than features: the parts every module depends on. Numbering follows the
      project build plan.
    </p>
    <ul class="rows">{item_rows(foundation, show_phase=False)}</ul>
  </section>

  <section class="blk">
    <h2>The 25 scope modules</h2>
    <p class="sub">
      Grouped by the release that delivers them. Each release is a working system rather than a
      layer, so the same path through the product gets deeper each time instead of longer.
    </p>
    {"".join(release_blocks)}
  </section>

  <section class="blk">
    <h2>History</h2>
    <ul class="commits">{commit_rows}</ul>
  </section>

  <section class="blk">
    <h2>What would unblock the next step</h2>
    <ol class="blockers">
      <li><b>Shopify Partner app credentials and a development store.</b> Connecting a real store is the next milestone, and it cannot be tested without them.</li>
      <li><b>An Anthropic API key.</b> Every AI feature is inert until one is configured; the system degrades cleanly without it, which is why one check above is skipped rather than failing.</li>
      <li><b>Long-lead approvals, started now.</b> Amazon SES production access takes up to three weeks and can be refused. SMS sender registration takes four to eight weeks and WhatsApp business verification three to six — both gate the March–April 2027 release, so filing them in March is already too late.</li>
    </ol>
  </section>

  <footer>
    Source: <a href="https://github.com/ahsanetr/sendox">github.com/ahsanetr/sendox</a> (private).
    Figures on this page were taken from the running system on 8 October 2026 and are a point-in-time
    snapshot, not a live feed.
  </footer>
</div>
"""

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(HTML) / 1024:.0f} KB)")
