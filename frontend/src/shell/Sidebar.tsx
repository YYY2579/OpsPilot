import { useEffect, useState } from "react";
import { useShell } from "../state/shell";
import { DATABASES, PROJECTS, SERVERS } from "../mock/data";
import { envColor as realEnvColor, envLabel } from "../api/types";
import { useDatabases, useProjects, useServers } from "../api/hooks";
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
  const [notice, setNotice] = useState<string | null>(null);

  // 真实数据源：后端在线则用真实返回值，离线（纯设计态预览）才回退 mock。
  // 三个列表都是真实 API，不再有"只有界面没有实现"的空壳。
  const { data: realServers } = useServers();
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
    realServers
      ? realServers.map((s) => ({ key: s.id, name: s.name, sub: s.host, env: s.environment,
                                  status: s.status, active: s.id === activeServerId }))
      : SERVERS.map((s) => ({ key: s.id, name: s.name, sub: s.ip, env: s.env,
                              status: s.status, active: s.name === "HK-Ubuntu" }));

  const databases: { key: string; name: string; sub: string; env: string }[] =
    realDatabases
      ? realDatabases.map((d) => ({ key: d.id, name: d.name, sub: `${d.host}:${d.port}`,
                                    env: d.environment }))
      : DATABASES.map((d) => ({ key: d.id, name: d.name,
                                sub: d.tables ? `${d.tables} 张表` : "缓存实例", env: d.env }));

  const projects: { key: string; name: string; env: string }[] =
    realProjects
      ? realProjects.map((p) => ({ key: p.id, name: p.name, env: p.environment }))
      : PROJECTS.map((p) => ({ key: p.id, name: p.name, env: p.env }));

  // 计数一律取真实数组长度（离线时取 mock 长度），不再写死。
  const counts = { servers: servers.length, databases: databases.length, projects: projects.length };

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

      {notice && (
        <div className="shrink-0 mx-[10px] mb-[6px] px-[9px] py-[6px] rounded-[6px] text-[11px] leading-[1.4]"
             style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
          {notice}
        </div>
      )}

      <div className="shrink-0 border-t border-line px-[10px] py-[8px] grid grid-cols-2 gap-[6px]">
        <button onClick={() => { setNav("servers"); setNotice("选择左侧任一服务器，在中间输入运维指令即可开始（Agent 会真实 SSH 采集）。"); }}
          className="h-[30px] rounded-[7px] bg-accent border border-accent text-white text-[12px] font-semibold flex items-center justify-center gap-[5px]">
          <Icon.plus size={12} />新建连接
        </button>
        <button onClick={() => { setNav("projects"); setNotice("在中间输入「新建项目」并给出名称与路径，Agent 会通过 API 落库。"); }}
          className="h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px]">
          <Icon.plus size={12} />新建项目
        </button>
        <button onClick={() => { setNav("databases"); setNotice(backendOnline
            ? "已连接后端：数据库列表来自 /api/connections/databases 真实返回值。"
            : "后端未连接：请先启动 backend（uvicorn ops_pilot.server.app:app --port 8700）并用 VITE_API_BASE 指向它。"); }}
          className="col-span-2 h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px]">
          <Icon.gear size={12} />连接管理 · 凭据管理
        </button>
      </div>
    </aside>
  );
}
