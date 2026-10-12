"use client";

import {
  Boxes,
  ChevronsUpDown,
  Home,
  LogOut,
  Mail,
  Settings,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";

import { logout } from "@/lib/api";
import { useSession } from "@/lib/session";
import { SchemePicker } from "@/components/app/scheme-picker";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Home", icon: Home },
  { href: "/campaigns", label: "Campaigns", icon: Mail },
  { href: "/flows", label: "Flows", icon: Workflow },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/brand", label: "Brand", icon: Sparkles },
];

const SECONDARY: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/dev", label: "System", icon: Boxes },
];

export function Sidebar() {
  const pathname = usePathname();
  const { me, activeWorkspace, refresh, setActiveWorkspaceId } = useSession();
  const [switcherOpen, setSwitcherOpen] = useState(false);

  return (
    <aside className="sticky top-0 flex h-screen w-[17rem] shrink-0 flex-col bg-sidebar text-sidebar-foreground">
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
            className="flex w-full items-center gap-2.5 cursor-pointer rounded-md bg-sidebar-accent px-3 py-2.5 text-left transition-colors duration-200 hover:brightness-110"
          >
            <span className="grid size-7 shrink-0 place-items-center rounded-md bg-sidebar-primary text-xs font-semibold text-sidebar-primary-foreground">
              {(activeWorkspace?.name ?? "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-sidebar-accent-foreground">
                {activeWorkspace?.name ?? "No workspace"}
              </span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 opacity-50" aria-hidden />
          </button>

          {switcherOpen && (
            <div className="absolute inset-x-4 top-full z-20 mt-1.5 overflow-hidden rounded-md bg-sidebar ring-1 ring-sidebar-border shadow-xl">
              {me.workspaces.map((workspace) => (
                <button
                  key={workspace.id}
                  type="button"
                  onClick={() => {
                    setActiveWorkspaceId(workspace.id);
                    setSwitcherOpen(false);
                  }}
                  className={`block w-full truncate px-3.5 py-2.5 cursor-pointer text-left text-sm transition-colors duration-200 hover:bg-sidebar-accent ${
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

      <nav className="min-h-0 flex-1 overflow-y-auto px-4" aria-label="Main">
        <ul className="flex flex-col gap-1">
          {NAV.map((item) => (
            <li key={item.href}>
              <NavLink item={item} pathname={pathname} />
            </li>
          ))}
        </ul>

        <ul className="mt-7 flex flex-col gap-1 border-t border-sidebar-border/60 pt-5">
          {SECONDARY.map((item) => (
            <li key={item.href}>
              <NavLink item={item} pathname={pathname} />
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex items-center gap-2 border-t border-sidebar-border/60 px-4 py-3">
        <SchemePicker />
        {me ? (
          <>
            <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-sidebar-foreground">
              {me.user.full_name ?? me.user.email}
            </span>
            <button
              type="button"
              onClick={() => void logout().then(refresh)}
              aria-label="Sign out"
              title="Sign out"
              className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-sidebar-foreground transition-colors duration-200 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            >
              <LogOut className="size-4" aria-hidden />
            </button>
          </>
        ) : (
          <Link
            href="/signin"
            className="flex-1 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground transition-colors duration-200 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          >
            Sign in
          </Link>
        )}
      </div>
    </aside>
  );
}

function NavLink({
  item,
  pathname,
}: {
  item: { href: string; label: string; icon: LucideIcon };
  pathname: string;
}) {
  const active =
    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-200 ${
        active
          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
      }`}
    >
      <Icon
        className={`size-[1.125rem] shrink-0 ${active ? "text-sidebar-primary" : ""}`}
        aria-hidden
      />
      {item.label}
    </Link>
  );
}
