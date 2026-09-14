import { useEffect, useState } from "react";
import { useShell } from "../state/shell";
import { envColor as realEnvColor, envLabel } from "../api/types";
import { useDatabases, useProjects, useServers } from "../api/hooks";
import { API_BASE, DEFAULT_API_BASE, setApiBase } from "../api/client";
import NewResourceDialog, { type NewKind } from "../components/NewResourceDialog";
import { Icon } from "./icons";

function EnvTag({ env }: { env: string }) {
  return <span className="ml-auto text-[11px] font-medium shrink-0" style={{ color: realEnvColor(env) }}>{envLabel(env)}</span>;
}

function StatusDot({ status }: { status: string }) {
  const color = status === "online" ? "var(--ok)" : status === "offline" ? "var(--err)" : "var(--text3)";
  return <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: color }} />;
}

function GroupLabel({ children }: { children: string }) {
  return <div className="px-[14px] pt-[10px] pb-[5px] text-[10px] tracking-[.6px] text-ink3">{children}</div>;
}

function Row({ active, onClick, children }: { active?: boolean; onClick?: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`w-full flex items-center gap-[8px] h-[28px] px-[8px] rounded-[6px] text-left
        ${active ? "" : "hover:bg-surface2"}`}
      style={active ? { background: "var(--accent-soft)", color: "var(--accent)", fontWeight: 600 } : undefined}>
      {children}
    </button>
  );
}

function Leaf({ label, level = 1, right, active, caret, icon }: {
  label: string; level?: 1 | 2; right?: string; active?: boolean;
  caret?: "open" | "closed"; icon?: "term";
}) {
  return (
    <button className={`leaf${level === 2 ? " l2" : ""}`}
            style={active ? { color: "var(--text)", borderLeftColor: "var(--accent)", background: "var(--panel2)" } : undefined}>
      {caret && <span className="text-ink3 text-[9px] w-[9px]">{caret === "open" ? "▾" : "▸"}</span>}
      {icon === "term" && <Icon.terminal size={11} className="text-ink3" />}
      <span>{label}</span>
      {right && <span className="sp">{right}</span>}
    </button>
  );
}

export default function Sidebar({ stateId }: { stateId?: string }) {
  const { nav, setNav } = useShell();
  const collapsed = useShell((s) => s.leftCollapsed);
  const dbOpen = stateId === "08";
  const backendOnline = useShell((s) => s.backendOnline);
  const activeServerId = useShell((s) => s.activeServerId);
  const setActiveServer = useShell((s) => s.setActiveServer);
  const [dialog, setDialog] = useState<NewKind | null>(null);
  const [editingBase, setEditingBase] = useState(false);
  const [baseVal, setBaseVal] = useState(API_BASE);

  // 唯一数据源：真实 API。**不再有 mock 回退** —— 后端离线时列表为空并显式提示，
  // 绝不静默塞入演示数据。运维场景下"分不清哪个数字是真的"比空白危险得多。
  const { data: realServers, isError: serversError } = useServers();
  const { data: realDatabases } = useDatabases();
  const { data: realProjects } = useProjects();

  // 真实数据到位后自动选中第一台服务器 —— 否则概览面板会一直停在
  // "请选中一台服务器"的空提示，而后端明明有数据，看起来像没接上。
  useEffect(() => {
    if (activeServerId) return;
    const first = realServers?.[0];
    if (first) setActiveServer(first.id);
  }, [realServers, activeServerId, setActiveServer]);

  const servers: { key: string; name: string; sub: string; env: string; status: string; active: boolean }[] =
    (realServers ?? []).map((s) => ({ key: s.id, name: s.name, sub: s.host, env: s.environment,
                                      status: s.status, active: s.id === activeServerId }));

  const databases: { key: string; name: string; sub: string; env: string }[] =
    (realDatabases ?? []).map((d) => ({ key: d.id, name: d.name, sub: `${d.host}:${d.port}`,
                                        env: d.environment }));

  const projects: { key: string; name: string; env: string }[] =
    (realProjects ?? []).map((p) => ({ key: p.id, name: p.name, env: p.environment }));

  // 计数一律取真实数组长度，不再写死。
  const counts = { servers: servers.length, databases: databases.length, projects: projects.length };
  const showOffline = !backendOnline || serversError;

  if (collapsed) {
    return (
      <div className="sidemini">
        <button onClick={() => setNav("servers")} title="服务器"
                className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${nav === "servers" ? "bg-surface2 text-accent" : "text-ink2"}`}>
          <Icon.server />
        </button>
        <button onClick={() => setNav("databases")} title="数据库"
                className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${nav === "databases" ? "bg-surface2 text-accent" : "text-ink2"}`}>
          <Icon.db />
        </button>
        <button onClick={() => setNav("projects")} title="项目"
                className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${nav === "projects" ? "bg-surface2 text-accent" : "text-ink2"}`}>
          <Icon.folder />
        </button>
        <button onClick={() => setNav("history")} title="任务历史"
                className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${nav === "history" ? "bg-surface2 text-accent" : "text-ink2"}`}>
          <Icon.history />
        </button>
        <button onClick={() => setNav("starred")} title="收藏"
                className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${nav === "starred" ? "bg-surface2 text-accent" : "text-ink2"}`}>
          <Icon.star />
        </button>
      </div>
    );
  }

  return (
    <aside className="sidebar">
      <div className="mx-[10px] mt-[10px] mb-[8px]">
        <div className="flex items-center gap-[7px] h-[30px] px-[9px] rounded-[7px] border border-line bg-field text-ink3">
          <Icon.search size={13} />
          <span className="text-[12px] truncate">搜索服务器、数据库、项目…</span>
          <kbd className="ml-auto shrink-0 text-[10px] px-[5px] py-[1px] rounded border border-line text-ink3">Ctrl K</kbd>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-[6px] pb-[6px]">
        {showOffline && (
          <div className="mx-[8px] mt-[8px] mb-[4px] px-[10px] py-[8px] rounded-[6px] text-[11px] leading-[1.6]"
               style={{ background: "var(--bg2)", color: "var(--text3)" }}>
            后端未连接 —— 列表为空是真实状态，不是加载失败。
            <div className="mt-[3px]">启动 FastAPI 服务后刷新即可看到资源。</div>
          </div>
        )}
        <GroupLabel>资源</GroupLabel>
        <Row active={nav === "servers"} onClick={() => setNav("servers")}>
          <Icon.server size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">服务器</span>
          <span className="ml-auto text-[11px] text-ink3">{counts.servers}</span>
        </Row>

        {nav === "servers" && servers.map((s) => (
          <Row key={s.key} active={s.active}
               onClick={() => { setActiveServer(s.key); setNav("servers"); }}>
            <span className="w-[13px]" />
            <StatusDot status={s.status} />
            <span className="flex flex-col min-w-0 leading-[1.25]">
              <span className="text-[12.5px] text-ink truncate">{s.name}</span>
              <span className="text-[10.5px] text-ink3">{s.sub}</span>
            </span>
            <span className="ml-auto text-[11px] font-medium shrink-0"
                  style={{ color: realEnvColor(s.env) }}>{envLabel(s.env)}</span>
          </Row>
        ))}

        <Row active={nav === "databases"} onClick={() => setNav("databases")}>
          <Icon.db size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">数据库</span>
          <span className="ml-auto text-[11px] text-ink3">{counts.databases}</span>
        </Row>

        {nav === "databases" && (dbOpen ? (
          <>
            {databases.map((d, i) => (
              <div key={d.key}>
                <Row active={i === 0}>
                  <span className="w-[13px]" />
                  <Icon.db size={13} className="text-ink2 shrink-0" />
                  <span className="flex flex-col min-w-0 leading-[1.25]">
                    <span className="text-[12.5px] text-ink truncate">{d.name}</span>
                    <span className="text-[10.5px] text-ink3">{d.sub}</span>
                  </span>
                  <EnvTag env={d.env} />
                </Row>
                {i === 0 && (
                  <>
                    <Leaf label="Tables" caret="closed" />
                    <Leaf label="Views" caret="closed" />
                    <Leaf label="Query Console" icon="term" />
                  </>
                )}
              </div>
            ))}
          </>
        ) : databases.map((d) => (
          <Row key={d.key}>
            <span className="w-[13px]" />
            <span className="flex flex-col min-w-0 leading-[1.25]">
              <span className="text-[12.5px] text-ink truncate">{d.name}</span>
              <span className="text-[10.5px] text-ink3">{d.sub}</span>
            </span>
            <EnvTag env={d.env} />
          </Row>
        )))}

        <GroupLabel>工作</GroupLabel>
        <Row active={nav === "projects"} onClick={() => setNav("projects")}>
          <Icon.folder size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">项目</span>
          <span className="ml-auto text-[11px] text-ink3">{counts.projects}</span>
        </Row>

        {nav === "projects" && projects.map((p) => (
          <Row key={p.key}>
            <span className="w-[13px]" />
            <Icon.folder size={12} className="text-ink3 shrink-0" />
            <span className="text-[12.5px] text-ink truncate">{p.name}</span>
            <EnvTag env={p.env} />
          </Row>
        ))}

        <Row active={nav === "history"} onClick={() => setNav("history")}>
          <Icon.history size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">任务历史</span>
        </Row>
        <Row active={nav === "starred"} onClick={() => setNav("starred")}>
          <Icon.star size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">收藏</span>
        </Row>
      </nav>

      <div className="shrink-0 border-t border-line px-[10px] py-[8px] grid grid-cols-2 gap-[6px]">
        <button onClick={() => setDialog("server")} disabled={showOffline}
                title={showOffline ? "后端未连接，无法新建" : "登记一台服务器"}
                className="h-[30px] rounded-[7px] bg-accent border border-accent text-white text-[12px] font-semibold flex items-center justify-center gap-[5px] disabled:opacity-45">
          <Icon.plus size={12} />新建连接
        </button>
        <button onClick={() => setDialog("project")} disabled={showOffline}
                title={showOffline ? "后端未连接，无法新建" : "登记一个项目"}
                className="h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px] disabled:opacity-45">
          <Icon.plus size={12} />新建项目
        </button>
        <button onClick={() => setEditingBase((v) => !v)}
                className="col-span-2 h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px]">
          <Icon.gear size={12} />后端设置
        </button>
      </div>

      {editingBase && (
        <div className="shrink-0 mx-[10px] mb-[8px] px-[9px] py-[8px] rounded-[6px] border border-line"
             style={{ background: "var(--bg2)" }}>
          <div className="text-[11px] text-ink3 mb-[5px] leading-[1.5]">
            后端地址。桌面端默认为 <code>{DEFAULT_API_BASE}</code>，改端口后在这里同步。
          </div>
          <div className="flex gap-[6px]">
            <input value={baseVal} onChange={(e) => setBaseVal(e.target.value)}
                   placeholder={DEFAULT_API_BASE}
                   className="flex-1 h-[28px] px-[8px] rounded-[6px] border border-line bg-field text-[12px] text-ink outline-none" />
            <button onClick={() => { setApiBase(baseVal.trim()); window.location.reload(); }}
                    className="h-[28px] px-[11px] rounded-[6px] bg-accent border border-accent text-white text-[11.5px] font-semibold">
              保存并重连
            </button>
          </div>
        </div>
      )}

      {dialog && <NewResourceDialog kind={dialog} onClose={() => setDialog(null)} />}
    </aside>
  );
}
