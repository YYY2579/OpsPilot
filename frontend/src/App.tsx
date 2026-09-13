import { useEffect } from "react";
import { useShell } from "./state/shell";
import { currentStateId } from "./mock/data";
import MenuBar from "./shell/MenuBar";
import TopBar from "./shell/TopBar";
import Sidebar from "./shell/Sidebar";
import Center from "./shell/Center";
import Rail from "./shell/Rail";

const STATE_META: Record<string, { task?: string; pill: "run" | "wait" | "done" | "fail" }> = {
  "01": { pill: "run" },
  "02": { task: "分析 CPU 高负载原因", pill: "run" },
  "03": { task: "分析 CPU 高负载原因", pill: "run" },
  "04": { task: "分析 CPU 高负载原因", pill: "run" },
  "05": { task: "重启 backend 容器", pill: "wait" },
  "06": { task: "分析 CPU 高负载原因", pill: "done" },
  "07": { task: "获取 Pod 列表", pill: "fail" },
  "08": { task: "核对订单表结构", pill: "run" },
  "09": { task: "分析 CPU 高负载原因", pill: "run" },
  "10": { task: "分析 CPU 高负载原因", pill: "run" },
  "13": { task: "分析 CPU 高负载原因", pill: "run" },
  "14": { task: "分析 CPU 高负载原因", pill: "run" },
  "15": { task: "分析 CPU 高负载原因", pill: "run" },
};

export default function App() {
  const { theme, setTheme, setMenu, setTier, setRailTab, setNav, rightCollapsed, toggleLeft } = useShell();
  const stateId = currentStateId();
  const meta = STATE_META[stateId] ?? STATE_META["01"];

  // 主题 → <html> class（令牌切换的唯一开关）
  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // 状态参数驱动的初始状态（M5-8：13 个状态可切换）
  useEffect(() => {
    setMenu(null);
    if (stateId === "08") setNav("databases");
    else if (stateId !== "01") setNav("servers");
    setRailTab("overview");
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
      <div className="main">
        <Sidebar />
        <Center stateId={stateId} />
        <Rail />
      </div>
    </div>
  );
}
