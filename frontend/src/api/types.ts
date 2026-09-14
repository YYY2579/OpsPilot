export type EnvKey = "production" | "staging" | "development" | "lab";

export interface ServerRow {
  id: string; name: string; host: string; port: number; username: string;
  credential_ref: string; environment: EnvKey; status: string;
}
export interface DatabaseRow {
  id: string; name: string; db_type: string; host: string; port: number;
  username: string; credential_ref: string; readonly: number; environment: EnvKey; status: string;
}
export interface ProjectRow {
  id: string; name: string; path: string; repository_url: string; environment: EnvKey;
}
export interface TaskRow {
  id: string; title: string; user_request: string; context_type: string; context_id: string;
  status: string; current_step: string; risk_level: string;
}
export interface ApprovalRow {
  id: string; task_id: string; operation_description: string; risk_level: string;
  impact: string; rollback_plan: string; status: string;
}
export interface TaskEventRow {
  id: string; task_id: string; kind: string; state: string; message: string;
  payload: Record<string, unknown> | string;
}
export interface Projection {
  state: string; internal: boolean; terminal: boolean;
  history: { state: string; reason: string }[];
  tool_calls: number; approvals: number; rejections: number;
}
export interface PermissionView {
  session_id: string; environment: string; tier: string;
  expires_at: number | null; tiers: string[];
}

export const envLabel = (env: string): "生产" | "测试" | "开发" =>
  env === "production" ? "生产" : env === "staging" ? "测试" : "开发";

export const envColor = (env: string): string =>
  env === "production" ? "var(--err)" : env === "staging" ? "var(--warn)" : "var(--text3)";

export const TERMINAL_TASK_STATES = new Set(["completed", "failed", "cancelled", "timeout"]);

/** SDK 执行状态 → 规格 §A7 业务状态（源码索引 §0.2 的映射锚点） */
export function projectSdkStatus(sdk: string): string {
  switch (sdk) {
    case "waiting_for_confirmation": return "WAITING_APPROVAL";
    case "finished": return "COMPLETED";
    case "error": return "FAILED";
    case "paused": return "WAITING_USER";
    case "running": return "INSPECT";
    default: return "INSPECT";
  }
}

/** 主机健康快照（GET /api/servers/:id/health 的真实返回） */
export interface HealthSnapshot {
  server_id: string;
  name?: string | null;
  host?: string | null;
  environment?: string | null;
  ok: boolean;
  stage?: string;
  kind?: string;
  message?: string;
  latency_ms?: number;
  uptime_text?: string;
  os?: { name: string };
  cpu?: { percent: number; load_avg: number[]; cores: number; status: string };
  memory?: { percent: number; used_gb: number; total_gb: number; status: string };
  disk?: { used_percent: number; status: string };
  top_process?: { pid: number; name: string; cpu: number }[];
  services?: Record<string, string>;
  anomalies?: { item?: string; level?: string; hint?: string }[];
}

/** 后端 status 字段 → 面板三态色（未知即 unknown，不假设"正常"） */
export function healthTone(status: string | undefined): "ok" | "warn" | "err" {
  if (status === "ok" || status === "active") return "ok";
  if (status === "warning" || status === "degraded") return "warn";
  return "err";
}
