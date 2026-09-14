import type {
  ApprovalRow, DatabaseRow, PermissionView, ProjectRow, Projection,
  ServerRow, TaskEventRow, TaskRow,
} from "./types";

/** 桌面壳（Tauri）下前端跑在 tauri:// 协议里，相对路径 /api/... 会打到
 *  tauri://localhost/api/... 而不是后端 —— 必须显式指向后端地址。
 *  真实踩过：v0.1.0 打包后所有 API 静默失败，界面"点哪哪不动"。 */
function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  if ("__TAURI_INTERNALS__" in window) return true;
  const proto = window.location?.protocol ?? "";
  return proto === "tauri:" || proto === "asset:" || proto === "file:";
}

/** 后端默认地址。可用 localStorage["opspilot.apiBase"] 覆盖（设置里改端口时用）。 */
export const DEFAULT_API_BASE = "http://127.0.0.1:8791";

function resolveApiBase(): string {
  const env = import.meta.env.VITE_API_BASE as string | undefined;
  if (env) return env;
  try {
    const saved = localStorage.getItem("opspilot.apiBase");
    if (saved) return saved;
  } catch { /* localStorage 不可用时忽略 */ }
  return isTauri() ? DEFAULT_API_BASE : "";
}

export let API_BASE = resolveApiBase();

/** 运行时改后端地址（设置面板 / 端口变更），改完立刻生效并重存。 */
export function setApiBase(next: string) {
  API_BASE = next.replace(/\/+$/, "");
  try {
    if (next) localStorage.setItem("opspilot.apiBase", API_BASE);
    else localStorage.removeItem("opspilot.apiBase");
  } catch { /* ignore */ }
}

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

/** 探测后端。**依次尝试**候选地址，成功即固定 —— 不依赖任何环境判定。
 *
 * 为什么必须枚举：v0.1.1 仅靠 isTauri() 判定，实机（Windows Tauri v2）下
 * 判定没命中，API_BASE 仍是空串，请求全打到 tauri://localhost 而静默失败。
 * 与其猜环境，不如真去连一次。返回连通的那个地址，失败返回 null。 */
const PROBE_CANDIDATES = ["", DEFAULT_API_BASE, "http://localhost:8791"];

export async function probeBackend(): Promise<string | null> {
  const tried = [API_BASE, ...PROBE_CANDIDATES.filter((c) => c !== API_BASE)];
  for (const base of tried) {
    try {
      const resp = await fetch(`${base}/api/connections/servers`, {
        signal: AbortSignal.timeout(2500),
      });
      if (!resp.ok) continue;
      API_BASE = base;
      try {
        if (base) localStorage.setItem("opspilot.apiBase", base);
        else localStorage.removeItem("opspilot.apiBase");
      } catch { /* ignore */ }
      return base || "（同源）";
    } catch { /* 换下一个候选 */ }
  }
  return null;
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
// 注意：参数名必须是 rejected_reason（与后端 app.py 的 reject() 签名一致）。
// 曾写成 ?reason= —— 后端静默忽略并落默认值 "User rejected the action."，
// 用户填的拒绝理由全部丢失，审计里答不出"为什么拒绝"（真实踩过）。
export const rejectApproval = (id: string, reason: string) =>
  request<ApprovalRow & { resume: Record<string, unknown> }>(
    `/api/approvals/${id}/reject?rejected_reason=${encodeURIComponent(reason)}`, { method: "POST" });

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

// ---------- 上下文用量（ContextRing 真实数据源） ----------
export interface ContextUsage {
  task_id: string;
  model?: string;
  input_tokens: number;
  output_tokens: number;
  context_used_tokens: number;
  model_context_limit: number | null;
  context_used_percent: number | null;
  cache_hit_tokens: number;
  cache_miss_tokens: number;
  cache_hit_ratio: number | null;
  ring_state: "ok" | "warning" | "critical" | "unknown";
}
export const getContextUsage = (taskId: string) =>
  request<ContextUsage>(`/api/tasks/${taskId}/context-usage`);

// ---------- 主机健康（真实采集，非 mock） ----------
export const getServerHealth = (serverId: string) =>
  request<import("./types").HealthSnapshot>(`/api/servers/${serverId}/health`);
