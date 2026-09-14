"""L5 地板与工具风险等级登记（§A6.2 / §A6.5.1）。

框架的 ConfirmationPolicy 只能表达"要不要问"，**没有"拒绝执行"这个能力**。
所以 L5（不可逆操作）的硬拦截必须落在工具层：任何 L5 工具在执行前必须调用
`enforce_floor()`，未获人工批准就抛错 —— 这条规则不随权限档位改变。
"""
from __future__ import annotations

from ops_pilot.security.levels import RiskLevel


class L5Blocked(RuntimeError):
    """L5 操作在未获人工批准时被拦截。"""


def enforce_floor(level: RiskLevel, *, approved: bool) -> None:
    """L5 硬地板：任何档位下都必须人工批准才可执行。"""
    if level is RiskLevel.L5 and not approved:
        raise L5Blocked(
            "L5 不可逆操作必须人工确认后才可执行（删除数据库 / 清空数据表 / 重建集群 等）"
        )


#: 已实现工具的默认风险等级（供审计与前端展示；写工具接入时在这里登记）
#: 只读工具全部为 L1
TOOL_LEVELS: dict[str, RiskLevel] = {
    "get_server_health": RiskLevel.L1,
    "get_disk_usage": RiskLevel.L1,
    "get_process_list": RiskLevel.L1,
    "get_service_status": RiskLevel.L1,
    "get_service_logs": RiskLevel.L1,
    "list_docker_containers": RiskLevel.L1,
    "get_container_logs": RiskLevel.L1,
    "check_port": RiskLevel.L1,
    "check_http": RiskLevel.L1,
    "list_databases": RiskLevel.L1,
    "list_tables": RiskLevel.L1,
    "describe_table": RiskLevel.L1,
    "query_readonly": RiskLevel.L1,
    "explain_sql": RiskLevel.L1,
    "restart_service": RiskLevel.L3,     # 首个写工具（会中断服务）
    # K8s 只读（经 SSH 在服务器上执行 kubectl，kubeconfig 永不离机）
    "list_namespaces": RiskLevel.L1,
    "list_pods": RiskLevel.L1,
    "get_pod_logs": RiskLevel.L1,
    "get_events": RiskLevel.L1,
    # 告警响应（Prometheus + Alertmanager 只读查询）
    # **曾经漏登记**：list_alerts 未在此表 → 落到未知默认 L4 → 只读查询
    # 被误判成高危写操作，白白卡住审批门，巡检任务停在 WAITING_APPROVAL。
    "list_alerts": RiskLevel.L1,
    "inspect_alert": RiskLevel.L1,
    "query_metrics": RiskLevel.L1,
    # K8s 滚动更新诊断（只读）
    "rollout_status": RiskLevel.L1,
}

#: 已实现的写工具（需要审批）。与 register_all.WRITE_TOOL_NAMES 保持一致。
TOOL_WRITE_LEVELS: dict[str, RiskLevel] = {
    "restart_service": RiskLevel.L3,
    "scale_workload": RiskLevel.L3,
    "rollback_deploy": RiskLevel.L3,
    "run_change_script": RiskLevel.L4,
}

#: 规格 §A5.2 中尚未实现的写工具，预先登记等级（实现时必须遵守）
PLANNED_WRITE_TOOL_LEVELS: dict[str, RiskLevel] = {
    "restart_container": RiskLevel.L3,
    "restart_service": RiskLevel.L3,
    "upload_file": RiskLevel.L3,
    "run_shell": RiskLevel.L4,
    "delete_file": RiskLevel.L4,
    "execute_sql": RiskLevel.L4,
    "apply_kubernetes_yaml": RiskLevel.L4,
    "backup_database": RiskLevel.L2,
    "reload_config": RiskLevel.L3,
}


def level_of(tool_name: str) -> RiskLevel:
    """查工具等级；未知工具按 L4 保守处理（宁严勿松）。"""
    if tool_name in TOOL_LEVELS:
        return TOOL_LEVELS[tool_name]
    if tool_name in TOOL_WRITE_LEVELS:
        return TOOL_WRITE_LEVELS[tool_name]
    if tool_name in PLANNED_WRITE_TOOL_LEVELS:
        return PLANNED_WRITE_TOOL_LEVELS[tool_name]
    return RiskLevel.L4


def audit_level_table() -> list[str]:
    """自检：返回"已注册为只读但未在 TOOL_LEVELS 登记等级"的工具名。

    等级表与工具清单是两份数据，靠人工同步必然漂移（已真实踩过：
    list_alerts 漏登记被当成 L4 写操作）。启动自检与测试都调用本函数，
    把漂移暴露成显式 failure，而不是让它在运行时表现为"莫名其妙的审批"。
    """
    try:
        from ops_pilot.tools.register_all import READONLY_TOOL_NAMES, WRITE_TOOL_NAMES
    except Exception:  # noqa: BLE001 - 未装 SDK 时跳过
        return []
    known = set(TOOL_LEVELS) | set(TOOL_WRITE_LEVELS)
    return sorted(n for n in (*READONLY_TOOL_NAMES, *WRITE_TOOL_NAMES) if n not in known)
