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


def test_server_lookup_accepts_logical_alias(client):
    """server 路径参数必须是 主键 id / credential_ref / name 三者通吃。

    真实踩过：前端与 Agent 用逻辑别名（如 `jzz-18`）调用 /health，
    而路由只按随机主键查 → 静默 404，界面显示不出真实数据。
    """
    server = client.post("/api/connections/servers", json={
        "name": "生产靶机-jzz18",
        "host": "192.168.1.20",
        "username": "root",
        "credential_ref": "jzz-18",
        "environment": "production",
    }).json()

    for ref in (server["id"], "jzz-18", "生产靶机-jzz18"):
        r = client.get(f"/api/connections/servers/{ref}")
        assert r.status_code == 200, f"alias {ref!r} 未解析"
        assert r.json()["id"] == server["id"]

    assert client.get("/api/connections/servers/nope-not-exist").status_code == 404


def test_server_reregistration_dedupes_by_credential_ref(client):
    """同一逻辑主机重复注册应更新原行，不产生重复记录。"""
    body = {
        "name": "生产靶机-jzz18",
        "host": "192.168.1.20",
        "username": "root",
        "credential_ref": "jzz-18",
        "environment": "production",
    }
    first = client.post("/api/connections/servers", json=body).json()
    again = client.post("/api/connections/servers", json={**body, "host": "192.168.1.21"}).json()

    assert again["id"] == first["id"], "重复注册应复用原 id"
    assert again["host"] == "192.168.1.21", "字段应被更新"
    rows = client.get("/api/connections/servers").json()
    assert len([s for s in rows if s["credential_ref"] == "jzz-18"]) == 1


def test_health_endpoint_reports_stage_when_credential_missing(client):
    """凭据缺失时必须返回 ok=false + stage，而不是编造指标。"""
    client.post("/api/connections/servers", json={
        "name": "无凭据主机",
        "host": "10.255.255.1",
        "username": "root",
        "credential_ref": "no-such-cred-alias",
        "environment": "development",
    })
    r = client.get("/api/servers/no-such-cred-alias/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["stage"] in ("credential", "ssh", "collect")
    # 失败时不得伪造任何指标字段
    assert "cpu" not in body and "memory" not in body and "disk" not in body
    assert isinstance(body.get("message"), str) and body["message"]


def test_health_server_id_is_row_id_not_credential_ref(client):
    """身份字段不能被采集结果覆盖：server_id 必须是行主键，不是凭据别名。

    probe_health() 的返回里自带 server_id（= credential_ref），字典解包时
    若把它排在后面就会覆盖接口自己算出的 id —— 前端据此做键会错乱。
    """
    import ops_pilot.server.app as app_mod

    server = client.post("/api/connections/servers", json={
        "name": "身份测试机", "host": "10.1.1.1", "username": "root",
        "credential_ref": "ident-alias", "environment": "development",
    }).json()

    # 打桩采集层，避免真连 SSH；返回里故意带上会冲突的 server_id。
    def fake_probe(ref, **_):
        return {"ok": True, "stage": "ok", "server_id": ref, "cpu": {"percent": 1.0}}

    monkey = app_mod.probe_health
    app_mod.probe_health = fake_probe
    try:
        body = client.get("/api/servers/ident-alias/health").json()
    finally:
        app_mod.probe_health = monkey

    assert body["server_id"] == server["id"], "server_id 应是行主键"
    assert body["credential_ref"] == "ident-alias"
    assert body["cpu"]["percent"] == 1.0, "采集值应保留"


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
