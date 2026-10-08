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
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    // A network-level failure means the API is not reachable at all, which is a
    // different problem from a 5xx and worth saying plainly.
    throw new ApiError(`Cannot reach the API at ${API_BASE}`, 0);
  }

  const body = (await response.json().catch(() => null)) as unknown;

  if (!response.ok && response.status !== 503) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail, response.status);
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
