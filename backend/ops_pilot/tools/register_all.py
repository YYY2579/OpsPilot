"""工具注册总入口（**依赖 OpenHands SDK**）。

只读工具全部在这里注册；纯逻辑测试不要 import 本模块。
用法：`import ops_pilot.tools.register_all` 即可让所有工具进入 ToolRegistry。
"""
from __future__ import annotations

import ops_pilot.tools.alerting  # noqa: F401  告警响应（Prometheus + Alertmanager）
import ops_pilot.tools.change  # noqa: F401    受控变更 + 滚动更新诊断
import ops_pilot.tools.database  # noqa: F401
import ops_pilot.tools.docker  # noqa: F401
import ops_pilot.tools.get_server_health.definition  # noqa: F401
import ops_pilot.tools.k8s  # noqa: F401
import ops_pilot.tools.network  # noqa: F401
import ops_pilot.tools.service_ops  # noqa: F401
import ops_pilot.tools.system  # noqa: F401

#: 写工具（需要审批，L3 及以上）
#: 这些工具默认 dry_run=true，且必须有回滚方案，否则拒绝执行
WRITE_TOOL_NAMES = (
    "restart_service",
    "scale_workload",
    "rollback_deploy",
    "run_change_script",
)

#: 规格 §A5.2 中已实现的只读工具（顺序即展示顺序）
READONLY_TOOL_NAMES = (
    "get_server_health",
    "get_disk_usage",
    "get_process_list",
    "get_service_status",
    "get_service_logs",
    "list_docker_containers",
    "get_container_logs",
    "check_port",
    "check_http",
    "list_databases",
    "list_tables",
    "describe_table",
    "query_readonly",
    "explain_sql",
    # K8s 排障（k8s.py 已实现，此前遗漏注册导致 Agent 用不到）
    # 注意：这些工具不在本机放 kubeconfig，而是 SSH 到装有 kubectl 的机器执行
    "list_namespaces",
    "list_pods",
    "get_pod_logs",
    "get_events",
    # 告警响应（alerting.py，Prometheus + Alertmanager 真实接入）
    "list_alerts",
    "inspect_alert",
    "query_metrics",
    # K8s 滚动更新诊断（只读）
    "rollout_status",
)


def tool_specs() -> list:
    """返回可直接传给 Agent(tools=[...]) 的 Tool spec 列表。"""
    from openhands.sdk.tool import Tool

    return [Tool(name=name) for name in (*READONLY_TOOL_NAMES, *WRITE_TOOL_NAMES)]
