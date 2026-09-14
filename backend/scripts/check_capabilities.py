#!/usr/bin/env python3
"""OpsPilot 能力自检（离线静态检查，不需要装任何依赖）。

回答一个问题：**现在到底哪些能力是真的、哪些是缺的？**

检查项：
1. 工具注册一致性 —— 声明在工具列表里的，代码里必须真的注册了
2. 能力矩阵      —— 对照六类运维场景，标注已实现 / 部分实现 / 未实现
3. 接入配置检查  —— 真实接入所需的环境变量是否齐备（缺什么直接点名）

用法：
    python backend/scripts/check_capabilities.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # OpsPilot/
BACKEND = Path(__file__).resolve().parents[1]       # OpsPilot/backend
TOOLS_DIR = ROOT / "backend" / "ops_pilot" / "tools"
REGISTER_FILE = TOOLS_DIR / "register_all.py"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------- 1. 注册一致性
def scan_registered_tools() -> dict[str, str]:
    """扫描所有工具模块，返回 {工具名: 来自哪个文件}（支持跨行写法与子目录）。"""
    found: dict[str, str] = {}
    if not TOOLS_DIR.exists():
        return found
    for path in TOOLS_DIR.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        text = _read(path)
        # ToolAnnotations( ... title="xxx" ...) 可能跨行
        for m in re.finditer(r"ToolAnnotations\(", text):
            start = m.end()
            depth = 1
            i = start
            while i < len(text) and depth > 0:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            block = text[start:i]
            tm = re.search(r'title\s*=\s*["\'](\w+)["\']', block)
            if tm:
                found[tm.group(1)] = str(path.relative_to(TOOLS_DIR))
    return found


def scan_declared_tools() -> tuple[set[str], set[str]]:
    text = _read(REGISTER_FILE)
    readonly: set[str] = set()
    write: set[str] = set()
    m = re.search(r"READONLY_TOOL_NAMES\s*=\s*\((.*?)\)", text, re.S)
    if m:
        readonly = set(re.findall(r'"(\w+)"', m.group(1)))
    m = re.search(r"WRITE_TOOL_NAMES\s*=\s*\((.*?)\)", text, re.S)
    if m:
        write = set(re.findall(r'"(\w+)"', m.group(1)))
    return readonly, write


# ---------------------------------------------------------------- 2. 能力矩阵
# (能力, 场景, 依赖的工具, 状态, 说明)
CAPABILITIES = [
    ("主机健康巡检", "①日常巡检", "get_server_health", "done", "CPU/内存/磁盘/负载/关键进程真实采集"),
    ("磁盘与进程分析", "①日常巡检", "get_disk_usage, get_process_list", "done", ""),
    ("服务状态查看", "①日常巡检", "get_service_status", "done", ""),
    ("容器清单与日志", "①日常巡检", "list_docker_containers, get_container_logs", "done", ""),
    ("数据库只读查询", "①日常巡检", "list_databases, list_tables, describe_table, query_readonly", "done", "SQL 白名单，只允许只读语句"),
    ("服务日志检索", "②故障排查", "get_service_logs", "done", "journalctl/文件日志"),
    ("端口与 HTTP 探测", "②故障排查", "check_port, check_http", "done", ""),
    ("Pod 状态与日志", "③K8s排障", "list_pods, get_pod_logs", "done", "SSH 到装有 kubectl 的机器执行"),
    ("集群事件分析", "③K8s排障", "get_events", "done", "此前未注册，现已接入工具列表"),
    ("命名空间列表", "③K8s排障", "list_namespaces", "done", "此前未注册，现已接入工具列表"),
    ("滚动更新失败诊断", "③K8s排障", "rollout_status", "done", "期望/已更新/就绪副本数 + 卡住原因"),
    ("告警查询", "⑤告警响应", "list_alerts", "done", "Alertmanager 真实接入，需配置 ALERTMANAGER_URL"),
    ("告警定位与影响面", "⑤告警响应", "inspect_alert", "done", "关联 PromQL 量化影响范围"),
    ("指标查询", "⑤告警响应", "query_metrics", "done", "Prometheus 真实接入，需配置 PROMETHEUS_URL"),
    ("服务重启", "④变更操作", "restart_service", "done", "支持 dry-run；L3 审批"),
    ("扩缩容", "④变更操作", "scale_workload", "done", "dry-run 优先，自动记录回滚命令（原副本数）"),
    ("K8s 回滚", "④变更操作", "rollback_deploy", "done", "rollout undo，支持指定 revision；dry-run 先列可回滚版本"),
    ("通用变更执行", "④变更操作", "run_change_script", "done", "部署/Ansible/自定义脚本；回滚命令必填，否则拒绝"),
    ("服务部署/发布", "④变更操作", "run_change_script", "partial", "执行通道已就绪，但部署脚本需你提供（不臆测部署逻辑）"),
    ("统一错误码与修复步骤", "⑥诊断结论", "diagnostics/", "done", "50 个错误码，覆盖 9 个故障层次"),
    ("未实现能力显式标注", "⑥诊断结论", "diagnostics.not_implemented", "done", "禁止编造结果冒充已实现"),
]

# ---------------------------------------------------------------- 3. 接入配置
REQUIRED_ENV = {
    "ALERTMANAGER_URL": "告警查询（Alertmanager 地址，如 http://host:9093）",
    "PROMETHEUS_URL": "指标查询（Prometheus 地址，如 http://host:9090）",
    "LLM_API_KEY": "Agent 大脑（或 DEEPSEEK_API_KEY）",
}
OPTIONAL_ENV = {
    "ALERTING_AUTH_TOKEN": "告警接口 Bearer 认证",
    "ALERTING_BASIC_USER": "告警接口 Basic 认证用户名",
    "ALERTING_BASIC_PASS": "告警接口 Basic 认证密码",
}


def load_repo_env() -> None:
    """按项目既有约定加载 .env 与 key.txt（不覆盖已存在的环境变量）。

    必须同时读 key.txt：真实部署里模型 key 常以裸 `sk-...` 形式存在那里
    （见 server/settings.py 的 _load_file），只读 .env 会误报 LLM_API_KEY 缺失。
    这里复用 settings.load_env 保证与运行时**完全同源**，避免两份实现漂移。
    """
    import sys
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        from ops_pilot.server.settings import load_env
        load_env(force=True)
    except Exception:  # noqa: BLE001 - 自检脚本必须能在模块缺失时降级运行
        pass


def main() -> int:
    load_repo_env()
    print("=" * 72)
    print("OpsPilot 能力自检")
    print("=" * 72)

    # 1. 注册一致性
    registered = scan_registered_tools()
    readonly, write = scan_declared_tools()
    declared = readonly | write
    print(f"\n【1】工具注册一致性")
    print(f"    工具列表声明：只读 {len(readonly)} + 写 {len(write)}，共 {len(declared)}")
    print(f"    代码中已注册：{len(registered)}")
    ghost = sorted(declared - set(registered))
    orphan = sorted(set(registered) - declared)
    print(f"    声明了但代码没有：{ghost or '无 ✓'}")
    print(f"    已注册但未列入：{orphan or '无 ✓'}")
    if ghost:
        for g in ghost:
            print(f"        ✗ {g}")

    # 2. 能力矩阵
    print(f"\n【2】能力矩阵")
    by_scene: dict[str, list[tuple]] = {}
    for cap in CAPABILITIES:
        by_scene.setdefault(cap[1], []).append(cap)
    counts = {"done": 0, "partial": 0, "missing": 0}
    for scene in sorted(by_scene):
        print(f"\n    {scene}")
        for name, _, tools, state, note in by_scene[scene]:
            counts[state] += 1
            mark = {"done": "✓", "partial": "~", "missing": "✗"}[state]
            tail = f"  —— {note}" if note else ""
            print(f"      {mark} {name}  [{tools}]{tail}")
    print(f"\n    合计：已实现 {counts['done']} / 部分 {counts['partial']} / 缺失 {counts['missing']}")

    # 3. 接入配置
    print(f"\n【3】接入配置（真实接入所需，缺哪项对应能力就不可用）")
    missing_required = []
    for k, desc in REQUIRED_ENV.items():
        v = os.environ.get(k) or os.environ.get("DEEPSEEK_API_KEY") if k == "LLM_API_KEY" else os.environ.get(k)
        if v:
            print(f"    ✓ {k}  ({desc})")
        else:
            print(f"    ✗ {k}  缺失 —— {desc}")
            missing_required.append(k)
    print(f"\n    可选项：")
    for k, desc in OPTIONAL_ENV.items():
        print(f"    {'✓' if os.environ.get(k) else '-'} {k}  ({desc})")

    print("\n" + "=" * 72)
    if ghost or missing_required:
        print("结论：存在阻塞项 ——")
        if ghost:
            print(f"  · {len(ghost)} 个工具声明了但未实现：{', '.join(ghost)}")
        if missing_required:
            print(f"  · {len(missing_required)} 项接入信息未提供：{', '.join(missing_required)}")
    else:
        print("结论：无阻塞项，可进行真实环境接入验证")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
