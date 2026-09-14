"""16 态业务投影测试（§A7）。

纯逻辑，不依赖 SDK —— 事件用 runtime.states.Event 直接构造。
"""
from __future__ import annotations

import pytest

from ops_pilot.runtime.states import (
    INTERNAL,
    READ_ONLY_TOOLS,
    TERMINAL,
    Event,
    Projection,
    TaskState,
    cancel,
    project,
    user_message,
)


def feed(*events: Event, start: Projection | None = None) -> Projection:
    proj = start or Projection()
    for ev in events:
        project(proj, ev)
    return proj


def test_initial_state_is_received():
    proj = Projection()
    assert proj.state is TaskState.RECEIVED


def test_first_agent_message_goes_to_plan():
    proj = feed(Event(kind="message", text="我先看一下这台机器的负载情况。"))
    assert proj.state is TaskState.PLAN
    # 中间经过了内部态 CLASSIFY_TASK
    assert [s for s, _ in proj.history][:2] == ["CLASSIFY_TASK", "PLAN"]


def test_readonly_tool_goes_to_inspect_then_analyze():
    proj = feed(
        Event(kind="message", text="开始检查"),
        Event(kind="action", tool="get_server_health"),
    )
    assert proj.state is TaskState.INSPECT
    assert proj.tool_calls == 1
    project(proj, Event(kind="observation", tool="get_server_health"))
    assert proj.state is TaskState.ANALYZE
    assert proj.state in INTERNAL


def test_every_declared_readonly_tool_maps_to_inspect():
    for tool in sorted(READ_ONLY_TOOLS):
        proj = feed(Event(kind="action", tool=tool))
        assert proj.state is TaskState.INSPECT, tool


def test_write_tool_goes_to_propose_fix():
    proj = feed(Event(kind="action", tool="restart_container"))
    assert proj.state is TaskState.PROPOSE_FIX


def test_waiting_for_confirmation_maps_to_waiting_approval():
    proj = feed(Event(kind="status", status="waiting_for_confirmation"))
    assert proj.state is TaskState.WAITING_APPROVAL
    assert proj.approvals == 1


def test_approval_then_execute_then_verify():
    proj = feed(
        Event(kind="action", tool="restart_container"),
        Event(kind="status", status="waiting_for_confirmation"),
    )
    assert proj.state is TaskState.WAITING_APPROVAL
    project(proj, Event(kind="action", tool="restart_container"))     # 批准后再次发出该动作
    assert proj.state is TaskState.EXECUTE
    project(proj, Event(kind="observation", tool="restart_container"))
    assert proj.state is TaskState.VERIFY


def test_approved_action_observation_goes_to_verify():
    """批准后框架只补发 observation（不重发 action）—— 必须能从 WAITING_APPROVAL 进验证。"""
    proj = Projection()
    project(proj, Event(kind="action", tool="restart_service"))
    project(proj, Event(kind="status", status="waiting_for_confirmation"))
    assert proj.state is TaskState.WAITING_APPROVAL
    project(proj, Event(kind="observation", tool="restart_service"))
    assert proj.state is TaskState.VERIFY
    project(proj, Event(kind="message", text="已完成重启并验证"))
    assert proj.state is TaskState.REPORT


def test_message_from_waiting_approval_can_close():
    proj = Projection()
    project(proj, Event(kind="status", status="waiting_for_confirmation"))
    project(proj, Event(kind="message", text="无需继续，结论如下"))
    assert proj.state is TaskState.REPORT


def test_rejection_returns_to_analyze():
    proj = feed(
        Event(kind="status", status="waiting_for_confirmation"),
        Event(kind="reject", tool="restart_container", text="用户拒绝"),
    )
    assert proj.state is TaskState.ANALYZE
    assert proj.rejections == 1


def test_tool_error_returns_to_analyze_not_failed():
    """工具级错误回到 ANALYZE 让 Agent 自愈，而不是直接判任务失败。

    依据：Agent 的探查天然包含试错（真实案例：先试错一个 server_id、拿到
    "未配置" 后改用正确标识，任务最终产出了完整报告）。若一见工具报错就
    FAILED，巡检任务会被误判。任务级失败由框架 status=error 或会话异常兜底。
    """
    proj = feed(Event(kind="tool_error", tool="list_pods", text="dial tcp timeout"))
    assert proj.state is TaskState.ANALYZE
    assert proj.state not in TERMINAL
    assert proj.errors == 1


def test_status_error_goes_to_failed():
    """真正的任务级失败仍然由框架 status=error 判定为 FAILED（终态）。"""
    proj = feed(Event(kind="status", status="error"))
    assert proj.state is TaskState.FAILED
    assert proj.state in TERMINAL


def test_finished_maps_to_completed_and_is_terminal():
    proj = feed(
        Event(kind="action", tool="get_server_health"),
        Event(kind="observation", tool="get_server_health"),
        Event(kind="message", text="主机健康，无异常"),
        Event(kind="status", status="finished"),
    )
    assert proj.state is TaskState.COMPLETED
    # 终态后事件不再迁移
    project(proj, Event(kind="action", tool="get_server_health"))
    assert proj.state is TaskState.COMPLETED


def test_paused_maps_to_waiting_user_then_back_on_new_message():
    proj = feed(Event(kind="status", status="paused"))
    assert proj.state is TaskState.WAITING_USER
    user_message(proj)
    assert proj.state is TaskState.ANALYZE


def test_timeout_and_cancel():
    assert feed(Event(kind="timeout")).state is TaskState.TIMEOUT
    proj = feed(Event(kind="action", tool="get_server_health"))
    cancel(proj, "用户点了取消")
    assert proj.state is TaskState.CANCELLED
    # 终态不可再取消/迁移
    cancel(proj)
    assert proj.history[-1][1] == "用户点了取消"


def test_unknown_status_is_ignored():
    proj = feed(Event(kind="status", status="stuck"))
    assert proj.state is TaskState.RECEIVED      # stuck 不映射到业务态


def test_internal_and_terminal_sets_match_spec():
    # §A7.1：一半状态是内部决策态，不单独占版面
    assert INTERNAL == {TaskState.CLASSIFY_TASK, TaskState.SELECT_CONTEXT, TaskState.ANALYZE}
    assert TERMINAL == {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.TIMEOUT}


def test_normalize_unwraps_str_enum_status():
    """str-Enum 必须取 .value，否则 execution_status 事件会被整条丢掉。"""
    from enum import Enum

    from ops_pilot.runtime.events import normalize

    class ConversationExecutionStatus(str, Enum):
        WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
        FINISHED = "finished"

    class _Ev:
        key = "execution_status"

        def __init__(self, value):
            self.value = value

    ev = normalize(_Ev(ConversationExecutionStatus.WAITING_FOR_CONFIRMATION))
    assert ev is not None and ev.kind == "status" and ev.status == "waiting_for_confirmation"
    assert feed(ev).state is TaskState.WAITING_APPROVAL

    ev = normalize(_Ev(ConversationExecutionStatus.FINISHED))
    assert ev is not None and ev.status == "finished"

    # 其他 key 不关心（按属性判断，不依赖类名）
    class _Other:
        key = "title"
        value = "x"

    assert normalize(_Other()) is None


def test_projection_to_dict_serializable():
    proj = feed(Event(kind="action", tool="get_disk_usage"))
    d = proj.to_dict()
    assert d["state"] == "INSPECT" and d["internal"] is False and d["terminal"] is False
    assert d["tool_calls"] == 1 and isinstance(d["history"], list)


@pytest.mark.parametrize("tool", ["run_shell", "delete_file", "execute_sql", "restart_service"])
def test_planned_write_tools_are_not_readonly(tool):
    assert tool not in READ_ONLY_TOOLS
    assert feed(Event(kind="action", tool=tool)).state is TaskState.PROPOSE_FIX
