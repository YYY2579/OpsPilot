"""网络连通性只读工具：check_port / check_http（规格 §A5.2）。

语义：**以目标服务器为起点**发起探测 —— 运维排查中最常见的问题是
"这台机器能不能连到那台机器/那个端口"，所以 server_id 表示探测发起方。
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
from ops_pilot.tools.sshcmd import clamp, run_lenient


# ============================ check_port ============================

class CheckPortAction(Action):
    server_id: str = Field(description="从哪台主机发起探测（目标主机标识，非 IP）")
    host: str = Field(description="要探测的目标地址（IP 或域名）")
    port: int = Field(description="要探测的端口")
    timeout: int = Field(default=3, description="超时秒数（1–15）")


class CheckPortObservation(JsonObservation):
    server_id: str
    host: str
    port: int
    reachable: bool
    result: str          # open / timeout / refused_or_closed
    anomalies: list[dict[str, str]]


class CheckPortExecutor(SshReadOnlyExecutor[CheckPortAction, CheckPortObservation]):
    def collect(self, runner: Any, action: CheckPortAction) -> dict[str, Any]:
        t = clamp(action.timeout, 1, 15)
        # bash 的 /dev/tcp 是最轻量的探测方式：0=通，124=超时，其它=拒绝/关闭
        cmd = f"timeout {t} bash -c '</dev/tcp/{action.host}/{action.port}'"
        code, _out, err = run_lenient(runner, cmd, t + 5)
        if code == 0:
            result = "open"
        elif code == 124:
            result = "timeout"
        elif "command not found" in (err or "").lower() or code == 127:
            raise ValueError("目标主机缺少 bash，无法使用 /dev/tcp 探测")
        else:
            result = "refused_or_closed"
        reachable = result == "open"
        anomalies = [] if reachable else [{
            "item": f"port:{action.host}:{action.port}",
            "level": "warning",
            "hint": f"端口不可达（{result}）",
        }]
        return {
            "server_id": action.server_id,
            "host": action.host,
            "port": action.port,
            "reachable": reachable,
            "result": result,
            "anomalies": anomalies,
        }

    def build(self, action: CheckPortAction, data: dict[str, Any]) -> CheckPortObservation:
        return CheckPortObservation(**data)


class CheckPortTool(ToolDefinition[CheckPortAction, CheckPortObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[CheckPortTool]:
        return [cls(
            action_type=CheckPortAction,
            observation_type=CheckPortObservation,
            description="从指定服务器探测某个 host:port 是否可达（只读，使用 bash /dev/tcp）。"
                        "用于排查网络不通、防火墙拦截、服务未监听等问题。",
            annotations=ToolAnnotations(title="check_port", readOnlyHint=True, openWorldHint=True),
            executor=CheckPortExecutor(),
        )]


# ============================ check_http ============================

class CheckHttpAction(Action):
    server_id: str = Field(description="从哪台主机发起请求（目标主机标识，非 IP）")
    url: str = Field(description="要检查的完整 URL，如 http://192.168.1.10/health")
    method: str = Field(default="GET", description="HTTP 方法，默认 GET")
    timeout: int = Field(default=8, description="超时秒数（1–30）")


class CheckHttpObservation(JsonObservation):
    server_id: str
    url: str
    status_code: int | None
    time_total_s: float | None
    ok: bool
    anomalies: list[dict[str, str]]


class CheckHttpExecutor(SshReadOnlyExecutor[CheckHttpAction, CheckHttpObservation]):
    def collect(self, runner: Any, action: CheckHttpAction) -> dict[str, Any]:
        t = clamp(action.timeout, 1, 30)
        method = action.method.upper()
        cmd = (f"curl -sS -o /dev/null -m {t} -X {method} "
               f"-w '%{{http_code}} %{{time_total}}' {action.url}")
        code, out, err = run_lenient(runner, cmd, t + 5)
        if code != 0:
            detail = ((err or out) or "").strip()[:200]
            anomalies = [{"item": f"http:{action.url}", "level": "warning",
                          "hint": f"请求失败：{detail or f'curl exit {code}'}"}]
            return {
                "server_id": action.server_id,
                "url": action.url,
                "status_code": None,
                "time_total_s": None,
                "ok": False,
                "anomalies": anomalies,
            }
        parts = out.split()
        status_code = int(parts[0]) if parts and parts[0].isdigit() else None
        time_total = float(parts[1]) if len(parts) > 1 else None
        ok = status_code is not None and 200 <= status_code < 400
        anomalies = [] if ok else [{
            "item": f"http:{action.url}",
            "level": "critical" if (status_code or 0) >= 500 else "warning",
            "hint": f"HTTP {status_code}",
        }]
        return {
            "server_id": action.server_id,
            "url": action.url,
            "status_code": status_code,
            "time_total_s": time_total,
            "ok": ok,
            "anomalies": anomalies,
        }

    def build(self, action: CheckHttpAction, data: dict[str, Any]) -> CheckHttpObservation:
        return CheckHttpObservation(**data)


class CheckHttpTool(ToolDefinition[CheckHttpAction, CheckHttpObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[CheckHttpTool]:
        return [cls(
            action_type=CheckHttpAction,
            observation_type=CheckHttpObservation,
            description="从指定服务器发起一次 HTTP 请求，只返回状态码与耗时（不返回响应体），"
                        "并对非 2xx/3xx 给出 anomalies。适合做健康检查端点验证。",
            annotations=ToolAnnotations(title="check_http", readOnlyHint=True, openWorldHint=True),
            executor=CheckHttpExecutor(),
        )]


register_tool(CheckPortTool.name, CheckPortTool)
register_tool(CheckHttpTool.name, CheckHttpTool)
