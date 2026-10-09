"use client";

import { useState } from "react";

import { getAiStatus, pingAi, type AiPing } from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Badge, Button, Card, ErrorNote } from "@/components/dev-ui";

export function AiStatus() {
  const { data, error } = usePolledResource(getAiStatus);
  const [ping, setPing] = useState<AiPing | null>(null);
  const [busy, setBusy] = useState(false);
  const [pingError, setPingError] = useState<string | null>(null);

  async function runPing() {
    setBusy(true);
    setPingError(null);
    try {
      setPing(await pingAi());
    } catch (cause) {
      setPingError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Claude API"
      subtitle="Transport for every AI agent — Strategy, Copywriting, Optimization"
      action={<Badge status={data?.configured ? "done" : "planned"} />}
    >
      {error && <ErrorNote>{error}</ErrorNote>}

      {data && (
        <>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            model <span className="font-mono">{data.model}</span> ·{" "}
            {data.configured ? "API key present" : "no API key"}
          </p>
          {data.hint && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">{data.hint}</p>
          )}
          <div className="mt-3">
            <Button onClick={() => void runPing()} disabled={busy || !data.configured}>
              {busy ? "Calling…" : "Round-trip a prompt"}
            </Button>
          </div>
        </>
      )}

      {pingError && (
        <div className="mt-3">
          <ErrorNote>{pingError}</ErrorNote>
        </div>
      )}

      {ping && (
        <p className="mt-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
          → &quot;{ping.text}&quot; · {ping.model} · {ping.input_tokens} in /{" "}
          {ping.output_tokens} out
        </p>
      )}
    </Card>
  );
}
