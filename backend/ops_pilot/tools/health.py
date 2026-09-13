"""健康快照采集与异常判断（纯逻辑，无 SDK 依赖）。

规格依据：需求开发文档 §A5.2 —— 输出强制含 anomalies；**异常判断在 Executor 内完成，
不交给 LLM**（输出稳定、可测试、换模型不掉链子）。
全部采集命令为只读；阈值集中在本模块，便于审计与调整。
"""
from __future__ import annotations

from typing import Any, Sequence

from ops_pilot.ssh.client import CommandRunner

# CollectionError 与命令执行统一由 sshcmd 提供（其他工具复用同一套错误协议）
from ops_pilot.tools.sshcmd import CollectionError, run_checked

# ---- 阈值（§A6.2 精神：阈值在工具内，不交给 LLM） ----
CPU_WARN = 80.0
CPU_CRIT = 95.0
LOAD_RATIO_WARN = 1.5      # load1 / cores
MEM_WARN = 85.0
MEM_CRIT = 95.0
DISK_WARN = 85.0
DISK_CRIT = 95.0

LEVEL_OK = "ok"
LEVEL_WARN = "warning"
LEVEL_CRIT = "critical"

# 单条命令超时（秒）
COMMAND_TIMEOUT = 10.0


def _parse_loadavg(text: str) -> list[float]:
    parts = text.split()[0:3]
    return [float(x) for x in parts]


def _parse_cores(text: str) -> int:
    return int(text.strip().splitlines()[0])


def _parse_meminfo(text: str) -> dict[str, float]:
    info: dict[str, float] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            if key in ("MemTotal", "MemAvailable"):
                info[key] = float(rest.strip().split()[0])  # kB
    if "MemTotal" not in info or "MemAvailable" not in info:
        raise CollectionError("command", "/proc/meminfo 缺少 MemTotal/MemAvailable")
    return info


def _parse_df_root(text: str) -> float:
    """`df -P /` → 根分区 Use%（取最后一行的倒数第二列）。"""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise CollectionError("command", "df 输出异常")
    cols = lines[-1].split()
    if len(cols) < 5:
        raise CollectionError("command", "df 输出列数异常")
    return float(cols[-2].rstrip("%"))


def _parse_ps(text: str) -> list[dict[str, Any]]:
    """`ps -eo pid,comm,%cpu --sort=-%cpu` → 前 N 行（去掉表头）。"""
    rows: list[dict[str, Any]] = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append({"pid": int(parts[0]), "name": parts[1], "cpu": float(parts[2])})
    return rows


def _parse_os_release(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def _parse_proc_stat_pair(text: str) -> float:
    """同一命令内两次采样 /proc/stat，计算 CPU 总使用率（%）。

    采集命令：cat /proc/stat; sleep 0.5; cat /proc/stat
    """
    samples: list[list[float]] = []
    for line in text.splitlines():
        if line.startswith("cpu "):
            fields = [float(x) for x in line.split()[1:]]
            samples.append(fields)
            if len(samples) == 2:
                break
    if len(samples) < 2:
        raise CollectionError("command", "/proc/stat 采样不足")
    first, last = samples[0], samples[1]
    idle_delta = (last[3] + (last[4] if len(last) > 4 else 0.0)) - (
        first[3] + (first[4] if len(first) > 4 else 0.0)
    )
    total_delta = sum(b - a for a, b in zip(first, last))
    if total_delta <= 0:
        raise CollectionError("command", "/proc/stat 采样间隔无效")
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)


def _status(percent: float, warn: float, crit: float) -> str:
    if percent >= crit:
        return LEVEL_CRIT
    if percent >= warn:
        return LEVEL_WARN
    return LEVEL_OK


_CPU_STAT_CMD = "cat /proc/stat; sleep 0.5; cat /proc/stat"


def collect_health(
    runner: CommandRunner,
    *,
    server_id: str,
    key_services: Sequence[str] = (),
    timeout: float = COMMAND_TIMEOUT,
) -> dict[str, Any]:
    """采集目标主机健康快照（全部只读命令）。失败抛 CollectionError。"""
    load_avg = _parse_loadavg(run_checked(runner, "cat /proc/loadavg", timeout))
    cores = _parse_cores(run_checked(runner, "nproc", timeout))
    cpu_percent = _parse_proc_stat_pair(run_checked(runner, _CPU_STAT_CMD, timeout + 2.0))

    mem = _parse_meminfo(run_checked(runner, "cat /proc/meminfo", timeout))
    mem_total_gb = round(mem["MemTotal"] / 1024 / 1024, 2)
    mem_used_gb = round((mem["MemTotal"] - mem["MemAvailable"]) / 1024 / 1024, 2)
    mem_percent = round(mem_used_gb / mem_total_gb * 100, 1)

    disk_percent = _parse_df_root(run_checked(runner, "df -P /", timeout))
    top_process = _parse_ps(run_checked(runner, "ps -eo pid,comm,%cpu --sort=-%cpu | head -6", timeout))[:5]
    os_name = _parse_os_release(run_checked(runner, "cat /etc/os-release", timeout))

    services: dict[str, str] = {}
    for name in key_services:
        code, out, _err = runner.run(f"systemctl is-active {name}", timeout)
        value = (out or "").strip()
        services[name] = value or "unknown"   # 空输出=命令本身失败，如实标记

    snapshot: dict[str, Any] = {
        "server_id": server_id,
        "cpu": {
            "percent": cpu_percent,
            "load_avg": load_avg,
            "cores": cores,
            "status": _status(cpu_percent, CPU_WARN, CPU_CRIT),
        },
        "memory": {
            "percent": mem_percent,
            "used_gb": mem_used_gb,
            "total_gb": mem_total_gb,
            "status": _status(mem_percent, MEM_WARN, MEM_CRIT),
        },
        "disk": {
            "used_percent": disk_percent,
            "status": _status(disk_percent, DISK_WARN, DISK_CRIT),
        },
        "top_process": top_process,
        "os": {"name": os_name},
        "services": services,
    }
    snapshot["anomalies"] = analyze_anomalies(snapshot)
    return snapshot


def analyze_anomalies(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """异常判断（在 Executor 内完成，不交给 LLM）。返回 [{item, level, hint}]。"""
    anomalies: list[dict[str, str]] = []
    cpu = snapshot["cpu"]
    mem = snapshot["memory"]
    disk = snapshot["disk"]

    if cpu["percent"] >= CPU_CRIT:
        anomalies.append({"item": "cpu", "level": LEVEL_CRIT, "hint": f"CPU 使用率 {cpu['percent']}% ≥ {CPU_CRIT}%"})
    elif cpu["percent"] >= CPU_WARN:
        anomalies.append({"item": "cpu", "level": LEVEL_WARN, "hint": f"CPU 使用率 {cpu['percent']}% ≥ {CPU_WARN}%"})

    if cpu["cores"]:
        ratio = round(cpu["load_avg"][0] / cpu["cores"], 2)
        if ratio >= LOAD_RATIO_WARN:
            anomalies.append({"item": "load", "level": LEVEL_WARN, "hint": f"load/cores = {ratio} ≥ {LOAD_RATIO_WARN}"})

    if mem["percent"] >= MEM_CRIT:
        anomalies.append({"item": "memory", "level": LEVEL_CRIT, "hint": f"内存使用率 {mem['percent']}% ≥ {MEM_CRIT}%"})
    elif mem["percent"] >= MEM_WARN:
        anomalies.append({"item": "memory", "level": LEVEL_WARN, "hint": f"内存使用率 {mem['percent']}% ≥ {MEM_WARN}%"})

    if disk["used_percent"] >= DISK_CRIT:
        anomalies.append({"item": "disk", "level": LEVEL_CRIT, "hint": f"磁盘使用率 {disk['used_percent']}% ≥ {DISK_CRIT}%"})
    elif disk["used_percent"] >= DISK_WARN:
        anomalies.append({"item": "disk", "level": LEVEL_WARN, "hint": f"磁盘使用率 {disk['used_percent']}% ≥ {DISK_WARN}%"})

    for name, state in snapshot.get("services", {}).items():
        if state in ("inactive", "failed", "unknown"):
            level = LEVEL_CRIT if state == "failed" else LEVEL_WARN
            anomalies.append({"item": f"service:{name}", "level": level, "hint": f"服务状态 {state}"})

    return anomalies
