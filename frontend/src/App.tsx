import { useEffect } from "react";
import { useShell } from "./state/shell";
import { currentStateId, isLiveMode } from "./lib/viewState";
import MenuBar from "./shell/MenuBar";
import TopBar from "./shell/TopBar";
import Sidebar from "./shell/Sidebar";
import Center from "./shell/Center";
import Rail from "./shell/Rail";
import EscalationDialog from "./components/EscalationDialog";
import { probeBackend } from "./api/client";
import { useServers } from "./api/hooks";

type Mode = "Auto" | "Plan" | "Execute" | "Review";
const CPU = "分析 CPU 高负载原因";

const STATE_META: Record<string, { task?: string; pill: "run" | "wait" | "done" | "fail"; mode?: Mode; ringPct?: number }> = {
  "01": { pill: "run" },
  "02": { task: CPU, pill: "run" },
  "03": { task: CPU, pill: "run" },
  "04": { task: CPU, pill: "run" },
  "05": { task: "重启 backend 容器", pill: "wait", mode: "Plan" },      // 等审批时处于 Plan
  "06": { task: CPU, pill: "done", ringPct: 78 },                       // 长会话 → 琥珀环
  "07": { task: "获取 Pod 列表", pill: "fail" },
  "08": { task: "核对订单表结构", pill: "run" },
  "09": { task: CPU, pill: "run" },
  "10": { task: CPU, pill: "run" },
  "13": { task: CPU, pill: "run" },
  "14": { task: CPU, pill: "run" },
  "15": { task: CPU, pill: "run" },
};

export default function App() {
  const { theme, setTheme, setMenu, setTier, setRailTab, setNav, rightCollapsed, toggleLeft,
          dialogOpen, closeDialog, openDialog, backendOnline, setBackendOnline } = useShell();
  const stateId = currentStateId();          // null = 实况模式（默认）
  const design = stateId !== null;           // 仅显式 ?state=NN 才是设计态
  const meta = (stateId && STATE_META[stateId]) || STATE_META["01"];
  const live = isLiveMode();

  // 升级确认面板要展示**真实目标**，不能把演示主机名写进安全闸门
  const activeServerId = useShell((s) => s.activeServerId);
  const { data: allServers } = useServers();
  const activeServer = allServers?.find((s) => s.id === activeServerId);

  // 探测后端：设计态可离线（看版式）；实况态离线必须明确报错，不静默回退。
  useEffect(() => {
    void probeBackend().then(setBackendOnline);
  }, [setBackendOnline]);

  // 主题 → <html> class（令牌切换的唯一开关）
  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // 设计态的初始状态（M5-8：13 个状态可切换）。实况模式下不干预。
  useEffect(() => {
    if (!stateId) { setMenu(null); return; }
    setMenu(null);
    if (stateId === "08") setNav("databases");
    else if (stateId !== "01") setNav("servers");
    // 右栏默认 Tab 按状态：04/08→工具，06→任务，其余概览
    setRailTab(stateId === "04" || stateId === "08" ? "tools" : stateId === "06" ? "tasks" : "overview");
    setTier(stateId === "15" ? "full_access" : "requested_approval");
    if (stateId === "10") {
      setTheme("light");
      document.documentElement.classList.add("light");
    }
  }, [stateId, setMenu, setNav, setRailTab, setTier, setTheme]);

  // 状态 09：右侧面板收起
  useEffect(() => {
    if (stateId === "09") useShell.setState({ rightCollapsed: true });
  }, [stateId]);

  // 状态 13：菜单展开
  useEffect(() => {
    if (stateId === "13") setMenu("文件");
  }, [stateId, setMenu]);

  // 状态 14：直接展开升级确认面板（效果图-14）
  useEffect(() => {
    if (stateId === "14") openDialog();
  }, [stateId, openDialog]);

  // 快捷键：Ctrl+B 左栏、Ctrl+Alt+B 右栏、Ctrl+Shift+L 主题
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useShell.getState();
      if (e.ctrlKey && !e.altKey && e.key.toLowerCase() === "b") { e.preventDefault(); s.toggleLeft(); }
      if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "b") { e.preventDefault(); s.toggleRight(); }
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "l") { e.preventDefault(); s.toggleTheme(); }
      if (e.key === "Escape") s.setMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  void rightCollapsed;
  void toggleLeft;

  return (
    <div className="app">
      <MenuBar />
      <TopBar task={meta.task} state={meta.pill} />
      {/* 实况态 + 后端离线：明确报错，绝不静默换成演示数据 */}
      {live && !backendOnline && (
        <div className="px-[14px] py-[6px] text-[12px] flex items-center gap-[8px]"
             style={{ background: "var(--warn-soft, rgba(214,158,46,.14))", color: "var(--warn)" }}>
          <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: "var(--warn)" }} />
          后端未连接 —— 当前界面不显示任何数据。启动 FastAPI 服务后刷新即可。
        </div>
      )}
      <div className="main">
        <Sidebar stateId={stateId ?? undefined} />
        <Center stateId={stateId ?? "01"} mode={meta.mode} ringPct={meta.ringPct} live={live} design={design} />
        <Rail />
      </div>

      <EscalationDialog
        open={dialogOpen}
        target={activeServer?.name ?? "—"}
        serverId={activeServer?.id ?? "—"}
        host={activeServer?.host ?? "—"}
        environment={activeServer?.environment ?? "production"}
        onCancel={closeDialog}
        onConfirm={() => { setTier("full_access"); closeDialog(); }}
      />
    </div>
  );
}
