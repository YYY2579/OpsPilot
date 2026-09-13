"""工具注册总入口（**依赖 OpenHands SDK**）。

只读工具全部在这里注册；纯逻辑测试不要 import 本模块。
用法：`import ops_pilot.tools.register_all` 即可让所有工具进入 ToolRegistry。
"""
from __future__ import annotations

import ops_pilot.tools.docker  # noqa: F401
import ops_pilot.tools.get_server_health.definition  # noqa: F401
import ops_pilot.tools.network  # noqa: F401
import ops_pilot.tools.system  # noqa: F401

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
)


def tool_specs() -> list:
    """返回可直接传给 Agent(tools=[...]) 的 Tool spec 列表。"""
    from openhands.sdk.tool import Tool

    return [Tool(name=name) for name in READONLY_TOOL_NAMES]
