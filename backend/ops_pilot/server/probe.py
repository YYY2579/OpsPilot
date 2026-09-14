"""连接测试探针（§A10.1 / §A10.2 的 /test 端点实现）。

返回结构统一为：
    {"ok": bool, "stage": "credential"|"tcp"|"ssh"|"auth"|"ok", "latency_ms": int, ...}

安全纪律：只返回主机/端口/操作系统等**非敏感**信息；永不回传密码、私钥或密钥内容。
"""
from __future__ import annotations

import socket
import time
from typing import Any, Sequence

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


# ---------------------------------------------------------------- 主机健康快照
#: 巡检时一并探测的常见服务（不存在则如实标记 unknown，不假装"正常"）
DEFAULT_KEY_SERVICES = ("nginx", "docker", "mysql", "redis", "sshd", "k3s")


def collect_server_health(
    credential_ref: str,
    *,
    timeout: float = 8.0,
    key_services: Sequence[str] = DEFAULT_KEY_SERVICES,
    resolver: CredentialResolver | None = None,
) -> dict[str, Any]:
    """采集主机健康快照，供前端概览面板展示**真实**指标。

    与 Agent 工具 `get_server_health` 复用同一份纯逻辑
    （`ops_pilot.tools.health.collect_health`），保证界面与 Agent 看到的数据一致。

    返回结构（失败时 ok=False）：
        ok / server_id / os / uptime_s / cores / load_avg
        cpu_percent / mem_total_gb / mem_used_gb / mem_percent / disk_percent
        top_process[] / services{} / anomalies[] / latency_ms
    安全：只跑只读命令；不返回任何凭据内容。
    """
    import time as _time

    from ops_pilot.tools.health import CollectionError as _CollErr
    from ops_pilot.tools.health import analyze_anomalies, collect_health

    resolver = resolver or CredentialResolver()
    started = _time.perf_counter()

    def elapsed() -> int:
        return int((_time.perf_counter() - started) * 1000)

    try:
        credential = resolver.resolve(credential_ref)
    except CredentialError as exc:
        return {"ok": False, "stage": "credential", "kind": exc.kind,
                "message": exc.detail, "latency_ms": elapsed()}

    runner = None
    try:
        runner = ParamikoCommandRunner(credential, connect_timeout=timeout)
        snapshot = collect_health(runner, server_id=credential_ref,
                                  key_services=tuple(key_services), timeout=timeout)
        snapshot["ok"] = True
        snapshot["latency_ms"] = elapsed()
        snapshot["anomalies"] = analyze_anomalies(snapshot)
        # 附加只读的辅助信息（uptime / 服务状态）
        try:
            snapshot["uptime_text"] = run_checked(runner, "uptime -p", timeout).strip()
        except Exception:  # noqa: BLE001 - 辅助信息缺失不影响主快照
            snapshot["uptime_text"] = ""
        return snapshot
    except (SshError, _CollErr) as exc:
        return {"ok": False, "stage": "ssh", "kind": getattr(exc, "kind", "ssh"),
                "message": getattr(exc, "detail", str(exc)), "latency_ms": elapsed()}
    except Exception as exc:  # noqa: BLE001 - 采集层异常统一转成可读结果
        return {"ok": False, "stage": "collect", "kind": "collect",
                "message": str(exc)[:300], "latency_ms": elapsed()}
    finally:
        if runner is not None:
            runner.close()
