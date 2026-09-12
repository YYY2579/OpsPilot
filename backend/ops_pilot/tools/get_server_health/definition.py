"""get_server_health 的 OpenHands SDK 胶水层。

接入方式全部来自《源码索引》§1（公开 API，零侵入）：
- 继承 ToolDefinition，实现 create(cls, conv_state, **params)，模块尾 register_tool(...)；
  类名 GetServerHealthTool 经 __init_subclass__ 自动命名为 get_server_health（tool.py L386-391）。
- 工具内抛 ValueError 会被 agent 包装成 AgentErrorEvent（agent.py L1427-1438）。
- readOnlyHint=True → 免确认（L 级 = L1 只读）。

凭据纪律（§A6.4）：CredentialResolver 只在 Executor 内调用；凭据与脱敏结果
绝不写入 Action / Observation / 日志。
"""
from __future__ import annotations

import json
from typing import Any, Sequence

from openhands.sdk.llm import TextContent
from openhands.sdk.tool import (
    Action,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)
from pydantic import Field

from ops_pilot.credentials import CredentialError, CredentialResolver, SshCredential
from ops_pilot.ssh.client import ParamikoCommandRunner, SshError
from ops_pilot.tools.health import CollectionError
from ops_pilot.tools.health import collect_health

DESCRIPTION = (
    "只读获取目标主机的健康快照（CPU / 内存 / 磁盘 / 负载 / 高占用进程 / 操作系统 / "
    "关键服务），返回结构化 JSON 并附带 anomalies 异常列表。"
)


class GetServerHealthAction(Action):
    """只读健康快照的输入。**只允许 server_id，绝不出现 IP / 用户名 / 密码**（§A6.4）。"""

    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")


class GetServerHealthObservation(Observation):
    """健康快照。结构即规格 §A5.2 的输出 schema。"""

    server_id: str
    cpu: dict[str, Any]
    memory: dict[str, Any]
    disk: dict[str, Any]
    top_process: list[dict[str, Any]]
    os: dict[str, Any]
    services: dict[str, str]
    anomalies: list[dict[str, str]]

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        """给 LLM 的内容：紧凑 JSON（不含任何凭据字段）。"""
        payload = {
            "server_id": self.server_id,
            "cpu": self.cpu,
            "memory": self.memory,
            "disk": self.disk,
            "top_process": self.top_process,
            "os": self.os,
            "services": self.services,
            "anomalies": self.anomalies,
        }
        return [TextContent(text=json.dumps(payload, ensure_ascii=False))]

    @property
    def ok(self) -> bool:
        return not self.anomalies


class GetServerHealthExecutor(
    ToolExecutor[GetServerHealthAction, GetServerHealthObservation]
):
    """凭据解析与 SSH 采集都发生在这一层内部（§A6.4 第 3 条）。"""

    def __init__(
        self,
        resolver: CredentialResolver | None = None,
        key_services: Sequence[str] = (),
        connect_timeout: float = 8.0,
        command_timeout: float = 10.0,
    ) -> None:
        self._resolver = resolver or CredentialResolver()
        self._key_services = tuple(key_services)
        self._connect_timeout = connect_timeout
        self._command_timeout = command_timeout

    def __call__(
        self,
        action: GetServerHealthAction,
        conversation: Any = None,
    ) -> GetServerHealthObservation:
        runner = None
        try:
            # 凭据解析：只在本方法作用域内存在，绝不外泄
            credential: SshCredential = self._resolver.resolve(action.server_id)
            runner = ParamikoCommandRunner(credential, connect_timeout=self._connect_timeout)
            snapshot = collect_health(
                runner,
                server_id=action.server_id,
                key_services=self._key_services,
                timeout=self._command_timeout,
            )
        except (SshError, CollectionError, CredentialError) as exc:
            # 明确区分：认证失败 / 网络不通 / 命令失败（规格 §A12）
            raise ValueError(f"SSH {exc.kind}: {exc.detail}") from exc
        finally:
            if runner is not None:
                runner.close()
        return GetServerHealthObservation(**snapshot)


class GetServerHealthTool(
    ToolDefinition[GetServerHealthAction, GetServerHealthObservation]
):
    @classmethod
    def create(
        cls,
        conv_state: Any = None,
        resolver: CredentialResolver | None = None,
        key_services: Sequence[str] = (),
        **kwargs: Any,
    ) -> Sequence[GetServerHealthTool]:
        return [
            cls(
                action_type=GetServerHealthAction,
                observation_type=GetServerHealthObservation,
                description=DESCRIPTION,
                annotations=ToolAnnotations(
                    title="get_server_health",
                    readOnlyHint=True,   # → L1 只读，免确认（§A6.5.1）
                ),
                executor=GetServerHealthExecutor(resolver, key_services),
            )
        ]


# 模块级注册（源码索引 §1.2）：import 本模块即生效
register_tool(GetServerHealthTool.name, GetServerHealthTool)
