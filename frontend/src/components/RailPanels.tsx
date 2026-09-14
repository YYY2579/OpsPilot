import { Icon } from "../shell/icons";
import { useServerHealth } from "../api/hooks";
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

export function ToolsPanel() {
  const tools = [
    { name: "get_server_health", note: "✓ 1.2s", cls: "s-ok" },
    { name: "get_process_list", note: "✓ 1.8s", cls: "s-ok" },
    { name: "list_docker_containers", note: "✓ 1.5s", cls: "s-ok", active: true },
    { name: "get_container_logs", note: "● 执行中", cls: "s-run" },
  ];
  return (
    <div className="railin">
      <Sec title="工具标签" right={<span style={{ color: "var(--text2)" }}>本次会话 4 次</span>}>
        {tools.map((t) => (
          <div className="row" key={t.name}
               style={t.active ? { background: "var(--accent-soft)", borderRadius: 6, padding: "4px 6px", margin: "0 -6px" } : undefined}>
            <span>{t.name}</span><span className={`r ${t.cls}`}>{t.note}</span>
          </div>
        ))}
        <div className="mt-[7px] text-[11.5px] text-ink3">点击任一工具，聊天区会定位到对应的调用记录。</div>
      </Sec>

      <Sec title="目标资源">
        <Row k="server_id" v="hk-ubuntu" mono />
        <Row k="环境" v={<span className="badge h">生产</span>} />
        <Row k="模式" v={<span className="badge l">只读</span>} />
      </Sec>
    </div>
  );
}

export function TasksPanel({ done = true }: { done?: boolean }) {
  const steps = [
    { n: "获取系统指标", s: "已完成 · 1.2s" },
    { n: "获取进程列表", s: "已完成 · 1.8s" },
    { n: "检查 Docker 容器", s: "已完成 · 1.5s" },
    { n: "分析容器日志", s: "已完成 · 1.8s" },
    { n: "生成修复建议", s: "已完成" },
    { n: "审批并重启容器", s: "已批准 · 2.4s" },
    { n: "执行后验证", s: done ? "已完成 · 健康检查通过" : "待执行" },
  ];
  return (
    <div className="railin">
      <Sec title="任务进度" right={<span className="s-ok flex items-center gap-[5px]"><i className="dot" />已完成</span>}>
        <div className="text-[12.5px] font-medium mb-[8px]">分析 CPU 高负载原因</div>
        <div className="tl">
          {steps.map((s) => (
            <div className={`n ${s.s.startsWith("待") ? "" : "ok"}`} key={s.n}>{s.n}<small>{s.s}</small></div>
          ))}
        </div>
      </Sec>

      <Sec title="审计记录">
        <Row k="task_id" v="task_20260913_001" mono />
        <Row k="工具调用" v="6 次" />
        <Row k="审批" v={<span className="badge m">1 次（已批准）</span>} />
        <Row k="凭据解析" v="工具层内部 · 未入 prompt" />
      </Sec>
    </div>
  );
}

export function LogsPanel() {
  const lines = [
    { ts: "10:23:07", text: "ERROR  GC overhead limit exceeded", tone: "s-err" },
    { ts: "10:23:07", text: "ERROR  OutOfMemoryError: Java heap space", tone: "s-err" },
    { ts: "10:22:41", text: "WARN   heap usage 87% > threshold 85%", tone: "s-warn" },
    { ts: "10:21:10", text: "INFO   healthcheck failed (unhealthy)", tone: "s-dim" },
    { ts: "10:20:02", text: "INFO   container opspilot-backend started", tone: "s-dim" },
  ];
  return (
    <div className="railin">
      <Sec title="日志" right={<span className="flex items-center gap-[6px] text-ink3">
        <Icon.search size={11} />搜索 · 级别 · 时间范围
      </span>}>
        {lines.map((l, i) => (
          <div className="logline" key={i}>
            <span className="ts">{l.ts}</span>
            <span className={l.tone}>{l.text}</span>
          </div>
        ))}
      </Sec>

      <Sec title="来源">
        <Row k="目标" v="HK-Ubuntu" />
        <Row k="来源" v="容器 opspilot-backend" />
        <Row k="时间范围" v="最近 15 分钟" />
        <Row k="级别" v="ERROR 及以上" />
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
