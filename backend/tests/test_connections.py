"""M2 收尾测试：连接测试端点、database/project API、审计留痕。

SSH 成功路径用 monkeypatch 替换 ParamikoCommandRunner（不真连主机）；
失败路径与 TCP 路径用真实代码跑。
"""
from __future__ import annotations

import json
import socket
import threading

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ops_pilot.server import db, probe  # noqa: E402
from ops_pilot.server.app import app, store  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    app.state.conn = db.connect()
    store.reset_session("sess-1")
    # 默认：环境里没有凭据 → 走 credential 失败路径
    for key in list(__import__("os").environ):
        if key.startswith("OPSPILOT_"):
            monkeypatch.delenv(key, raising=False)
    return TestClient(app)


def _create_server(client, **over):
    body = {"name": "HK-Ubuntu", "host": "156.224.28.147", "username": "root",
            "credential_ref": "hk-ubuntu", "environment": "production"}
    body.update(over)
    return client.post("/api/connections/servers", json=body).json()


# ---------------- 服务器连接测试 ----------------

def test_server_test_missing_credential(client):
    server = _create_server(client)
    r = client.post(f"/api/connections/servers/{server['id']}/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["stage"] == "credential"
    assert "OPSPILOT_HK_UBUNTU_HOST" in body["message"]
    # 失败也要落审计
    events = client.get("/api/audit").json()
    assert any(e["kind"] == "connection_test" and e["detail"]["ok"] is False for e in events)


def test_server_test_success_writes_online_and_audit(client, monkeypatch):
    monkeypatch.setenv("OPSPILOT_HK_UBUNTU_HOST", "10.0.0.5")
    monkeypatch.setenv("OPSPILOT_HK_UBUNTU_USERNAME", "root")
    monkeypatch.setenv("OPSPILOT_HK_UBUNTU_PASSWORD", "s3cr3t-PASS")

    class FakeRunner:
        def __init__(self, credential, connect_timeout=8.0):
            self.credential = credential

        def run(self, command, timeout=10.0):
            return 0, 'PRETTY_NAME="Ubuntu 24.04.1 LTS"\n', ""

        def close(self):
            pass

    monkeypatch.setattr(probe, "ParamikoCommandRunner", FakeRunner)
    server = _create_server(client)
    body = client.post(f"/api/connections/servers/{server['id']}/test").json()

    assert body["ok"] is True and body["stage"] == "ok"
    assert body["os"] == "Ubuntu 24.04.1 LTS"
    assert "password" not in json.dumps(body).lower()
    assert "s3cr3t" not in json.dumps(body)

    # status 被更新
    assert client.get(f"/api/connections/servers/{server['id']}").json()["status"] == "online"

    # 审计：解析留痕（脱敏视图）+ 连接测试
    events = client.get("/api/audit").json()
    cred_events = [e for e in events if e["kind"] == "credential_resolve"]
    assert cred_events, "凭据解析必须留痕（§A6.4）"
    dumped = json.dumps(cred_events)
    assert "s3cr3t-PASS" not in dumped          # 审计里绝不能出现密钥
    assert cred_events[0]["detail"]["auth"] == "password"

    # 审计可按 kind 过滤
    only_cred = client.get("/api/audit", params={"kind": "credential_resolve"}).json()
    assert all(e["kind"] == "credential_resolve" for e in only_cred)


def test_server_test_404(client):
    assert client.post("/api/connections/servers/nope/test").status_code == 404


# ---------------- 数据库连接 ----------------

def test_database_crud_and_test_tcp_failure(client):
    row = client.post("/api/connections/databases", json={
        "name": "MySQL-Production", "host": "127.0.0.1", "port": 1,
        "username": "readonly", "credential_ref": "mysql-prod", "environment": "production",
    }).json()
    assert row["db_type"] == "mysql" and row["readonly"] == 1

    body = client.post(f"/api/connections/databases/{row['id']}/test").json()
    assert body["ok"] is False and body["stage"] == "tcp"
    assert client.get("/api/connections/databases").json()[0]["status"] == "offline"


def test_database_test_tcp_success_degrades_gracefully(client):
    # 起一个本地监听端口，模拟「TCP 可达但没有驱动」
    server_sock = socket.socket()
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]
    threading.Thread(target=lambda: server_sock.accept(), daemon=True).start()

    row = client.post("/api/connections/databases", json={
        "name": "MySQL-Test", "host": "127.0.0.1", "port": port,
        "username": "root", "credential_ref": "mysql-test",
    }).json()
    body = client.post(f"/api/connections/databases/{row['id']}/test").json()
    server_sock.close()

    assert body["ok"] is True and body["stage"] == "tcp"
    assert "pymysql" in body["message"] or "认证检查" in body["message"]


# ---------------- 项目 ----------------

def test_project_crud(client):
    row = client.post("/api/projects", json={
        "name": "Monitoring Stack", "path": "/opt/monitoring",
        "repository_url": "git@github.com:me/monitoring.git", "environment": "production",
    }).json()
    assert row["default_branch"] == "main"
    assert [p["name"] for p in client.get("/api/projects").json()] == ["Monitoring Stack"]


# ---------------- 权限变更审计 ----------------

def test_permission_changes_are_audited_including_denials(client):
    # 被闸门拒绝的升级尝试也要留痕
    r = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "full_access", "acknowledged": True,
    })
    assert r.status_code == 422

    ok = client.post("/api/session/sess-1/permission", json={
        "environment": "production", "target": "full_access",
        "acknowledged": True, "env_confirm": "production",
    })
    assert ok.status_code == 200

    events = client.get("/api/audit", params={"kind": "permission_change"}).json()
    kinds = [e["detail"]["kind"] for e in events]
    assert "denied" in kinds and "upgrade" in kinds
    assert all(e["environment"] == "production" for e in events)
