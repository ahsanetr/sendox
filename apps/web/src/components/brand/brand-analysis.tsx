"use client";

import {
  AlertTriangle,
  Brain,
  ChevronDown,
  Loader2,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  getBrandAnalysis,
  restoreBrandAnalysis,
  startBrandAnalysis,
  type BrandAnalysisResult,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, EmptyState, Pill } from "@/components/app/primitives";

/** What the agent concluded from the brand's own data, and how sure it is.
 *
 *  Three things are shown that an AI feature usually hides: the confidence and
 *  why it is what it is, the places where the merchant's answers disagree with
 *  their catalogue, and the exact prompt. An analysis you cannot argue with is
 *  one you have to either trust completely or ignore completely, and neither is
 *  a reasonable thing to ask of someone whose brand it is.
 */

const CONFIDENCE_TONE = {
  high: "positive",
  medium: "attention",
  low: "attention",
} as const;

export function BrandAnalysis() {
  const { activeWorkspace } = useSession();
  const workspaceId = activeWorkspace?.id ?? null;

  const [data, setData] = useState<BrandAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setData(await getBrandAnalysis(workspaceId));
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [workspaceId]);

  useEffect(() => {
    const first = setTimeout(() => void load(), 0);
    return () => clearTimeout(first);
  }, [load]);

  // While an analysis is running, poll until a newer version appears. The task
  // is a model call of tens of seconds, which is too long to leave the page
  // claiming nothing happened.
  useEffect(() => {
    if (!running) return;
    const started = data?.generated ? data.version : 0;
    const timer = setInterval(() => {
      void (async () => {
        if (!workspaceId) return;
        const next = await getBrandAnalysis(workspaceId).catch(() => null);
        if (next?.generated && next.version > started) {
          setData(next);
          setRunning(false);
        }
      })();
    }, 4000);
    const giveUp = setTimeout(() => setRunning(false), 180_000);
    return () => {
      clearInterval(timer);
      clearTimeout(giveUp);
    };
  }, [running, workspaceId, data]);

  async function analyse() {
    if (!workspaceId) return;
    setRunning(true);
    setError(null);
    try {
      await startBrandAnalysis(workspaceId);
    } catch (reason: unknown) {
      setRunning(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function restore(version: number) {
    if (!workspaceId) return;
    await restoreBrandAnalysis(workspaceId, version).catch(() => null);
    await load();
  }

  if (!workspaceId) {
    return <p className="text-sm text-muted-foreground">Select a workspace first.</p>;
  }

  if (error) {
    return (
      <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive ring-1 ring-inset ring-destructive/20">
        {error}
      </p>
    );
  }

  if (data === null) {
    return (
      <div className="panel animate-pulse space-y-3 p-6">
        <div className="h-4 w-56 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
      </div>
    );
  }

  if (!data.generated) {
    return (
      <EmptyState
        icon={Brain}
        headline="Nothing analysed yet"
        body="Once your store is imported, Sendox reads the catalogue and your storefront copy and writes down what they say about your brand. It runs automatically after an import, or you can start it here."
        action={
          <Button onClick={() => void analyse()} disabled={running}>
            {running ? "Analysing…" : "Analyse my brand"}
          </Button>
        }
      />
    );
  }

  const a = data.analysis;
  const tone = CONFIDENCE_TONE[a.confidence ?? "low"];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={tone}>{a.confidence ?? "unknown"} confidence</Pill>
          <span className="text-xs text-muted-foreground">
            Version {data.version} · {data.model} ·{" "}
            {new Date(data.generated_at).toLocaleString()}
          </span>
        </div>
        <Button variant="quiet" onClick={() => void analyse()} disabled={running}>
          {running ? (
            <>
              <Loader2 className="mr-1.5 size-3.5 animate-spin" aria-hidden />
              Analysing
            </>
          ) : (
            "Re-analyse"
          )}
        </Button>
      </div>

      {a.confidence_reason && (
        <p className="rounded-md bg-muted px-3 py-2.5 text-sm leading-relaxed text-muted-foreground">
          {a.confidence_reason}
        </p>
      )}

      {/* The disagreements lead, because they are the only part that tells the
          merchant something they did not already know. */}
      {a.contradictions && a.contradictions.length > 0 && (
        <div className="panel border-attention/40 p-5">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="size-4 text-attention" aria-hidden />
            Where your answers and your data disagree
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Not necessarily errors. Usually one of the two is out of date, and only you
            know which.
          </p>
          <ul className="mt-3 space-y-2">
            {a.contradictions.map((item) => (
              <li
                key={item}
                className="border-l-2 border-attention/40 pl-3 text-sm leading-relaxed"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel divide-y divide-border/60">
        <Field label="Positioning" value={a.positioning} />
        <Field label="Audience" value={a.audience} />
        <Field label="Tone" value={a.tone} />
        <Field label="Sells" value={a.sells} />
        <Field label="Does not sell" value={a.does_not_sell} />
        <Field label="Price positioning" value={a.price_positioning?.summary} />
        <Field label="Product themes" value={a.product_themes} />
        <Field label="What sets it apart" value={a.usps} />
        <Field label="Voice markers" value={a.voice_markers} />
        <Field label="Vocabulary it uses" value={a.vocabulary} />
      </div>

      {data.sources.missing && data.sources.missing.length > 0 && (
        <div className="panel p-5">
          <h4 className="text-sm font-semibold">What it could not read</h4>
          <ul className="mt-2 space-y-1.5">
            {data.sources.missing.map((gap) => (
              <li key={gap} className="text-sm leading-relaxed text-muted-foreground">
                {gap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.versions.length > 1 && (
        <div className="panel p-5">
          <h4 className="text-sm font-semibold">Earlier versions</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Nothing is deleted. If a re-analysis is worse, put an earlier one back.
          </p>
          <ul className="mt-3 divide-y divide-border/60">
            {data.versions.map((item) => (
              <li
                key={item.version}
                className="flex items-center justify-between gap-3 py-2"
              >
                <span className="text-sm">
                  Version {item.version}
                  <span className="ml-2 text-xs text-muted-foreground">
                    {new Date(item.generated_at).toLocaleString()}
                  </span>
                </span>
                {item.current ? (
                  <Pill tone="accent">Current</Pill>
                ) : (
                  <button
                    type="button"
                    onClick={() => void restore(item.version)}
                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
                  >
                    <RotateCcw className="size-3.5" aria-hidden />
                    Restore
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* The prompt, in full. If a conclusion is wrong, this is the only place
          that explains why without guessing. */}
      <div className="panel">
        <button
          type="button"
          onClick={() => setShowPrompt((open) => !open)}
          aria-expanded={showPrompt}
          className="flex w-full cursor-pointer items-center justify-between gap-3 px-5 py-3.5 text-left transition-colors duration-200 hover:bg-surface-sunken"
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-muted-foreground" aria-hidden />
            Exactly what the model was given
          </span>
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            {data.input_tokens.toLocaleString()} in / {data.output_tokens.toLocaleString()} out
            <ChevronDown
              className={`size-4 transition-transform duration-200 ${showPrompt ? "rotate-180" : ""}`}
              aria-hidden
            />
          </span>
        </button>
        {showPrompt && (
          <pre className="max-h-96 overflow-auto border-t border-border px-5 py-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
            {data.prompt}
          </pre>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  if (Array.isArray(value) && value.length === 0) return null;

  return (
    <div className="px-5 py-3.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {Array.isArray(value) ? (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {value.map((item) => (
            <li
              key={String(item)}
              className="rounded-md bg-muted px-2 py-1 text-xs text-foreground"
            >
              {String(item)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-0.5 text-sm leading-relaxed">{String(value)}</p>
      )}
    </div>
  );
}
