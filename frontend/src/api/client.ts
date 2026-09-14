import type {
  ApprovalRow, DatabaseRow, PermissionView, ProjectRow, Projection,
  ServerRow, TaskEventRow, TaskRow,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try { const j = await resp.json(); detail = j.detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(resp.status, String(detail));
  }
  return resp.json() as Promise<T>;
}

/** 探测后端是否在线（决定前端走真数据还是 mock） */
export async function probeBackend(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/connections/servers`, {
      signal: AbortSignal.timeout(2500),
    });
    return resp.ok;
  } catch { return false; }
}

// ---------- 连接管理 ----------
export const getServers = () => request<ServerRow[]>("/api/connections/servers");
export const createServer = (body: Record<string, unknown>) =>
  request<ServerRow>("/api/connections/servers", { method: "POST", body: JSON.stringify(body) });
export const testServer = (id: string) =>
  request<Record<string, unknown>>(`/api/connections/servers/${id}/test`, { method: "POST" });
export const getDatabases = () => request<DatabaseRow[]>("/api/connections/databases");
export const createDatabase = (body: Record<string, unknown>) =>
  request<DatabaseRow>("/api/connections/databases", { method: "POST", body: JSON.stringify(body) });
export const getProjects = () => request<ProjectRow[]>("/api/projects");
export const createProject = (body: Record<string, unknown>) =>
  request<ProjectRow>("/api/projects", { method: "POST", body: JSON.stringify(body) });

// ---------- 任务 ----------
export const getTasks = () => request<TaskRow[]>("/api/tasks");
export const getTask = (id: string) => request<TaskRow>(`/api/tasks/${id}`);
export interface RunTaskBody {
  server_id: string; user_request: string; title?: string;
  tier: string; environment: string; async_run: boolean;
}
export const runTask = (body: RunTaskBody) =>
  request<TaskRow & { state: string; elapsed_s?: number; approval_id?: string; waiting?: boolean }>(
    "/api/tasks/run", { method: "POST", body: JSON.stringify(body) });
export const getTaskState = (id: string) => request<Projection>(`/api/tasks/${id}/state`);
export const getTaskEvents = (id: string) => request<TaskEventRow[]>(`/api/tasks/${id}/events`);
export const cancelTask = (id: string) =>
  request<Record<string, unknown>>(`/api/tasks/${id}/cancel`, { method: "POST" });

// ---------- 审批 ----------
export const listApprovals = () => request<ApprovalRow[]>("/api/approvals");
export const approveApproval = (id: string) =>
  request<ApprovalRow & { resume: Record<string, unknown> }>(
    `/api/approvals/${id}/approve`, { method: "POST" });
export const rejectApproval = (id: string, reason: string) =>
  request<ApprovalRow & { resume: Record<string, unknown> }>(
    `/api/approvals/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: "POST" });

// ---------- 权限档位 ----------
export const getPermission = (sessionId: string, environment: string) =>
  request<PermissionView>(`/api/session/${sessionId}/permission?environment=${environment}`);
export const changePermission = (
  sessionId: string, body: { environment: string; target: string; acknowledged?: boolean; env_confirm?: string },
) => request<Record<string, unknown>>(`/api/session/${sessionId}/permission`, {
  method: "POST", body: JSON.stringify(body),
});

// ---------- 审计 ----------
export const getAudit = (kind?: string, limit = 100) =>
  request<Record<string, unknown>[]>(`/api/audit?limit=${limit}${kind ? `&kind=${kind}` : ""}`);

// ---------- 主机健康（真实采集，非 mock） ----------
export const getServerHealth = (serverId: string) =>
  request<import("./types").HealthSnapshot>(`/api/servers/${serverId}/health`);
