"""审计记录（§A6.5.5 / §A6.4）。

三类必须留痕的事件：
- credential_resolve：每次凭据解析（谁/何时/为哪个 server_id）——注意只记引用，不记密钥
- permission_change ：权限档位变更（who / when / from / to / env / session）
- tool_execution    ：工具执行（含 tier 与 approval_kind，M3/M6 接入）
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ops_pilot.server import db

KIND_CREDENTIAL = "credential_resolve"
KIND_PERMISSION = "permission_change"
KIND_TOOL = "tool_execution"


def record(
    conn: sqlite3.Connection,
    *,
    kind: str,
    actor: str = "system",
    target_type: str = "",
    target_id: str = "",
    tier: str | None = None,
    environment: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict:
    """写入一条审计记录。detail 必须是**脱敏后**的内容（不得含密钥）。"""
    return db.insert(conn, "auditevent", {
        "kind": kind,
        "actor": actor,
        "target_type": target_type,
        "target_id": target_id,
        "tier": tier,
        "environment": environment,
        "detail": detail or {},
    })


def list_events(conn: sqlite3.Connection, *, kind: str | None = None, limit: int = 100) -> list[dict]:
    rows = db.fetch_all(conn, "auditevent", order="created_at DESC")
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    out = []
    for r in rows[:limit]:
        item = dict(r)
        raw = item.get("detail")
        if isinstance(raw, str):
            try:
                item["detail"] = json.loads(raw)
            except json.JSONDecodeError:
                item["detail"] = {"raw": raw}
        out.append(item)
    return out


def make_credential_hook(conn: sqlite3.Connection, actor: str = "system"):
    """给 CredentialResolver 用的回调：每次解析留痕（只记引用与主机，不记密钥）。"""

    def _hook(info: dict[str, Any]) -> None:
        record(
            conn,
            kind=KIND_CREDENTIAL,
            actor=actor,
            target_type="server",
            target_id=str(info.get("server_id", "")),
            detail=info,          # 调用方保证这里已经是 redacted 视图
        )

    return _hook
