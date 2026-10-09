// Typed client for the Sendox API. One place that knows the base URL and the
// response shapes, so components stay free of fetch plumbing.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ProbeStatus = "ok" | "error";

export type Readiness = {
  status: "ok" | "degraded";
  version: string;
  env: string;
  checks: Record<
    string,
    { status: ProbeStatus; latency_ms: number; detail?: string }
  >;
};

export type ItemStatus = "done" | "in_progress" | "partial" | "planned";

export type StatusItem = {
  id: string;
  name: string;
  release: string;
  phase?: string;
  status: ItemStatus;
  note?: string;
};

export type Release = { id: string; title: string; window: string };

export type BuildStatus = {
  api_version: string;
  totals: Record<string, number>;
  note: string;
  releases: Release[];
  foundation: StatusItem[];
  modules: StatusItem[];
};

export type DatabaseStatus =
  | { reachable: false; error: string }
  | {
      reachable: true;
      migration_revision: string | null;
      session_role: string;
      session_is_superuser: boolean;
      tables: string[];
      tenant_scoped_tables: string[];
      rls_protected_tables: string[];
      unprotected_tables: string[];
      enforced: boolean;
    };

export type MjmlError = { line: number; message: string; tagName: string };

export type RenderResult = {
  ok: boolean;
  errors: MjmlError[];
  html_bytes: number;
  responsive: boolean;
  html: string;
};

export type VectorStats = {
  tenant_id: string;
  collection: string;
  chunks: number;
  embedding_model: string;
  dimensions: number;
  distance: string;
};

export type VectorMatch = {
  id: string;
  similarity: number;
  distance: number;
  content_type: string | null;
  text: string;
};

export type VectorQueryResult = {
  query: string;
  tenant_id: string;
  matches: VectorMatch[];
};

export type AiStatus = {
  configured: boolean;
  model: string;
  hint: string | null;
};

export type AiPing = {
  text: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
};

export type TaskAccepted = { task_id: string; state: string };

export type TaskResult = {
  task_id: string;
  state: string;
  ready: boolean;
  result: { status: string; echo: string } | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

/** Pydantic reports field errors as objects; our own validation as plain strings. */
function readDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "string"
          ? item
          : String((item as { msg?: unknown }).msg ?? JSON.stringify(item)),
      )
      .join(" · ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      // The API issues an httpOnly session cookie, so the session is never
      // readable by page scripts. localhost:3000 and localhost:8000 are the same
      // site (ports do not change the site), so a SameSite=Lax cookie is sent.
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    // A network-level failure means the API is not reachable at all, which is a
    // different problem from a 5xx and worth saying plainly.
    throw new ApiError(`Cannot reach the API at ${API_BASE}`, 0);
  }

  const body = (await response.json().catch(() => null)) as unknown;

  if (!response.ok && response.status !== 503) {
    throw new ApiError(readDetail(body, response.statusText), response.status);
  }

  return body as T;
}

// 503 is an expected answer here: it means "reachable, but a dependency is down".
export const getReadiness = () => request<Readiness>("/health/ready");

export const getBuildStatus = () => request<BuildStatus>("/status/modules");

export const getDatabaseStatus = () => request<DatabaseStatus>("/status/database");

export const renderSampleEmail = (mjml?: string) =>
  request<RenderResult>("/dev/mjml/render", {
    method: "POST",
    body: JSON.stringify(mjml ? { mjml } : {}),
  });

export const getVectorStats = () => request<VectorStats>("/dev/vectors/stats");

export const seedVectors = () =>
  request<VectorStats & { chunks_written: number }>("/dev/vectors/seed", {
    method: "POST",
  });

export const queryVectors = (query: string, topK = 3) =>
  request<VectorQueryResult>("/dev/vectors/query", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK }),
  });

export const dropVectors = () =>
  request<{ dropped: string }>("/dev/vectors", { method: "DELETE" });

export const getAiStatus = () => request<AiStatus>("/dev/ai/status");

export const pingAi = () => request<AiPing>("/dev/ai/ping", { method: "POST" });

export const enqueuePing = (payload: string) =>
  request<TaskAccepted>(
    `/dev/tasks/ping?payload=${encodeURIComponent(payload)}`,
    { method: "POST" },
  );

export const getTask = (taskId: string) =>
  request<TaskResult>(`/dev/tasks/${taskId}`);


// ------------------------------------------------------------------ accounts

export type Me = {
  user: {
    id: string;
    email: string;
    full_name: string | null;
    email_verified: boolean;
    created_at: string;
  };
  workspaces: {
    id: string;
    name: string;
    slug: string;
    timezone: string;
    role: MemberRole;
  }[];
};

export type MemberRole = "owner" | "admin" | "editor" | "viewer";

export const ROLE_ORDER: MemberRole[] = ["viewer", "editor", "admin", "owner"];

export type RegisterResult = {
  user: Me["user"];
  next: string;
  dev_hint: string | null;
  dev_verification_token: string | null;
};

export type Member = {
  user_id: string;
  email: string | null;
  full_name: string | null;
  role: MemberRole;
  joined_at: string;
};

export type Invitation = {
  id: string;
  email: string;
  role: MemberRole;
  expires_at: string;
};

export type AuditEntry = {
  action: string;
  target: string | null;
  actor_user_id: string | null;
  meta: Record<string, unknown>;
  at: string;
};

export const getMe = () => request<Me>("/auth/me");

export const register = (body: {
  email: string;
  password: string;
  full_name?: string;
  workspace_name?: string;
}) => request<RegisterResult>("/auth/register", { method: "POST", body: JSON.stringify(body) });

export const verifyEmail = (token: string) =>
  request<{ user: Me["user"] }>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });

export const login = (email: string, password: string) =>
  request<{ user: Me["user"] }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const logout = () => request<{ status: string }>("/auth/logout", { method: "POST" });

export const deleteAccount = () =>
  request<{ status: string; workspaces_deleted: number; memberships_removed: number }>(
    "/auth/me",
    { method: "DELETE" },
  );

// ---------------------------------------------------------------- workspaces

export const createWorkspace = (name: string, timezone = "UTC") =>
  request<Me["workspaces"][number]>("/workspaces", {
    method: "POST",
    body: JSON.stringify({ name, timezone }),
  });

export const updateWorkspace = (
  id: string,
  body: { name?: string; timezone?: string },
) =>
  request<Me["workspaces"][number]>(`/workspaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const getMembers = (id: string) => request<Member[]>(`/workspaces/${id}/members`);

export const setMemberRole = (id: string, userId: string, role: MemberRole) =>
  request<{ status: string }>(`/workspaces/${id}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });

export const removeMember = (id: string, userId: string) =>
  request<{ status: string }>(`/workspaces/${id}/members/${userId}`, { method: "DELETE" });

export const getInvitations = (id: string) =>
  request<Invitation[]>(`/workspaces/${id}/invitations`);

export const inviteMember = (id: string, email: string, role: MemberRole) =>
  request<{ invitation: Invitation; dev_invitation_token: string | null }>(
    `/workspaces/${id}/invitations`,
    { method: "POST", body: JSON.stringify({ email, role }) },
  );

export const acceptInvitation = (token: string) =>
  request<{ status: string; workspace: { id: string; name: string }; role: MemberRole }>(
    "/invitations/accept",
    { method: "POST", body: JSON.stringify({ token }) },
  );

export const previewInvitation = (token: string) =>
  request<{ email: string; role: MemberRole; workspace: string | null; expires_at: string }>(
    "/invitations/preview",
    { method: "POST", body: JSON.stringify({ token }) },
  );

export const getAudit = (id: string) => request<AuditEntry[]>(`/workspaces/${id}/audit`);


// -------------------------------------------------------------------- Shopify

export type ShopifyStore = {
  id: string;
  shop_domain: string;
  shop_name: string | null;
  currency: string | null;
  scopes: string[];
  connected: boolean;
  installed_at: string | null;
  last_sync_at: string | null;
};

export type ShopifyStatus = {
  configured: boolean;
  public_url_set: boolean;
  ready: boolean;
  redirect_uri: string;
  scopes: string[];
  api_version: string;
  stores: ShopifyStore[];
  hint: string | null;
};

export const getShopifyStatus = (workspaceId: string) =>
  request<ShopifyStatus>(`/workspaces/${workspaceId}/shopify/status`);

export const beginShopifyInstall = (workspaceId: string, shop: string) =>
  request<{ authorize_url: string; shop_domain: string }>(
    `/workspaces/${workspaceId}/shopify/install`,
    { method: "POST", body: JSON.stringify({ shop }) },
  );

export const disconnectShopifyStore = (workspaceId: string, storeId: string) =>
  request<{ status: string; shop_domain: string }>(
    `/workspaces/${workspaceId}/shopify/stores/${storeId}`,
    { method: "DELETE" },
  );

export type ImportedData = {
  counts: { contacts: number; events: number; products: number };
  top_contacts: {
    email: string;
    name: string | null;
    consent: string;
    orders: number;
    spent: number;
  }[];
  products: { title: string; price: number | null; status: string | null }[];
};

export const syncShopifyStore = (workspaceId: string, storeId: string) =>
  request<{ status: string; task_id: string; shop_domain: string }>(
    `/workspaces/${workspaceId}/shopify/stores/${storeId}/sync`,
    { method: "POST" },
  );

export const getImportedData = (workspaceId: string) =>
  request<ImportedData>(`/workspaces/${workspaceId}/shopify/data`);
