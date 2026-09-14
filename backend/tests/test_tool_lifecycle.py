"""工具执行记录的生命周期：必须收口，不能永远停在 running。

真实踩过：`toolexecution.status` 在 action 时写入 "running"，但没有任何
代码在收到 observation 后把它改为终态 —— 审计表把已完成的只读巡检
永久标成"正在执行"，前端看板据此显示错误的运行中状态。
"""
from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from ops_pilot.runtime.runner import ConversationRunner  # noqa: E402
from ops_pilot.runtime.states import Event as InternalEvent  # noqa: E402
from ops_pilot.server import db  # noqa: E402


@pytest.fixture
def runner():
    conn = db.connect()
    r = ConversationRunner(conn)
    return r


def _rows(runner, task_id):
    return [row for row in db.fetch_all(runner.conn, "toolexecution")
            if row["task_id"] == task_id]


def test_observation_closes_tool_as_success(runner):
    task_id = "t-obs"
    runner._apply(InternalEvent(kind="action", tool="get_server_health"), task_id)
    assert _rows(runner, task_id)[0]["status"] == "running"

    runner._apply(InternalEvent(kind="observation", tool="get_server_health",
                                payload={"output": "ok"}), task_id)
    row = _rows(runner, task_id)[0]
    assert row["status"] == "success"
    assert "output" in row["result"] or "output" in str(row["result"])


def test_tool_error_closes_tool_as_error(runner):
    task_id = "t-err"
    runner._apply(InternalEvent(kind="action", tool="get_disk_usage"), task_id)
    runner._apply(InternalEvent(kind="tool_error", tool="get_disk_usage",
                                text="command failed"), task_id)
    row = _rows(runner, task_id)[0]
    assert row["status"] == "error"
    assert "command failed" in str(row["result"])


def test_reject_closes_tool_as_rejected(runner):
    task_id = "t-rej"
    runner._apply(InternalEvent(kind="action", tool="restart_service"), task_id)
    runner._apply(InternalEvent(kind="reject", tool="restart_service",
                                text="用户拒绝"), task_id)
    assert _rows(runner, task_id)[0]["status"] == "rejected"


def test_repeated_calls_pair_fifo(runner):
    """同一工具连续调用两次，两次 observation 应分别收口各自的行。"""
    task_id = "t-fifo"
    runner._apply(InternalEvent(kind="action", tool="get_server_health"), task_id)
    runner._apply(InternalEvent(kind="action", tool="get_server_health"), task_id)
    rows = _rows(runner, task_id)
    assert len(rows) == 2 and all(r["status"] == "running" for r in rows)

    runner._apply(InternalEvent(kind="observation", tool="get_server_health"), task_id)
    done = [r for r in _rows(runner, task_id) if r["status"] != "running"]
    assert len(done) == 1, "第一次 observation 只应收口一条"

    runner._apply(InternalEvent(kind="observation", tool="get_server_health"), task_id)
    assert all(r["status"] == "success" for r in _rows(runner, task_id))


def test_close_all_open_marks_remaining_unknown(runner):
    task_id = "t-leftover"
    runner._apply(InternalEvent(kind="action", tool="get_server_health"), task_id)
    runner._close_all_open(task_id, status="unknown")
    row = _rows(runner, task_id)[0]
    assert row["status"] == "unknown"
    assert row["duration_ms"] is not None, "收口时必须补上真实耗时"


def test_duration_recorded_on_success(runner):
    """审计里的 duration_ms 必须是真实耗时，不能留空。"""
    import time as _t

    task_id = "t-dur"
    runner._apply(InternalEvent(kind="action", tool="get_server_health"), task_id)
    _t.sleep(0.05)
    runner._apply(InternalEvent(kind="observation", tool="get_server_health"), task_id)
    row = _rows(runner, task_id)[0]
    assert row["duration_ms"] is not None and row["duration_ms"] >= 50


def test_unmatched_observation_is_noop(runner):
    """没有对应 action 的 observation（如重启后补发）不应抛异常。"""
    runner._apply(InternalEvent(kind="observation", tool="ghost_tool"), "t-ghost")


def test_orphan_reconciliation_marks_interrupted():
    """重启后遗留的 running 任务/工具行必须被改成如实的 interrupted/unknown。"""
    from ops_pilot.server.app import _reconcile_orphans

    conn = db.connect()
    task = db.insert(conn, "agenttask", {"title": "被杀的任务", "status": "running",
                                         "current_step": "INSPECT"})
    tool = db.insert(conn, "toolexecution", {"task_id": task["id"],
                                            "tool_name": "get_server_health",
                                            "status": "running"})
    _reconcile_orphans(conn)
    assert db.fetch_one(conn, "agenttask", task["id"])["status"] == "interrupted"
    assert db.fetch_one(conn, "toolexecution", tool["id"])["status"] == "unknown"


def test_orphan_reconciliation_leaves_terminal_rows_alone():
    from ops_pilot.server.app import _reconcile_orphans

    conn = db.connect()
    task = db.insert(conn, "agenttask", {"title": "已完成", "status": "completed",
                                         "current_step": "COMPLETED"})
    tool = db.insert(conn, "toolexecution", {"task_id": task["id"],
                                            "tool_name": "get_server_health",
                                            "status": "success"})
    _reconcile_orphans(conn)
    assert db.fetch_one(conn, "agenttask", task["id"])["status"] == "completed"
    assert db.fetch_one(conn, "toolexecution", tool["id"])["status"] == "success"
