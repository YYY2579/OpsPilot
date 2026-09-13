"""写类工具：restart_service（§A5.2，L3 中风险）。

这是第一个**需要审批**的工具，用于验证审批闭环（M6-3）：
- `readOnlyHint=False` + `destructiveHint=True` → analyzer 判为 L3 → 在"请求审批"
  和"帮我批准"档下都要人工确认（§A6.5.1 矩阵）
- 提供 `dry_run`（默认 False）：只校验目标与服务是否存在，不真的重启。
  既方便演练，也方便在真实环境先"预演"一遍。

凭据纪律不变：凭据只在 Executor 内解析。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openhands.sdk.tool import (
    Action,
    ToolAnnotations,
    ToolDefinition,
    register_tool,
)
from pydantic import Field

from ops_pilot.tools._base import JsonObservation, SshReadOnlyExecutor
from ops_pilot.tools.sshcmd import run_lenient

#: 服务名白名单（防注入：只允许保守字符集）
import re

SERVICE_RE = re.compile(r"^[A-Za-z0-9@._:-]{1,64}$")


class RestartServiceAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    service: str = Field(description="要重启的 systemd 服务名，如 nginx")
    dry_run: bool = Field(
        default=False,
        description="true=只检查服务是否存在与当前状态，不执行重启（演练用）",
    )


class RestartServiceObservation(JsonObservation):
    server_id: str
    service: str
    command: str
    dry_run: bool
    exit_code: int
    output: str
    anomalies: list[dict[str, str]]


class RestartServiceExecutor(SshReadOnlyExecutor[RestartServiceAction, RestartServiceObservation]):
    """虽然叫 ReadOnlyExecutor（复用它的凭据/连接/错误映射），但本工具会改变系统状态。"""

    def collect(self, runner: Any, action: RestartServiceAction) -> dict[str, Any]:
        service = action.service.strip()
        if not SERVICE_RE.match(service):
            raise ValueError(f"服务名不合法：{service!r}（只允许字母数字 @ . _ : -）")

        command = (
            f"systemctl is-active {service} >/dev/null 2>&1 && echo present || echo missing"
            if action.dry_run
            else f"systemctl restart {service} && systemctl is-active {service}"
        )
        code, out, err = run_lenient(runner, command, self._command_timeout + 10)
        output = (out or "").strip() or (err or "").strip()

        anomalies: list[dict[str, str]] = []
        if action.dry_run and output.startswith("missing"):
            anomalies.append({"item": f"service:{service}", "level": "critical",
                              "hint": "服务不存在，重启会失败"})
        elif not action.dry_run:
            if code != 0:
                anomalies.append({"item": f"service:{service}", "level": "critical",
                                  "hint": f"重启失败：{output[:120]}"})
            elif "active" not in output:
                anomalies.append({"item": f"service:{service}", "level": "warning",
                                  "hint": f"重启后状态异常：{output}"})

        return {
            "server_id": action.server_id,
            "service": service,
            "command": command,
            "dry_run": action.dry_run,
            "exit_code": code,
            "output": output,
            "anomalies": anomalies,
        }

    def build(self, action: RestartServiceAction,
              data: dict[str, Any]) -> RestartServiceObservation:
        return RestartServiceObservation(**data)


class RestartServiceTool(ToolDefinition[RestartServiceAction, RestartServiceObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[RestartServiceTool]:
        return [cls(
            action_type=RestartServiceAction,
            observation_type=RestartServiceObservation,
            description=(
                "重启目标主机上的 systemd 服务（中风险，会短暂中断该服务）。"
                "先用 dry_run=true 确认服务存在，再执行真正的重启。"
                "执行前必须向用户说明影响与回滚方案。"
            ),
            annotations=ToolAnnotations(
                title="restart_service",
                readOnlyHint=False,       # → L3，需要审批
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            ),
            executor=RestartServiceExecutor(),
        )]


register_tool(RestartServiceTool.name, RestartServiceTool)
