import { Icon } from "../shell/icons";
import { useApprovals, useServerHealth, useTaskEvents, useTaskState } from "../api/hooks";
import { useShell } from "../state/shell";
import { healthTone, type HealthSnapshot } from "../api/types";

function Sec({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="sec">
      <div className="sh">{title}{right != null && <span className="r flex items-center gap-[5px]">{right}</span>}</div>
      {children}
    </div>
  );
}

function Row({ k, v, mono }: { k: React.ReactNode; v: React.ReactNode; mono?: boolean }) {
  return <div className="row">{k}<span className={`r ${mono ? "font-mono" : ""}`} style={{ color: "var(--text2)" }}>{v}</span></div>;
}

function StatusRow({ name, state, text }: { name: string; state: "ok" | "warn" | "err"; text?: string }) {
  const map = { ok: { text: "正常", cls: "s-ok" }, warn: { text: "警告", cls: "s-warn" }, err: { text: "异常", cls: "s-err" } }[state];
  return <div className="row"><span>{name}</span><span className={`r ${map.cls} flex items-center gap-[5px]`}><i className="dot" />{text ?? map.text}</span></div>;
}

function Metric({ label, value, pct, tone }: { label: string; value: string; pct: number; tone: "ok" | "warn" | "err" }) {
  const color = `var(--${tone})`;
  return (
    <div className="metric">
      <div className="lb"><span>{label}</span></div>
      <div className="vl" style={{ color }}>{value}</div>
      <div className="bar"><i style={{ width: `${pct}%`, background: color }} /></div>
    </div>
  );
}

/** 服务名 → 中文展示名（仅用于显示，取值仍是后端原样） */
const SERVICE_LABEL: Record<string, string> = {
  nginx: "Nginx", docker: "Docker", mysql: "MySQL", redis: "Redis",
  sshd: "SSH", k3s: "k3s", node_exporter: "node-exporter",
};
/** systemd 状态 → 面板三态（空/unknown 一律按异常显示，不假装正常） */
function serviceTone(v: string): "ok" | "warn" | "err" {
  if (v === "active") return "ok";
  if (v === "activating" || v === "reloading") return "warn";
  return "err";
}
function serviceText(v: string): string {
  if (v === "active") return "正常";
  if (v === "inactive") return "未运行";
  if (v === "failed") return "失败";
  if (v === "unknown" || !v) return "未知";
  return v;
}

/** 离线（纯设计态预览）时的占位快照。**不是**"演示数据"，仅用于无后端时保持版式。 */
const OFFLINE_SNAPSHOT: HealthSnapshot = {
  server_id: "", ok: false, stage: "offline",
  message: "后端未连接，无法采集真实指标",
};

function OfflineNotice({ text }: { text: string }) {
  return (
    <div className="px-[10px] py-[8px] text-[11px] leading-[1.5] rounded-[6px]"
         style={{ background: "var(--bg2)", color: "var(--text3)" }}>
      {text}
    </div>
  );
}

/**
 * 面板空态：三种原因分别给话术，**任何情况下都不填占位业务数据**。
 *
 * 右栏的工具 / 任务 / 日志三个 Tab 只反映"当前这一次真实会话"。
 * 没有会话就是没有内容 —— 用假数字把面板填满会让用户分不清真假，
 * 这在运维场景里比空白危险得多。
 */
type PanelReason = "offline" | "no-task" | "loading";

const PANEL_EMPTY_TEXT: Record<PanelReason, { title: string; hint: string }> = {
  offline: { title: "后端未连接", hint: "启动 FastAPI 服务后刷新，本面板展示当前会话的真实数据。" },
  "no-task": { title: "暂无进行中的会话", hint: "在中间聊天区描述任务并发送后，这里会实时反映本次会话。" },
  loading: { title: "加载中…", hint: "" },
};

function PanelEmpty({ reason }: { reason: PanelReason }) {
  const { title, hint } = PANEL_EMPTY_TEXT[reason];
  return (
    <div className="px-[10px] py-[14px] text-center">
      <div className="text-[12px] mb-[6px]" style={{ color: "var(--text3)" }}>{title}</div>
      {hint && <div className="text-[11px] leading-[1.6]" style={{ color: "var(--text3)" }}>{hint}</div>}
    </div>
  );
}

export function OverviewPanel() {
  const activeServerId = useShell((s) => s.activeServerId);
  const backendOnline = useShell((s) => s.backendOnline);
  const { data, isLoading } = useServerHealth(activeServerId || null);

  // 后端在线但没有选中服务器 → 提示去选，而不是显示假指标
  if (backendOnline && !activeServerId) {
    return (
      <div className="railin">
        <Sec title="服务器信息">
          <OfflineNotice text="请在左侧「服务器」中选中一台，面板将展示它的真实指标。" />
        </Sec>
      </div>
    );
  }

  if (backendOnline && isLoading) {
    return (
      <div className="railin">
        <Sec title="服务器信息">
          <OfflineNotice text="正在通过 SSH 采集真实指标…" />
        </Sec>
      </div>
    );
  }

  const snap: HealthSnapshot = backendOnline
    ? (data ?? { ...OFFLINE_SNAPSHOT, message: "采集未返回数据" })
    : OFFLINE_SNAPSHOT;
  const failed = !snap.ok;

  const cpu = snap.cpu;
  const mem = snap.memory;
  const disk = snap.disk;
  const load1 = cpu?.load_avg?.[0];
  const cores = cpu?.cores ?? 1;

  return (
    <div className="railin">
      <Sec title="服务器信息" right={
        failed
          ? <span className="s-err flex items-center gap-[5px]"><i className="dot" />不可用</span>
          : <span className="s-ok flex items-center gap-[5px]"><i className="dot" />在线</span>
      }>
        <div className="host">
          <div>
            <div className="nm">{snap.name || activeServerId || "未选择"}</div>
            <div className="meta">
              <span>{snap.os?.name ?? "—"}</span>
              <span>{cores} vCPU</span>
              <span>{mem ? `${mem.total_gb} GB RAM` : "—"}</span>
            </div>
          </div>
        </div>
        {failed && (
          <div className="mt-[8px]">
            <OfflineNotice text={snap.message || "采集失败"} />
          </div>
        )}
      </Sec>

      {!failed && (
        <>
          <Sec title="资源占用">
            <div className="metrics">
              <Metric label="CPU" value={cpu ? `${cpu.percent}%` : "—"}
                      pct={cpu?.percent ?? 0} tone={healthTone(cpu?.status)} />
              <Metric label="内存" value={mem ? `${mem.percent}%` : "—"}
                      pct={mem?.percent ?? 0} tone={healthTone(mem?.status)} />
              <Metric label="磁盘" value={disk ? `${disk.used_percent}%` : "—"}
                      pct={disk?.used_percent ?? 0} tone={healthTone(disk?.status)} />
              <Metric label="系统负载"
                      value={load1 != null ? load1.toFixed(2) : "—"}
                      pct={load1 != null ? Math.min(100, Math.round(load1 / cores * 100)) : 0}
                      tone={load1 != null && load1 / cores > 1 ? "warn" : "ok"} />
            </div>
          </Sec>

          <Sec title="服务状态">
            {Object.keys(snap.services ?? {}).length === 0
              ? <Row k="—" v="未采集" />
              : Object.entries(snap.services!).map(([name, v]) => (
                  <StatusRow key={name} name={SERVICE_LABEL[name] ?? name}
                             state={serviceTone(v)} text={serviceText(v)} />
                ))}
          </Sec>

          {(snap.anomalies?.length ?? 0) > 0 && (
            <Sec title="异常项">
              {snap.anomalies!.map((a, i) => {
                const it = a as { item?: string; level?: string; hint?: string };
                const tone = it.level === "critical" || it.level === "crit" ? "err"
                           : it.level === "warning" || it.level === "warn" ? "warn" : "err";
                return (
                  <div className="row" key={i}>
                    <span className={`${tone === "warn" ? "s-warn" : "s-err"} shrink-0`}>
                      {it.item ?? "异常"}
                    </span>
                    <span className="r" style={{ color: "var(--text2)" }}>{it.hint ?? ""}</span>
                  </div>
                );
              })}
            </Sec>
          )}

          <Sec title="快速信息">
            <Row k="IP 地址" v={snap.host ?? "—"} mono />
            <Row k="操作系统" v={snap.os?.name ?? "—"} />
            <Row k="运行时间" v={snap.uptime_text || "—"} />
            <Row k="采集耗时" v={snap.latency_ms != null ? `${snap.latency_ms} ms` : "—"} />
          </Sec>
        </>
      )}
    </div>
  );
}

/** 工具卡状态 → 面板色（后端 toolexecution.status / 事件 kind） */
function toolTone(status: string): { cls: string; note: string } {
  if (status === "success") return { cls: "s-ok", note: "✓" };
  if (status === "error") return { cls: "s-err", note: "✕" };
  if (status === "rejected") return { cls: "s-warn", note: "⊘" };
  if (status === "running") return { cls: "s-run", note: "●" };
  return { cls: "s-dim", note: "·" };
}

export function ToolsPanel() {
  const backendOnline = useShell((s) => s.backendOnline);
  const activeTaskId = useShell((s) => s.activeTaskId);
  const activeServerId = useShell((s) => s.activeServerId);

  const events = useTaskEvents(activeTaskId);
  const state = useTaskState(activeTaskId);

  if (!backendOnline) return <div className="railin"><PanelEmpty reason="offline" /></div>;
  if (!activeTaskId) return <div className="railin"><PanelEmpty reason="no-task" /></div>;
  if (events.isLoading) return <div className="railin"><PanelEmpty reason="loading" /></div>;

  // 本次会话的工具调用序列：action 起一条，observation / tool_error / reject 收口。
  // 与后端 runner._open_tools 的 FIFO 配对同构（这里只做展示，不做落库）。
  const rows = [...(events.data ?? [])].reverse();
  const calls: { name: string; status: string; level: string }[] = [];
  const open: Record<string, number[]> = {};
  for (const e of rows) {
    const payload = (typeof e.payload === "string" ? {} : e.payload) ?? {};
    const tool = (payload.tool as string) ?? e.message ?? "";
    if (e.kind === "action") {
      calls.push({ name: tool, status: "running", level: String(payload.security_risk ?? "L1") });
      (open[tool] ??= []).push(calls.length - 1);
    } else if (e.kind === "observation" || e.kind === "tool_error" || e.kind === "reject") {
      const q = open[tool];
      const idx = q?.shift();
      if (idx !== undefined) {
        calls[idx].status =
          e.kind === "observation" ? "success" : e.kind === "tool_error" ? "error" : "rejected";
      }
    }
  }

  return (
    <div className="railin">
      <Sec title="工具标签" right={<span style={{ color: "var(--text2)" }}>本次会话 {calls.length} 次</span>}>
        {calls.length === 0
          ? <PanelEmpty reason="no-task" />
          : calls.map((t, i) => {
              const tone = toolTone(t.status);
              return (
                <div className="row" key={`${t.name}-${i}`}
                     style={t.status === "running"
                       ? { background: "var(--accent-soft)", borderRadius: 6, padding: "4px 6px", margin: "0 -6px" }
                       : undefined}>
                  <span className="font-mono">{t.name || "—"}</span>
                  <span className={`r ${tone.cls}`}>{tone.note} {t.level}</span>
                </div>
              );
            })}
      </Sec>

      <Sec title="目标资源">
        <Row k="server_id" v={activeServerId || "未选择"} mono />
        <Row k="环境" v={<span className="badge h">生产</span>} />
        <Row k="模式" v={<span className="badge l">只读</span>} />
        <Row k="工具调用" v={`${state.data?.tool_calls ?? calls.length} 次`} />
      </Sec>
    </div>
  );
}

/** 12 态 → 中文展示名（与 RealStream.stateBadge 同一套口径） */
const STATE_LABEL: Record<string, string> = {
  RECEIVED: "已接收", CLASSIFY_TASK: "识别任务", SELECT_CONTEXT: "选定资源",
  PLAN: "计划", INSPECT: "采集", ANALYZE: "分析", PROPOSE_FIX: "提出方案",
  WAITING_APPROVAL: "待审批", EXECUTE: "执行", VERIFY: "验证", REPORT: "结论",
  COMPLETED: "完成", FAILED: "失败", CANCELLED: "已取消", TIMEOUT: "超时",
  WAITING_USER: "等你补充",
};

export function TasksPanel() {
  const backendOnline = useShell((s) => s.backendOnline);
  const activeTaskId = useShell((s) => s.activeTaskId);

  const state = useTaskState(activeTaskId);
  const approvals = useApprovals();

  if (!backendOnline) return <div className="railin"><PanelEmpty reason="offline" /></div>;
  if (!activeTaskId) return <div className="railin"><PanelEmpty reason="no-task" /></div>;
  if (state.isLoading) return <div className="railin"><PanelEmpty reason="loading" /></div>;

  const proj = state.data;
  const history = proj?.history ?? [];
  const myApprovals = (approvals.data ?? []).filter((a) => a.task_id === activeTaskId);
  const terminal = proj?.terminal ?? false;

  return (
    <div className="railin">
      <Sec title="任务进度"
           right={terminal
             ? <span className="s-ok flex items-center gap-[5px]"><i className="dot" />已结束</span>
             : <span className="s-run flex items-center gap-[5px]"><i className="dot" />进行中</span>}>
        <div className="text-[12.5px] font-medium mb-[8px]">
          {STATE_LABEL[proj?.state ?? ""] ?? proj?.state ?? "—"}
        </div>
        {history.length === 0
          ? <div className="text-[11.5px] text-ink3">尚无状态迁移记录。</div>
          : (
            <div className="tl">
              {history.map((h, i) => (
                <div className="n ok" key={`${h.state}-${i}`}>
                  {STATE_LABEL[h.state] ?? h.state}
                  <small>{h.reason}</small>
                </div>
              ))}
            </div>
          )}
      </Sec>

      <Sec title="审计记录">
        <Row k="task_id" v={activeTaskId} mono />
        <Row k="工具调用" v={`${proj?.tool_calls ?? 0} 次`} />
        <Row k="审批" v={myApprovals.length === 0
          ? "0 次"
          : <span className="badge m">{myApprovals.length} 次（{myApprovals.filter((a) => a.status === "approved").length} 已批准）</span>} />
        <Row k="拒绝" v={`${proj?.rejections ?? 0} 次`} />
        <Row k="凭据解析" v="工具层内部 · 未入 prompt" />
      </Sec>
    </div>
  );
}

/** 事件 kind → 日志级别与配色 */
function logTone(kind: string): { level: string; cls: string } {
  if (kind === "tool_error") return { level: "ERROR", cls: "s-err" };
  if (kind === "reject") return { level: "WARN ", cls: "s-warn" };
  if (kind === "observation") return { level: "OUT  ", cls: "s-dim" };
  if (kind === "state") return { level: "STATE", cls: "s-run" };
  if (kind === "approval") return { level: "APPR ", cls: "s-warn" };
  return { level: kind.toUpperCase().slice(0, 5).padEnd(5), cls: "s-dim" };
}

function firstLine(v: unknown): string {
  if (typeof v === "string") return v.split("\n")[0].slice(0, 200);
  if (v == null) return "";
  try { return JSON.stringify(v).slice(0, 200); } catch { return ""; }
}

export function LogsPanel() {
  const backendOnline = useShell((s) => s.backendOnline);
  const activeTaskId = useShell((s) => s.activeTaskId);
  const activeServerId = useShell((s) => s.activeServerId);

  const events = useTaskEvents(activeTaskId);

  if (!backendOnline) return <div className="railin"><PanelEmpty reason="offline" /></div>;
  if (!activeTaskId) return <div className="railin"><PanelEmpty reason="no-task" /></div>;
  if (events.isLoading) return <div className="railin"><PanelEmpty reason="loading" /></div>;

  // 当前会话的事件流（时间倒序，最新在上）。内容取自真实 taskevent 表，
  // 展示 message；observation 的正文在 payload.text / payload.content。
  const rows = (events.data ?? []).slice(-40);
  const lines = rows.map((e) => {
    const payload = (typeof e.payload === "string" ? {} : e.payload) ?? {};
    const body = e.message
      || firstLine(payload.text)
      || firstLine(payload.content)
      || firstLine(payload);
    return { ts: e.id.slice(-6), kind: e.kind, tool: String(payload.tool ?? ""), body };
  });

  return (
    <div className="railin">
      <Sec title="事件流" right={<span className="flex items-center gap-[6px] text-ink3">
        <Icon.search size={11} />当前会话 · 最近 {lines.length} 条
      </span>}>
        {lines.length === 0
          ? <div className="text-[11.5px] text-ink3 px-[10px] py-[10px] text-center">本次会话暂无事件。</div>
          : lines.map((l, i) => {
              const tone = logTone(l.kind);
              return (
                <div className="logline" key={i}>
                  <span className="ts">{l.ts}</span>
                  <span className={tone.cls}>
                    {tone.level}{l.tool ? ` ${l.tool}` : ""}  {l.body}
                  </span>
                </div>
              );
            })}
      </Sec>

      <Sec title="来源">
        <Row k="目标" v={activeServerId || "未选择"} />
        <Row k="来源" v="taskevent 表 · 当前任务" />
        <Row k="范围" v={`最近 ${lines.length} 条事件`} />
        <Row k="级别" v="全部" />
      </Sec>

      <div className="sec">
        <div className="sh">下一步</div>
        <div className="text-[11.5px] text-ink3 leading-[1.8]">
          「在聊天中分析」会把当前筛选结果作为上下文交给 Agent，由它调用工具做交叉验证。
        </div>
      </div>
    </div>
  );
}
