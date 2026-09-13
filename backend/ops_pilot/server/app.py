"""OpsPilot 后端 API（M2 骨架，§A10 路由）。

职责边界（决策记录 001）：资源管理 / 任务 / 审批 / 审计在这里；
Agent 与工具执行在 OpenHands agent-server —— 本服务不跑 Agent。
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ops_pilot.credentials import CredentialResolver
from ops_pilot.server import db
from ops_pilot.server import audit, settings
from ops_pilot.server.probe import test_database, test_server
from ops_pilot.server.usage import normalize_usage, ring_state
from ops_pilot.server.permission import (
    DEFAULT_BY_ENV,
    PermissionDenied,
    PermissionStore,
    TIERS,
)

app = FastAPI(title="OpsPilot Backend", version="0.1.0")
store = PermissionStore()


@app.on_event("startup")
def _startup() -> None:
    settings.load_env()          # 凭据只进内存，不打印（§A6.4）
    app.state.conn = db.connect(os.environ.get("OPSPILOT_DB", "opspilot.db"))


# ---------- 连接管理（§A10.1 / §A10.2） ----------

class ServerIn(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: str = "ssh_key"
    credential_ref: str
    environment: str = "development"
    tags: str = ""
    description: str = ""


@app.post("/api/connections/servers")
def create_server(body: ServerIn):
    return db.insert(app.state.conn, "serverconnection", body.model_dump())


@app.get("/api/connections/servers")
def list_servers():
    return db.fetch_all(app.state.conn, "serverconnection")


@app.get("/api/connections/servers/{server_id}")
def get_server(server_id: str):
    row = db.fetch_one(app.state.conn, "serverconnection", server_id)
    if row is None:
        raise HTTPException(404, "server not found")
    return row


@app.post("/api/connections/servers/{server_id}/test")
def test_server_connection(server_id: str, actor: str = "mir Y"):
    """SSH 连接测试。凭据解析会写审计（只记引用与主机，不记密钥）。"""
    row = db.fetch_one(app.state.conn, "serverconnection", server_id)
    if row is None:
        raise HTTPException(404, "server not found")
    resolver = CredentialResolver(on_resolve=audit.make_credential_hook(app.state.conn, actor))
    result = test_server(row["credential_ref"], resolver=resolver)
    audit.record(
        app.state.conn,
        kind="connection_test",
        actor=actor,
        target_type="server",
        target_id=server_id,
        environment=row.get("environment"),
        detail={"ok": result["ok"], "stage": result["stage"], "latency_ms": result["latency_ms"]},
    )
    db.update(app.state.conn, "serverconnection", server_id,
              {"status": "online" if result["ok"] else "offline"})
    return result


# ---------- 数据库连接（§A10.2） ----------

class DatabaseIn(BaseModel):
    name: str
    db_type: str = "mysql"
    host: str
    port: int = 3306
    username: str
    credential_ref: str
    database_name: str = ""
    readonly: bool = True
    environment: str = "development"


@app.post("/api/connections/databases")
def create_database(body: DatabaseIn):
    return db.insert(app.state.conn, "databaseconnection", body.model_dump())


@app.get("/api/connections/databases")
def list_databases():
    return db.fetch_all(app.state.conn, "databaseconnection")


@app.post("/api/connections/databases/{database_id}/test")
def test_database_connection(database_id: str, actor: str = "mir Y"):
    row = db.fetch_one(app.state.conn, "databaseconnection", database_id)
    if row is None:
        raise HTTPException(404, "database not found")
    result = test_database(row["credential_ref"], row["host"], row["port"], row["db_type"])
    audit.record(
        app.state.conn,
        kind="connection_test",
        actor=actor,
        target_type="database",
        target_id=database_id,
        environment=row.get("environment"),
        detail={"ok": result["ok"], "stage": result["stage"], "latency_ms": result["latency_ms"]},
    )
    db.update(app.state.conn, "databaseconnection", database_id,
              {"status": "online" if result["ok"] else "offline"})
    return result


# ---------- 项目（§A10.3） ----------

class ProjectIn(BaseModel):
    name: str
    path: str = ""
    repository_url: str = ""
    default_branch: str = "main"
    environment: str = "development"
    description: str = ""


@app.post("/api/projects")
def create_project(body: ProjectIn):
    return db.insert(app.state.conn, "project", body.model_dump())


@app.get("/api/projects")
def list_projects():
    return db.fetch_all(app.state.conn, "project")


# ---------- 任务（§A10.4） ----------

class TaskIn(BaseModel):
    title: str
    user_request: str
    context_type: str = "server"
    context_id: str = ""
    risk_level: str = "L1"
    created_by: str = "mir Y"


@app.post("/api/tasks")
def create_task(body: TaskIn):
    return db.insert(app.state.conn, "agenttask", body.model_dump())


@app.get("/api/tasks")
def list_tasks():
    return db.fetch_all(app.state.conn, "agenttask")


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    row = db.fetch_one(app.state.conn, "agenttask", task_id)
    if row is None:
        raise HTTPException(404, "task not found")
    return row


# ---------- 审批（§A10.5） ----------

class ApprovalIn(BaseModel):
    task_id: str
    tool_execution_id: str = ""
    operation_description: str
    risk_level: str = "L3"
    impact: str = ""
    rollback_plan: str = ""


@app.post("/api/approvals")
def create_approval(body: ApprovalIn):
    return db.insert(app.state.conn, "approvalrequest", body.model_dump())


@app.get("/api/approvals")
def list_approvals():
    return db.fetch_all(app.state.conn, "approvalrequest")


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, approved_by: str = "mir Y"):
    row = db.update(
        app.state.conn,
        "approvalrequest",
        approval_id,
        {"status": "approved", "approved_by": approved_by, "approved_at": db.now()},
    )
    if row is None:
        raise HTTPException(404, "approval not found")
    return row


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, rejected_reason: str = "User rejected the action."):
    row = db.update(
        app.state.conn,
        "approvalrequest",
        approval_id,
        {"status": "rejected", "rejected_reason": rejected_reason},
    )
    if row is None:
        raise HTTPException(404, "approval not found")
    return row


# ---------- 上下文用量（§B5.1 ContextRing 数据源） ----------

class UsageIn(BaseModel):
    """agent-server / 前端上报一次 LLM 调用的原始 usage（各家字段不同，后端归一化）。"""
    task_id: str
    session_id: str = ""
    model: str = ""
    model_context_limit: int | None = None
    usage: dict[str, Any]


@app.post("/api/tasks/{task_id}/context-usage")
def record_context_usage(task_id: str, body: UsageIn):
    payload = normalize_usage(body.usage, model_context_limit=body.model_context_limit)
    row = db.insert(app.state.conn, "contextusage", {
        "task_id": task_id,
        "session_id": body.session_id,
        "model": body.model,
        "raw": body.usage,
        **payload,
    })
    return {**row, "ring_state": ring_state(payload["context_used_percent"])}


@app.get("/api/tasks/{task_id}/context-usage")
def get_context_usage(task_id: str):
    rows = [r for r in db.fetch_all(app.state.conn, "contextusage") if r["task_id"] == task_id]
    if not rows:
        raise HTTPException(404, "该任务还没有用量记录")
    latest = rows[0]
    return {**latest, "ring_state": ring_state(latest["context_used_percent"])}


# ---------- 权限档位（§A6.5） ----------

class PermissionIn(BaseModel):
    environment: str
    target: str
    acknowledged: bool = False
    env_confirm: str | None = None
    actor: str = "mir Y"


@app.get("/api/session/{session_id}/permission")
def get_permission(session_id: str, environment: str = "production"):
    if environment not in DEFAULT_BY_ENV:
        raise HTTPException(422, f"未知环境：{environment}")
    sp = store.get(session_id, environment)
    return {"session_id": session_id, "environment": environment, "tier": sp.tier,
            "expires_at": sp.expires_at, "tiers": list(TIERS)}


@app.post("/api/session/{session_id}/permission")
def change_permission(session_id: str, body: PermissionIn):
    if body.environment not in DEFAULT_BY_ENV:
        raise HTTPException(422, f"未知环境：{body.environment}")
    try:
        record = store.change(
            session_id,
            body.environment,
            body.target,
            acknowledged=body.acknowledged,
            env_confirm=body.env_confirm,
        )
    except PermissionDenied as exc:
        # 被闸门拒绝的升级尝试同样要留痕（安全事件，不是噪音）
        audit.record(app.state.conn, kind=audit.KIND_PERMISSION, actor=body.actor,
                     target_type="session", target_id=session_id,
                     tier=body.target, environment=body.environment,
                     detail={"kind": "denied", "reason": str(exc), "from": None, "to": body.target})
        raise HTTPException(422, str(exc))
    record["actor"] = body.actor
    record["at"] = time.time()
    audit.record(app.state.conn, kind=audit.KIND_PERMISSION, actor=body.actor,
                 target_type="session", target_id=session_id,
                 tier=body.target, environment=body.environment,
                 detail={"kind": record["kind"], "from": record["from"], "to": record["to"]})
    return record


# ---------- 审计查询（§A6.5.5） ----------

@app.get("/api/audit")
def query_audit(kind: str | None = None, limit: int = 100):
    return audit.list_events(app.state.conn, kind=kind, limit=limit)
