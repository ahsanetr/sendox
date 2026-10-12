"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { logout } from "@/lib/api";
import { useSession } from "@/lib/session";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/flows", label: "Flows" },
  { href: "/contacts", label: "Contacts" },
  { href: "/brand", label: "Brand" },
] as const;

const SECONDARY = [
  { href: "/settings", label: "Settings" },
  { href: "/dev", label: "System" },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { me, activeWorkspace, refresh, setActiveWorkspaceId } = useSession();
  const [switcherOpen, setSwitcherOpen] = useState(false);

  return (
    <aside className="flex w-[17rem] shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 pt-6 pb-4">
        <Link
          href="/"
          className="text-[1.0625rem] font-semibold tracking-[-0.01em] text-white"
        >
          Sendox
        </Link>
      </div>

      {/* Workspace switcher. The current workspace is the most consequential
          piece of state in the app — everything below is scoped to it — so it
          sits at the top of the rail rather than hidden in a menu. */}
      {me && (
        <div className="relative px-4 pb-4">
          <button
            type="button"
            onClick={() => setSwitcherOpen((open) => !open)}
            aria-expanded={switcherOpen}
            className="flex w-full items-center gap-2.5 rounded-xl bg-sidebar-accent px-3 py-2.5 text-left transition hover:brightness-110"
          >
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-sidebar-primary text-xs font-semibold text-sidebar-primary-foreground">
              {(activeWorkspace?.name ?? "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-sidebar-accent-foreground">
                {activeWorkspace?.name ?? "No workspace"}
              </span>
            </span>
            <span className="text-xs opacity-60">{switcherOpen ? "▴" : "▾"}</span>
          </button>

          {switcherOpen && (
            <div className="absolute inset-x-4 top-full z-20 mt-1.5 overflow-hidden rounded-xl bg-sidebar ring-1 ring-sidebar-border shadow-xl">
              {me.workspaces.map((workspace) => (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => {
                    setActiveWorkspaceId(workspace.id);
                    setSwitcherOpen(false);
                  }}
                  className={`block w-full truncate px-3.5 py-2.5 text-left text-sm transition hover:bg-sidebar-accent ${
                    workspace.id === activeWorkspace?.id
                      ? "text-sidebar-accent-foreground"
                      : "text-sidebar-foreground"
                  }`}
                >
                  {workspace.name}
                </button>
              ))}
              <Link
                href="/settings"
                onClick={() => setSwitcherOpen(false)}
                className="block border-t border-sidebar-border px-3.5 py-2.5 text-sm text-sidebar-foreground transition hover:bg-sidebar-accent"
              >
                Manage workspaces
              </Link>
            </div>
          )}
        </div>
      )}

      <nav className="flex-1 px-4" aria-label="Main">
        <ul className="flex flex-col gap-1">
          {NAV.map((item) => (
            <li key={item.href}>
              <NavLink href={item.href} label={item.label} pathname={pathname} />
            </li>
          ))}
        </ul>

        <ul className="mt-7 flex flex-col gap-1 border-t border-sidebar-border/60 pt-5">
          {SECONDARY.map((item) => (
            <li key={item.href}>
              <NavLink href={item.href} label={item.label} pathname={pathname} />
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-sidebar-border/60 px-4 py-4">
        {me ? (
          <div className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-sidebar-foreground">
              {me.user.full_name ?? me.user.email}
            </span>
            <button
              type="button"
              onClick={() => void logout().then(refresh)}
              className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs text-sidebar-foreground transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            >
              Sign out
            </button>
          </div>
        ) : (
          <Link
            href="/signin"
            className="block rounded-lg px-3 py-2 text-sm text-sidebar-foreground transition hover:bg-sidebar-accent"
          >
            Sign in
          </Link>
        )}
      </div>
    </aside>
  );
}

function NavLink({
  href,
  label,
  pathname,
}: {
  href: string;
  label: string;
  pathname: string;
}) {
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`block rounded-xl px-3.5 py-2.5 text-sm transition ${
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
      }`}
    >
      {label}
    </Link>
  );
}
