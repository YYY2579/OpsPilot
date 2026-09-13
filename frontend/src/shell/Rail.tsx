import type { ReactElement } from "react";

import { useShell, type RailTab } from "../state/shell";
import { useViewportWidth, BREAKPOINTS } from "../lib/useViewport";
import { Icon } from "./icons";
import { LogsPanel, OverviewPanel, TasksPanel, ToolsPanel } from "../components/RailPanels";

const TABS: { key: RailTab; label: string }[] = [
  { key: "overview", label: "概览" },
  { key: "tools", label: "工具" },
  { key: "tasks", label: "任务" },
  { key: "logs", label: "日志" },
];

const TAB_ICON: Record<RailTab, (p: { size?: number }) => ReactElement> = {
  overview: Icon.server, tools: Icon.tools, tasks: Icon.tasks, logs: Icon.logs,
};

export default function Rail() {
  const { railTab, setRailTab, rightCollapsed, toggleRight } = useShell();
  const width = useViewportWidth();
  const autoCollapsed = width <= BREAKPOINTS.rightAutoCollapse;
  const collapsed = rightCollapsed || autoCollapsed;

  if (collapsed) {
    return (
      <div className="railmini">
        {TABS.map((t) => {
          const Ico = TAB_ICON[t.key];
          return (
            <button key={t.key} title={t.label} onClick={() => { setRailTab(t.key); toggleRight(); }}
              className={`w-[30px] h-[30px] rounded-[7px] grid place-items-center ${railTab === t.key ? "bg-surface2 text-accent" : "text-ink2"}`}>
              <Ico size={14} />
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <aside className="rail">
      <div className="flex items-center border-b border-line">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setRailTab(t.key)}
            className={`flex-1 h-[42px] text-[12.5px] ${railTab === t.key ? "text-accent font-medium" : "text-ink2 hover:text-ink"}`}
            style={railTab === t.key ? { boxShadow: "inset 0 -2px 0 var(--accent)" } : undefined}>
            {t.label}
          </button>
        ))}
      </div>
      {railTab === "overview" && <OverviewPanel />}
      {railTab === "tools" && <ToolsPanel />}
      {railTab === "tasks" && <TasksPanel />}
      {railTab === "logs" && <LogsPanel />}
    </aside>
  );
}
