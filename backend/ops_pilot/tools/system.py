"""系统类只读工具：get_disk_usage / get_process_list / get_service_status / get_service_logs

规格 §A5.2 命名表。全部 readOnlyHint=True（L1 只读，免确认）。
异常判断在 Executor 内完成（§A5.2），不交给 LLM。
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
from ops_pilot.tools.sshcmd import clamp, run_checked, run_lenient, tail

DISK_WARN, DISK_CRIT = 85.0, 95.0
INODE_WARN, INODE_CRIT = 85.0, 95.0
PROC_CPU_WARN, PROC_CPU_CRIT = 80.0, 200.0
PROC_MEM_WARN = 30.0


# ============================ get_disk_usage ============================

class GetDiskUsageAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    min_percent: float = Field(default=0.0, description="只返回使用率不低于该值的挂载点")
    limit: int = Field(default=20, description="最多返回挂载点数量（1–50）")


class GetDiskUsageObservation(JsonObservation):
    server_id: str
    filesystems: list[dict[str, Any]]
    inode_percent: float | None = None
    anomalies: list[dict[str, str]]


def _parse_df(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.strip().splitlines()[1:]:      # 跳过表头
        cols = line.split()
        if len(cols) < 6:
            continue
        rows.append({
            "filesystem": cols[0],
            "size_kb": int(cols[1]) if cols[1].isdigit() else None,
            "used_kb": int(cols[2]) if cols[2].isdigit() else None,
            "avail_kb": int(cols[3]) if cols[3].isdigit() else None,
            "use_percent": float(cols[4].rstrip("%")),
            "mount": cols[5],
        })
    return rows


def analyze_disk(payload: dict[str, Any]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    for fs in payload["filesystems"]:
        pct = fs["use_percent"]
        if pct >= DISK_CRIT:
            anomalies.append({"item": f"disk:{fs['mount']}", "level": "critical",
                              "hint": f"使用率 {pct}% ≥ {DISK_CRIT}%"})
        elif pct >= DISK_WARN:
            anomalies.append({"item": f"disk:{fs['mount']}", "level": "warning",
                              "hint": f"使用率 {pct}% ≥ {DISK_WARN}%"})
    inode = payload.get("inode_percent")
    if inode is not None:
        if inode >= INODE_CRIT:
            anomalies.append({"item": "inode:/", "level": "critical", "hint": f"inode 使用率 {inode}%"})
        elif inode >= INODE_WARN:
            anomalies.append({"item": "inode:/", "level": "warning", "hint": f"inode 使用率 {inode}%"})
    return anomalies


class GetDiskUsageExecutor(SshReadOnlyExecutor[GetDiskUsageAction, GetDiskUsageObservation]):
    def collect(self, runner: Any, action: GetDiskUsageAction) -> dict[str, Any]:
        text = run_checked(runner, "df -P -x tmpfs -x devtmpfs -x overlay", self._command_timeout)
        filesystems = [fs for fs in _parse_df(text) if fs["use_percent"] >= action.min_percent]
        filesystems.sort(key=lambda fs: fs["use_percent"], reverse=True)
        payload: dict[str, Any] = {
            "server_id": action.server_id,
            "filesystems": filesystems[: clamp(action.limit, 1, 50)],
        }
        code, out, _err = run_lenient(runner, "df -Pi /", self._command_timeout)
        if code == 0 and out.strip():
            cols = out.strip().splitlines()[-1].split()
            if len(cols) >= 5:
                payload["inode_percent"] = float(cols[4].rstrip("%"))
        payload["anomalies"] = analyze_disk(payload)
        return payload

    def build(self, action: GetDiskUsageAction, data: dict[str, Any]) -> GetDiskUsageObservation:
        return GetDiskUsageObservation(**data)


class GetDiskUsageTool(ToolDefinition[GetDiskUsageAction, GetDiskUsageObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetDiskUsageTool]:
        return [cls(
            action_type=GetDiskUsageAction,
            observation_type=GetDiskUsageObservation,
            description="只读获取各文件系统的磁盘使用率与 inode 使用率，并返回 anomalies 异常列表。",
            annotations=ToolAnnotations(title="get_disk_usage", readOnlyHint=True),
            executor=GetDiskUsageExecutor(),
        )]


# ============================ get_process_list ============================

class GetProcessListAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    limit: int = Field(default=15, description="返回条数（1–50）")
    sort_by: str = Field(default="cpu", description="排序字段：cpu 或 mem")


class GetProcessListObservation(JsonObservation):
    server_id: str
    sort_by: str
    processes: list[dict[str, Any]]
    process_total: int
    anomalies: list[dict[str, str]]


def _parse_ps(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.strip().splitlines()[1:]:
        cols = line.split(None, 6)
        if len(cols) < 7:
            continue
        rows.append({
            "pid": int(cols[0]),
            "ppid": int(cols[1]) if cols[1].isdigit() else None,
            "user": cols[2],
            "name": cols[3],
            "cpu_percent": float(cols[4]),
            "mem_percent": float(cols[5]),
            "elapsed": cols[6],
        })
    return rows


def analyze_processes(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    for p in rows:
        if p["cpu_percent"] >= PROC_CPU_CRIT:
            anomalies.append({"item": f"proc:{p['name']}({p['pid']})", "level": "critical",
                              "hint": f"CPU {p['cpu_percent']}%（可能多核累加）"})
        elif p["cpu_percent"] >= PROC_CPU_WARN:
            anomalies.append({"item": f"proc:{p['name']}({p['pid']})", "level": "warning",
                              "hint": f"CPU {p['cpu_percent']}%"})
        if p["mem_percent"] >= PROC_MEM_WARN:
            anomalies.append({"item": f"proc:{p['name']}({p['pid']})", "level": "warning",
                              "hint": f"内存 {p['mem_percent']}%"})
    return anomalies


class GetProcessListExecutor(SshReadOnlyExecutor[GetProcessListAction, GetProcessListObservation]):
    def collect(self, runner: Any, action: GetProcessListAction) -> dict[str, Any]:
        limit = clamp(action.limit, 1, 50)
        sort_key = "-%mem" if action.sort_by == "mem" else "-%cpu"
        cmd = f"ps -eo pid,ppid,user,comm,%cpu,%mem,etime --sort={sort_key} | head -{limit + 1}"
        text = run_checked(runner, cmd, self._command_timeout)
        rows = _parse_ps(text)
        code, out, _err = run_lenient(runner, "ps -e --no-headers | wc -l", self._command_timeout)
        total = int(out.strip()) if code == 0 and out.strip().isdigit() else len(rows)
        return {
            "server_id": action.server_id,
            "sort_by": action.sort_by,
            "processes": rows[:limit],
            "process_total": total,
            "anomalies": analyze_processes(rows[:limit]),
        }

    def build(self, action: GetProcessListAction, data: dict[str, Any]) -> GetProcessListObservation:
        return GetProcessListObservation(**data)


class GetProcessListTool(ToolDefinition[GetProcessListAction, GetProcessListObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetProcessListTool]:
        return [cls(
            action_type=GetProcessListAction,
            observation_type=GetProcessListObservation,
            description="只读获取按 CPU 或内存排序的进程列表（含 PID/父 PID/用户/CPU%/内存%/运行时长），"
                        "并返回 anomalies。注意 %CPU 在多核上可能大于 100。",
            annotations=ToolAnnotations(title="get_process_list", readOnlyHint=True),
            executor=GetProcessListExecutor(),
        )]


# ============================ get_service_status ============================

class GetServiceStatusAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    services: list[str] = Field(description="要检查的服务名列表，如 ['nginx','docker']（1–20 个）")


class GetServiceStatusObservation(JsonObservation):
    server_id: str
    services: dict[str, dict[str, str]]
    anomalies: list[dict[str, str]]


class GetServiceStatusExecutor(SshReadOnlyExecutor[GetServiceStatusAction, GetServiceStatusObservation]):
    def collect(self, runner: Any, action: GetServiceStatusAction) -> dict[str, Any]:
        names = [s.strip() for s in action.services if s.strip()][:20]
        if not names:
            raise ValueError("services 不能为空")
        services: dict[str, dict[str, str]] = {}
        for name in names:
            code, out, _err = run_lenient(
                runner, f"systemctl is-active {name}; systemctl is-enabled {name}", self._command_timeout
            )
            lines = (out or "").strip().splitlines()
            services[name] = {
                "active": lines[0].strip() if len(lines) > 0 and lines[0].strip() else "unknown",
                "enabled": lines[1].strip() if len(lines) > 1 and lines[1].strip() else "unknown",
            }
        anomalies: list[dict[str, str]] = []
        for name, state in services.items():
            if state["active"] == "failed":
                anomalies.append({"item": f"service:{name}", "level": "critical", "hint": "服务处于 failed"})
            elif state["active"] != "active":
                anomalies.append({"item": f"service:{name}", "level": "warning",
                                  "hint": f"服务状态 {state['active']}"})
        return {"server_id": action.server_id, "services": services, "anomalies": anomalies}

    def build(self, action: GetServiceStatusAction, data: dict[str, Any]) -> GetServiceStatusObservation:
        return GetServiceStatusObservation(**data)


class GetServiceStatusTool(ToolDefinition[GetServiceStatusAction, GetServiceStatusObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetServiceStatusTool]:
        return [cls(
            action_type=GetServiceStatusAction,
            observation_type=GetServiceStatusObservation,
            description="只读检查指定 systemd 服务的运行状态与开机自启状态（systemctl is-active / is-enabled）。",
            annotations=ToolAnnotations(title="get_service_status", readOnlyHint=True),
            executor=GetServiceStatusExecutor(),
        )]


# ============================ get_service_logs ============================

class GetServiceLogsAction(Action):
    server_id: str = Field(description="目标主机标识，如 hk-ubuntu（非 IP）")
    service: str = Field(description="systemd 服务名，如 nginx")
    lines: int = Field(default=50, description="返回最近多少行（1–500）")
    since: str | None = Field(default=None, description="journalctl 时间范围，如 '-1h' 或 '2026-09-13 09:00'")


class GetServiceLogsObservation(JsonObservation):
    server_id: str
    service: str
    lines_returned: int
    truncated: bool
    log_text: str
    anomalies: list[dict[str, str]]


# 日志异常关键词（真实运维高频短语，"timed out" 这类带空格的必须单独列）
_ERROR_KEYWORDS = (
    "error", "failed", "failure", "fatal", "panic", "exception",
    "timeout", "timed out", "refused", "denied", "no space left", "out of memory",
)


class GetServiceLogsExecutor(SshReadOnlyExecutor[GetServiceLogsAction, GetServiceLogsObservation]):
    def collect(self, runner: Any, action: GetServiceLogsAction) -> dict[str, Any]:
        n = clamp(action.lines, 1, 500)
        since = f' --since "{action.since}"' if action.since else ""
        cmd = f"journalctl -u {action.service} -n {n} --no-pager -o short-iso{since}"
        code, out, err = run_lenient(runner, cmd, self._command_timeout + 5)
        if code != 0 and not out.strip():
            raise ValueError(f"读取 {action.service} 日志失败：{(err or '').strip()[:200]}")
        text, truncated = tail(out, n)
        hits = [kw for kw in _ERROR_KEYWORDS if kw in text.lower()]
        anomalies = ([{"item": f"logs:{action.service}", "level": "warning",
                       "hint": f"日志中出现关键词：{', '.join(hits)}"}] if hits else [])
        return {
            "server_id": action.server_id,
            "service": action.service,
            "lines_returned": len(text.splitlines()) if text else 0,
            "truncated": truncated,
            "log_text": text,
            "anomalies": anomalies,
        }

    def build(self, action: GetServiceLogsAction, data: dict[str, Any]) -> GetServiceLogsObservation:
        return GetServiceLogsObservation(**data)


class GetServiceLogsTool(ToolDefinition[GetServiceLogsAction, GetServiceLogsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetServiceLogsTool]:
        return [cls(
            action_type=GetServiceLogsAction,
            observation_type=GetServiceLogsObservation,
            description="只读读取指定 systemd 服务最近的日志（journalctl -n），带关键词异常提示。",
            annotations=ToolAnnotations(title="get_service_logs", readOnlyHint=True),
            executor=GetServiceLogsExecutor(),
        )]


register_tool(GetDiskUsageTool.name, GetDiskUsageTool)
register_tool(GetProcessListTool.name, GetProcessListTool)
register_tool(GetServiceStatusTool.name, GetServiceStatusTool)
register_tool(GetServiceLogsTool.name, GetServiceLogsTool)
