export interface ServerRow {
  id: string; name: string; env: "生产" | "测试" | "开发"; ip: string; status: "online" | "offline" | "unknown";
}
export interface DatabaseRow { id: string; name: string; env: "生产" | "测试" | "开发"; tables: number }
export interface ProjectRow { id: string; name: string; env: "生产" | "测试" | "开发" }

export const SERVERS: ServerRow[] = [
  { id: "hk-ubuntu", name: "HK-Ubuntu", env: "生产", ip: "156.224.28.147", status: "online" },
  { id: "rocky-k8s-master", name: "Rocky-K8s-Master", env: "生产", ip: "192.168.1.153", status: "online" },
  { id: "rocky-k8s-node01", name: "Rocky-K8s-Node01", env: "测试", ip: "192.168.1.154", status: "online" },
  { id: "deploy-server", name: "Deploy-Server", env: "开发", ip: "192.168.1.160", status: "offline" },
];

export const DATABASES: DatabaseRow[] = [
  { id: "mysql-prod", name: "MySQL-Production", env: "生产", tables: 42 },
  { id: "mysql-test", name: "MySQL-Test", env: "测试", tables: 18 },
  { id: "redis-prod", name: "Redis-Production", env: "生产", tables: 0 },
];

export const PROJECTS: ProjectRow[] = [
  { id: "personal-blog", name: "Personal Blog", env: "开发" },
  { id: "monitoring-stack", name: "Monitoring Stack", env: "生产" },
  { id: "cicd-lab", name: "CI/CD Lab", env: "测试" },
];

export const NAV_COUNTS = { servers: 4, databases: 3, projects: 3 };

export const envColor: Record<ServerRow["env"], string> = {
  生产: "var(--err)",
  测试: "var(--warn)",
  开发: "var(--text3)",
};

/** 13 个状态（对应 assets/ 下 15 张效果图，M5-8 状态映射用） */
export const STATES = [
  { id: "01", name: "空白欢迎页" },
  { id: "02", name: "已选服务器未聊天" },
  { id: "03", name: "Agent 执行中" },
  { id: "04", name: "工具调用展开" },
  { id: "05", name: "等待用户审批" },
  { id: "06", name: "任务完成" },
  { id: "07", name: "工具执行失败" },
  { id: "08", name: "数据库树展开" },
  { id: "09", name: "右侧面板收起" },
  { id: "10", name: "浅色主题" },
  { id: "13", name: "顶部菜单展开" },
  { id: "14", name: "完全访问升级确认" },
  { id: "15", name: "完全访问已开启" },
] as const;

export function currentStateId(): string {
  const p = new URLSearchParams(window.location.search).get("state");
  return p ?? "01";
}
