"""SQLite 数据层（M2 骨架：§A9 六张表）。

MVP 用标准库 sqlite3，接口保持薄；后续换 SQLAlchemy 时只动本文件。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS serverconnection (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL, port INTEGER DEFAULT 22,
    username TEXT, auth_type TEXT DEFAULT 'ssh_key', credential_ref TEXT,
    environment TEXT DEFAULT 'development', tags TEXT, description TEXT,
    jump_host_id TEXT, status TEXT DEFAULT 'unknown',
    created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS databaseconnection (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, db_type TEXT DEFAULT 'mysql',
    host TEXT NOT NULL, port INTEGER, username TEXT, credential_ref TEXT,
    database_name TEXT, readonly INTEGER DEFAULT 1, environment TEXT,
    status TEXT DEFAULT 'unknown', created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT, repository_url TEXT,
    default_branch TEXT, environment TEXT, description TEXT,
    created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS agenttask (
    id TEXT PRIMARY KEY, title TEXT, user_request TEXT, context_type TEXT,
    context_id TEXT, status TEXT DEFAULT 'pending', risk_level TEXT,
    current_step TEXT, created_by TEXT, created_at INTEGER, updated_at INTEGER,
    completed_at INTEGER
);
CREATE TABLE IF NOT EXISTS toolexecution (
    id TEXT PRIMARY KEY, task_id TEXT, tool_name TEXT, target_type TEXT,
    target_id TEXT, arguments TEXT, result TEXT, status TEXT,
    exit_code INTEGER, duration_ms INTEGER, risk_level TEXT, approved_by TEXT,
    tier TEXT, approval_kind TEXT, created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS taskevent (
    id TEXT PRIMARY KEY, task_id TEXT, kind TEXT, state TEXT, message TEXT,
    payload TEXT, created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS auditevent (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT DEFAULT 'system',
    target_type TEXT, target_id TEXT, tier TEXT, environment TEXT, detail TEXT,
    created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS contextusage (
    id TEXT PRIMARY KEY, task_id TEXT, session_id TEXT, model TEXT,
    input_tokens INTEGER, output_tokens INTEGER, context_used_tokens INTEGER,
    model_context_limit INTEGER, context_used_percent REAL,
    cache_hit_tokens INTEGER, cache_miss_tokens INTEGER, cache_hit_ratio REAL,
    raw TEXT, created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS approvalrequest (
    id TEXT PRIMARY KEY, task_id TEXT, tool_execution_id TEXT,
    operation_description TEXT, risk_level TEXT, impact TEXT, rollback_plan TEXT,
    status TEXT DEFAULT 'pending', approved_by TEXT, approved_at INTEGER,
    rejected_reason TEXT, created_at INTEGER, updated_at INTEGER
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> int:
    return int(time.time())


def insert(conn: sqlite3.Connection, table: str, row: dict) -> dict:
    row = dict(row)
    row.setdefault("id", new_id())
    row.setdefault("created_at", now())
    row.setdefault("updated_at", row["created_at"])
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(_jsonify(row)))
    conn.commit()
    # 重读：让表默认值（如 agenttask.status='pending'）出现在响应里
    return fetch_one(conn, table, row["id"])


def update(conn: sqlite3.Connection, table: str, row_id: str, patch: dict) -> dict | None:
    row = fetch_one(conn, table, row_id)
    if row is None:
        return None
    patch = dict(patch)
    patch["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in patch)
    conn.execute(f"UPDATE {table} SET {cols} WHERE id = ?", [*_jsonify(patch), row_id])
    conn.commit()
    return fetch_one(conn, table, row_id)


def fetch_one(conn: sqlite3.Connection, table: str, row_id: str) -> dict | None:
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_all(conn: sqlite3.Connection, table: str, order: str = "created_at DESC") -> list[dict]:
    cur = conn.execute(f"SELECT * FROM {table} ORDER BY {order}")
    return [dict(r) for r in cur.fetchall()]


def resolve_server(conn: sqlite3.Connection, ref: str) -> dict | None:
    """按 主键 id / credential_ref（逻辑别名）/ name 任一解析服务器行。

    前端与 Agent 都习惯用逻辑别名（如 `jzz-18`）而不是随机主键 id，
    若只按 id 查会让 /health 这类端点静默 404 —— 这是真实踩过的 bug。
    多个候选时取最近更新的一条（同一逻辑主机的重复注册只保留最新）。
    """
    if not ref:
        return None
    row = fetch_one(conn, "serverconnection", ref)
    if row is not None:
        return row
    cur = conn.execute(
        "SELECT * FROM serverconnection WHERE credential_ref = ? OR name = ?"
        " ORDER BY updated_at DESC, created_at DESC LIMIT 1",
        (ref, ref),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_server(conn: sqlite3.Connection, row: dict) -> dict:
    """按 credential_ref 去重注册：同一逻辑主机重复注册时更新而非新增。"""
    row = dict(row)
    existing = None
    ref = row.get("credential_ref")
    if ref:
        cur = conn.execute(
            "SELECT * FROM serverconnection WHERE credential_ref = ?"
            " ORDER BY created_at ASC LIMIT 1",
            (ref,),
        )
        r = cur.fetchone()
        existing = dict(r) if r else None
    if existing is None:
        return insert(conn, "serverconnection", row)
    # 保留原 id，避免已引用它的任务/审计失去指向；删除此前重复行。
    patch = {k: v for k, v in row.items() if k not in ("id", "created_at")}
    conn.execute(
        "DELETE FROM serverconnection WHERE credential_ref = ? AND id != ?",
        (ref, existing["id"]),
    )
    conn.commit()
    return update(conn, "serverconnection", existing["id"], patch)


def _jsonify(row: dict) -> list:
    out = []
    for v in row.values():
        if isinstance(v, (dict, list)):
            out.append(json.dumps(v, ensure_ascii=False))
        else:
            out.append(v)
    return out
