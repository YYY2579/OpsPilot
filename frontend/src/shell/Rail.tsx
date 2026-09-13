import type { ReactElement } from "react";

import { useShell, type RailTab } from "../state/shell";
import { useViewportWidth, BREAKPOINTS } from "../lib/useViewport";
import { Icon } from "./icons";

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
      <div className="p-[12px] text-[12px] text-ink3">
        {railTab === "overview" && "概览面板：服务器卡 / 2×2 指标卡 / 服务状态 / 网络状态 / 快速信息（M5-7）"}
        {railTab === "tools" && "工具面板：工具调用明细 / 目标资源 / 审计卡（M5-7）"}
        {railTab === "tasks" && "任务面板：步骤链 / 时间线 / 审计卡（M5-7）"}
        {railTab === "logs" && "日志面板：日志列表 / 筛选 / 在聊天中分析（M5-7）"}
      </div>
    </aside>
  );
}
