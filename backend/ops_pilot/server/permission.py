"""权限档位模型（需求开发文档 §A6.5）。

三档：requested_approval（请求审批）/ approve_for_me（帮我批准）/ full_access（完全访问）。
- 档位决定"默认要不要问"，风险等级决定"能不能被档位豁免"（矩阵见规格 §A6.5.1）。
- **L5 是地板**：不可逆操作在任何档位下都不自动执行 —— 由工具层前置拦截，本模块不豁免。
- 升级需过闸门，降级即时；档位按会话作用域；完全访问 30 分钟自动回落（§A6.5.4）。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

TIER_REQUESTED = "requested_approval"
TIER_APPROVE = "approve_for_me"
TIER_FULL = "full_access"

TIERS = (TIER_REQUESTED, TIER_APPROVE, TIER_FULL)
_ORDER = {TIER_REQUESTED: 0, TIER_APPROVE: 1, TIER_FULL: 2}

# 各环境默认档（§A6.5.4）
DEFAULT_BY_ENV = {
    "production": TIER_REQUESTED,
    "staging": TIER_REQUESTED,
    "development": TIER_APPROVE,
    "lab": TIER_APPROVE,
}

FULL_ACCESS_TTL_SECONDS = 30 * 60   # 完全访问 30 分钟自动回落


class PermissionDenied(ValueError):
    """升级闸门未通过。detail 说明具体原因（§A6.5.3）。"""


@dataclass
class SessionPermission:
    tier: str
    environment: str
    expires_at: float | None = None


def default_for(environment: str) -> str:
    return DEFAULT_BY_ENV.get(environment, TIER_REQUESTED)


class PermissionStore:
    """会话级档位存储（内存）。进程重启即回落默认档 —— 这是刻意设计（§A6.5.4）。"""

    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._sessions: dict[str, SessionPermission] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str, environment: str) -> SessionPermission:
        with self._lock:
            sp = self._sessions.get(session_id)
            if sp is None or sp.environment != environment:
                sp = SessionPermission(tier=default_for(environment), environment=environment)
                self._sessions[session_id] = sp
            elif sp.expires_at is not None and self._clock() >= sp.expires_at:
                # 完全访问到期 → 自动回落（§A6.5.4）
                sp = SessionPermission(tier=default_for(environment), environment=environment)
                self._sessions[session_id] = sp
            return sp

    def change(
        self,
        session_id: str,
        environment: str,
        target: str,
        *,
        acknowledged: bool = False,
        env_confirm: str | None = None,
    ) -> dict:
        """变更档位。返回审计记录（who 由调用方补充）；闸门不过抛 PermissionDenied。"""
        if target not in TIERS:
            raise PermissionDenied(f"未知档位：{target}")
        current = self.get(session_id, environment)
        record = {
            "session_id": session_id,
            "environment": environment,
            "from": current.tier,
            "to": target,
        }

        if target == current.tier:
            record["kind"] = "nochange"
            return record

        upgrade = _ORDER[target] > _ORDER[current.tier]
        if upgrade:
            # ---- 升级闸门（§A6.5.3，不对称：降级不需要） ----
            if not acknowledged:
                raise PermissionDenied("升级档位需要勾选风险警告")
            if target == TIER_FULL and environment == "production" and env_confirm != environment:
                raise PermissionDenied("生产环境开启完全访问需要输入环境名确认")
            if target == TIER_FULL:
                # 完全访问：30 分钟自动回落
                expires_at = self._clock() + FULL_ACCESS_TTL_SECONDS
            else:
                expires_at = None
        else:
            # 降级即时生效，不需要确认
            expires_at = None

        with self._lock:
            self._sessions[session_id] = SessionPermission(
                tier=target, environment=environment, expires_at=expires_at
            )
        record["kind"] = "upgrade" if upgrade else "downgrade"
        if expires_at:
            record["expires_at"] = expires_at
        return record

    def reset_session(self, session_id: str) -> None:
        """切换会话 / 关闭应用 → 回落默认档（§A6.5.4）。"""
        with self._lock:
            self._sessions.pop(session_id, None)
