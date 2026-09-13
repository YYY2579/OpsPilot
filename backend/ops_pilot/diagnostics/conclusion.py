"""统一诊断结论结构。

所有工具对外返回 Diagnosis，而不是散装的原始输出。
字段含义：
- ok        是否成功（成功也可能带 warning，见 anomalies）
- layer     故障层次（host/service/container/k8s/database/network/alerting/change）
- code      错误码（ok 时为 "OK"，见 codes.py）
- summary   一句话结论（人话，不是日志原文）
- evidence  证据列表：命令/查询 + 实际返回值，可复核
- fix_steps 有序修复步骤（可执行，不是空话）
- impact    影响范围（影响什么服务/多少实例/用户可见性）
- rollback  回滚方案（写操作必填，只读为 None）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ops_pilot.diagnostics.codes import LAYER_CAPABILITY, CAPABILITY_NOT_IMPLEMENTED, spec_of

OK = "OK"


@dataclass
class Diagnosis:
    ok: bool
    layer: str
    code: str = OK
    summary: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    fix_steps: list[str] = field(default_factory=list)
    impact: str = ""
    rollback: str | None = None
    anomalies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "layer": self.layer,
            "code": self.code,
            "summary": self.summary,
            "evidence": self.evidence,
            "fix_steps": self.fix_steps,
            "impact": self.impact,
            "rollback": self.rollback,
            "anomalies": self.anomalies,
        }


def ok(
    layer: str,
    summary: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
    impact: str = "",
    anomalies: list[dict[str, Any]] | None = None,
) -> Diagnosis:
    """成功结论。"""
    return Diagnosis(
        ok=True, layer=layer, code=OK, summary=summary,
        evidence=evidence or [], fix_steps=[], impact=impact,
        anomalies=anomalies or [],
    )


def fail(
    code: str,
    *,
    summary: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    extra_fix_steps: tuple[str, ...] = (),
    impact: str = "",
    rollback: str | None = None,
    anomalies: list[dict[str, Any]] | None = None,
) -> Diagnosis:
    """失败结论：自动带上该错误码的标准修复步骤。"""
    spec = spec_of(code)
    steps = list(spec.fix_steps) + list(extra_fix_steps)
    return Diagnosis(
        ok=False, layer=spec.layer, code=code,
        summary=summary or spec.summary,
        evidence=evidence or [], fix_steps=steps, impact=impact,
        rollback=rollback, anomalies=anomalies or [],
    )


def not_implemented(capability: str, *, reason: str = "") -> Diagnosis:
    """能力未实现时必须显式返回这个，绝不允许编造结果冒充已实现。"""
    spec = spec_of(CAPABILITY_NOT_IMPLEMENTED)
    return Diagnosis(
        ok=False, layer=LAYER_CAPABILITY, code=CAPABILITY_NOT_IMPLEMENTED,
        summary=f"能力未实现：{capability}" + (f"（{reason}）" if reason else ""),
        evidence=[{"capability": capability, "reason": reason}],
        fix_steps=list(spec.fix_steps),
        impact="该能力不可用，请勿据此结论做决策",
    )


def add_evidence(d: Diagnosis, **kv: Any) -> Diagnosis:
    """追加一条证据（链式用）。"""
    d.evidence.append(kv)
    return d


# ---------- SSH 异常 → 错误码映射 ----------
def map_ssh_error(kind: str, detail: str) -> str:
    """_base.py 抛出的 ValueError(f"SSH {kind}: {detail}") 统一在这里归类。"""
    from ops_pilot.diagnostics.codes import (
        HOST_CMD_FAILED, HOST_PERMISSION_DENIED,
        HOST_SSH_AUTH_FAILED, HOST_SSH_UNREACHABLE,
    )
    k = (kind or "").lower()
    if "auth" in k or "凭据" in k or "credential" in k:
        return HOST_SSH_AUTH_FAILED
    if "connect" in k or "network" in k or "unreach" in k or "timeout" in k:
        return HOST_SSH_UNREACHABLE
    if "permission" in k or "denied" in k:
        return HOST_PERMISSION_DENIED
    return HOST_CMD_FAILED
