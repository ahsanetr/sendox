"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, getMe, type Me, type MemberRole } from "@/lib/api";

const ACTIVE_WORKSPACE_KEY = "sendox.activeWorkspace";

type SessionState = {
  me: Me | null;
  loading: boolean;
  error: string | null;
  activeWorkspaceId: string | null;
  activeWorkspace: Me["workspaces"][number] | null;
  role: MemberRole | null;
  refresh: () => void;
  setActiveWorkspaceId: (id: string | null) => void;
};

const SessionContext = createContext<SessionState | null>(null);

/** Remembering the chosen workspace is a per-viewer convenience, so localStorage
 *  is the right home for it — and it must survive the storage being unavailable. */
function readStored(): string | null {
  try {
    return localStorage.getItem(ACTIVE_WORKSPACE_KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string | null): void {
  try {
    if (id) localStorage.setItem(ACTIVE_WORKSPACE_KEY, id);
    else localStorage.removeItem(ACTIVE_WORKSPACE_KEY);
  } catch {
    /* private window or blocked site data; the app still works */
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeWorkspaceId, setActive] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getMe();
      setMe(next);
      setError(null);

      // Keep the remembered workspace only while it is still one of theirs.
      const stored = readStored();
      const valid = next.workspaces.find((w) => w.id === stored);
      setActive(valid?.id ?? next.workspaces[0]?.id ?? null);
    } catch (cause) {
      setMe(null);
      // Not being signed in is a state, not an error worth showing.
      setError(cause instanceof ApiError && cause.isUnauthenticated ? null : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = () => void load();
    const timer = setTimeout(run, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const setActiveWorkspaceId = useCallback((id: string | null) => {
    setActive(id);
    writeStored(id);
  }, []);

  const value = useMemo<SessionState>(() => {
    const activeWorkspace =
      me?.workspaces.find((w) => w.id === activeWorkspaceId) ?? null;
    return {
      me,
      loading,
      error,
      activeWorkspaceId,
      activeWorkspace,
      role: activeWorkspace?.role ?? null,
      refresh: () => void load(),
      setActiveWorkspaceId,
    };
  }, [me, loading, error, activeWorkspaceId, load, setActiveWorkspaceId]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
