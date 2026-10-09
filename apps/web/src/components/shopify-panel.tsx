"use client";

import { useCallback, useEffect, useState } from "react";

import {
  beginShopifyInstall,
  disconnectShopifyStore,
  getImportedData,
  getShopifyStatus,
  syncShopifyStore,
  type ImportedData,
  type ShopifyStatus,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Badge, Button, Card, ErrorNote, Field, Note, inputClass } from "@/components/ui";

const RANK = { viewer: 0, editor: 1, admin: 2, owner: 3 } as const;

export function ShopifyPanel() {
  const { activeWorkspace, role } = useSession();
  const [status, setStatus] = useState<ShopifyStatus | null>(null);
  const [shop, setShop] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [data, setData] = useState<ImportedData | null>(null);

  const workspaceId = activeWorkspace?.id ?? null;

  const load = useCallback(async (id: string) => {
    try {
      setStatus(await getShopifyStatus(id));
      setData(await getImportedData(id));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  // Shopify sends the merchant back to this page with the outcome in the query
  // string, because the callback itself has no UI to show them.
  useEffect(() => {
    const timer = setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      const connected = params.get("shopify_connected");
      const failed = params.get("shopify_error");
      if (connected) setOutcome(`Connected ${connected}.`);
      if (failed) setError(failed);
      if (connected || failed) {
        window.history.replaceState({}, "", window.location.pathname);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    const id = workspaceId;
    const timer = setTimeout(() => void load(id), 0);
    return () => clearTimeout(timer);
  }, [workspaceId, load]);

  if (!activeWorkspace) {
    return (
      <Card title="Shopify">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Select a workspace to connect a store.
        </p>
      </Card>
    );
  }

  const mayConnect = role !== null && RANK[role] >= RANK.admin;
  const stores = status?.stores ?? [];
  const live = stores.filter((store) => store.connected);

  return (
    <Card
      title="Shopify"
      subtitle="Phase 1.2 / M3 — the merchant installs the app and approves scopes, exactly as they would for Klaviyo"
      action={<Badge status={live.length > 0 ? "done" : "planned"} />}
    >
      {error && <ErrorNote>{error}</ErrorNote>}
      {outcome && (
        <div className="mb-3">
          <Note>{outcome}</Note>
        </div>
      )}

      {status && !status.ready && (
        <div className="mb-3">
          <ErrorNote>{status.hint}</ErrorNote>
        </div>
      )}

      {status && (
        <dl className="mb-4 flex flex-col gap-1 text-xs">
          <div className="flex flex-wrap gap-x-2">
            <dt className="w-28 shrink-0 text-zinc-500 dark:text-zinc-400">Redirect URL</dt>
            <dd className="min-w-0 font-mono break-all">{status.redirect_uri}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="w-28 shrink-0 text-zinc-500 dark:text-zinc-400">Scopes</dt>
            <dd className="min-w-0 font-mono break-all">{status.scopes.join(", ")}</dd>
          </div>
          <div className="flex flex-wrap gap-x-2">
            <dt className="w-28 shrink-0 text-zinc-500 dark:text-zinc-400">API version</dt>
            <dd className="font-mono">{status.api_version}</dd>
          </div>
        </dl>
      )}

      {stores.length > 0 && (
        <ul className="mb-4 divide-y divide-zinc-200 dark:divide-zinc-800">
          {stores.map((store) => (
            <li key={store.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {store.shop_name ?? store.shop_domain}
                </span>
                <span className="block truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">
                  {store.shop_domain}
                  {store.currency ? ` · ${store.currency}` : ""}
                </span>
              </span>
              <Badge status={store.connected ? "done" : "planned"} />
              {store.connected && (
                <Button
                  onClick={() =>
                    void (async () => {
                      setBusy(`sync-${store.id}`);
                      setError(null);
                      try {
                        await syncShopifyStore(activeWorkspace.id, store.id);
                        setOutcome(
                          "Import queued. It runs in a worker — re-check in a few seconds.",
                        );
                        // Give the worker a head start before reading counts back.
                        setTimeout(() => void load(activeWorkspace.id), 4000);
                      } catch (cause) {
                        setError(cause instanceof Error ? cause.message : String(cause));
                      } finally {
                        setBusy(null);
                      }
                    })()
                  }
                  disabled={busy !== null}
                >
                  {busy === `sync-${store.id}` ? "Queuing…" : "Import data"}
                </Button>
              )}
              {mayConnect && store.connected && (
                <Button
                  onClick={() =>
                    void (async () => {
                      setBusy(store.id);
                      try {
                        await disconnectShopifyStore(activeWorkspace.id, store.id);
                        await load(activeWorkspace.id);
                      } catch (cause) {
                        setError(cause instanceof Error ? cause.message : String(cause));
                      } finally {
                        setBusy(null);
                      }
                    })()
                  }
                  disabled={busy !== null}
                >
                  Disconnect
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form
        className="flex flex-wrap items-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800"
        onSubmit={(event) => {
          event.preventDefault();
          void connect();
        }}
      >
        <div className="min-w-48 flex-1">
          <Field
            label="Store domain"
            hint="Just the handle is enough — northwind becomes northwind.myshopify.com"
          >
            <input
              id="shopify-shop"
              value={shop}
              onChange={(event) => setShop(event.target.value)}
              className={inputClass}
              placeholder="your-store.myshopify.com"
              disabled={!mayConnect || !status?.ready}
            />
          </Field>
        </div>
        <Button
          onClick={() => void connect()}
          disabled={busy !== null || !mayConnect || !status?.ready || shop.trim().length < 3}
        >
          {busy === "install" ? "Redirecting…" : "Connect store"}
        </Button>
      </form>

      {!mayConnect && (
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Connecting a store requires the admin role; you are {role}.
        </p>
      )}

      {data && data.counts.contacts + data.counts.products > 0 && (
        <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Imported from Shopify
          </h3>
          <dl className="mt-2 grid grid-cols-3 gap-4">
            {[
              ["Contacts", data.counts.contacts],
              ["Events", data.counts.events],
              ["Products", data.counts.products],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dd className="font-mono text-xl tabular-nums">{String(value)}</dd>
                <dt className="text-xs text-zinc-500 dark:text-zinc-400">{String(label)}</dt>
              </div>
            ))}
          </dl>

          {data.top_contacts.length > 0 && (
            <ul className="mt-3 divide-y divide-zinc-200 dark:divide-zinc-800">
              {data.top_contacts.map((contact) => (
                <li
                  key={contact.email}
                  className="flex flex-wrap items-baseline gap-2 py-1.5 text-xs"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {contact.name ?? contact.email}
                  </span>
                  <span className="font-mono text-zinc-500 dark:text-zinc-400">
                    {contact.orders} orders
                  </span>
                  <span className="font-mono tabular-nums">{contact.spent.toFixed(2)}</span>
                  <Badge
                    status={contact.consent === "subscribed" ? "done" : "planned"}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        You will be sent to your Shopify admin to approve the scopes above, then
        returned here. The access token is encrypted per workspace before it is stored.
      </p>
    </Card>
  );

  async function connect() {
    if (!activeWorkspace) return;
    setBusy("install");
    setError(null);
    try {
      const { authorize_url } = await beginShopifyInstall(activeWorkspace.id, shop.trim());
      // Full navigation, not fetch: this is the merchant's own Shopify admin.
      window.location.href = authorize_url;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(null);
    }
  }
}
