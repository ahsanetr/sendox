"use client";

import { useState } from "react";

import {
  dropVectors,
  getVectorStats,
  queryVectors,
  seedVectors,
  type VectorMatch,
} from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Badge, Button, Card, ErrorNote } from "@/components/ui";

const EXAMPLE_QUERIES = [
  "can I send something back?",
  "what should I wear on my hands?",
  "how do you write marketing copy?",
];

export function BrandKnowledge() {
  const { data: stats, error: statsError, refresh } = usePolledResource(getVectorStats);
  const [query, setQuery] = useState(EXAMPLE_QUERIES[0]);
  const [matches, setMatches] = useState<VectorMatch[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
      refresh();
    }
  }

  const seeded = (stats?.chunks ?? 0) > 0;

  return (
    <Card
      title="Brand knowledge (vector store)"
      subtitle="Phase 0.5 / M7 groundwork — embeddings run locally, no API key, no per-call cost"
      action={<Badge status={seeded ? "partial" : "planned"} />}
    >
      {statsError && <ErrorNote>{statsError}</ErrorNote>}
      {error && <ErrorNote>{error}</ErrorNote>}

      {stats && (
        <dl className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          {[
            ["Chunks", String(stats.chunks)],
            ["Dimensions", String(stats.dimensions)],
            ["Distance", stats.distance],
            ["Model", stats.embedding_model.replace(" (ONNX, local)", "")],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
              <dd className="font-mono">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() => void run("seed", seedVectors)}
          disabled={busy !== null}
        >
          {busy === "seed" ? "Embedding…" : "Seed sample brand content"}
        </Button>
        <Button
          onClick={() =>
            void run("drop", async () => {
              await dropVectors();
              setMatches(null);
            })
          }
          disabled={busy !== null || !seeded}
        >
          Drop
        </Button>
      </div>

      <div className="mt-4">
        <label
          htmlFor="vector-query"
          className="block text-xs text-zinc-500 dark:text-zinc-400"
        >
          Semantic search — try wording that shares no words with the source text
        </label>
        <div className="mt-1.5 flex flex-wrap gap-2">
          <input
            id="vector-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-transparent px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700"
            placeholder="ask something"
          />
          <Button
            onClick={() =>
              void run("query", async () => {
                const result = await queryVectors(query);
                setMatches(result.matches);
              })
            }
            disabled={busy !== null || !seeded || query.trim() === ""}
          >
            {busy === "query" ? "Searching…" : "Search"}
          </Button>
        </div>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {EXAMPLE_QUERIES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuery(example)}
              className="rounded-full border border-zinc-300 px-2 py-0.5 text-xs text-zinc-600 transition hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-400"
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {matches && (
        <ul className="mt-4 space-y-2">
          {matches.length === 0 && (
            <li className="text-xs text-zinc-500 dark:text-zinc-400">
              No matches — seed the knowledge base first.
            </li>
          )}
          {matches.map((match) => (
            <li
              key={match.id}
              className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800"
            >
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                  {match.similarity.toFixed(3)}
                </span>
                <span className="text-zinc-500 dark:text-zinc-400">
                  {match.content_type ?? "unknown"}
                </span>
                <span className="ml-auto font-mono text-zinc-400 dark:text-zinc-500">
                  {match.id}
                </span>
              </div>
              <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">{match.text}</p>
            </li>
          ))}
        </ul>
      )}

      {!seeded && (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          Nothing embedded yet. Seeding writes five sample chunks (about page, brand
          voice, two products, FAQ) standing in for what the storefront crawler will
          extract in phase 1.4.
        </p>
      )}
    </Card>
  );
}
