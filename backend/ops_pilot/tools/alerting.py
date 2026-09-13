"""告警与监控接入（Prometheus + Alertmanager）。

设计原则：
1. **真实接入**：走真实的 HTTP API（httpx），不返回任何编造的告警或指标值。
2. **配置外置**：地址与认证全部来自环境变量（.env），不写死在代码里。
   未配置时返回 NOT_IMPLEMENTED 并说明缺什么，绝不假装"查过了但没有告警"。
3. **结论化输出**：返回结构化 Diagnosis（层次/错误码/证据/修复步骤/影响范围）。

需要的环境变量（写入 OpsPilot/.env）：
    ALERTMANAGER_URL=http://<host>:9093
    PROMETHEUS_URL=http://<host>:9090
    ALERTING_AUTH_TOKEN=<Bearer token>          # 可选
    ALERTING_BASIC_USER / ALERTING_BASIC_PASS   # 可选（Basic Auth）
    ALERTING_VERIFY_TLS=true                    # 可选，默认 true
"""
from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from openhands.sdk.tool import (
    Action, Observation, ToolAnnotations, ToolDefinition, ToolExecutor, register_tool,
)
from pydantic import Field

from ops_pilot.diagnostics.codes import (
    ALERT_FIRING, ALERTMANAGER_UNREACHABLE, PROMETHEUS_UNREACHABLE, PROMQL_INVALID,
)
from ops_pilot.diagnostics.conclusion import Diagnosis, fail, not_implemented, ok

DEFAULT_TIMEOUT = 10.0

# 用于判断"影响范围"的常见标签（不同团队命名不同，按顺序尝试）
_SERVICE_KEYS = ("service", "app", "job", "application", "app_kubernetes_io_name")
_NS_KEYS = ("namespace", "kubernetes_namespace", "ns")
_INSTANCE_KEYS = ("instance", "pod", "node", "host")


# ---------------------------------------------------------------- 配置与请求
def _cfg(name: str, default: str = "") -> str:
    from ops_pilot.server.settings import load_env
    load_env()
    return (os.environ.get(name) or default).strip()


def _client_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {"timeout": DEFAULT_TIMEOUT}
    token = _cfg("ALERTING_AUTH_TOKEN")
    user, pwd = _cfg("ALERTING_BASIC_USER"), _cfg("ALERTING_BASIC_PASS")
    headers: dict[str, str] = {}
    auth = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if user and pwd:
        auth = (user, pwd)
    verify = _cfg("ALERTING_VERIFY_TLS", "true").lower() not in ("false", "0", "no")
    return {**kwargs, "headers": headers, "auth": auth, "verify": verify}


def _get_json(base: str, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any, str]:
    """真实 HTTP GET。返回 (status, json_or_None, error_text)。"""
    import httpx
    url = base.rstrip("/") + path
    try:
        with httpx.Client(**_client_kwargs()) as cli:
            resp = cli.get(url, params=params or {})
        try:
            payload = resp.json()
        except Exception:
            payload = None
        return resp.status_code, payload, ("" if resp.is_success else resp.text[:300])
    except Exception as exc:  # 连接失败/超时/DNS 等
        return 0, None, f"{type(exc).__name__}: {str(exc)[:200]}"


def _first_label(labels: dict[str, Any], keys: Sequence[str]) -> str:
    for k in keys:
        v = labels.get(k)
        if v:
            return str(v)
    return ""


# ---------------------------------------------------------------- 影响范围
def _assess_impact(alert: dict[str, Any], all_alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """基于真实数据判断影响范围。

    - 有 Prometheus 就查该服务的实例总数与异常数，给出真实占比
    - 没有 Prometheus 就只统计告警维度，并明确标注"未接入指标，无法量化"
    """
    labels = alert.get("labels") or {}
    service = _first_label(labels, _SERVICE_KEYS)
    namespace = _first_label(labels, _NS_KEYS)
    instance = _first_label(labels, _INSTANCE_KEYS)
    severity = str(labels.get("severity") or "unknown")

    same_service = [
        a for a in all_alerts
        if service and _first_label(a.get("labels") or {}, _SERVICE_KEYS) == service
    ]

    impact: dict[str, Any] = {
        "service": service or "(无 service 标签)",
        "namespace": namespace or "(无)",
        "instance": instance or "(无)",
        "severity": severity,
        "related_alert_count": len(same_service),
        "related_alert_names": sorted({str((a.get("labels") or {}).get("alertname", "")) for a in same_service})[:10],
    }

    prom = _cfg("PROMETHEUS_URL")
    if not prom or not service:
        impact["quantified"] = False
        impact["note"] = "未配置 PROMETHEUS_URL 或告警缺少 service 标签，无法量化受影响实例比例"
        return impact

    # 真实查询：该服务实例总数 与 当前不可用数
    total_q = f'count(up{{service="{service}"}})'
    down_q = f'count(up{{service="{service}"}} == 0)'
    st1, total_v, _ = _query_prom(prom, total_q)
    st2, down_v, _ = _query_prom(prom, down_q)
    if st1 and total_v is not None:
        impact["instances_total"] = total_v
    if st2 and down_v is not None:
        impact["instances_down"] = down_v
    if st1 and st2 and total_v:
        impact["quantified"] = True
        impact["impact_ratio"] = f"{down_v}/{total_v}"
        impact["impact_text"] = (
            f"服务 {service}：{down_v}/{total_v} 个实例异常"
            + (f"；命名空间 {namespace}" if namespace else "")
        )
    else:
        impact["quantified"] = False
        impact["note"] = "Prometheus 查询未返回可用数据，影响范围未能量化"
    return impact


def _query_prom(base: str, promql: str) -> tuple[int, float | None, str]:
    """执行 PromQL，返回 (是否成功, 数值, 错误信息)。"""
    status, payload, err = _get_json(base, "/api/v1/query", {"query": promql})
    if not status:
        return 0, None, err
    if status != 200:
        return 0, None, err or f"HTTP {status}"
    try:
        results = (payload or {}).get("data", {}).get("result", [])
        if not results:
            return 1, None, "无数据"
        value = results[0].get("value")  # [timestamp, "value"]
        return 1, float(value[1]), ""
    except Exception as exc:
        return 0, None, f"解析失败: {type(exc).__name__}: {str(exc)[:150]}"


# ---------------------------------------------------------------- 工具 1：查告警
class ListAlertsAction(Action):
    severity: str = Field(default="", description="按级别过滤，如 critical / warning；留空表示全部")
    service: str = Field(default="", description="按服务名过滤（匹配 service/app/job 标签）；留空表示全部")
    limit: int = Field(default=50, description="最多返回多少条告警")


class ListAlertsObservation(Observation):
    diagnosis: dict[str, Any]
    alerts: list[dict[str, Any]]
    count: int


class ListAlertsExecutor(ToolExecutor[ListAlertsAction, ListAlertsObservation]):
    def __call__(self, action: ListAlertsAction, conversation: Any = None) -> ListAlertsObservation:
        base = _cfg("ALERTMANAGER_URL")
        if not base:
            d = not_implemented("查询告警", reason="未配置 ALERTMANAGER_URL")
            return ListAlertsObservation(diagnosis=d.to_dict(), alerts=[], count=0)

        params: dict[str, Any] = {"active": "true", "silenced": "false", "inhibited": "false"}
        filters = []
        if action.severity:
            filters.append(f'severity="{action.severity}"')
        if action.service:
            filters.append(f'service="{action.service}"')
        if filters:
            params["filter"] = " and ".join(filters) if len(filters) > 1 else filters[0]
        # Alertmanager filter 语法不支持 service= 之外的自定义键，这里改用客户端过滤兜底

        status, payload, err = _get_json(base, "/api/v2/alerts", params)
        if not status:
            d = fail(ALERTMANAGER_UNREACHABLE, evidence=[{"url": base, "error": err}],
                     impact="无法获取当前告警，告警响应能力不可用")
            return ListAlertsObservation(diagnosis=d.to_dict(), alerts=[], count=0)
        if status != 200:
            d = fail(ALERTMANAGER_UNREACHABLE, summary=f"Alertmanager 返回 HTTP {status}",
                     evidence=[{"url": base, "status": status, "body": err}])
            return ListAlertsObservation(diagnosis=d.to_dict(), alerts=[], count=0)

        raw = payload if isinstance(payload, list) else []
        # 客户端兜底过滤（服务端 filter 对自定义标签不一定生效）
        items = []
        for a in raw:
            labels = a.get("labels") or {}
            if action.severity and str(labels.get("severity", "")).lower() != action.severity.lower():
                continue
            if action.service and _first_label(labels, _SERVICE_KEYS) != action.service:
                continue
            items.append({
                "alertname": labels.get("alertname"),
                "severity": labels.get("severity"),
                "service": _first_label(labels, _SERVICE_KEYS),
                "namespace": _first_label(labels, _NS_KEYS),
                "instance": _first_label(labels, _INSTANCE_KEYS),
                "state": (a.get("status") or {}).get("state"),
                "starts_at": a.get("startsAt"),
                "summary": (a.get("annotations") or {}).get("summary", ""),
                "description": (a.get("annotations") or {}).get("description", ""),
                "fingerprint": a.get("fingerprint"),
            })

        items = items[: max(1, action.limit)]
        if not items:
            d = ok("alerting", "当前没有符合条件的活跃告警",
                   evidence=[{"source": base, "active_alerts_total": len(raw)}])
        else:
            d = fail(ALERT_FIRING, summary=f"存在 {len(items)} 条活跃告警",
                     evidence=[{"source": base, "active_alerts_total": len(raw), "sample": items[:3]}],
                     impact=f"涉及服务：{', '.join(sorted({i['service'] for i in items if i['service']})) or '(未知)'}",
                     extra_fix_steps=(
                         "优先处理 severity=critical 的告警",
                         "用 inspect_alert 逐条定位触发原因与影响范围",
                     ))
        return ListAlertsObservation(diagnosis=d.to_dict(), alerts=items, count=len(items))


class ListAlertsTool(ToolDefinition[ListAlertsAction, ListAlertsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ListAlertsTool]:
        return [cls(
            action_type=ListAlertsAction,
            observation_type=ListAlertsObservation,
            description=(
                "查询当前正在触发的告警（Alertmanager 真实接口）。"
                "返回告警名称、级别、服务、实例与摘要；未配置告警地址时会明确说明未实现，不编造结果。"
            ),
            annotations=ToolAnnotations(title="list_alerts", readOnlyHint=True),
            executor=ListAlertsExecutor(),
        )]


# ---------------------------------------------------------------- 工具 2：定位单条告警
class InspectAlertAction(Action):
    alert_name: str = Field(default="", description="告警名称（alertname）；与 fingerprint 二选一")
    fingerprint: str = Field(default="", description="告警指纹；与 alert_name 二选一")
    promql: str = Field(
        default="",
        description="可选的补充排查 PromQL（如 up、node_memory_MemAvailable_bytes）；留空则用告警标签自动推断",
    )


class InspectAlertObservation(Observation):
    diagnosis: dict[str, Any]
    alert: dict[str, Any]
    impact: dict[str, Any]
    metrics: list[dict[str, Any]]


class InspectAlertExecutor(ToolExecutor[InspectAlertAction, InspectAlertObservation]):
    def __call__(self, action: InspectAlertAction, conversation: Any = None) -> InspectAlertObservation:
        base = _cfg("ALERTMANAGER_URL")
        if not base:
            d = not_implemented("定位告警", reason="未配置 ALERTMANAGER_URL")
            return InspectAlertObservation(diagnosis=d.to_dict(), alert={}, impact={}, metrics=[])

        status, payload, err = _get_json(base, "/api/v2/alerts", {"active": "true"})
        if not status or status != 200:
            d = fail(ALERTMANAGER_UNREACHABLE, evidence=[{"url": base, "error": err or f"HTTP {status}"}])
            return InspectAlertObservation(diagnosis=d.to_dict(), alert={}, impact={}, metrics=[])

        raw = payload if isinstance(payload, list) else []
        target = None
        for a in raw:
            labels = a.get("labels") or {}
            if action.fingerprint and a.get("fingerprint") == action.fingerprint:
                target = a
                break
            if action.alert_name and labels.get("alertname") == action.alert_name:
                target = a
                break

        if target is None:
            d = ok("alerting",
                   f"未找到匹配的活跃告警（alertname={action.alert_name or '-'}, "
                   f"fingerprint={action.fingerprint or '-'}）",
                   evidence=[{"active_alerts": [str((x.get('labels') or {}).get('alertname')) for x in raw][:20]}])
            return InspectAlertObservation(diagnosis=d.to_dict(), alert={}, impact={}, metrics=[])

        labels = target.get("labels") or {}
        annotations = target.get("annotations") or {}
        alert_view = {
            "alertname": labels.get("alertname"),
            "severity": labels.get("severity"),
            "labels": labels,
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
            "starts_at": target.get("startsAt"),
            "generator_url": target.get("generatorURL"),
        }
        impact = _assess_impact(target, raw)

        # 查关联指标：优先用传入的 PromQL，否则按告警标签自动推断
        metrics: list[dict[str, Any]] = []
        prom = _cfg("PROMETHEUS_URL")
        queries: list[str] = []
        if action.promql:
            queries.append(action.promql)
        else:
            svc = _first_label(labels, _SERVICE_KEYS)
            inst = _first_label(labels, _INSTANCE_KEYS)
            if svc:
                queries.append(f'up{{service="{svc}"}}')
            if inst:
                queries.append(f'up{{instance="{inst}"}}')
        if prom and queries:
            for q in queries[:3]:
                okq, val, qerr = _query_prom(prom, q)
                metrics.append({"query": q, "ok": bool(okq), "value": val, "error": qerr or None})
        elif not prom:
            metrics.append({"query": "(未配置 PROMETHEUS_URL)", "ok": False,
                            "value": None, "error": "无法查询关联指标，影响范围无法量化"})

        d = fail(ALERT_FIRING,
                 summary=f"告警 {labels.get('alertname')} 正在触发：{annotations.get('summary', '(无摘要)')}",
                 evidence=[{"alert": alert_view}, {"metrics": metrics}],
                 impact=impact.get("impact_text") or f"服务 {impact.get('service')}，同服务告警 {impact.get('related_alert_count')} 条",
                 extra_fix_steps=(
                     "结合 description 与关联指标判断触发原因（是资源问题、依赖问题还是变更引入）",
                     "确认影响范围后再决定处理方式，必要时先止血再根治",
                 ))
        return InspectAlertObservation(diagnosis=d.to_dict(), alert=alert_view,
                                       impact=impact, metrics=metrics)


class InspectAlertTool(ToolDefinition[InspectAlertAction, InspectAlertObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[InspectAlertTool]:
        return [cls(
            action_type=InspectAlertAction,
            observation_type=InspectAlertObservation,
            description=(
                "定位单条告警：读取详情、查询关联指标、判断触发原因与影响范围。"
                "所有数值来自真实 Prometheus 查询，查不到就明确说明。"
            ),
            annotations=ToolAnnotations(title="inspect_alert", readOnlyHint=True),
            executor=InspectAlertExecutor(),
        )]


# ---------------------------------------------------------------- 工具 3：查指标
class QueryMetricsAction(Action):
    promql: str = Field(description="PromQL 查询语句，如 up{service=\"api\"}")
    note: str = Field(default="", description="这次查询想回答什么问题（便于归档）")


class QueryMetricsObservation(Observation):
    diagnosis: dict[str, Any]
    query: str
    value: float | None
    series: list[dict[str, Any]]


class QueryMetricsExecutor(ToolExecutor[QueryMetricsAction, QueryMetricsObservation]):
    def __call__(self, action: QueryMetricsAction, conversation: Any = None) -> QueryMetricsObservation:
        prom = _cfg("PROMETHEUS_URL")
        if not prom:
            d = not_implemented("查询指标", reason="未配置 PROMETHEUS_URL")
            return QueryMetricsObservation(diagnosis=d.to_dict(), query=action.promql,
                                           value=None, series=[])
        status, payload, err = _get_json(prom, "/api/v1/query", {"query": action.promql})
        if not status:
            d = fail(PROMETHEUS_UNREACHABLE, evidence=[{"url": prom, "error": err}])
            return QueryMetricsObservation(diagnosis=d.to_dict(), query=action.promql,
                                           value=None, series=[])
        if status != 200:
            d = fail(PROMQL_INVALID, summary=f"Prometheus 返回 HTTP {status}",
                     evidence=[{"query": action.promql, "body": err}])
            return QueryMetricsObservation(diagnosis=d.to_dict(), query=action.promql,
                                           value=None, series=[])
        try:
            result = (payload or {}).get("data", {}).get("result", [])
        except Exception:
            result = []
        series = [{"metric": r.get("metric"), "value": (r.get("value") or [None, None])[1]} for r in result[:20]]
        value = None
        if series and series[0]["value"] is not None:
            try:
                value = float(series[0]["value"])
            except Exception:
                value = None
        d = ok("alerting",
               f"PromQL 返回 {len(series)} 条序列" + (f"（首值 {value}）" if value is not None else "（无数值）"),
               evidence=[{"query": action.promql, "series_count": len(series), "sample": series[:3]}])
        return QueryMetricsObservation(diagnosis=d.to_dict(), query=action.promql,
                                       value=value, series=series)


class QueryMetricsTool(ToolDefinition[QueryMetricsAction, QueryMetricsObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[QueryMetricsTool]:
        return [cls(
            action_type=QueryMetricsAction,
            observation_type=QueryMetricsObservation,
            description="执行 PromQL 查询真实指标（用于验证告警是否仍在、判断趋势、量化影响）。",
            annotations=ToolAnnotations(title="query_metrics", readOnlyHint=True),
            executor=QueryMetricsExecutor(),
        )]


register_tool(ListAlertsTool.name, ListAlertsTool)
register_tool(InspectAlertTool.name, InspectAlertTool)
register_tool(QueryMetricsTool.name, QueryMetricsTool)
