"""M3 测试：L0–L5 决策矩阵逐格 + 命令危险模式 + L5 硬地板 + 框架策略接入。"""
from __future__ import annotations

import pytest

from openhands.sdk.security.risk import SecurityRisk

from ops_pilot.security import levels as lv
from ops_pilot.security.guard import (
    L5Blocked,
    TOOL_LEVELS,
    enforce_floor,
    level_of,
)
from ops_pilot.security.policy import (
    FullAccessPolicy,
    OpsPilotConfirmationPolicy,
    describe,
    policy_for_tier,
    risk_to_level,
)
from ops_pilot.server.permission import TIER_APPROVE, TIER_FULL, TIER_REQUESTED

ALL_LEVELS = [lv.RiskLevel.L0, lv.RiskLevel.L1, lv.RiskLevel.L2,
              lv.RiskLevel.L3, lv.RiskLevel.L4, lv.RiskLevel.L5]


# ---------------- 矩阵逐格 ----------------

EXPECTED = {
    # 档位            L0           L1           L2           L3           L4             L5
    TIER_REQUESTED: [lv.DECISION_AUTO, lv.DECISION_AUTO, lv.DECISION_ASK, lv.DECISION_ASK,
                     lv.DECISION_DOUBLE, lv.DECISION_DENY],
    TIER_APPROVE:   [lv.DECISION_AUTO, lv.DECISION_AUTO, lv.DECISION_AUTO, lv.DECISION_AUTO,
                     lv.DECISION_ASK, lv.DECISION_DENY],
    TIER_FULL:      [lv.DECISION_AUTO, lv.DECISION_AUTO, lv.DECISION_AUTO, lv.DECISION_AUTO,
                     lv.DECISION_AUTO, lv.DECISION_DENY],
}


@pytest.mark.parametrize("tier", [TIER_REQUESTED, TIER_APPROVE, TIER_FULL])
def test_matrix_every_cell(tier):
    got = [lv.decide(tier, l).action for l in ALL_LEVELS]
    assert got == EXPECTED[tier], f"{tier} 矩阵不符"


def test_l5_denied_in_every_tier():
    for tier in (TIER_REQUESTED, TIER_APPROVE, TIER_FULL):
        d = lv.decide(tier, lv.RiskLevel.L5)
        assert d.action == lv.DECISION_DENY and d.allowed is False
        assert "不可逆" in d.reason


def test_unknown_tier_falls_back_to_strictest():
    d = lv.decide("super_mode", lv.RiskLevel.L2)
    assert d.action == lv.DECISION_ASK          # 按请求审批处理


def test_only_auto_writes_audit_kind():
    assert lv.decide(TIER_FULL, lv.RiskLevel.L4).action == lv.DECISION_AUTO
    assert lv.decide(TIER_REQUESTED, lv.RiskLevel.L3).needs_human is True


# ---------------- annotations → 等级 ----------------

def test_annotations_to_level():
    assert lv.level_from_annotations(read_only=True, destructive=False,
                                     idempotent=True, open_world=False) is lv.RiskLevel.L1
    assert lv.level_from_annotations(read_only=False, destructive=True,
                                     idempotent=False, open_world=True) is lv.RiskLevel.L4
    assert lv.level_from_annotations(read_only=False, destructive=True,
                                     idempotent=True, open_world=False) is lv.RiskLevel.L3


# ---------------- 命令危险模式 ----------------

@pytest.mark.parametrize("command,expected", [
    ("rm -rf /var/log", lv.RiskLevel.L4),
    ("sudo iptables -F", lv.RiskLevel.L4),
    ("mysql -e 'DROP DATABASE prod'", lv.RiskLevel.L5),
    ("kubectl delete namespace prod", lv.RiskLevel.L5),
    ("systemctl stop nginx", lv.RiskLevel.L3),
    ("kill -9 1234", lv.RiskLevel.L3),
    ("docker system prune -af", lv.RiskLevel.L4),
    ("ls -l /tmp", None),
    ("df -P /", None),
])
def test_detect_command_level(command, expected):
    assert lv.detect_command_level(command) == expected


def test_escalate_takes_higher_level():
    # 基础 L1（只读工具）但命令里带 rm -rf → 抬到 L4
    assert lv.escalate(lv.RiskLevel.L1, "rm -rf /tmp/x") is lv.RiskLevel.L4
    # 基础 L3 且命令干净 → 保持 L3
    assert lv.escalate(lv.RiskLevel.L3, "ls -l") is lv.RiskLevel.L3
    # L5 已是地板，不再抬
    assert lv.escalate(lv.RiskLevel.L5, "ls") is lv.RiskLevel.L5


def test_detect_hits_explain_why():
    hits = lv.detect_command_hits("sudo rm -rf / && iptables -F")
    reasons = {h["reason"] for h in hits}
    assert "递归/强制删除" in reasons and "修改防火墙" in reasons


# ---------------- L5 地板（工具层硬拦截） ----------------

def test_enforce_floor_blocks_l5_without_approval():
    with pytest.raises(L5Blocked):
        enforce_floor(lv.RiskLevel.L5, approved=False)


def test_enforce_floor_allows_when_approved_or_below_l5():
    enforce_floor(lv.RiskLevel.L5, approved=True)     # 人工批准后放行
    enforce_floor(lv.RiskLevel.L4, approved=False)    # 非 L5 不受地板约束


def test_tool_levels_registry():
    readonly = {k: v for k, v in TOOL_LEVELS.items() if v is lv.RiskLevel.L1}
    assert len(readonly) == 18                  # 9 SSH + 5 DB + 4 K8s 只读
    assert TOOL_LEVELS["restart_service"] is lv.RiskLevel.L3   # 唯一写工具


def test_unknown_tool_defaults_to_l4():
    assert level_of("some_new_writer") is lv.RiskLevel.L4
    assert level_of("run_shell") is lv.RiskLevel.L4
    assert level_of("get_disk_usage") is lv.RiskLevel.L1


# ---------------- 框架策略接入 ----------------

def test_policy_should_confirm_matches_matrix():
    requested = OpsPilotConfirmationPolicy(tier=TIER_REQUESTED)
    # LOW 代表只读（L0/L1）→ 任何档位都自动，否则只读工具会被要求确认、会话卡在第一步
    assert requested.should_confirm(SecurityRisk.LOW) is False
    assert requested.should_confirm(SecurityRisk.MEDIUM) is True      # MEDIUM→L3：询问
    assert requested.should_confirm(SecurityRisk.HIGH) is True        # HIGH→L4：二次确认
    assert requested.should_confirm(SecurityRisk.UNKNOWN) is True     # UNKNOWN 按 L4 保守

    approve = OpsPilotConfirmationPolicy(tier=TIER_APPROVE)
    assert approve.should_confirm(SecurityRisk.LOW) is False
    assert approve.should_confirm(SecurityRisk.MEDIUM) is False       # L3 自动
    assert approve.should_confirm(SecurityRisk.HIGH) is True          # L4 询问


def test_analyzer_maps_tool_level_to_framework_risk():
    """analyzer 的映射必须与 policy 的反向映射语义一致（LOW=只读）。"""
    from ops_pilot.security.analyzer import LEVEL_TO_RISK, OpsPilotSecurityAnalyzer
    from ops_pilot.security.levels import RiskLevel

    assert LEVEL_TO_RISK[RiskLevel.L1] is SecurityRisk.LOW
    assert LEVEL_TO_RISK[RiskLevel.L4] is SecurityRisk.HIGH

    analyzer = OpsPilotSecurityAnalyzer()

    class _Ev:
        def __init__(self, tool, action=None):
            self.tool_name = tool
            self.action = action

    class _Cmd:
        def __init__(self, command):
            self.command = command

    # 只读工具 → LOW（自动）
    assert analyzer.security_risk(_Ev("get_server_health")) is SecurityRisk.LOW
    # 写工具 → HIGH
    assert analyzer.security_risk(_Ev("restart_container")) is SecurityRisk.MEDIUM  # L3
    assert analyzer.security_risk(_Ev("run_shell")) is SecurityRisk.HIGH            # L4
    # 命令里带危险模式 → 抬到 HIGH（L5 也走 HIGH，真正的拒绝在工具层）
    assert analyzer.security_risk(_Ev("run_shell", _Cmd("rm -rf /tmp"))) is SecurityRisk.HIGH
    assert analyzer.security_risk(_Ev("get_disk_usage", _Cmd("ls"))) is SecurityRisk.LOW
    # 批量接口（框架实际调用的那个）
    pairs = analyzer.analyze_pending_actions([_Ev("get_server_health"), _Ev("run_shell")])
    assert len(pairs) == 2 and pairs[0][1] is SecurityRisk.LOW


def test_full_access_policy_auto_for_high_risk():
    assert FullAccessPolicy().should_confirm(SecurityRisk.HIGH) is False


def test_policy_for_tier_and_describe():
    assert isinstance(policy_for_tier(TIER_FULL), FullAccessPolicy)
    assert type(policy_for_tier(TIER_REQUESTED)) is OpsPilotConfirmationPolicy

    info = describe(TIER_REQUESTED, SecurityRisk.HIGH)
    assert info["level"] == "L4" and info["action"] == lv.DECISION_DOUBLE
    assert risk_to_level(SecurityRisk.UNKNOWN) is lv.RiskLevel.L4
