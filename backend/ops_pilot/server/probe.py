"""连接测试探针（§A10.1 / §A10.2 的 /test 端点实现）。

返回结构统一为：
    {"ok": bool, "stage": "credential"|"tcp"|"ssh"|"auth"|"ok", "latency_ms": int, ...}

安全纪律：只返回主机/端口/操作系统等**非敏感**信息；永不回传密码、私钥或密钥内容。
"""
from __future__ import annotations

import socket
import time
from typing import Any

from ops_pilot.credentials import CredentialError, CredentialResolver
from ops_pilot.ssh.client import ParamikoCommandRunner, SshError
from ops_pilot.tools.sshcmd import CollectionError, run_checked

PING_COMMAND = "cat /etc/os-release"      # 只读且几乎所有 Linux 都有


def _os_name(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def test_server(credential_ref: str, *, timeout: float = 8.0, resolver: CredentialResolver | None = None) -> dict[str, Any]:
    """SSH 连接测试：解析凭据 → 连接 → 跑一条只读命令 → 记耗时。"""
    resolver = resolver or CredentialResolver()
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        credential = resolver.resolve(credential_ref)
    except CredentialError as exc:
        return {"ok": False, "stage": "credential", "kind": exc.kind,
                "message": exc.detail, "latency_ms": elapsed()}

    runner = None
    try:
        runner = ParamikoCommandRunner(credential, connect_timeout=timeout)
        output = run_checked(runner, PING_COMMAND, timeout)
        return {
            "ok": True,
            "stage": "ok",
            "latency_ms": elapsed(),
            "host": credential.host,
            "port": credential.port,
            "username": credential.username,
            "os": _os_name(output),
        }
    except (SshError, CollectionError) as exc:
        return {"ok": False, "stage": "ssh", "kind": exc.kind,
                "message": exc.detail, "latency_ms": elapsed()}
    finally:
        if runner is not None:
            runner.close()


def test_database(
    credential_ref: str,
    host: str,
    port: int,
    db_type: str = "mysql",
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """数据库连接测试：先 TCP 探活；装了驱动且拿到凭据时再做一次只读认证检查。"""
    started = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - started) * 1000)

    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return {"ok": False, "stage": "tcp", "kind": "network",
                "message": f"无法连接 {host}:{port}（{exc}）", "latency_ms": elapsed()}

    if db_type != "mysql":
        return {"ok": True, "stage": "tcp", "latency_ms": elapsed(), "host": host, "port": port,
                "message": f"TCP 可达；{db_type} 认证检查尚未实现"}

    try:
        import pymysql  # 延迟导入：未安装时降级为仅 TCP 检查
    except ImportError:
        return {"ok": True, "stage": "tcp", "latency_ms": elapsed(), "host": host, "port": port,
                "message": "TCP 可达；未安装 pymysql，跳过认证检查"}

    try:
        credential = CredentialResolver().resolve(credential_ref)
    except CredentialError as exc:
        return {"ok": False, "stage": "credential", "kind": exc.kind,
                "message": exc.detail, "latency_ms": elapsed()}

    try:
        connection = pymysql.connect(
            host=host, port=port, user=credential.username,
            password=credential.password or "", connect_timeout=int(timeout),
            read_timeout=int(timeout), charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")        # 只读
                version = cursor.fetchone()[0]
        finally:
            connection.close()
        return {"ok": True, "stage": "ok", "latency_ms": elapsed(), "host": host,
                "port": port, "server_version": version}
    except Exception as exc:  # noqa: BLE001 - 驱动异常统一转成可读结果
        return {"ok": False, "stage": "auth", "kind": "auth",
                "message": f"认证/查询失败：{str(exc)[:200]}", "latency_ms": elapsed()}
