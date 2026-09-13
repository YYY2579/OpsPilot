"""把 L0–L5 接到 OpenHands 的确认机制上（§A6.5.1）。

**能力边界（必须知道）**：框架的 `ConfirmationPolicyBase.should_confirm(risk)` 只收到
`SecurityRisk`（UNKNOWN/LOW/MEDIUM/HIGH 四档），拿不到工具名与我们的 L 级。
所以：
- 本策略用 4 档做**近似映射**，只能决定"要不要弹确认"；
- **L5 的硬拦截不在这里**，而在工具层的 `guard.enforce_floor()` —— 框架没有
  "拒绝执行"的表达能力，地板必须在我们的 Executor 里。
"""
from __future__ import annotations

from typing import Any

from openhands.sdk.security.confirmation_policy import ConfirmationPolicyBase
from openhands.sdk.security.risk import SecurityRisk
from pydantic import Field

from ops_pilot.server.permission import TIER_FULL, TIER_REQUESTED
from ops_pilot.security.levels import RiskLevel, decide

#: SecurityRisk → L 级。**有损映射，语义必须对齐 analyzer.LEVEL_TO_RISK**：
#: LOW ← L0/L1（只读，任何档位都自动）、MEDIUM ← L2/L3（写）、HIGH ← L4/L5、
#: UNKNOWN 保守按 L4。若把 LOW 映射成 L2，只读工具会在"请求审批"档下被要求确认，
#: 会话会卡在第一步（本项曾真实踩到）。
_RISK_TO_LEVEL = {
    SecurityRisk.UNKNOWN: RiskLevel.L4,
    SecurityRisk.LOW: RiskLevel.L1,
    SecurityRisk.MEDIUM: RiskLevel.L3,
    SecurityRisk.HIGH: RiskLevel.L4,
}


def risk_to_level(risk: SecurityRisk) -> RiskLevel:
    return _RISK_TO_LEVEL.get(risk, RiskLevel.L4)


class OpsPilotConfirmationPolicy(ConfirmationPolicyBase):
    """按权限档位 + 近似风险等级决定是否弹确认卡。"""

    tier: str = Field(default=TIER_REQUESTED, description="请求审批 / 帮我批准 / 完全访问")

    def should_confirm(self, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        return decide(self.tier, risk_to_level(risk)).needs_human


class AlwaysConfirmForTier(ConfirmationPolicyBase):
    """显式"每条都要确认"（用于最保守场景，例如陌生环境首次操作）。"""

    def should_confirm(self, risk: SecurityRisk = SecurityRisk.UNKNOWN) -> bool:
        return True


class FullAccessPolicy(OpsPilotConfirmationPolicy):
    """完全访问：L0–L4 全自动（HIGH 也不问）。"""

    tier: str = Field(default=TIER_FULL)


def policy_for_tier(tier: str) -> ConfirmationPolicyBase:
    """档位 → 策略实例。完全访问用专用子类，其余用通用策略。"""
    if tier == TIER_FULL:
        return FullAccessPolicy()
    return OpsPilotConfirmationPolicy(tier=tier)


def describe(tier: str, risk: SecurityRisk) -> dict[str, Any]:
    """给前端/审计用的可读说明。"""
    level = risk_to_level(risk)
    decision = decide(tier, level)
    return {
        "tier": tier,
        "security_risk": risk.value if hasattr(risk, "value") else str(risk),
        "level": level.value,
        "action": decision.action,
        "reason": decision.reason,
    }
