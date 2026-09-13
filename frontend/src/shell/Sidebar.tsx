import { useShell } from "../state/shell";
import { DATABASES, NAV_COUNTS, PROJECTS, SERVERS } from "../mock/data";
import { envColor as realEnvColor, envLabel } from "../api/types";
import { useServers } from "../api/hooks";
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
  const { data: realServers } = useServers();
  const activeServerId = useShell((s) => s.activeServerId);
  const setActiveServer = useShell((s) => s.setActiveServer);
  const servers: { key: string; name: string; sub: string; env: string; status: string; active: boolean }[] =
    realServers
      ? realServers.map((s) => ({ key: s.id, name: s.name, sub: s.host, env: s.environment,
                                  status: s.status, active: s.id === activeServerId }))
      : SERVERS.map((s) => ({ key: s.id, name: s.name, sub: s.ip, env: s.env,
                              status: s.status, active: s.name === "HK-Ubuntu" }));

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
          <span className="ml-auto text-[11px] text-ink3">{NAV_COUNTS.servers}</span>
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
          <span className="ml-auto text-[11px] text-ink3">{NAV_COUNTS.databases}</span>
        </Row>

        {nav === "databases" && (dbOpen ? (
          <>
            <Row active>
              <span className="w-[13px]" />
              <Icon.db size={13} className="text-ink2 shrink-0" />
              <span className="flex flex-col min-w-0 leading-[1.25]">
                <span className="text-[12.5px] text-ink truncate">MySQL-Production</span>
                <span className="text-[10.5px] text-ink3">192.168.1.20</span>
              </span>
              <EnvTag env="生产" />
            </Row>
            <Leaf label="Databases" caret="open" />
            <Leaf label="ruoyi_cloud" level={2} right="42 表" active />
            <Leaf label="opspilot" level={2} right="18 表" />
            <Leaf label="Tables" caret="closed" right="60" />
            <Leaf label="Views" caret="closed" right="4" />
            <Leaf label="Procedures" caret="closed" right="2" />
            <Leaf label="Functions" caret="closed" right="3" />
            <Leaf label="Query Console" icon="term" />
            {DATABASES.slice(1).map((d) => (
              <Row key={d.id}>
                <span className="w-[13px]" />
                <span className="flex flex-col min-w-0 leading-[1.25]">
                  <span className="text-[12.5px] text-ink truncate">{d.name}</span>
                  <span className="text-[10.5px] text-ink3">{d.tables ? `${d.tables} 张表` : "缓存实例"}</span>
                </span>
                <EnvTag env={d.env} />
              </Row>
            ))}
          </>
        ) : DATABASES.map((d) => (
          <Row key={d.id}>
            <span className="w-[13px]" />
            <span className="flex flex-col min-w-0 leading-[1.25]">
              <span className="text-[12.5px] text-ink truncate">{d.name}</span>
              <span className="text-[10.5px] text-ink3">{d.tables ? `${d.tables} 张表` : "缓存实例"}</span>
            </span>
            <EnvTag env={d.env} />
          </Row>
        )))}

        <GroupLabel>工作</GroupLabel>
        <Row active={nav === "projects"} onClick={() => setNav("projects")}>
          <Icon.folder size={13} className="text-ink2 shrink-0" />
          <span className="text-[12.5px] text-ink">项目</span>
          <span className="ml-auto text-[11px] text-ink3">{NAV_COUNTS.projects}</span>
        </Row>

        {nav === "projects" && PROJECTS.map((p) => (
          <Row key={p.id}>
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
        <button className="h-[30px] rounded-[7px] bg-accent border border-accent text-white text-[12px] font-semibold flex items-center justify-center gap-[5px]">
          <Icon.plus size={12} />新建连接
        </button>
        <button className="h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px]">
          <Icon.plus size={12} />新建项目
        </button>
        <button className="col-span-2 h-[30px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 hover:text-ink flex items-center justify-center gap-[5px]">
          <Icon.gear size={12} />连接管理 · 凭据管理
        </button>
      </div>
    </aside>
  );
}
