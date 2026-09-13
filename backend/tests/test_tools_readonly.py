"""M4 只读工具集测试（对应真实 SDK，FakeRunner 注入命令输出）。

覆盖：解析正确性 + 异常判断 + 失败归因。每工具一条主用例，保持精简。
"""
from __future__ import annotations

import json

import pytest

from ops_pilot.tools import docker as docker_mod
from ops_pilot.tools import network as net_mod
from ops_pilot.tools import system as sys_mod


class FakeRunner:
    """命令（前缀）→ (exit_code, stdout, stderr)。未命中返回 exit 1。"""

    def __init__(self, mapping: dict[str, tuple[int, str, str]]):
        self._m = mapping
        self.calls: list[str] = []

    def run(self, command: str, timeout: float = 10.0):
        self.calls.append(command)
        for key, value in self._m.items():
            if command == key or command.startswith(key):
                return value
        return 1, "", f"command not found: {command}"


def executor(cls):
    """构造 Executor 并注入假 resolver（不走真实 SSH）。"""
    ex = cls.__new__(cls)
    ex._resolver = None
    ex._connect_timeout = 1.0
    ex._command_timeout = 1.0
    return ex


def run_with(cls, action, mapping):
    """替换 collect 的 runner 来源：直接用 FakeRunner 调 collect + build。"""
    ex = executor(cls)
    data = ex.collect(FakeRunner(mapping), action)
    return ex.build(action, data)


# ---------------- get_disk_usage ----------------

DF = """Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1       83886080  75161927   8724153  90% /
/dev/sdb1      209715200  20971520 188743680  10% /data
"""
DFI = """Filesystem     Inodes IUsed IFree IUse% Mounted on
/dev/sda1      5242880 4700000 542880   90% /
"""


def test_disk_usage_parses_and_flags():
    obs = run_with(
        sys_mod.GetDiskUsageExecutor,
        sys_mod.GetDiskUsageAction(server_id="hk-ubuntu"),
        {"df -P -x tmpfs": (0, DF, ""), "df -Pi /": (0, DFI, "")},
    )
    assert len(obs.filesystems) == 2
    assert obs.filesystems[0]["mount"] == "/"        # 按使用率降序
    assert obs.inode_percent == 90.0
    items = {a["item"]: a["level"] for a in obs.anomalies}
    assert items["disk:/"] == "warning"              # 90% 落在 warn 区间
    assert items["inode:/"] == "warning"
    assert "disk:/data" not in items


def test_disk_usage_min_percent_filter():
    obs = run_with(
        sys_mod.GetDiskUsageExecutor,
        sys_mod.GetDiskUsageAction(server_id="hk-ubuntu", min_percent=50),
        {"df -P -x tmpfs": (0, DF, ""), "df -Pi /": (0, DFI, "")},
    )
    assert [fs["mount"] for fs in obs.filesystems] == ["/"]


# ---------------- get_process_list ----------------

PS = """    PID    PPID USER     COMMAND         %CPU %MEM     ELAPSED
 283500  283499 root     ps             100.0  0.1    00:00
 283501  283500 root     head            99.0  0.0    00:00
   2143       1 app      java           182.0 12.5    03:20:11
    882       1 root     containerd       8.6 35.2    10:11:02
   1174       1 root     nginx            4.2  3.1    03:20:10
"""


def test_process_list_parses_and_flags():
    obs = run_with(
        sys_mod.GetProcessListExecutor,
        sys_mod.GetProcessListAction(server_id="hk-ubuntu", limit=2),
        {"ps -eo pid,ppid,user": (0, PS, ""), "ps -e --no-headers": (0, "512\n", "")},
    )
    assert obs.process_total == 512
    # 采样命令自身（ps/head）必须被剔除，不能污染榜首
    assert all(p["name"] not in {"ps", "head"} for p in obs.processes)
    assert obs.processes[0] == {
        "pid": 2143, "ppid": 1, "user": "app", "name": "java",
        "cpu_percent": 182.0, "mem_percent": 12.5, "elapsed": "03:20:11",
    }
    assert len(obs.processes) == 2                     # limit 生效
    items = {a["item"]: a["level"] for a in obs.anomalies}
    assert items["proc:java(2143)"] == "warning"       # 182% 在 warn(80)–crit(200) 之间
    assert items["proc:containerd(882)"] == "warning"  # 内存 35.2% ≥ 30%


# ---------------- get_service_status ----------------

def test_service_status_ok_and_failed():
    mapping = {
        "systemctl is-active nginx;": (3, "active\nenabled\n", ""),
        "systemctl is-active mysql;": (3, "failed\ndisabled\n", ""),
    }
    obs = run_with(
        sys_mod.GetServiceStatusExecutor,
        sys_mod.GetServiceStatusAction(server_id="hk-ubuntu", services=["nginx", "mysql"]),
        mapping,
    )
    assert obs.services["nginx"] == {"active": "active", "enabled": "enabled"}
    assert obs.services["mysql"] == {"active": "failed", "enabled": "disabled"}
    items = {a["item"]: a["level"] for a in obs.anomalies}
    assert items["service:mysql"] == "critical"
    assert "service:nginx" not in items


def test_service_status_empty_list_rejected():
    with pytest.raises(ValueError):
        run_with(
            sys_mod.GetServiceStatusExecutor,
            sys_mod.GetServiceStatusAction(server_id="hk-ubuntu", services=[" "]),
            {},
        )


# ---------------- get_service_logs ----------------

JOURNAL = "\n".join(f"2026-09-13T09:0{i}:00+08:00 host nginx[11]: line {i}" for i in range(6))


def test_service_logs_truncates_and_flags_keywords():
    body = JOURNAL + "\n2026-09-13T09:09:00+08:00 host nginx[11]: upstream timed out"
    obs = run_with(
        sys_mod.GetServiceLogsExecutor,
        sys_mod.GetServiceLogsAction(server_id="hk-ubuntu", service="nginx", lines=3),
        {"journalctl -u nginx": (0, body, "")},
    )
    assert obs.lines_returned == 3
    assert obs.truncated is True
    assert "timed out" in obs.log_text
    assert obs.anomalies and obs.anomalies[0]["level"] == "warning"


def test_service_logs_failure_is_clear():
    with pytest.raises(ValueError) as exc:
        run_with(
            sys_mod.GetServiceLogsExecutor,
            sys_mod.GetServiceLogsAction(server_id="hk-ubuntu", service="nope", lines=5),
            {"journalctl -u nope": (1, "", "No journal files were found.")},
        )
    assert "nope" in str(exc.value)


# ---------------- list_docker_containers ----------------

def _docker_line(name, state, status):
    return json.dumps({"ID": "abc123def4567890", "Names": name, "Image": "img:1",
                       "State": state, "Status": status, "Ports": "80/tcp"})


def test_list_docker_containers_ok():
    out = "\n".join([_docker_line("nginx", "running", "Up 3 hours"),
                     _docker_line("backend", "exited", "Exited (1) 2 hours ago")])
    obs = run_with(
        docker_mod.ListDockerContainersExecutor,
        docker_mod.ListDockerContainersAction(server_id="hk-ubuntu"),
        {"docker ps ": (0, out + "\n", "")},
    )
    assert obs.total == 2 and obs.running == 1
    assert obs.containers[0]["id"] == "abc123def456"
    items = {a["item"]: a["level"] for a in obs.anomalies}
    assert items["container:backend"] == "warning"     # exited
    assert "container:nginx" not in items


def test_list_docker_containers_missing_docker():
    with pytest.raises(ValueError) as exc:
        run_with(
            docker_mod.ListDockerContainersExecutor,
            docker_mod.ListDockerContainersAction(server_id="hk-ubuntu"),
            {"docker ps ": (127, "", "bash: docker: command not found")},
        )
    assert "未安装 docker" in str(exc.value)


# ---------------- get_container_logs ----------------

def test_container_logs_ok_and_truncated():
    out = "\n".join(f"line {i}" for i in range(5))
    obs = run_with(
        docker_mod.GetContainerLogsExecutor,
        docker_mod.GetContainerLogsAction(server_id="hk-ubuntu", container="backend", lines=3),
        {"docker logs --tail 3 backend": (0, out + "\n", "")},
    )
    assert obs.truncated is True
    assert obs.lines_returned == 3
    assert obs.log_text.endswith("line 4")


def test_container_logs_missing_container():
    with pytest.raises(ValueError) as exc:
        run_with(
            docker_mod.GetContainerLogsExecutor,
            docker_mod.GetContainerLogsAction(server_id="hk-ubuntu", container="ghost"),
            {"docker logs --tail 100 ghost": (1, "Error: No such container: ghost\n", "")},
        )
    assert "容器不存在" in str(exc.value)


# ---------------- check_port ----------------

def test_check_port_open_timeout_refused():
    A = net_mod.CheckPortAction
    E = net_mod.CheckPortExecutor
    obs = run_with(E, A(server_id="hk-ubuntu", host="192.168.1.153", port=6443),
                   {"timeout 3 bash -c": (0, "", "")})
    assert obs.reachable is True and obs.result == "open" and obs.anomalies == []

    obs = run_with(E, A(server_id="hk-ubuntu", host="10.0.0.9", port=6443),
                   {"timeout 3 bash -c": (124, "", "")})
    assert obs.result == "timeout" and obs.anomalies[0]["level"] == "warning"

    obs = run_with(E, A(server_id="hk-ubuntu", host="10.0.0.9", port=80),
                   {"timeout 3 bash -c": (1, "", "")})
    assert obs.result == "refused_or_closed" and obs.reachable is False


def test_check_port_requires_bash():
    with pytest.raises(ValueError) as exc:
        run_with(net_mod.CheckPortExecutor,
                 net_mod.CheckPortAction(server_id="hk-ubuntu", host="h", port=1),
                 {"timeout 3 bash -c": (127, "", "bash: command not found")})
    assert "缺少 bash" in str(exc.value)


# ---------------- check_http ----------------

def test_check_http_ok_and_5xx():
    A, E = net_mod.CheckHttpAction, net_mod.CheckHttpExecutor
    obs = run_with(E, A(server_id="hk-ubuntu", url="http://127.0.0.1/health"),
                   {"curl -sS": (0, "200 0.012\n", "")})
    assert obs.ok is True and obs.status_code == 200 and obs.anomalies == []

    obs = run_with(E, A(server_id="hk-ubuntu", url="http://127.0.0.1/health"),
                   {"curl -sS": (0, "503 0.412\n", "")})
    assert obs.ok is False and obs.anomalies[0]["level"] == "critical"


def test_check_http_connection_failure():
    obs = run_with(net_mod.CheckHttpExecutor,
                   net_mod.CheckHttpAction(server_id="hk-ubuntu", url="http://10.0.0.9/"),
                   {"curl -sS": (7, "", "curl: (7) Failed to connect")})
    assert obs.ok is False and obs.status_code is None
    assert "Failed to connect" in obs.anomalies[0]["hint"]


# ---------------- 注册完整性 ----------------

def test_all_readonly_tools_registered():
    from openhands.sdk.tool.registry import list_registered_tools

    import ops_pilot.tools.register_all as reg

    registered = set(list_registered_tools())
    missing = [n for n in reg.READONLY_TOOL_NAMES if n not in registered]
    assert not missing, f"未注册：{missing}"


def test_all_tools_are_read_only():
    import ops_pilot.tools.register_all as reg

    from openhands.sdk.tool import resolve_tool

    class _StubState:      # create(conv_state=...) 里我们的工具不使用 workspace
        pass

    bad = []
    for name in reg.READONLY_TOOL_NAMES:
        tools = resolve_tool(
            __import__("openhands.sdk.tool", fromlist=["Tool"]).Tool(name=name), _StubState()
        )
        for t in tools:
            if not (t.annotations and t.annotations.readOnlyHint):
                bad.append(name)
    assert not bad, f"以下工具未声明 readOnlyHint=True：{bad}"
