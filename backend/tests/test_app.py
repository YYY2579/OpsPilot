"""API 冒烟测试（M2 骨架）：连接管理 / 任务 / 审批 / 权限档位端点。"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi 未安装（pip install -e '.[dev]'）")
from fastapi.testclient import TestClient  # noqa: E402

from ops_pilot.server.app import app, store  # noqa: E402


@pytest.fixture
def client():
    app.state.conn = __import__("ops_pilot.server.db", fromlist=["connect"]).connect()
    store.reset_session("sess-1")
    return TestClient(app)


def test_server_crud(client):
    body = {
        "name": "HK-Ubuntu",
        "host": "192.168.1.10",
        "username": "deploy",
        "credential_ref": "cred-hk-01",
        "environment": "production",
    }
    r = client.post("/api/connections/servers", json=body)
    assert r.status_code == 200
    server = r.json()
    assert server["name"] == "HK-Ubuntu"

    r = client.get("/api/connections/servers")
    assert any(s["server_id"] if False else s["name"] == "HK-Ubuntu" for s in r.json())

    r = client.get(f"/api/connections/servers/{server['id']}")
    assert r.status_code == 200


def test_task_and_approval_flow(client):
    task = client.post("/api/tasks", json={
        "title": "分析 CPU 高负载原因",
        "user_request": "检查这台服务器最近为什么 CPU 使用率很高",
        "context_type": "server",
        "context_id": "hk-ubuntu",
    }).json()
    assert task["status"] == "pending"

    approval = client.post("/api/approvals", json={
        "task_id": task["id"],
        "operation_description": "重启 backend 容器",
        "risk_level": "L3",
        "impact": "服务中断 5～15 秒",
        "rollback_plan": "重新启动原容器",
    }).json()
    assert approval["status"] == "pending"

    approved = client.post(f"/api/approvals/{approval['id']}/approve").json()
    assert approved["status"] == "approved"

    rejected = client.post(f"/api/approvals/{approval['id']}/reject", params={
        "rejected_reason": "User rejected the action."
    }).json()
    assert rejected["status"] == "rejected"


def test_permission_endpoints(client):
    # 默认档：生产环境 = 请求审批
    r = client.get("/api/session/sess-1/permission", params={"environment": "production"})
    assert r.json()["tier"] == "requested_approval"

    # 升级到帮我批准：需要勾选警告
    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "approve_for_me", "acknowledged": False,
    })
    assert r.status_code == 422

    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "approve_for_me", "acknowledged": True,
    })
    assert r.status_code == 200 and r.json()["to"] == "approve_for_me"

    # 升级到完全访问：生产环境必须输环境名
    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "full_access", "acknowledged": True,
    })
    assert r.status_code == 422

    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "full_access",
        "acknowledged": True, "env_confirm": "production",
    })
    assert r.status_code == 200 and r.json()["to"] == "full_access"

    # 降级：不需要确认
    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "requested_approval",
    })
    assert r.status_code == 200 and r.json()["kind"] == "downgrade"
