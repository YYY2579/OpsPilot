"""风险等级 L0–L5 与决策矩阵（需求开发文档 §A6.2 / §A6.5.1）。

两条正交维度：
- **风险等级 L0–L5** 描述"这个动作有多危险"，L5 = 没有回滚方案的操作
- **权限档位** 描述"默认要不要问"

矩阵（§A6.5.1 逐格实现）：

| 档位         | L0–L1 | L2   | L3   | L4       | L5   |
|--------------|-------|------|------|----------|------|
| 请求审批      | 自动  | 询问 | 询问 | 二次确认  | 拒绝 |
| 帮我批准      | 自动  | 自动 | 自动 | 询问     | 拒绝 |
| 完全访问      | 自动  | 自动 | 自动 | 自动     | 拒绝 |

**L5 是地板**：任何档位都不自动执行 —— 这是本模块最不能被绕过的规则。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from ops_pilot.server.permission import (
    TIER_APPROVE,
    TIER_FULL,
    TIER_REQUESTED,
)


class RiskLevel(str, Enum):
    L0 = "L0"   # 只读且无副作用（读文件、查状态）
    L1 = "L1"   # 只读查询（本项目的运维只读工具）
    L2 = "L2"   # 低风险写（重启单个服务、清临时文件）
    L3 = "L3"   # 中风险写（改配置、重启容器、部署）
    L4 = "L4"   # 高风险（删文件、改防火墙/SSH、批量变更）
    L5 = "L5"   # 禁止自动执行（删库、清表、重建集群）


# 决策结果
DECISION_AUTO = "auto"                  # 直接执行，记审计（approval_kind=tier_auto）
DECISION_ASK = "ask"                    # 走确认卡
DECISION_DOUBLE = "double_confirm"      # 询问通过后再二次确认
DECISION_DENY = "deny"                  # 不执行

_ORDER = {RiskLevel.L0: 0, RiskLevel.L1: 1, RiskLevel.L2: 2,
          RiskLevel.L3: 3, RiskLevel.L4: 4, RiskLevel.L5: 5}

#: §A6.5.1 矩阵，行=档位，列=L0..L5
MATRIX: dict[str, dict[RiskLevel, str]] = {
    TIER_REQUESTED: {
        RiskLevel.L0: DECISION_AUTO, RiskLevel.L1: DECISION_AUTO,
        RiskLevel.L2: DECISION_ASK, RiskLevel.L3: DECISION_ASK,
        RiskLevel.L4: DECISION_DOUBLE, RiskLevel.L5: DECISION_DENY,
    },
    TIER_APPROVE: {
        RiskLevel.L0: DECISION_AUTO, RiskLevel.L1: DECISION_AUTO,
        RiskLevel.L2: DECISION_AUTO, RiskLevel.L3: DECISION_AUTO,
        RiskLevel.L4: DECISION_ASK, RiskLevel.L5: DECISION_DENY,
    },
    TIER_FULL: {
        RiskLevel.L0: DECISION_AUTO, RiskLevel.L1: DECISION_AUTO,
        RiskLevel.L2: DECISION_AUTO, RiskLevel.L3: DECISION_AUTO,
        RiskLevel.L4: DECISION_AUTO, RiskLevel.L5: DECISION_DENY,
    },
}


@dataclass(frozen=True)
class Decision:
    level: RiskLevel
    tier: str
    action: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.action != DECISION_DENY

    @property
    def needs_human(self) -> bool:
        return self.action in (DECISION_ASK, DECISION_DOUBLE)


def decide(tier: str, level: RiskLevel) -> Decision:
    """按 §A6.5.1 矩阵给出决策。未知档位一律按最严（请求审批）处理。"""
    table = MATRIX.get(tier, MATRIX[TIER_REQUESTED])
    action = table[level]

    # L5 地板：显式再挡一次，防止以后有人往 MATRIX 里改了 L5 又忘了一致性
    if level is RiskLevel.L5 and action != DECISION_DENY:
        action = DECISION_DENY

    reason = {
        DECISION_AUTO: f"{level.value} 在「{_tier_label(tier)}」下自动执行（记审计）",
        DECISION_ASK: f"{level.value} 需要人工确认",
        DECISION_DOUBLE: f"{level.value} 需要二次确认",
        DECISION_DENY: f"{level.value} 为不可逆操作，任何档位下都不自动执行",
    }[action]
    return Decision(level=level, tier=tier, action=action, reason=reason)


def _tier_label(tier: str) -> str:
    return {TIER_REQUESTED: "请求审批", TIER_APPROVE: "帮我批准", TIER_FULL: "完全访问"}.get(tier, tier)


# ---------- 由 ToolAnnotations 推导风险等级（§A6.2） ----------

def level_from_annotations(read_only: bool, destructive: bool, idempotent: bool, open_world: bool) -> RiskLevel:
    """把框架的 4 个 annotation 位映射到 L 级。

    注意：这是**默认推导**，具体工具可用自己的 annotations/自定义等级覆盖。
    """
    if read_only:
        return RiskLevel.L1
    if destructive and not idempotent:
        return RiskLevel.L4
    if destructive:
        return RiskLevel.L3
    if open_world:
        return RiskLevel.L2
    return RiskLevel.L2


# ---------- 命令危险模式识别（§A5.3）：命中即抬升等级 ----------

#: (正则, 最低等级, 说明)
DANGER_PATTERNS: tuple[tuple[str, RiskLevel, str], ...] = (
    (r"\b(rm\s+-rf|rm\s+-fr|shred|wipefs)\b", RiskLevel.L4, "递归/强制删除"),
    (r"\b(mkfs(\.\w+)?|dd\s+if=|fdisk|parted)\b", RiskLevel.L4, "磁盘/文件系统操作"),
    (r"\b(drop\s+database|drop\s+table|truncate\s+table)\b", RiskLevel.L5, "删除数据库对象"),
    (r"\b(kubectl\s+delete\s+(ns|namespace|pvc|pv)|kubeadm\s+reset)\b", RiskLevel.L5, "删除集群资源"),
    (r"\b(iptables|nft|ufw|firewall-cmd)\b", RiskLevel.L4, "修改防火墙"),
    (r"(sshd_config|authorized_keys|/etc/sudoers)", RiskLevel.L4, "修改 SSH/提权配置"),
    (r"\bsystemctl\s+(stop|disable|mask)\b", RiskLevel.L3, "停止/禁用服务"),
    (r"\b(kill\s+-9|killall|pkill)\b", RiskLevel.L3, "强制杀进程"),
    (r"\b(history\s+-c|>\s*/var/log/|truncate\s+-s\s*0)\b", RiskLevel.L4, "清除日志/历史"),
    (r"\b(reboot|shutdown|halt|poweroff)\b", RiskLevel.L4, "重启/关机"),
    (r"\b(docker\s+rmi|docker\s+system\s+prune|docker\s+volume\s+rm)\b", RiskLevel.L4, "删除镜像/卷/清理"),
    (r"\b(sudo\s+)?(userdel|groupdel|passwd)\b", RiskLevel.L4, "用户/口令变更"),
    (r"\bchmod\s+(777|-R\s+777)\b", RiskLevel.L3, "放宽权限"),
)


def detect_command_level(command: str) -> RiskLevel | None:
    """扫描命令，返回命中的最高风险等级；未命中返回 None。"""
    if not command:
        return None
    text = command.lower()
    hits = [level for pattern, level, _ in DANGER_PATTERNS if re.search(pattern, text)]
    if not hits:
        return None
    return max(hits, key=lambda lv: _ORDER[lv])


def detect_command_hits(command: str) -> list[dict[str, str]]:
    """返回所有命中的模式（供确认卡展示"为什么危险"）。"""
    text = (command or "").lower()
    return [
        {"pattern": pattern, "level": level.value, "reason": reason}
        for pattern, level, reason in DANGER_PATTERNS
        if re.search(pattern, text)
    ]


def escalate(base: RiskLevel, command: str | None) -> RiskLevel:
    """把命令危险模式叠加到基础等级上，取更高者。"""
    if base is RiskLevel.L5:
        return base                     # 已在地板，无需再抬
    hit = detect_command_level(command or "")
    if hit is None:
        return base
    return hit if _ORDER[hit] > _ORDER[base] else base
