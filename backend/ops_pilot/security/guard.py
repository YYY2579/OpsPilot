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
#: 当前 9 个工具全部为只读 → L1
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
    "restart_service": RiskLevel.L3,     # 首个写工具（会中断服务）
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
    if tool_name in PLANNED_WRITE_TOOL_LEVELS:
        return PLANNED_WRITE_TOOL_LEVELS[tool_name]
    return RiskLevel.L4
