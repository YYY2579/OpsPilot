"""任务状态投影：把 SDK 事件流映射成规格 §A7 的 16 个业务状态。

**为什么需要这一层**：框架的执行状态只有 8 个值（idle/running/paused/
waiting_for_confirmation/finished/error/stuck/deleting，见《源码索引》§2.2），
而产品规格要求 16 个可展示的业务状态。两者是**不同维度**：

- 框架状态 = "会话循环在干什么"
- 业务状态 = "这次运维任务进行到哪一步"

本模块是**纯函数式 reducer**：输入归一化事件，输出新状态。不依赖 SDK，便于单测。

设计原则（与规格 §A7.1「UI 如何呈现」一致）：
- 一半状态是内部决策态（CLASSIFY_TASK / SELECT_CONTEXT / ANALYZE），屏幕不单独显示
- 状态只前进不后退，除了 WAITING_APPROVAL → EXECUTE / ANALYZE 这条环路
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskState(str, Enum):
    RECEIVED = "RECEIVED"                     # 收到用户请求
    CLASSIFY_TASK = "CLASSIFY_TASK"           # 判断任务类型（内部态）
    SELECT_CONTEXT = "SELECT_CONTEXT"         # 选定目标资源（内部态）
    PLAN = "PLAN"                             # 产出执行计划
    INSPECT = "INSPECT"                       # 只读采集
    ANALYZE = "ANALYZE"                       # 分析（内部态）
    PROPOSE_FIX = "PROPOSE_FIX"               # 提出变更方案
    WAITING_APPROVAL = "WAITING_APPROVAL"     # 等待人工审批
    EXECUTE = "EXECUTE"                       # 执行变更
    VERIFY = "VERIFY"                         # 执行后验证
    REPORT = "REPORT"                         # 生成结论
    COMPLETED = "COMPLETED"                   # 正常结束
    FAILED = "FAILED"                         # 失败结束
    CANCELLED = "CANCELLED"                   # 用户取消
    TIMEOUT = "TIMEOUT"                       # 超时
    WAITING_USER = "WAITING_USER"             # 等用户补充信息


#: 终态（不可再迁移）
TERMINAL = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.TIMEOUT}

#: 内部态 —— 屏幕不单独显示（§A7.1）
INTERNAL = {TaskState.CLASSIFY_TASK, TaskState.SELECT_CONTEXT, TaskState.ANALYZE}

#: 只读工具（命中即 INSPECT）；写工具（命中即 PROPOSE_FIX → 需审批）
READ_ONLY_TOOLS = frozenset({
    "get_server_health", "get_disk_usage", "get_process_list", "get_service_status",
    "get_service_logs", "list_docker_containers", "get_container_logs", "check_port",
    "check_http", "list_pods", "list_namespaces", "get_pod_logs", "get_events",
    "list_databases", "list_tables", "describe_table", "query_readonly", "explain_sql",
})


@dataclass
class Event:
    """归一化事件（由 runtime/events.py 从 SDK 事件转换而来）。"""
    kind: str                     # action | observation | tool_error | message | reject | status | timeout
    tool: str | None = None
    text: str = ""
    status: str | None = None     # SDK 的 execution_status 值
    ok: bool = True
    payload: dict = field(default_factory=dict)


@dataclass
class Projection:
    state: TaskState = TaskState.RECEIVED
    history: list[tuple[str, str]] = field(default_factory=list)   # [(state, reason)]
    tool_calls: int = 0
    approvals: int = 0
    rejections: int = 0

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "internal": self.state in INTERNAL,
            "terminal": self.state in TERMINAL,
            "history": [{"state": s, "reason": r} for s, r in self.history],
            "tool_calls": self.tool_calls,
            "approvals": self.approvals,
            "rejections": self.rejections,
        }


def _is_write_tool(tool: str | None) -> bool:
    return bool(tool) and tool not in READ_ONLY_TOOLS


def project(proj: Projection, ev: Event) -> Projection:
    """按事件推进状态。已是终态则不再迁移（除 CANCELLED 覆盖）。"""
    if proj.state in TERMINAL and not (ev.kind == "status" and ev.status == "deleting"):
        return proj

    def move(new: TaskState, reason: str) -> Projection:
        proj.state = new
        proj.history.append((new.value, reason))
        return proj

    if ev.kind == "timeout":
        return move(TaskState.TIMEOUT, "任务超时")

    if ev.kind == "status":
        s = (ev.status or "").lower()
        if s == "waiting_for_confirmation":
            proj.approvals += 1
            return move(TaskState.WAITING_APPROVAL, "框架进入等待确认")
        if s == "finished":
            return move(TaskState.COMPLETED, "会话正常结束")
        if s == "error":
            return move(TaskState.FAILED, "会话报错")
        if s == "paused":
            return move(TaskState.WAITING_USER, "会话暂停")
        return proj

    if ev.kind == "reject":
        proj.rejections += 1
        # 拒绝后回到分析态：Agent 需要换方案
        return move(TaskState.ANALYZE, "用户拒绝/驳回待执行动作")

    if ev.kind == "tool_error":
        return move(TaskState.FAILED, f"工具 {ev.tool} 执行失败")

    if ev.kind == "action":
        proj.tool_calls += 1
        # 判断顺序很关键：**审批通过后的动作无论读写都是"执行"**，
        # 必须先于"写操作 → 提方案"判断，否则写工具永远回不到 EXECUTE。
        if proj.state == TaskState.WAITING_APPROVAL:
            return move(TaskState.EXECUTE, f"审批通过，执行 {ev.tool}")
        if _is_write_tool(ev.tool):
            return move(TaskState.PROPOSE_FIX, f"写操作 {ev.tool}")
        if proj.state == TaskState.RECEIVED:
            move(TaskState.SELECT_CONTEXT, "选定目标资源")
        return move(TaskState.INSPECT, f"只读采集 {ev.tool}")

    if ev.kind == "observation":
        # **注意**：审批通过后框架只补发 Observation，不会重发 ActionEvent
        # （它执行的是此前已发出的那个 pending action）。所以 WAITING_APPROVAL
        # 也必须作为"进入验证"的源状态，否则状态会卡在待审批（真实踩过）。
        if proj.state in (TaskState.EXECUTE, TaskState.WAITING_APPROVAL):
            return move(TaskState.VERIFY, "执行完成，开始验证")
        if proj.state == TaskState.INSPECT:
            return move(TaskState.ANALYZE, "拿到采集结果")
        return proj

    if ev.kind == "message":
        # Agent 给出最终结论 → REPORT（WAITING_APPROVAL / EXECUTE 也要能收尾）
        if proj.state in (TaskState.ANALYZE, TaskState.INSPECT, TaskState.VERIFY,
                          TaskState.PROPOSE_FIX, TaskState.EXECUTE, TaskState.WAITING_APPROVAL):
            return move(TaskState.REPORT, "Agent 输出结论")
        if proj.state == TaskState.RECEIVED:
            move(TaskState.CLASSIFY_TASK, "判断任务类型")
            return move(TaskState.PLAN, "产出计划")
        return proj

    return proj


def cancel(proj: Projection, reason: str = "用户取消") -> Projection:
    if proj.state in TERMINAL:
        return proj
    proj.state = TaskState.CANCELLED
    proj.history.append((TaskState.CANCELLED.value, reason))
    return proj


def user_message(proj: Projection) -> Projection:
    """收到新的用户消息（补充信息）→ 回到分析。"""
    if proj.state in TERMINAL:
        return proj
    if proj.state == TaskState.WAITING_USER:
        proj.state = TaskState.ANALYZE
        proj.history.append((TaskState.ANALYZE.value, "收到用户补充信息"))
    return proj
