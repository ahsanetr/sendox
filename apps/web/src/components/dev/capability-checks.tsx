"use client";

import { useState } from "react";

import {
  enqueuePing,
  getTask,
  renderSampleEmail,
  type RenderResult,
} from "@/lib/api";
import { Button, Card, ErrorNote } from "@/components/dev-ui";

const POLL_INTERVAL_MS = 400;
const POLL_ATTEMPTS = 25;

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>
      </div>
      <div className="flex min-w-0 shrink-0 items-center gap-3">{children}</div>
    </div>
  );
}

export function CapabilityChecks() {
  const [queueLog, setQueueLog] = useState<string[]>([]);
  const [queueBusy, setQueueBusy] = useState(false);
  const [render, setRender] = useState<RenderResult | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runQueueCheck() {
    setQueueBusy(true);
    setQueueLog([]);
    setError(null);
    try {
      const accepted = await enqueuePing(`dashboard ${new Date().toISOString()}`);
      setQueueLog([`enqueued ${accepted.task_id.slice(0, 8)}… state=${accepted.state}`]);

      for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
        const task = await getTask(accepted.task_id);
        if (task.ready) {
          setQueueLog((log) => [
            ...log,
            `state=${task.state}`,
            `worker echoed: ${task.result?.echo ?? "(no payload)"}`,
          ]);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      setQueueLog((log) => [...log, "timed out — is the worker running?"]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setQueueBusy(false);
    }
  }

  async function runRenderCheck() {
    setRenderBusy(true);
    setError(null);
    try {
      setRender(await renderSampleEmail());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRenderBusy(false);
    }
  }

  return (
    <Card
      title="Capability checks"
      subtitle="Runs the real paths, not mocks — each button exercises live infrastructure"
    >
      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
        <Row
          label="Queue round-trip"
          hint="API enqueues sendox.ping → Redis → Celery worker executes → result read back"
        >
          <Button onClick={() => void runQueueCheck()} disabled={queueBusy}>
            {queueBusy ? "Running…" : "Run"}
          </Button>
        </Row>

        {queueLog.length > 0 && (
          <ul className="space-y-1 py-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
            {queueLog.map((line, index) => (
              <li key={index}>→ {line}</li>
            ))}
          </ul>
        )}

        <Row
          label="MJML email render"
          hint="API posts MJML to the Node sidecar and gets cross-client HTML back (phase 1.8 uses this exact path)"
        >
          <Button onClick={() => void runRenderCheck()} disabled={renderBusy}>
            {renderBusy ? "Rendering…" : "Render sample"}
          </Button>
        </Row>

        {render && (
          <div className="py-3">
            <p className="font-mono text-xs text-zinc-600 dark:text-zinc-400">
              → {render.html_bytes.toLocaleString()} bytes ·{" "}
              {render.responsive ? "responsive (@media present)" : "no media queries"} ·{" "}
              {render.ok ? "no errors" : `${render.errors.length} error(s)`}
            </p>
            {!render.ok && (
              <ul className="mt-1 space-y-0.5 text-xs text-rose-600 dark:text-rose-400">
                {render.errors.map((mjmlError, index) => (
                  <li key={index}>
                    line {mjmlError.line} · {mjmlError.message}
                  </li>
                ))}
              </ul>
            )}
            <iframe
              title="Rendered email preview"
              srcDoc={render.html}
              sandbox=""
              className="mt-3 h-80 w-full rounded-lg border border-zinc-200 bg-white dark:border-zinc-800"
            />
          </div>
        )}
      </div>
    </Card>
  );
}
