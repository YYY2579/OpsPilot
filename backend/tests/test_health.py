"""get_server_health 纯逻辑层测试：解析 + 异常判断 + 命令失败归因。

不依赖 OpenHands SDK 与 paramiko —— SSH 输出通过 FakeRunner 注入。
"""
from __future__ import annotations

import pytest

from ops_pilot.ssh.client import SshError
from ops_pilot.tools.health import (
    CollectionError,
    LEVEL_CRIT,
    LEVEL_WARN,
    analyze_anomalies,
    collect_health,
)

# ---- 可复用的假采集输出（演示占位，非真实主机数据） ----

LOADAVG = "3.02 2.88 2.71 1/512 12345\n"
NPROC = "4\n"
MEMINFO = "\n".join(
    [
        "MemTotal:        8388608 kB",
        "MemFree:          512000 kB",
        "MemAvailable:     819200 kB",
        "Buffers:          128000 kB",
        "Cached:           640000 kB",
    ]
)
DF_HIGH = "Filesystem 1K-blocks Used Available Capacity Mounted\n/dev/sda1  83886080  75161927  8724153  90% /\n"
DF_OK = "Filesystem 1K-blocks Used Available Capacity Mounted\n/dev/sda1  83886080  25165824  58720256  30% /\n"
PS = (
    "  PID COMMAND         %CPU\n"
    " 2143 java          182.0\n"
    "  882 containerd     8.6\n"
    " 1174 nginx          4.2\n"
    "  301 dockerd        3.1\n"
    "  555 sshd           0.3\n"
    "  700 cron           0.1\n"
)
OS_RELEASE = 'PRETTY_NAME="Ubuntu 24.04 LTS"\nNAME="Ubuntu"\n'

PROC_STAT_HIGH = (
    "cpu  100 0 50 400 0 0 0 0 0 0\n"    # 采样1：idle 400
    "cpu0 25 0 12 100 0 0 0 0 0 0\n"
    "cpu  250 0 100 430 0 0 0 0 0 0\n"   # 采样2：idle 430 → busy 200/230 ≈ 87%
    "cpu0 62 0 25 107 0 0 0 0 0 0\n"
)
PROC_STAT_IDLE = (
    "cpu  100 0 50 1000 0 0 0 0 0 0\n"
    "cpu0 25 0 12 250 0 0 0 0 0 0\n"
    "cpu  150 0 60 2000 0 0 0 0 0 0\n"  # 采样2：仍大量空闲
    "cpu0 37 0 15 500 0 0 0 0 0 0\n"
)


class FakeRunner:
    """把命令 → 输出 的映射注入采集层。"""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping
        self.calls: list[str] = []

    def run(self, command: str, timeout: float = 10.0) -> tuple[int, str, str]:
        self.calls.append(command)
        for key, value in self._mapping.items():
            if command == key or command.startswith(key):
                return 0, value, ""
        return 1, "", f"command not found: {command}"


def _base_mapping(proc_stat: str, df: str = DF_OK) -> dict[str, str]:
    return {
        "cat /proc/loadavg": LOADAVG,
        "nproc": NPROC,
        "cat /proc/stat": proc_stat,
        "cat /proc/meminfo": MEMINFO,
        "df -P /": df,
        "ps -eo pid,comm,%cpu": PS,
        "cat /etc/os-release": OS_RELEASE,
    }


def test_collect_health_parses_all_sections():
    runner = FakeRunner(_base_mapping(PROC_STAT_HIGH, DF_HIGH))
    snap = collect_health(runner, server_id="hk-ubuntu", key_services=("docker", "nginx"))

    assert snap["server_id"] == "hk-ubuntu"
    # CPU：两采样差值 → 高使用率
    assert snap["cpu"]["percent"] > 80
    assert snap["cpu"]["cores"] == 4
    assert snap["cpu"]["load_avg"] == [3.02, 2.88, 2.71]
    # 内存：total 8 GiB，available 0.78125 GiB → used ≈ 90.2%
    assert snap["memory"]["total_gb"] == 8.0
    assert snap["memory"]["percent"] > 85
    # 磁盘
    assert snap["disk"]["used_percent"] == 90.0
    # 进程
    assert snap["top_process"][0] == {"pid": 2143, "name": "java", "cpu": 182.0}
    assert len(snap["top_process"]) == 5
    # 系统
    assert snap["os"]["name"] == "Ubuntu 24.04 LTS"
    # 服务：未注入 systemctl 输出 → 如实标记 unknown
    assert snap["services"] == {"docker": "unknown", "nginx": "unknown"}
    # 异常判断在采集函数内已完成（§A5.2）
    items = {a["item"] for a in snap["anomalies"]}
    # load/cores = 3.02/4 ≈ 0.76 < 1.5 → 无 load 异常；服务未注入输出 → unknown 告警
    assert {"cpu", "memory", "disk", "service:docker", "service:nginx"} <= items


def test_anomalies_levels_warn_vs_critical():
    runner = FakeRunner(_base_mapping(PROC_STAT_HIGH, DF_HIGH))
    snap = collect_health(runner, server_id="hk-ubuntu")
    levels = {a["item"]: a["level"] for a in snap["anomalies"]}
    # CPU 采样差值计算出的使用率落在 warn 区间
    assert levels["cpu"] == LEVEL_WARN
    assert levels["memory"] == LEVEL_WARN
    assert levels["disk"] == LEVEL_WARN   # 90%：warn(85) ≤ x < crit(95)
    # load/cores = 3.02/4 = 0.755 → 不应有 load 异常
    assert "load" not in levels


def test_anomalies_empty_when_all_ok():
    mapping = _base_mapping(PROC_STAT_IDLE, DF_OK)
    mapping["cat /proc/meminfo"] = "\n".join(
        [
            "MemTotal:        8388608 kB",
            "MemAvailable:     6291456 kB",
        ]
    )
    runner = FakeRunner(mapping)
    snap = collect_health(runner, server_id="hk-ubuntu")
    assert snap["anomalies"] == []
    assert snap["cpu"]["status"] == "ok"
    assert snap["memory"]["status"] == "ok"
    assert snap["disk"]["status"] == "ok"


def test_service_failed_is_critical():
    mapping = _base_mapping(PROC_STAT_IDLE, DF_OK)
    runner = FakeRunner(mapping)
    # FakeRunner 只匹配前缀键；is-active 单独注入
    mapping["systemctl is-active docker"] = "failed\n"
    mapping["systemctl is-active nginx"] = "active\n"
    snap = collect_health(runner, server_id="hk-ubuntu", key_services=("docker", "nginx"))
    item = [a for a in snap["anomalies"] if a["item"] == "service:docker"]
    assert item and item[0]["level"] == LEVEL_CRIT


def test_ssh_auth_error_is_reported_clearly():
    class AuthFail:
        def run(self, command: str, timeout: float = 10.0):
            raise SshError("auth", "认证失败：user@host")

    with pytest.raises(CollectionError) as excinfo:
        collect_health(AuthFail(), server_id="hk-ubuntu")
    assert excinfo.value.kind == "auth"


def test_command_error_is_reported_clearly():
    class CmdFail:
        def run(self, command: str, timeout: float = 10.0):
            if command == "cat /proc/loadavg":
                return 1, "", "cat: /proc/loadavg: No such file or directory"
            return 0, LOADAVG, ""

    with pytest.raises(CollectionError) as excinfo:
        collect_health(CmdFail(), server_id="hk-ubuntu")
    assert excinfo.value.kind == "command"
    assert "exit 1" in str(excinfo.value)


def test_analyze_is_idempotent():
    runner = FakeRunner(_base_mapping(PROC_STAT_HIGH, DF_HIGH))
    snap = collect_health(runner, server_id="hk-ubuntu")
    again = analyze_anomalies(snap)
    assert again == snap["anomalies"]
