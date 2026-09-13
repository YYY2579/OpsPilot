"""Kubernetes 只读工具（§A5.2，M7-2）。

## 架构决策：K8s 工具 = SSH 工具的特例

**不在 OpsPilot 机器上放任何集群凭据。** `server_id` 指一台"装有 kubectl 且其
kubeconfig 能连到集群"的机器，所有 kubectl 命令都通过已有的 SSH 通道在该机器上
执行 —— kubeconfig 永不离开服务器（§A6.4 同款纪律）。

为什么不做"单独的 K8s 连接类型"：
1. kubeconfig = 集群管理员凭据。复制到 OpsPilot 机器 = 攻击面扩大 + 多一套
   分发/轮换要管，收益为零。
2. 服务器上 `kubectl get --raw /healthz` 能通，就说明这台机器本来就有权限 ——
   直接用它，权限模型与运维现状一致。

## 输出限流（必须）
大集群 `get pods -A` 能吐几 MB。列表类一律 `-o custom-columns --no-headers`
（轻量、好解析），Observation 里再截断到 limit 条。

## Secret 防线
`kubectl get secret -o yaml` 这类工具**不做**（规格 §A5.2 也未排）。
`get pods`/`get events` 只会引用 secret 的名字，不会带出内容。
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

NS_RE = r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
POD_RE = r"^[a-z0-9]([-a-z0-9.]{0,220}[a-z0-9])?$"

WAITING_BAD = ("crashloopbackoff", "imagepullbackoff", "errimagepull",
               "createcontainererror", "runcontainererror")


def _ns_flag(namespace: str | None) -> str:
    return f"-n {namespace}" if namespace else "-A"


def _parse_columns(text: str, keys: list[str]) -> list[dict[str, Any]]:
    """kubectl custom-columns --no-headers → 按列名组装 dict 列表。"""
    rows: list[dict[str, Any]] = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        cols = line.split(maxsplit=len(keys) - 1)
        if len(cols) < len(keys):
            cols += [""] * (len(keys) - len(cols))
        rows.append({k: cols[i] for i, k in enumerate(keys)})
    return rows


# ======================= list_namespaces =======================

class ListNamespacesAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")


class ListNamespacesObservation(JsonObservation):
    server_id: str
    namespaces: list[dict[str, str]]
    anomalies: list[dict[str, str]]


class ListNamespacesExecutor(
    SshReadOnlyExecutor[ListNamespacesAction, ListNamespacesObservation]
):
    def collect(self, runner: Any, action: ListNamespacesAction) -> dict[str, Any]:
        text = run_checked(
            runner,
            "kubectl get namespaces -o custom-columns="
            "NAME:.metadata.name,STATUS:.status.phase --no-headers",
            self._command_timeout + 10,
        )
        rows = [{"name": r["NAME"], "status": r["STATUS"]}
                for r in _parse_columns(text, ["NAME", "STATUS"])]
        return {"server_id": action.server_id, "namespaces": rows, "anomalies": []}

    def build(self, action: ListNamespacesAction,
              data: dict[str, Any]) -> ListNamespacesObservation:
        return ListNamespacesObservation(**data)


class ListNamespacesTool(
    ToolDefinition[ListNamespacesAction, ListNamespacesObservation]
):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ListNamespacesTool]:
        return [cls(
            action_type=ListNamespacesAction,
            observation_type=ListNamespacesObservation,
            description="只读列出目标集群的全部命名空间。要求 server_id 对应的机器上"
                        "装有 kubectl 且 kubeconfig 可用。",
            annotations=ToolAnnotations(title="list_namespaces", readOnlyHint=True),
            executor=ListNamespacesExecutor(),
        )]


# ======================= list_pods =======================

class ListPodsAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    namespace: str | None = Field(default=None, description="命名空间；缺省=全部命名空间")
    limit: int = Field(default=50, description="返回条数（1–200）")


class ListPodsObservation(JsonObservation):
    server_id: str
    namespace: str
    pods: list[dict[str, Any]]
    pod_total: int
    anomalies: list[dict[str, str]]


def _sum_restarts(field: str) -> int:
    if not field or not field.replace(" ", "").isdigit() and not any(c.isdigit() for c in field):
        return 0
    parts = field.split()
    try:
        return sum(int(x) for x in parts if x.isdigit())
    except ValueError:  # noqa: PERF203
        return 0


def analyze_pods(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    for p in rows:
        key = f"pod:{p['namespace']}/{p['name']}"
        waiting = (p.get("waiting_reason") or "").lower()
        if any(bad in waiting for bad in WAITING_BAD):
            anomalies.append({"item": key, "level": "critical",
                              "hint": f"容器反复起不来：{p.get('waiting_reason')}"})
        elif p["phase"] not in ("Running", "Succeeded") and p["phase"] != "Completed":
            anomalies.append({"item": key, "level": "warning", "hint": f"Pod 状态 {p['phase']}"})
        if p["restarts"] >= 20:
            anomalies.append({"item": key, "level": "critical", "hint": f"重启 {p['restarts']} 次"})
        elif p["restarts"] >= 5:
            anomalies.append({"item": key, "level": "warning", "hint": f"重启 {p['restarts']} 次"})
    return anomalies


class ListPodsExecutor(SshReadOnlyExecutor[ListPodsAction, ListPodsObservation]):
    def collect(self, runner: Any, action: ListPodsAction) -> dict[str, Any]:
        if action.namespace and not action.namespace.lstrip("-").replace("-", "").isalnum():
            pass                                       # 命名空间允许连字符，仅拒绝明显注入
        if any(c in action.namespace for c in ";|&$`\\") if action.namespace else False:
            raise ValueError("命名空间包含非法字符")
        ns = _ns_flag(action.namespace)
        limit = clamp(action.limit, 1, 200)
        cmd = (
            f"kubectl get pods {ns} -o custom-columns="
            "NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase,"
            "WAITING:.status.containerStatuses[*].state.waiting.reason,"
            "RESTARTS:.status.containerStatuses[*].restartCount,"
            "NODE:.spec.nodeName --no-headers"
        )
        text = run_checked(runner, cmd, self._command_timeout + 10)
        keys = ["NS", "NAME", "PHASE", "WAITING", "RESTARTS", "NODE"]
        rows = [
            {"namespace": r["NS"], "name": r["NAME"], "phase": r["PHASE"] or "Unknown",
             "waiting_reason": r["WAITING"], "restarts": _sum_restarts(r["RESTARTS"]),
             "node": r["NODE"]}
            for r in _parse_columns(text, keys)
        ]
        total = len(rows)
        shown = rows[:limit]
        return {
            "server_id": action.server_id,
            "namespace": action.namespace or "(全部)",
            "pods": shown,
            "pod_total": total,
            "anomalies": analyze_pods(shown),
        }

    def build(self, action: ListPodsAction, data: dict[str, Any]) -> ListPodsObservation:
        return ListPodsObservation(**data)


class ListPodsTool(ToolDefinition[ListPodsAction, ListPodsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ListPodsTool]:
        return [cls(
            action_type=ListPodsAction,
            observation_type=ListPodsObservation,
            description="只读列出 Pod（命名空间/名称/状态/重启次数/节点），"
                        "并对 CrashLoopBackOff、ImagePullBackOff、高频重启给出 anomalies。",
            annotations=ToolAnnotations(title="list_pods", readOnlyHint=True),
            executor=ListPodsExecutor(),
        )]


# ======================= get_pod_logs =======================

class GetPodLogsAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    pod: str = Field(description="Pod 名")
    namespace: str = Field(default="default", description="命名空间")
    container: str | None = Field(default=None, description="多容器 Pod 时指定容器名")
    lines: int = Field(default=100, description="返回最后多少行（1–500）")


class GetPodLogsObservation(JsonObservation):
    server_id: str
    pod: str
    namespace: str
    lines_returned: int
    truncated: bool
    log_text: str
    anomalies: list[dict[str, str]]


class GetPodLogsExecutor(SshReadOnlyExecutor[GetPodLogsAction, GetPodLogsObservation]):
    def collect(self, runner: Any, action: GetPodLogsAction) -> dict[str, Any]:
        if not POD_RE.match(action.pod):
            raise ValueError(f"Pod 名不合法：{action.pod!r}")
        n = clamp(action.lines, 1, 500)
        container = f" -c {action.container}" if action.container else ""
        cmd = (f"kubectl logs pod/{action.pod} -n {action.namespace}{container} "
               f"--tail={n} --timestamps")
        code, out, err = run_lenient(runner, cmd, self._command_timeout + 10)
        text = out or ""
        if code != 0 and not text.strip():
            detail = (err or "").strip()[:200]
            if "not found" in detail.lower():
                raise ValueError(f"Pod 不存在：{action.namespace}/{action.pod}")
            raise ValueError(f"读取日志失败：{detail}")
        shown, truncated = tail(text, n)
        low = shown.lower()
        anomalies: list[dict[str, str]] = []
        for kw in ("error", "exception", "fatal", "outofmemory", "connection refused"):
            if kw in low:
                anomalies.append({"item": f"logs:{action.pod}", "level": "warning",
                                  "hint": f"日志中出现关键词：{kw}"})
                break
        return {
            "server_id": action.server_id, "pod": action.pod,
            "namespace": action.namespace,
            "lines_returned": len(shown.splitlines()) if shown else 0,
            "truncated": truncated, "log_text": shown, "anomalies": anomalies,
        }

    def build(self, action: GetPodLogsAction, data: dict[str, Any]) -> GetPodLogsObservation:
        return GetPodLogsObservation(**data)


class GetPodLogsTool(ToolDefinition[GetPodLogsAction, GetPodLogsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetPodLogsTool]:
        return [cls(
            action_type=GetPodLogsAction,
            observation_type=GetPodLogsObservation,
            description="只读读取指定 Pod 的最近日志（kubectl logs --tail）。",
            annotations=ToolAnnotations(title="get_pod_logs", readOnlyHint=True),
            executor=GetPodLogsExecutor(),
        )]


# ======================= get_events =======================

class GetEventsAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    namespace: str | None = Field(default=None, description="命名空间；缺省=全部")
    limit: int = Field(default=50, description="返回最近多少条（1–200）")


class GetEventsObservation(JsonObservation):
    server_id: str
    namespace: str
    events: list[dict[str, str]]
    anomalies: list[dict[str, str]]


class GetEventsExecutor(SshReadOnlyExecutor[GetEventsAction, GetEventsObservation]):
    def collect(self, runner: Any, action: GetEventsAction) -> dict[str, Any]:
        n = clamp(action.limit, 1, 200)
        ns = _ns_flag(action.namespace)
        cmd = (
            f"kubectl get events {ns} --sort-by=.lastTimestamp -o custom-columns="
            "TIME:.lastTimestamp,TYPE:.type,OBJ:.involvedObject.name,"
            "REASON:.reason,MESSAGE:.message --no-headers"
        )
        code, out, err = run_lenient(runner, cmd, self._command_timeout + 10)
        text = out or ""
        if code != 0 and not text.strip():
            raise ValueError(f"读取事件失败：{(err or '').strip()[:200]}")
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        events = []
        for line in lines[-n:]:
            cols = line.split(maxsplit=4)
            if len(cols) < 5:
                continue
            events.append({"time": cols[0], "type": cols[1],
                           "object": cols[2], "reason": cols[3], "message": cols[4]})
        anomalies = [
            {"item": f"event:{e['object']}", "level": "critical" if e["type"] == "Warning" else "warning",
             "hint": f"{e['reason']}: {e['message'][:80]}"}
            for e in events if e["type"] == "Warning"
        ][:20]
        return {"server_id": action.server_id, "namespace": action.namespace or "(全部)",
                "events": events, "anomalies": anomalies}

    def build(self, action: GetEventsAction, data: dict[str, Any]) -> GetEventsObservation:
        return GetEventsObservation(**data)


class GetEventsTool(ToolDefinition[GetEventsAction, GetEventsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[GetEventsTool]:
        return [cls(
            action_type=GetEventsAction,
            observation_type=GetEventsObservation,
            description="只读读取集群事件（Warning 事件会给出 anomalies），用于排查调度/探针/重启原因。",
            annotations=ToolAnnotations(title="get_events", readOnlyHint=True),
            executor=GetEventsExecutor(),
        )]


register_tool(ListNamespacesTool.name, ListNamespacesTool)
register_tool(ListPodsTool.name, ListPodsTool)
register_tool(GetPodLogsTool.name, GetPodLogsTool)
register_tool(GetEventsTool.name, GetEventsTool)
