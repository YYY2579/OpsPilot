"""权限档位状态机测试（§A6.5）。

覆盖：默认档按环境 / 降级即时 / 升级闸门 / 生产环境名确认 / 30 分钟回落 / 切会话回落。
"""
from __future__ import annotations

import pytest

from ops_pilot.server.permission import (
    DEFAULT_BY_ENV,
    FULL_ACCESS_TTL_SECONDS,
    PermissionDenied,
    PermissionStore,
    TIER_APPROVE,
    TIER_FULL,
    TIER_REQUESTED,
)


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_defaults_by_environment():
    assert DEFAULT_BY_ENV["production"] == TIER_REQUESTED
    assert DEFAULT_BY_ENV["staging"] == TIER_REQUESTED
    assert DEFAULT_BY_ENV["development"] == TIER_APPROVE
    store = PermissionStore(clock=FakeClock())
    assert store.get("s1", "production").tier == TIER_REQUESTED
    assert store.get("s2", "development").tier == TIER_APPROVE


def test_unknown_environment_uses_strict_default():
    store = PermissionStore(clock=FakeClock())
    assert store.get("s1", "unknown-env").tier == TIER_REQUESTED


def test_downgrade_is_instant_without_confirmation():
    store = PermissionStore(clock=FakeClock())
    store.change("s1", "production", TIER_FULL, acknowledged=True, env_confirm="production")
    # 完全访问 → 请求审批：直接降，不需要确认
    record = store.change("s1", "production", TIER_REQUESTED)
    assert record["kind"] == "downgrade"
    assert store.get("s1", "production").tier == TIER_REQUESTED


def test_upgrade_requires_acknowledgement():
    # production 默认 requested_approval，从这里升到 approve_for_me 才是真正的"升级"
    store = PermissionStore(clock=FakeClock())
    with pytest.raises(PermissionDenied):
        store.change("s1", "production", TIER_APPROVE, acknowledged=False)
    record = store.change("s1", "production", TIER_APPROVE, acknowledged=True)
    assert record["kind"] == "upgrade"
    assert store.get("s1", "production").tier == TIER_APPROVE


def test_full_access_gate_on_production():
    store = PermissionStore(clock=FakeClock())
    # 未勾选 → 拒绝
    with pytest.raises(PermissionDenied):
        store.change("s1", "production", TIER_FULL, acknowledged=False)
    # 勾选了但生产环境没输环境名 → 拒绝
    with pytest.raises(PermissionDenied):
        store.change("s1", "production", TIER_FULL, acknowledged=True)
    # 环境名输错 → 拒绝
    with pytest.raises(PermissionDenied):
        store.change("s1", "production", TIER_FULL, acknowledged=True, env_confirm="测试")
    # 全部满足 → 通过，且带过期时间
    record = store.change("s1", "production", TIER_FULL, acknowledged=True, env_confirm="production")
    assert record["kind"] == "upgrade"
    assert store.get("s1", "production").tier == TIER_FULL


def test_full_access_gate_skipped_on_development():
    """非生产环境开完全访问：勾选警告即可，不需要输环境名。"""
    store = PermissionStore(clock=FakeClock())
    record = store.change("s1", "development", TIER_FULL, acknowledged=True)
    assert record["kind"] == "upgrade"
    assert store.get("s1", "development").tier == TIER_FULL


def test_full_access_auto_falls_back_after_ttl():
    clock = FakeClock(now=1000.0)
    store = PermissionStore(clock=clock)
    store.change("s1", "production", TIER_FULL, acknowledged=True, env_confirm="production")
    assert store.get("s1", "production").tier == TIER_FULL
    clock.now += FULL_ACCESS_TTL_SECONDS - 1
    assert store.get("s1", "production").tier == TIER_FULL      # 还没到期
    clock.now += 2
    assert store.get("s1", "production").tier == TIER_REQUESTED  # 到期自动回落


def test_switching_session_falls_back_to_default():
    store = PermissionStore(clock=FakeClock())
    store.change("s1", "production", TIER_FULL, acknowledged=True, env_confirm="production")
    # 切到另一个会话 → 默认档；回到 s1 也应回落（同 id 不同环境视为新会话）
    assert store.get("s2", "production").tier == TIER_REQUESTED
    store.reset_session("s1")
    assert store.get("s1", "production").tier == TIER_REQUESTED


def test_same_tier_is_nochange():
    store = PermissionStore(clock=FakeClock())
    record = store.change("s1", "production", TIER_REQUESTED)
    assert record["kind"] == "nochange"


def test_unknown_tier_rejected():
    store = PermissionStore(clock=FakeClock())
    with pytest.raises(PermissionDenied):
        store.change("s1", "production", "super_mode")
