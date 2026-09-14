import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useShell } from "../state/shell";
import * as api from "./client";

export function useBackend() {
  const online = useShell((s) => s.backendOnline);
  return { online, api };
}

export function useServers() {
  const online = useShell((s) => s.backendOnline);
  return useQuery({
    queryKey: ["servers"],
    queryFn: api.getServers,
    enabled: online,
    staleTime: 30_000,
  });
}

export function useDatabases() {
  const online = useShell((s) => s.backendOnline);
  return useQuery({ queryKey: ["databases"], queryFn: api.getDatabases, enabled: online });
}

export function useProjects() {
  const online = useShell((s) => s.backendOnline);
  return useQuery({ queryKey: ["projects"], queryFn: api.getProjects, enabled: online });
}

export function useTaskList() {
  const online = useShell((s) => s.backendOnline);
  return useQuery({ queryKey: ["tasks"], queryFn: api.getTasks, enabled: online });
}

export function useTaskState(taskId: string | null) {
  const online = useShell((s) => s.backendOnline);
  return useQuery({
    queryKey: ["task-state", taskId],
    queryFn: () => api.getTaskState(taskId!),
    enabled: online && !!taskId,
    refetchInterval: (query) => {
      const state = query.state.data?.state ?? "";
      return state === "COMPLETED" || state === "FAILED" || state === "CANCELLED"
        || state === "TIMEOUT" ? false : 2000;
    },
  });
}

export function useTaskEvents(taskId: string | null) {
  const online = useShell((s) => s.backendOnline);
  const state = useTaskState(taskId).data?.state ?? "";
  return useQuery({
    queryKey: ["task-events", taskId, state],
    queryFn: () => api.getTaskEvents(taskId!),
    enabled: online && !!taskId,
  });
}

export function usePermission(sessionId: string, environment: string) {
  const online = useShell((s) => s.backendOnline);
  return useQuery({
    queryKey: ["permission", sessionId, environment],
    queryFn: () => api.getPermission(sessionId, environment),
    enabled: online,
  });
}

export function useApprovals() {
  const online = useShell((s) => s.backendOnline);
  return useQuery({ queryKey: ["approvals"], queryFn: api.listApprovals, enabled: online });
}

export function useRunTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.runTask,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tasks"] });
      void qc.invalidateQueries({ queryKey: ["task-state"] });
    },
  });
}

export function useApprove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.approveApproval(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["task-state"] });
      void qc.invalidateQueries({ queryKey: ["task-events"] });
    },
  });
}

export function useReject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { id: string; reason: string }) => api.rejectApproval(p.id, p.reason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["task-state"] });
    },
  });
}

export function useChangeTier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { sessionId: string; environment: string; target: string;
                      acknowledged?: boolean; env_confirm?: string }) =>
      api.changePermission(p.sessionId, {
        environment: p.environment, target: p.target,
        acknowledged: p.acknowledged, env_confirm: p.env_confirm,
      }),
    onSuccess: (_d, p) => {
      void qc.invalidateQueries({ queryKey: ["permission", p.sessionId] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export { api };

/**
 * 主机健康快照：概览面板的真实数据源。
 *
 * 仅在选定服务器且后端在线时轮询；`serverId` 为空即不发请求（面板显示待选）。
 * 30s 轮询——巡检面板不需要秒级，避免对靶机造成无谓 SSH 压力。
 */
export function useServerHealth(serverId: string | null) {
  const online = useShell((s) => s.backendOnline);
  return useQuery({
    queryKey: ["server-health", serverId],
    queryFn: () => api.getServerHealth(serverId!),
    enabled: online && !!serverId,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
