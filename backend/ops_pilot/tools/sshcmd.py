"""SSH 采集公共层：命令执行 + 错误归一（供各只读工具复用）。

规格：§A5.2 每个工具输出 schema 稳定、异常判断在 Executor 内完成。
"""
from __future__ import annotations

from typing import Any

from ops_pilot.ssh.client import CommandRunner, SshError

DEFAULT_COMMAND_TIMEOUT = 10.0


class CollectionError(RuntimeError):
    """采集失败。kind 来自 SshError（auth / network / command）。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


def run_checked(runner: CommandRunner, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> str:
    """执行命令，非 0 退出或空输出即抛 CollectionError。"""
    try:
        code, out, err = runner.run(command, timeout)
    except SshError as exc:   # 统一错误类型：纯逻辑层只抛 CollectionError
        raise CollectionError(exc.kind, exc.detail) from exc
    if code != 0:
        raise CollectionError("command", f"命令失败（exit {code}）：{command} → {err.strip()[:200]}")
    if not out.strip():
        raise CollectionError("command", f"命令无输出：{command}")
    return out


def run_lenient(runner: CommandRunner, command: str, timeout: float = DEFAULT_COMMAND_TIMEOUT) -> tuple[int, str, str]:
    """执行命令但容忍非 0 退出（用于 is-active / check_port 等本身用退出码表达结果的命令）。"""
    try:
        return runner.run(command, timeout)
    except SshError as exc:
        raise CollectionError(exc.kind, exc.detail) from exc


def tail(text: str, max_lines: int) -> tuple[str, bool]:
    """截断文本到最多 max_lines 行，返回 (文本, 是否被截断)。"""
    lines = text.rstrip("\n").splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines), False
    return "\n".join(lines[-max_lines:]), True


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def as_dict(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)
