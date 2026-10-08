import { BuildStatusPanel } from "@/components/build-status";
import { CapabilityChecks } from "@/components/capability-checks";
import { DatabaseStatus } from "@/components/database-status";
import { ServiceHealth } from "@/components/service-health";

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
          Internal dev dashboard
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Sendox</h1>
        <p className="mt-2 max-w-prose text-sm text-zinc-600 dark:text-zinc-400">
          AI-native multi-channel marketing platform for Shopify brands. This page
          shows what is actually wired up and working — not what the plan says
          should be. Everything below queries the live backend.
        </p>
      </header>

      <div className="space-y-5">
        <ServiceHealth />
        <DatabaseStatus />
        <CapabilityChecks />
        <BuildStatusPanel />
      </div>

      <footer className="mt-10 border-t border-zinc-200 pt-4 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        Plan: <code>docs/BUILD-PLAN.md</code> · Environment gotchas:{" "}
        <code>docs/DEV-ENVIRONMENT.md</code> · API docs:{" "}
        <a
          href="http://localhost:8000/docs"
          className="underline hover:no-underline"
        >
          localhost:8000/docs
        </a>
      </footer>
    </main>
  );
}
