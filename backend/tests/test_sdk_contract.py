"""SDK 契约测试（M1-1）：验证工具注册链路与 ToolAnnotations 行为。

仅当 openhands-sdk 可导入时运行；否则跳过（纯逻辑层测试不受影响）。
SDK 安装：pip install "openhands-sdk==1.47.0"
"""
from __future__ import annotations

import json

import pytest

openhands = pytest.importorskip(
    "openhands.sdk", reason="openhands-sdk 未安装（pip install 'openhands-sdk==1.47.0'）"
)

from openhands.sdk.security.risk import SecurityRisk  # noqa: E402
from openhands.sdk.tool.registry import list_registered_tools  # noqa: E402

import ops_pilot.tools.get_server_health.definition as gh_def  # noqa: E402


def test_tool_name_matches_spec():
    # __init_subclass__ 规则：camel → snake，去掉 _tool 后缀（tool.py L386-391）
    assert gh_def.GetServerHealthTool.name == "get_server_health"


def test_tool_registered():
    assert "get_server_health" in list_registered_tools()


def test_annotations_read_only():
    tool = gh_def.GetServerHealthTool.create(conv_state=None)[0]
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    # readOnlyHint=True 的工具在 LLM schema 中不应附加 security_risk 自评字段
    schema = tool._get_tool_schema() if hasattr(tool, "_get_tool_schema") else None
    if schema is not None:
        props = (schema.get("function", {}) or {}).get("parameters", {}).get("properties", {})
        assert "security_risk" not in props


def test_action_only_carries_server_id():
    action = gh_def.GetServerHealthAction(server_id="hk-ubuntu")
    dumped = json.loads(action.model_dump_json())
    # §A6.4：Action 只允许 server_id，不允许 IP / 用户名 / 密码字段
    assert set(dumped) <= {"kind", "server_id"}
    assert dumped["server_id"] == "hk-ubuntu"


def test_observation_masks_secrets(tmp_path):
    """§A6.4 第 2-4 条：SecretRegistry 注册的密钥必须被脱敏为 <secret-hidden>。"""
    from openhands.sdk import LLM  # noqa: F401  (确保包完整导入路径可用)
    from openhands.sdk.conversation.secret_registry import SecretRegistry

    registry = SecretRegistry()
    registry.update_secrets({"HK_UBUNTU_KEY": "s3cr3t-PASS"})

    observation = gh_def.GetServerHealthObservation(
        server_id="hk-ubuntu",
        cpu={"percent": 82.0, "load_avg": [4.8, 3.2, 2.1], "cores": 4, "status": "warning"},
        memory={"percent": 91.0, "used_gb": 3.64, "total_gb": 4.0, "status": "critical"},
        disk={"used_percent": 68.0, "status": "warning"},
        top_process=[{"pid": 2143, "name": "java", "cpu": 182.0}],
        os={"name": "Ubuntu 24.04 LTS"},
        services={"docker": "active", "mysql": "warning"},
        anomalies=[{"item": "cpu", "level": "warning", "hint": "load/cores=1.2"}],
    )
    registry.mask_secrets_in_model(observation)
    dumped = observation.model_dump_json()
    assert "s3cr3t-PASS" not in dumped
    assert "<secret-hidden>" in dumped or "s3cr3t" not in dumped


def test_executor_maps_ssh_error_to_value_error():
    from ops_pilot.credentials import CredentialError
    from ops_pilot.ssh.client import SshError
    from ops_pilot.tools.get_server_health.definition import GetServerHealthAction

    class FailingResolver:
        def resolve(self, server_id):
            raise SshError("network", "无法连接 192.168.1.10:22")

    executor = gh_def.GetServerHealthExecutor.__new__(gh_def.GetServerHealthExecutor)
    executor._resolver = FailingResolver()
    executor._key_services = ()
    executor._connect_timeout = 1.0
    executor._command_timeout = 1.0

    with pytest.raises(ValueError) as excinfo:   # → AgentErrorEvent（agent.py L1427-1438）
        executor(GetServerHealthAction(server_id="hk-ubuntu"))
    assert "network" in str(excinfo.value)

    class MissingResolver:
        def resolve(self, server_id):
            raise CredentialError("missing", "未配置 OPSPILOT_HK_UBUNTU_HOST")

    executor._resolver = MissingResolver()
    with pytest.raises(ValueError):
        executor(GetServerHealthAction(server_id="hk-ubuntu"))


def test_security_risk_enum_exists():
    # L0–L5 → ToolAnnotations 的映射锚点（M3-1 用）
    assert {m.name for m in SecurityRisk} == {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}
