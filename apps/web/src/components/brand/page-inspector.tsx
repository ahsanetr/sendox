"use client";

import { Eye, EyeOff, FileText, ImageIcon, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  getBrandPage,
  getBrandPages,
  setBrandPageExcluded,
  type BrandPage,
  type BrandPages,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, EmptyState, Pill } from "@/components/app/primitives";

/** What the crawler read, and the one decision the merchant owns about it.
 *
 *  This is the half of M6 that was missing. The crawl already worked, but its
 *  output went straight into the vector store, so the only way to see what the
 *  AI had learned was to search it. A search can only return pages it already
 *  judged relevant, which makes it exactly the wrong instrument for finding the
 *  page that should not have been learned from in the first place.
 */

const KIND_LABEL: Record<string, string> = {
  product: "Product",
  page: "Page",
  blog: "Journal",
  collection: "Collection",
  home: "Home",
};

export function PageInspector() {
  const { activeWorkspace } = useSession();
  const workspaceId = activeWorkspace?.id ?? null;

  const [data, setData] = useState<BrandPages | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reindexNeeded, setReindexNeeded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setData(await getBrandPages(workspaceId));
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [workspaceId]);

  // Deferred to the next tick rather than called in the effect's synchronous
  // phase, which is what react-hooks/set-state-in-effect guards against. Same
  // reasoning as use-polled-resource, which documents it at length.
  useEffect(() => {
    const first = setTimeout(() => void load(), 0);
    return () => clearTimeout(first);
  }, [load]);

  async function toggle(page: BrandPage) {
    if (!workspaceId) return;
    setBusy(page.id);
    try {
      await setBrandPageExcluded(workspaceId, page.id, page.included);
      setReindexNeeded(true);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(null);
    }
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
        <div className="h-4 w-48 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-5/6 rounded bg-muted" />
      </div>
    );
  }

  if (data.pages.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        headline="Nothing read yet"
        body="Once a store is connected, Sendox reads its public pages to learn how the brand writes. Everything it reads will be listed here for you to check."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
        <Figure value={data.counts.included} label="pages used" />
        <Figure value={data.counts.words.toLocaleString()} label="words of voice" />
        <Figure value={data.counts.images} label="images found" />
        {data.counts.pages !== data.counts.included && (
          <Figure
            value={data.counts.pages - data.counts.included}
            label="excluded by you"
            muted
          />
        )}
      </div>

      {reindexNeeded && (
        <p className="rounded-md bg-attention/10 px-3 py-2 text-sm text-attention ring-1 ring-inset ring-attention/20">
          Your changes apply the next time the storefront is indexed. Nothing already
          learned is forgotten until then.
        </p>
      )}

      <ul className="panel divide-y divide-border/60">
        {data.pages.map((page) => (
          <li
            key={page.id}
            className={`row-hover px-5 py-4 ${page.included ? "" : "opacity-55"}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="truncate text-sm font-medium">{page.title || page.url}</h4>
                  <Pill tone={page.included ? "neutral" : "attention"}>
                    {KIND_LABEL[page.kind] ?? page.kind}
                  </Pill>
                  {!page.included && <Pill tone="attention">Excluded</Pill>}
                </div>
                <a
                  href={page.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-0.5 block truncate font-mono text-xs text-muted-foreground hover:text-primary hover:underline"
                >
                  {page.url}
                </a>
                <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                  {page.preview}
                </p>
                <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
                  <span className="tabular">{page.word_count.toLocaleString()} words</span>
                  {page.images.length > 0 && (
                    <span className="flex items-center gap-1">
                      <ImageIcon className="size-3" aria-hidden />
                      {page.images.length}
                    </span>
                  )}
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                <Button variant="quiet" onClick={() => setOpen(page.id)}>
                  Read
                </Button>
                <button
                  type="button"
                  onClick={() => void toggle(page)}
                  disabled={busy === page.id}
                  aria-label={page.included ? "Exclude this page" : "Include this page"}
                  title={page.included ? "Exclude this page" : "Include this page"}
                  className="flex size-9 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {busy === page.id ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : page.included ? (
                    <Eye className="size-4" aria-hidden />
                  ) : (
                    <EyeOff className="size-4" aria-hidden />
                  )}
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {open && (
        <PageReader
          workspaceId={workspaceId}
          pageId={open}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

function Figure({
  value,
  label,
  muted,
}: {
  value: string | number;
  label: string;
  muted?: boolean;
}) {
  return (
    <div>
      <p
        className={`tabular text-2xl font-medium tracking-[-0.02em] ${
          muted ? "text-muted-foreground" : ""
        }`}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

/** The full extracted text of one page, exactly as the chunker will see it. */
function PageReader({
  workspaceId,
  pageId,
  onClose,
}: {
  workspaceId: string;
  pageId: string;
  onClose: () => void;
}) {
  const [page, setPage] = useState<(BrandPage & { text: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getBrandPage(workspaceId, pageId)
      .then((loaded) => {
        if (!cancelled) setPage(loaded);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, pageId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Extracted page text"
      className="fixed inset-0 z-40 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel flex max-h-[85vh] w-full max-w-3xl flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold tracking-tight">
              {page?.title || "Extracted text"}
            </h3>
            <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
              {page?.url ?? ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!page && !error && (
            <div className="space-y-2.5">
              {[...Array(6)].map((_, index) => (
                <div key={index} className="h-4 animate-pulse rounded bg-muted" />
              ))}
            </div>
          )}
          {page && (
            <>
              {/* Exactly what the chunker sees: site furniture already removed,
                  no markup. If this reads wrong, the knowledge base is wrong. */}
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{page.text}</p>
              {page.images.length > 0 && (
                <div className="mt-6 border-t border-border pt-5">
                  <p className="text-xs font-medium text-muted-foreground">
                    Images found on this page
                  </p>
                  <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {page.images.map((src) => (
                      <li key={src} className="overflow-hidden rounded-md border border-border">
                        {/* eslint-disable-next-line @next/next/no-img-element -- a
                            merchant's CDN is not in next.config's allowed hosts,
                            and adding every Shopify CDN there to preview a crawl
                            is not a trade worth making. */}
                        <img
                          src={src}
                          alt=""
                          loading="lazy"
                          className="aspect-square w-full bg-surface-sunken object-cover"
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
