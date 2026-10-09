"use client";

import { API_BASE, getReadiness } from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Button, Card, Dot, ErrorNote } from "@/components/dev-ui";

const REFRESH_MS = 10_000;

const DESCRIPTIONS: Record<string, string> = {
  postgres: "Contacts, campaigns, events",
  redis: "Celery broker + cache",
  chromadb: "Brand voice embeddings",
  mjml: "Email HTML renderer",
};

export function ServiceHealth() {
  const { data, error, checkedAt, refresh } = usePolledResource(
    getReadiness,
    REFRESH_MS,
  );

  return (
    <Card
      title="Backing services"
      subtitle={`${API_BASE}/health/ready${checkedAt ? ` · checked ${checkedAt}` : ""}`}
      action={<Button onClick={refresh}>Re-check</Button>}
    >
      {error && (
        <ErrorNote>
          {error}. Is the stack up? Run <code>make up</code> (Docker) or{" "}
          <code>make up-native</code>, then <code>make dev-api</code>.
        </ErrorNote>
      )}

      {data && (
        <>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            API v{data.version} · env {data.env} · overall{" "}
            <span
              className={
                data.status === "ok"
                  ? "font-medium text-emerald-600 dark:text-emerald-400"
                  : "font-medium text-rose-600 dark:text-rose-400"
              }
            >
              {data.status}
            </span>
          </p>

          <ul className="grid gap-2 sm:grid-cols-2">
            {Object.entries(data.checks).map(([name, check]) => (
              <li
                key={name}
                className="rounded-lg border border-zinc-200 px-3 py-2.5 dark:border-zinc-800"
              >
                <div className="flex items-center gap-2">
                  <Dot status={check.status} />
                  <span className="font-mono text-sm font-medium">{name}</span>
                  <span className="ml-auto text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
                    {check.latency_ms} ms
                  </span>
                </div>
                <p className="mt-1 pl-[1.125rem] text-xs text-zinc-500 dark:text-zinc-400">
                  {DESCRIPTIONS[name] ?? ""}
                </p>
                {check.detail && (
                  <p className="mt-1 pl-[1.125rem] text-xs break-words text-rose-600 dark:text-rose-400">
                    {check.detail}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {!data && !error && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Checking…</p>
      )}
    </Card>
  );
}
