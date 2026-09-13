"""OpsPilot 安全分析器：按**工具名**给出框架风险等级（§A6.2 的接缝）。

**为什么必须有它**：《源码索引》§1.4 确认，框架的
`agent._requires_user_confirmation()` 走的是
`state.security_analyzer.analyze_pending_actions(action_events)` —— 这里能拿到
ActionEvent（含 tool_name）。**不装 analyzer 时框架把每个动作的风险都当 UNKNOWN**，
再经我们的策略映射成 L4 → 连只读工具都要人工确认，会话会在第一步就挂住。

## 能力边界（必须知道）
框架的 `SecurityRisk` 只有 4 档（UNKNOWN/LOW/MEDIUM/HIGH），装不下我们的 L0–L5。
所以这里做**有损映射**：

| 我们的 L 级 | 框架 SecurityRisk | 框架层效果（请求审批档） |
|---|---|---|
| L0 / L1（只读） | LOW | 自动执行 |
| L2 / L3（低/中风险写） | MEDIUM | 询问 |
| L4（高风险） | HIGH | 二次确认 |
| L5（不可逆） | HIGH | **框架无法表达"拒绝"** |

**结论：L5 的真正拦截在工具层 `guard.enforce_floor()`，不能依赖框架。**
"""
from __future__ import annotations

from typing import Any

from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.risk import SecurityRisk

from ops_pilot.security.levels import RiskLevel, escalate
from ops_pilot.security.guard import level_of

#: 我们的 L 级 → 框架的 4 档（有损）
LEVEL_TO_RISK: dict[RiskLevel, SecurityRisk] = {
    RiskLevel.L0: SecurityRisk.LOW,
    RiskLevel.L1: SecurityRisk.LOW,
    RiskLevel.L2: SecurityRisk.MEDIUM,
    RiskLevel.L3: SecurityRisk.MEDIUM,
    RiskLevel.L4: SecurityRisk.HIGH,
    RiskLevel.L5: SecurityRisk.HIGH,
}

#: 命令字段候选名（不同工具的叫法不同）
_COMMAND_KEYS = ("command", "cmd", "sql", "script")


def _command_of(action_event: Any) -> str | None:
    action = getattr(action_event, "action", None)
    if action is None:
        return None
    for key in _COMMAND_KEYS:
        value = getattr(action, key, None)
        if isinstance(value, str) and value.strip():
            return value
    return None


class OpsPilotSecurityAnalyzer(SecurityAnalyzerBase):
    """工具名 → 我们的 L 级 → 框架风险档。命令类工具再叠加危险模式。"""

    def security_risk(self, action_event: Any) -> SecurityRisk:
        tool = getattr(action_event, "tool_name", "") or ""
        level = level_of(tool)                       # 未知工具按 L4 保守
        level = escalate(level, _command_of(action_event))
        return LEVEL_TO_RISK.get(level, SecurityRisk.HIGH)

    #: 框架会调这个批量接口（见 agent.py L1070-1076）
    def analyze_pending_actions(self, action_events: list[Any]):
        return [(ev, self.security_risk(ev)) for ev in action_events]


def describe_action(action_event: Any) -> dict[str, Any]:
    """给审计/前端用的可读说明。"""
    tool = getattr(action_event, "tool_name", "") or ""
    level = escalate(level_of(tool), _command_of(action_event))
    return {
        "tool_name": tool,
        "level": level.value,
        "security_risk": LEVEL_TO_RISK[level].value,
        "command": _command_of(action_event),
    }
