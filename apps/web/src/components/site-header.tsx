"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useSession } from "@/lib/session";
import { RoleBadge } from "@/components/ui";

const LINKS = [
  { href: "/", label: "System" },
  { href: "/account", label: "Account & workspaces" },
] as const;

export function SiteHeader() {
  const pathname = usePathname();
  const { me, activeWorkspace, loading } = useSession();

  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="font-semibold tracking-tight">
          Sendox
        </Link>

        <nav className="flex gap-4" aria-label="Main">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`text-sm transition ${
                  active
                    ? "font-medium text-zinc-900 dark:text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2 text-xs">
          {loading && <span className="text-zinc-400 dark:text-zinc-500">…</span>}
          {!loading && !me && (
            <Link
              href="/account"
              className="text-zinc-500 underline hover:no-underline dark:text-zinc-400"
            >
              Sign in
            </Link>
          )}
          {me && (
            <>
              {activeWorkspace && (
                <span className="hidden items-center gap-1.5 sm:flex">
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {activeWorkspace.name}
                  </span>
                  <RoleBadge role={activeWorkspace.role} />
                </span>
              )}
              <span className="max-w-40 truncate text-zinc-500 dark:text-zinc-400">
                {me.user.email}
              </span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
