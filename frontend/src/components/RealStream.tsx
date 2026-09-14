import { useEffect, useRef } from "react";

import { useTaskEvents, useTaskState, useApprovals, useApprove, useReject } from "../api/hooks";
import { ApprovalCard, KV, Term, ToolCard, ToolBody } from "./cards";
import { useShell } from "../state/shell";

function stateBadge(state: string) {
  const map: Record<string, { label: string; cls: string }> = {
    RECEIVED: { label: "已接收", cls: "s-dim" },
    PLAN: { label: "计划", cls: "s-dim" },
    INSPECT: { label: "采集", cls: "s-run" },
    ANALYZE: { label: "分析", cls: "s-run" },
    PROPOSE_FIX: { label: "提出方案", cls: "s-warn" },
    WAITING_APPROVAL: { label: "待审批", cls: "s-warn" },
    EXECUTE: { label: "执行", cls: "s-run" },
    VERIFY: { label: "验证", cls: "s-run" },
    REPORT: { label: "结论", cls: "s-ok" },
    COMPLETED: { label: "完成", cls: "s-ok" },
    FAILED: { label: "失败", cls: "s-err" },
    WAITING_USER: { label: "等你补充", cls: "s-warn" },
  };
  const m = map[state] ?? { label: state, cls: "s-dim" };
  return <span className={`text-[11px] ${m.cls}`}>{m.label}</span>;
}

export default function RealStream({ taskId }: { taskId: string }) {
  const state = useTaskState(taskId);
  const events = useTaskEvents(taskId);
  const approvals = useApprovals();
  const approve = useApprove();
  const reject = useReject();
  const activeServerId = useShell((s) => s.activeServerId);
  const bottomRef = useRef<HTMLDivElement>(null);

  const proj = state.data;
  const rows = [...(events.data ?? [])].reverse();       // 按时间正序
  const approval = (approvals.data ?? []).find(
    (a) => a.task_id === taskId && a.status === "pending");

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [rows.length]);

  if (state.isLoading) return <div className="stream text-ink3">加载任务状态…</div>;
  if (state.isError) return <div className="stream"><div className="msg-ai s-err">任务状态获取失败：{String(state.error)}</div></div>;

  return (
    <div className="stream">
      <div className="flex items-center gap-[8px] text-[12px] text-ink2">
        <span className="font-medium text-ink">任务 {taskId}</span>
        {stateBadge(proj?.state ?? "")}
        {proj && <span>· {proj.tool_calls} 次工具调用</span>}
        {proj?.terminal && <span className="s-ok">· 已结束</span>}
      </div>

      {rows.map((e) => {
        const payload = (typeof e.payload === "string" ? {} : e.payload) ?? {};
        const action = payload.action as Record<string, unknown> | undefined;
        const serverId = (action?.server_id as string) ?? "";

        if (e.kind === "action") {
          return (
            <ToolCard key={e.id} name={e.message || e.kind} desc={`server_id: ${serverId || "—"}`}
                      status="done" duration="—" badge={String(payload.security_risk ?? "L1")}>
              <ToolBody>
                <KV rows={[{ k: "server_id", v: <span className="font-mono">{serverId || "—"}</span>, mono: true }]} />
                <div className="mt-[6px] text-[11px] text-ink3">等待观察结果回填（M6-2 事件配对的精化项）</div>
              </ToolBody>
            </ToolCard>
          );
        }
        if (e.kind === "observation") {
          const p = payload as Record<string, unknown>;
          const content = p.content as unknown;
          return (
            <div key={e.id} className="text-[12.5px] text-ink2">
              <span className="mr-[6px] text-ink3">observation · {String(p.tool ?? "")}</span>
              {typeof content === "string" ? <Term>{content}</Term>
                : <Term>{JSON.stringify(payload, null, 2)}</Term>}
            </div>
          );
        }
        if (e.kind === "tool_error" || e.kind === "reject") {
          return <div key={e.id} className="msg-ai"><b className="s-err">{e.kind === "reject" ? "用户拒绝" : "工具失败"}</b>：{e.message}</div>;
        }
        return null;
      })}

      {approval && (
        <ApprovalCard
          operation={approval.operation_description}
          target={activeServerId || "—"}
          targetId={activeServerId || "—"}
          cause="框架已挂起等待你的确认"
          riskLevel={approval.risk_level}
          command="—（见工具调用明细）"
          impact={approval.impact}
          rollback={approval.rollback_plan}
          actions={{
            onApprove: () => approve.mutate(approval.id),
            onReject: () => reject.mutate({ id: approval.id, reason: "用户拒绝" }),
            busy: approve.isPending || reject.isPending,
          }}
        />
      )}

      <div ref={bottomRef} />
    </div>
  );
}
