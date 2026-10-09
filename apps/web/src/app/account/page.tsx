import { AuthPanel } from "@/components/auth-panel";
import { ShopifyPanel } from "@/components/shopify-panel";
import { WorkspacePanel } from "@/components/workspace-panel";

export const metadata = {
  title: "Account & workspaces — Sendox",
};

export default function AccountPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
          Phase 1.1 · Module M1
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          Accounts &amp; workspaces
        </h1>
        <p className="mt-2 max-w-prose text-sm text-zinc-600 dark:text-zinc-400">
          Sign-up with email confirmation, sessions in httpOnly cookies, workspaces with
          four roles, invitations, and an activity log. Every workspace&apos;s data is
          separated inside Postgres rather than by application code — switch workspaces
          below and the members, invitations and log all change with it.
        </p>
      </header>

      <div className="space-y-5">
        <AuthPanel />
        <WorkspacePanel />
        <ShopifyPanel />
      </div>
    </main>
  );
}
