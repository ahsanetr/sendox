"use client";

import { getDatabaseStatus } from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Badge, Card, ErrorNote } from "@/components/ui";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 py-1.5">
      <span className="w-40 shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
        {label}
      </span>
      <span className="min-w-0 font-mono text-xs">{children}</span>
    </div>
  );
}

export function DatabaseStatus() {
  const { data, error } = usePolledResource(getDatabaseStatus);

  if (error) {
    return (
      <Card title="Database & tenant isolation">
        <ErrorNote>{error}</ErrorNote>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="Database & tenant isolation">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Loading…</p>
      </Card>
    );
  }

  if (!data.reachable) {
    return (
      <Card title="Database & tenant isolation">
        <ErrorNote>
          Database unreachable — {data.error}. Run <code>make migrate</code> after{" "}
          <code>make up</code>.
        </ErrorNote>
      </Card>
    );
  }

  return (
    <Card
      title="Database & tenant isolation"
      subtitle="Phase 0.2 — row-level security enforced in Postgres, not in application code"
      action={<Badge status={data.enforced ? "done" : "error"} />}
    >
      {!data.enforced && (
        <ErrorNote>
          Tenant isolation is NOT enforced.
          {data.session_is_superuser &&
            " The session role is a superuser, and Postgres skips policies for superusers."}
          {data.unprotected_tables.length > 0 &&
            ` Unprotected: ${data.unprotected_tables.join(", ")}.`}
        </ErrorNote>
      )}

      <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
        <Field label="Migration revision">{data.migration_revision ?? "none"}</Field>
        <Field label="Session role">
          {data.session_role}
          {data.session_is_superuser ? (
            <span className="ml-2 text-rose-600 dark:text-rose-400">superuser</span>
          ) : (
            <span className="ml-2 text-emerald-600 dark:text-emerald-400">
              not superuser
            </span>
          )}
        </Field>
        <Field label="Tables">{data.tables.join(", ")}</Field>
        <Field label="Tenant-scoped">
          {data.tenant_scoped_tables.join(", ") || "none"}
        </Field>
        <Field label="RLS protected">
          {data.rls_protected_tables.join(", ") || "none"}
        </Field>
      </div>

      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        Every tenant-scoped table carries a FORCE&apos;d policy comparing{" "}
        <code>tenant_id</code> against the <code>app.current_tenant_id</code> session
        setting, and application sessions run as a non-superuser role. A query that
        forgets to filter by workspace returns nothing rather than another
        brand&apos;s data.
      </p>
    </Card>
  );
}
