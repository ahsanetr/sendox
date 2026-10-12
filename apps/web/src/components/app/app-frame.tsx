"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/lib/session";
import { Sidebar } from "@/components/app/sidebar";
import { SignInScreen } from "@/components/app/sign-in-screen";

/** The product chrome: a dark rail that stays put, and a scrolling canvas.
 *
 *  Signed-out visitors get the sign-in screen instead of an empty shell — a
 *  navigation rail full of links you cannot use is worse than no rail.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  const pathname = usePathname();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  // The system page is deliberately reachable without an account: it is how you
  // check whether the platform is up, which is most useful when it is not.
  if (!me && pathname !== "/dev") {
    return <SignInScreen />;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="min-w-0 flex-1 bg-canvas">
        <div className="measure pb-16">{children}</div>
      </main>
    </div>
  );
}
