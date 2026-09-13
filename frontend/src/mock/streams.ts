import type { Status } from "../components/cards";

export type Block =
  | { kind: "user"; text: string }
  | { kind: "ai"; text: string }
  | { kind: "plan"; title: string; steps: { name: string; status: Status; note: string }[] }
  | { kind: "tool"; name: string; desc: string; status: Status; duration: string; badge?: string;
      body?: "list_pods_expanded" | "ps_output" | "docker_ps" | "container_logs" | "restart_one_line" }
  | { kind: "approval" }
  | { kind: "summary" }
  | { kind: "error" };

const CPU_TASK = "检查这台服务器最近为什么 CPU 使用率很高";

const PLAN_STEPS: { name: string; status: Status; note: string }[] = [
  { name: "CPU 和系统负载", status: "done", note: "已完成 · 1.2s" },
  { name: "内存和 Swap", status: "done", note: "已完成 · 0.9s" },
  { name: "高占用进程", status: "done", note: "已完成 · 1.8s" },
  { name: "Docker 容器资源", status: "run", note: "执行中 · 3.2s" },
  { name: "最近系统日志", status: "todo", note: "待执行" },
];

export const STREAMS: Record<string, Block[]> = {
  "02": [{ kind: "ai", text: "已选中 HK-Ubuntu（生产 · 156.224.28.147）。描述你想完成的任务，我会先只读采集，再给出结论。" }],

  "03": [
    { kind: "user", text: CPU_TASK },
    { kind: "plan", title: "我会检查以下内容", steps: PLAN_STEPS },
    { kind: "tool", name: "get_process_list", desc: "获取进程列表", status: "done", duration: "1.8s", body: "ps_output" },
    { kind: "ai", text: "高占用进程是 java (PID 2143) 62.1%，属 backend 容器。正在核对容器级资源占用。" },
  ],

  "04": [
    { kind: "user", text: CPU_TASK },
    { kind: "plan", title: "我会检查以下内容", steps: [
      { name: "获取系统指标", status: "done", note: "已完成 · 1.2s" },
      { name: "获取进程列表", status: "done", note: "已完成 · 1.8s" },
      { name: "检查 Docker 容器", status: "run", note: "进行中 · 3.2s" },
      { name: "分析容器日志", status: "todo", note: "待执行" },
    ]},
    { kind: "tool", name: "list_docker_containers", desc: "列出容器信息 · 展开状态", status: "done",
      duration: "1.5s", body: "docker_ps" },
    { kind: "ai", text: "容器清单已拿到：opspilot-backend 处于 unhealthy，CPU 182%，其余容器正常。下一步读取它的日志确认原因。" },
  ],

  "05": [
    { kind: "user", text: CPU_TASK },
    { kind: "tool", name: "get_container_logs", desc: "获取容器日志", status: "done", duration: "1.8s", body: "container_logs" },
    { kind: "approval" },
  ],

  "06": [
    { kind: "user", text: CPU_TASK },
    { kind: "ai", text: "✓ 已完成 5 项检查（CPU 与负载 · 内存 · 高占用进程 · Docker 容器 · 系统日志）" },
    { kind: "tool", name: "restart_container", desc: "重启 backend 容器 · 已批准执行", status: "done",
      duration: "2.4s", badge: "L3", body: "restart_one_line" },
    { kind: "summary" },
  ],

  "07": [
    { kind: "user", text: "看一下 Rocky-K8s-Master 上最近的 Pod 重启情况" },
    { kind: "plan", title: "执行计划", steps: [
      { name: "校验目标主机连通性", status: "done", note: "已完成 · 0.6s" },
      { name: "获取 Pod 列表", status: "fail", note: "执行失败 · 5.0s" },
      { name: "查看 Pod 事件", status: "todo", note: "未执行" },
    ]},
    { kind: "tool", name: "list_pods", desc: "获取 Pod 列表", status: "fail", duration: "5.0s", badge: "L1",
      body: "list_pods_expanded" },
    { kind: "error" },
  ],

  "08": [{ kind: "ai", text: "已连接 MySQL-Production（只读）。左侧展开可查看库与表结构；需要查数据时我用 query_readonly。" }],

  "09": [{ kind: "user", text: CPU_TASK }, { kind: "ai", text: "我先读取主机健康快照，确认 CPU / 负载 / 内存 / 磁盘的实际情况。" }],
  "10": [{ kind: "user", text: CPU_TASK }, { kind: "ai", text: "我先读取主机健康快照，确认 CPU / 负载 / 内存 / 磁盘的实际情况。" }],
  "13": [{ kind: "user", text: CPU_TASK }, { kind: "ai", text: "我先读取主机健康快照，确认 CPU / 负载 / 内存 / 磁盘的实际情况。" }],
  "14": [{ kind: "user", text: CPU_TASK }, { kind: "ai", text: "我先读取主机健康快照，确认 CPU / 负载 / 内存 / 磁盘的实际情况。" }],
  "15": [{ kind: "user", text: CPU_TASK }, { kind: "ai", text: "我先读取主机健康快照，确认 CPU / 负载 / 内存 / 磁盘的实际情况。" }],
};
