import { useShell } from "../state/shell";
import { useViewportWidth, BREAKPOINTS } from "../lib/useViewport";
import { Icon } from "./icons";

const STATE_PILL: Record<string, { label: string; cls: string }> = {
  run: { label: "执行中", cls: "bg-accentsoft text-accent" },
  wait: { label: "待审批", cls: "bg-warnsoft text-warn" },
  done: { label: "已完成", cls: "bg-oksoft text-ok" },
  fail: { label: "失败", cls: "bg-errsoft text-err" },
};

export default function TopBar({ task, state = "run" }: { task?: string; state?: keyof typeof STATE_PILL }) {
  const { theme, toggleTheme, rightCollapsed, toggleRight } = useShell();
  const width = useViewportWidth();
  const pill = STATE_PILL[state];

  return (
    <div className="topbar">
      <button className="flex items-center gap-[6px] font-medium text-[13.5px] text-ink">
        个人工作区 <Icon.chevronDown size={12} className="text-ink3" />
      </button>

      {task && (
        <>
          <span className="w-px h-[22px] bg-line mx-1" />
          <div className="flex items-center gap-2 min-w-0 text-ink2">
            <b className="text-ink font-medium truncate">{task}</b>
            {pill && <span className={`inline-flex items-center gap-[5px] h-[22px] px-[9px] rounded-full text-[11.5px] font-medium ${pill.cls}`}>
              <span className="w-[6px] h-[6px] rounded-full bg-current" />{pill.label}
            </span>}
          </div>
        </>
      )}

      <div className="ml-auto flex items-center gap-1">
        <button onClick={toggleTheme} title={theme === "dark" ? "切换到浅色" : "切换到深色"}
                className="w-[28px] h-[28px] rounded-[7px] grid place-items-center text-ink2 hover:text-ink hover:bg-surface2">
          {theme === "dark" ? <Icon.sun /> : <Icon.moon />}
        </button>
        {(rightCollapsed || width <= BREAKPOINTS.rightAutoCollapse) && (
          <button onClick={toggleRight} title="展开右侧面板"
                  className="w-[28px] h-[28px] rounded-[7px] grid place-items-center hover:bg-surface2"
                  style={{ color: "var(--accent)" }}>
            <Icon.panel />
          </button>
        )}
        <button title="设置" className="w-[28px] h-[28px] rounded-[7px] grid place-items-center text-ink2 hover:text-ink hover:bg-surface2">
          <Icon.gear />
        </button>
        <span className="w-[26px] h-[26px] rounded-full bg-accentsoft text-accent text-[11px] font-medium grid place-items-center ml-1">MY</span>
      </div>
    </div>
  );
}
