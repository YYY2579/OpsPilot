"""只读工具的公共 Executor 骨架。

一个只读 SSH 工具 = Action(server_id + 参数) + Observation(结构化字段) +
Executor(解析凭据 → 执行只读命令 → 结构化输出，异常在 Executor 内判断)。

凭据纪律（§A6.4）：解析只发生在 Executor 内，绝不进入 Action / Observation / 日志。
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from openhands.sdk.llm import TextContent
from openhands.sdk.tool import Observation, ToolExecutor

from ops_pilot.credentials import CredentialError, CredentialResolver, SshCredential
from ops_pilot.ssh.client import ParamikoCommandRunner, SshError
from ops_pilot.tools.sshcmd import CollectionError

ActionT = TypeVar("ActionT")
ObservationT = TypeVar("ObservationT")


class SshReadOnlyExecutor(ToolExecutor[ActionT, ObservationT], Generic[ActionT, ObservationT]):
    """只读 SSH 工具的统一执行层。子类只需实现 collect() 与 build()。"""

    def __init__(
        self,
        resolver: CredentialResolver | None = None,
        connect_timeout: float = 8.0,
        command_timeout: float = 10.0,
    ) -> None:
        self._resolver = resolver or CredentialResolver()
        self._connect_timeout = connect_timeout
        self._command_timeout = command_timeout

    # ---- 子类实现 ----
    def collect(self, runner: Any, action: ActionT) -> dict[str, Any]:
        raise NotImplementedError

    def build(self, action: ActionT, data: dict[str, Any]) -> ObservationT:
        raise NotImplementedError

    # ---- 统一执行 ----
    def __call__(self, action: ActionT, conversation: Any = None) -> ObservationT:
        runner = None
        try:
            credential: SshCredential = self._resolver.resolve(getattr(action, "server_id"))
            runner = ParamikoCommandRunner(credential, connect_timeout=self._connect_timeout)
            data = self.collect(runner, action)
        except (SshError, CollectionError, CredentialError) as exc:
            # 明确区分：认证失败 / 网络不通 / 命令失败（规格 §A12）
            raise ValueError(f"SSH {exc.kind}: {exc.detail}") from exc
        finally:
            if runner is not None:
                runner.close()
        return self.build(action, data)


class JsonObservation(Observation):
    """默认把全部字段序列化成 JSON 给 LLM，避免每个工具重复实现 to_llm_content。"""

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        payload = {k: v for k, v in self.model_dump().items() if k != "kind"}
        return [TextContent(text=json.dumps(payload, ensure_ascii=False))]
