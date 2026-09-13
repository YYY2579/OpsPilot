"""Docker 只读工具：list_docker_containers / get_container_logs（规格 §A5.2）。"""
from __future__ import annotations

import json
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
from ops_pilot.tools.sshcmd import clamp, run_lenient


def _docker_missing(err: str) -> bool:
    low = (err or "").lower()
    return "command not found" in low or "no such file" in low or "not installed" in low


# ======================= list_docker_containers =======================

class ListDockerContainersAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    include_stopped: bool = Field(default=True, description="是否包含已停止容器（docker ps -a）")


class ListDockerContainersObservation(JsonObservation):
    server_id: str
    containers: list[dict[str, Any]]
    running: int
    total: int
    anomalies: list[dict[str, str]]


class ListDockerContainersExecutor(
    SshReadOnlyExecutor[ListDockerContainersAction, ListDockerContainersObservation]
):
    def collect(self, runner: Any, action: ListDockerContainersAction) -> dict[str, Any]:
        flag = "-a " if action.include_stopped else ""
        cmd = f"docker ps {flag}--format '{{{{json .}}}}'"
        code, out, err = run_lenient(runner, cmd, self._command_timeout)
        if _docker_missing(err):
            raise ValueError(f"目标主机未安装 docker：{(err or '').strip()[:120]}")
        if code != 0:
            raise ValueError(f"docker ps 失败（exit {code}）：{(err or '').strip()[:200]}")

        containers: list[dict[str, Any]] = []
        for line in out.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            containers.append({
                "id": (raw.get("ID") or "")[:12],
                "name": raw.get("Names"),
                "image": raw.get("Image"),
                "state": raw.get("State"),
                "status": raw.get("Status"),
                "ports": raw.get("Ports"),
            })
        running = sum(1 for c in containers if c["state"] == "running")
        anomalies: list[dict[str, str]] = []
        for c in containers:
            state = (c["state"] or "").lower()
            if state in ("restarting", "dead", "exited"):
                anomalies.append({
                    "item": f"container:{c['name']}",
                    "level": "critical" if state in ("restarting", "dead") else "warning",
                    "hint": f"容器状态 {state} · {c['status']}",
                })
        return {
            "server_id": action.server_id,
            "containers": containers,
            "running": running,
            "total": len(containers),
            "anomalies": anomalies,
        }

    def build(self, action: ListDockerContainersAction,
              data: dict[str, Any]) -> ListDockerContainersObservation:
        return ListDockerContainersObservation(**data)


class ListDockerContainersTool(
    ToolDefinition[ListDockerContainersAction, ListDockerContainersObservation]
):
    @classmethod
    def create(cls, conv_state: Any = None,
               **params: Any) -> Sequence[ListDockerContainersTool]:
        return [cls(
            action_type=ListDockerContainersAction,
            observation_type=ListDockerContainersObservation,
            description="只读列出目标主机上的 Docker 容器（含状态与端口），并对 restarting/dead/exited 给出 anomalies。",
            annotations=ToolAnnotations(title="list_docker_containers", readOnlyHint=True),
            executor=ListDockerContainersExecutor(),
        )]


# ======================= get_container_logs =======================

class GetContainerLogsAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    container: str = Field(description="容器名或 ID")
    lines: int = Field(default=100, description="返回最后多少行（1–1000）")
    timestamps: bool = Field(default=False, description="是否带时间戳")


class GetContainerLogsObservation(JsonObservation):
    server_id: str
    container: str
    lines_returned: int
    truncated: bool
    log_text: str
    anomalies: list[dict[str, str]]


class GetContainerLogsExecutor(
    SshReadOnlyExecutor[GetContainerLogsAction, GetContainerLogsObservation]
):
    def collect(self, runner: Any, action: GetContainerLogsAction) -> dict[str, Any]:
        n = clamp(action.lines, 1, 1000)
        ts = " --timestamps" if action.timestamps else ""
        cmd = f"docker logs --tail {n}{ts} {action.container} 2>&1"
        code, out, err = run_lenient(runner, cmd, self._command_timeout + 5)
        text = out or ""
        if code != 0 and not text.strip():
            detail = (err or text).strip()[:200]
            if _docker_missing(err):
                raise ValueError(f"目标主机未安装 docker：{detail}")
            raise ValueError(f"读取容器 {action.container} 日志失败：{detail}")
        if "No such container" in text:
            raise ValueError(f"容器不存在：{action.container}")
        lines_all = text.rstrip("\n").splitlines()
        truncated = len(lines_all) > n
        shown = "\n".join(lines_all[-n:]) if truncated else "\n".join(lines_all)
        low = shown.lower()
        anomalies: list[dict[str, str]] = []
        for kw in ("error", "panic", "fatal", "exception"):
            if kw in low:
                anomalies.append({"item": f"container:{action.container}", "level": "warning",
                                  "hint": f"日志中出现关键词：{kw}"})
                break
        return {
            "server_id": action.server_id,
            "container": action.container,
            "lines_returned": len(shown.splitlines()) if shown else 0,
            "truncated": truncated,
            "log_text": shown,
            "anomalies": anomalies,
        }

    def build(self, action: GetContainerLogsAction,
              data: dict[str, Any]) -> GetContainerLogsObservation:
        return GetContainerLogsObservation(**data)


class GetContainerLogsTool(ToolDefinition[GetContainerLogsAction, GetContainerLogsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetContainerLogsTool]:
        return [cls(
            action_type=GetContainerLogsAction,
            observation_type=GetContainerLogsObservation,
            description="只读读取指定容器的最近日志（docker logs --tail）。",
            annotations=ToolAnnotations(title="get_container_logs", readOnlyHint=True),
            executor=GetContainerLogsExecutor(),
        )]


register_tool(ListDockerContainersTool.name, ListDockerContainersTool)
register_tool(GetContainerLogsTool.name, GetContainerLogsTool)
