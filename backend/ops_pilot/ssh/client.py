"""SSH 命令执行适配器。

设计：ops_pilot.tools.health 只依赖 CommandRunner 协议（纯逻辑、可注入假实现测试），
paramiko 只在本文件内延迟导入 —— 真正连接时才需要安装。
"""
from __future__ import annotations

import socket
from typing import Protocol

from ops_pilot.credentials import SshCredential


class SshError(RuntimeError):
    """SSH 执行失败。kind: auth（认证失败）/ network（网络不通）/ command（命令失败）。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


class CommandRunner(Protocol):
    """健康采集只依赖这个协议，便于单测注入假输出。"""

    def run(self, command: str, timeout: float = 10.0) -> tuple[int, str, str]:
        """返回 (exit_code, stdout, stderr)。连接/执行失败抛 SshError。"""


class ParamikoCommandRunner:
    """基于 paramiko 的 CommandRunner。全部命令为只读采集命令。"""

    def __init__(
        self,
        credential: SshCredential,
        connect_timeout: float = 8.0,
    ) -> None:
        import paramiko  # 延迟导入：单测不需要装

        self._credential = credential
        self._connect_timeout = connect_timeout
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if credential.key_path:
                client.connect(
                    hostname=credential.host,
                    port=credential.port,
                    username=credential.username,
                    key_filename=credential.key_path,
                    timeout=connect_timeout,
                    banner_timeout=connect_timeout,
                    auth_timeout=connect_timeout,
                )
            else:
                client.connect(
                    hostname=credential.host,
                    port=credential.port,
                    username=credential.username,
                    password=credential.password,
                    timeout=connect_timeout,
                    banner_timeout=connect_timeout,
                    auth_timeout=connect_timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
        except paramiko.AuthenticationException as exc:
            raise SshError("auth", f"认证失败：{credential.username}@{credential.host}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise SshError("network", f"连接超时：{credential.host}:{credential.port}") from exc
        except (socket.gaierror, OSError) as exc:
            raise SshError("network", f"无法连接 {credential.host}:{credential.port}（{exc}）") from exc
        self._client = client

    def run(self, command: str, timeout: float = 10.0) -> tuple[int, str, str]:
        try:
            _stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
        except socket.timeout as exc:
            raise SshError("command", f"命令超时（>{timeout}s）：{command.splitlines()[0]}") from exc
        except OSError as exc:
            raise SshError("network", f"连接中断：{exc}") from exc
        return code, out, err

    def close(self) -> None:
        self._client.close()
