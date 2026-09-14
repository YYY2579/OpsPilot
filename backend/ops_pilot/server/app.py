"""OpsPilot 后端 API（M2 骨架，§A10 路由）。

职责边界（决策记录 001）：资源管理 / 任务 / 审批 / 审计在这里；
Agent 与工具执行在 OpenHands agent-server —— 本服务不跑 Agent。
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import os
from pathlib import Path

from ops_pilot.credentials import CredentialResolver
from ops_pilot.runtime.runner import ConversationRunner, RunnerError
from ops_pilot.runtime.states import TaskState
from ops_pilot.server import db
from ops_pilot.server import audit, settings
from ops_pilot.server.probe import test_database, test_server
from ops_pilot.server.probe import collect_server_health as probe_health
from ops_pilot.server.usage import normalize_usage, ring_state
from ops_pilot.server.permission import (
    DEFAULT_BY_ENV,
    PermissionDenied,
    PermissionStore,
    TIERS,
)

app = FastAPI(title="OpsPilot Backend", version="0.1.0")
store = PermissionStore()

# ---------- CORS（开发模式前端独立起在 5173/5199 等端口） ----------
# 打包后前端由本服务同源提供（见文件末尾 StaticFiles），但开发时前端跑在
# Vite 上，属跨域。缺这一层会让浏览器静默拒绝所有 API 调用，前端只能显示
# mock（真实踩过：页面显示 CPU 82% 的假数据，而真实值 3.0%）。
#
# 允许来源：默认仅本机开发端口；生产部署经反向代理同源，无需放宽。
# 用显式白名单而非 "*"，避免凭据与内网接口在任意站点下被读取。
_CORS_ORIGINS = [
    o.strip() for o in os.environ.get(
        "OPSPILOT_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5199,http://localhost:5199,"
        "http://tauri.localhost,https://tauri.localhost",
    ).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    settings.load_env()          # 凭据只进内存，不打印（§A6.4）
    app.state.conn = db.connect(os.environ.get("OPSPILOT_DB", "opspilot.db"))
    _reconcile_orphans(app.state.conn)
    _warn_level_drift()


def _warn_level_drift() -> None:
    """启动自检：工具清单与风险等级表若漂移，显式告警。

    漂移的后果不是崩溃，而是"只读工具被误判成高危写操作"，表现为巡检
    任务莫名卡在等待审批 —— 不查日志根本看不出原因。所以在启动时就喊出来。
    """
    from ops_pilot.security.guard import audit_level_table

    missing = audit_level_table()
    if missing:
        print(f"[ops_pilot] ⚠️ 风险等级表缺失登记（将按保守 L4 处理）：{missing}")


#: 进程重启后不可能还在跑的任务态（会话对象在内存里，重启即丢）。
_ORPHAN_TASK_STATUSES = ("pending", "running")
#: 未收到结果事件就随进程消失的工具执行态。
_ORPHAN_TOOL_STATUSES = ("running",)


def _reconcile_orphans(conn) -> None:
    """把重启后遗留的"进行中"记录改成如实的 interrupted，而不是假装还在跑。

    真实踩过：异步任务在进程被杀后永远停在 running，审计表里的工具行也
    永远停在 running —— 看板上显示"正在执行"，其实没有任何东西在执行。
    """
    for row in db.fetch_all(conn, "agenttask"):
        if (row.get("status") or "") in _ORPHAN_TASK_STATUSES:
            db.update(conn, "agenttask", row["id"],
                      {"status": "interrupted", "current_step": "INTERRUPTED"})
    for row in db.fetch_all(conn, "toolexecution"):
        if (row.get("status") or "") in _ORPHAN_TOOL_STATUSES:
            db.update(conn, "toolexecution", row["id"],
                      {"status": "unknown",
                       "result": {"note": "进程重启，未收到结果事件"}})


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
    """注册服务器。按 credential_ref 去重：重复注册同一逻辑主机走更新。"""
    return db.upsert_server(app.state.conn, body.model_dump())


@app.get("/api/connections/servers")
def list_servers():
    return db.fetch_all(app.state.conn, "serverconnection")


@app.get("/api/connections/servers/{server_id}")
def get_server(server_id: str):
    row = db.resolve_server(app.state.conn, server_id)
    if row is None:
        raise HTTPException(404, "server not found")
    return row


@app.post("/api/connections/servers/{server_id}/test")
def test_server_connection(server_id: str, actor: str = "mir Y"):
    """SSH 连接测试。凭据解析会写审计（只记引用与主机，不记密钥）。"""
    row = db.resolve_server(app.state.conn, server_id)
    if row is None:
        raise HTTPException(404, "server not found")
    resolver = CredentialResolver(on_resolve=audit.make_credential_hook(app.state.conn, actor))
    result = test_server(row["credential_ref"], resolver=resolver)
    audit.record(
        app.state.conn,
        kind="connection_test",
        actor=actor,
        target_type="server",
        target_id=row["id"],
        environment=row.get("environment"),
        detail={"ok": result["ok"], "stage": result["stage"], "latency_ms": result["latency_ms"]},
    )
    db.update(app.state.conn, "serverconnection", row["id"],
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


_runner: ConversationRunner | None = None


def get_runner() -> ConversationRunner:
    """进程内单例 runner（将来换成 agent-server 客户端时改这里）。"""
    global _runner
    if _runner is None:
        _runner = ConversationRunner(app.state.conn)
    else:
        _runner.conn = app.state.conn
    return _runner


class RunTaskIn(BaseModel):
    server_id: str
    user_request: str | None = None
    title: str | None = None
    tier: str = "requested_approval"
    environment: str = "production"
    async_run: bool = True


@app.post("/api/tasks/run")
def run_task(body: RunTaskIn):
    """创建并运行一次任务（默认后台线程执行，立即返回 task_id）。"""
    runner = get_runner()
    request = body.user_request or f"检查 server_id 为 {body.server_id} 的主机健康状态并给出结论"
    payload = dict(
        title=body.title or request[:40],
        user_request=request,
        server_id=body.server_id,
        tier=body.tier,
        environment=body.environment,
    )
    if body.async_run:
        row = runner.start_task_async(**payload)
        return {**row, "state": TaskState.RECEIVED.value, "mode": "async"}
    row = runner.start_task(**payload)
    result = runner.run(row["id"], **payload)
    fresh = db.fetch_one(app.state.conn, "agenttask", row["id"]) or row
    return {**fresh, **result, "mode": "sync"}


@app.get("/api/tasks/{task_id}/state")
def get_task_state(task_id: str):
    try:
        return get_runner().projection(task_id)
    except RunnerError:
        raise HTTPException(404, "task not found")


@app.get("/api/tasks/{task_id}/events")
def get_task_events(task_id: str, limit: int = 200):
    return get_runner().events(task_id, limit=limit)


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    return get_runner().cancel(task_id)


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


def _resolve_approval(approval_id: str, *, accept: bool, actor: str, reason: str = "") -> dict:
    """审批落库 + **恢复会话继续执行**（M6-3）。"""
    patch = ({"status": "approved", "approved_by": actor, "approved_at": db.now()}
             if accept else {"status": "rejected", "rejected_reason": reason})
    row = db.update(app.state.conn, "approvalrequest", approval_id, patch)
    if row is None:
        raise HTTPException(404, "approval not found")
    resumed: dict
    try:
        resumed = get_runner().resume(row["task_id"], accept=accept, reason=reason)
    except RunnerError as exc:
        resumed = {"error": str(exc)}       # 会话已不在内存（进程重启）——如实返回
    audit.record(app.state.conn, kind="approval", actor=actor, target_type="approval",
                 target_id=approval_id,
                 detail={"accept": accept, "reason": reason, "task_id": row["task_id"],
                         "resumed": resumed.get("state")})
    return {**row, "resume": resumed}


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, approved_by: str = "mir Y"):
    return _resolve_approval(approval_id, accept=True, actor=approved_by)


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str, rejected_reason: str = "User rejected the action."):
    return _resolve_approval(approval_id, accept=False, actor="mir Y", reason=rejected_reason)


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


# ---------- 数据库树（§B3 侧栏真数据） ----------

@app.get("/api/connections/databases/{database_id}/tree")
def get_database_tree(database_id: str):
    """返回数据库树结构（库 → 表），供侧栏渲染。凭据来自 .env。"""
    row = db.fetch_one(app.state.conn, "databaseconnection", database_id)
    if row is None:
        raise HTTPException(404, "database not found")
    from ops_pilot.db.client import PymysqlRunner
    from ops_pilot.db.credentials import DbCredentialResolver

    resolver = DbCredentialResolver()
    try:
        cred = resolver.resolve(row["credential_ref"])
    except Exception as exc:
        raise HTTPException(422, f"凭据解析失败：{exc}")
    runner = PymysqlRunner(cred)
    try:
        _, dbs = runner.query("SHOW DATABASES")
        tree = []
        for (db_name,) in dbs:
            if db_name in ("information_schema", "performance_schema", "mysql", "sys"):
                continue
            _, tables = runner.query(
                "SELECT table_name, table_rows, engine FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
                (db_name,), limit=500,
            )
            tree.append({
                "name": db_name,
                "table_count": len(tables),
                "tables": [{"name": t[0], "rows": t[1] or 0, "engine": t[2]} for t in tables[:100]],
            })
        return {"database_id": database_id, "host": row["host"], "databases": tree}
    finally:
        runner.close()


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


# ---------- 主机健康快照（前端概览面板的真实数据来源） ----------

@app.get("/api/servers/{server_id}/health")
def server_health(server_id: str):
    """真实采集目标主机健康快照（只读）。

    复用 Agent 工具 `get_server_health` 的同一份纯逻辑，保证界面与 Agent
    看到的数值一致。server_id 支持 主键 id / credential_ref（逻辑别名）/
    name 三种写法。未注册返回 404；凭据缺失返回 ok=false 并附带 stage
    （credential/ssh/collect），不编造指标。
    """
    row = db.resolve_server(app.state.conn, server_id)
    if row is None:
        raise HTTPException(status_code=404, detail="server not found")
    credential_ref = row.get("credential_ref") or row["id"]
    result = probe_health(credential_ref)
    # 注意顺序：probe_health 的返回里也带 server_id（= credential_ref），
    # 若放在后面会把这里的 id 覆盖掉 —— 必须让身份字段最后落定。
    return {**result, "server_id": row["id"], "credential_ref": credential_ref,
            "name": row.get("name"), "host": row.get("host"),
            "environment": row.get("environment")}


# ---------- 前端静态资源（打包后由后端同源提供，避免 CORS） ----------
_frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
