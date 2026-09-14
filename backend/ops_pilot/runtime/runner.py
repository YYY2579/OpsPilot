"""会话执行器（M6-2 / M6-3 的后端半边）。

职责：起一次真会话（OpenHands SDK 进程内），把事件投影成 16 态并落库；
**支持审批中断与恢复**（M6-3）。

## 恢复语义（依据框架源码）
`agent._step()`（software-agent-sdk `agent/agent.py` L653-663）第一步就检查
`ConversationState.get_unmatched_actions(state.active_branch())`：**有未匹配的
pending action 就直接执行**（隐式确认）。所以：

- **批准 = 再调一次 `conversation.run()`** —— pending action 会被执行；
- **拒绝 = `conversation.reject_pending_actions(reason)`** 再 run()，动作变成
  UserRejectObservation，Agent 据此换方案。

## 架构位置与限制
规格 §A3 的组装式方案里"跑 Agent"最终归属 agent-server；当前是**进程内实现**，
`ConversationRunner` 即接缝。限制：会话对象保存在进程内存里，
**进程重启后无法恢复待审批的会话**（待接 agent-server 后由服务端持久化解决）。

落库：agenttask + toolexecution + taskevent + approvalrequest。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any, Callable

from ops_pilot.runtime.events import normalize
from ops_pilot.runtime.states import Event as InternalEvent
from ops_pilot.runtime.states import (
    TERMINAL,
    Projection,
    TaskState,
    cancel,
    project,
)
from ops_pilot.server import db
from ops_pilot.server.permission import TIER_REQUESTED
from ops_pilot.security.guard import level_of


class RunnerError(RuntimeError):
    pass


#: 写工具的"影响 / 回滚"模板（审批卡要展示，§5.7）
_APPROVAL_TEMPLATES: dict[str, dict[str, str]] = {
    "restart_service": {
        "impact": "目标服务会中断数秒（重启期间请求失败）",
        "rollback": "服务未能正常启动时，用 systemctl status 查原因并回滚上一版本配置",
    },
    "restart_container": {
        "impact": "容器内服务中断 5～15 秒",
        "rollback": "重新启动原容器；失败则回滚上一镜像 tag",
    },
}


class ConversationRunner:
    """一次任务 = 一次会话。默认后台线程执行；待审批时挂起等待恢复。"""

    def __init__(
        self,
        conn,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        workspace_root: str | None = None,
        persist_root: str | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        self.conn = conn
        self.model = model or os.environ.get("LLM_MODEL", "deepseek/deepseek-chat")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY")
        self.persist_root = persist_root or os.path.join(workspace_root or os.getcwd(), "conversations")
        self.on_event = on_event
        self._lock = threading.Lock()
        self._proj: dict[str, Projection] = {}
        self._live: dict[str, Any] = {}        # task_id → live Conversation（待审批时挂起）
        self._tier: dict[str, str] = {}
        #: task_id → {tool_name: [toolexecution_id, ...]}：已发出 action、尚未收到
        #: observation/error/reject 的工具行。**必须收口**，否则审计表永远停在
        #: "running"，把已完成的只读巡检误报成"还在跑"（真实踩过）。
        self._open_tools: dict[str, dict[str, list[str]]] = {}

    # ---------- 任务生命周期 ----------

    def start_task(self, *, title: str, user_request: str, server_id: str,
                   tier: str = TIER_REQUESTED, environment: str = "production") -> dict:
        row = db.insert(self.conn, "agenttask", {
            "title": title,
            "user_request": user_request,
            "context_type": "server",
            "context_id": server_id,
            "status": "queued",
            "risk_level": level_of("get_server_health").value,
            "current_step": TaskState.RECEIVED.value,
            "created_by": "mir Y",
        })
        with self._lock:
            self._proj[row["id"]] = Projection()
            self._tier[row["id"]] = tier
        self._record(row["id"], "status", TaskState.RECEIVED.value, "任务已创建", {})
        return row

    def start_task_async(self, **kwargs: Any) -> dict:
        row = self.start_task(**kwargs)
        threading.Thread(target=self._run_guarded, args=(row["id"], kwargs), daemon=True).start()
        return row

    def _run_guarded(self, task_id: str, kwargs: dict) -> None:
        try:
            self.run(task_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 线程里必须兜底，否则状态永远停在 running
            self._apply(InternalEvent(kind="tool_error", tool="runner", text=str(exc)), task_id)
            self._close_all_open(task_id, status="error")
            db.update(self.conn, "agenttask", task_id, {"status": "failed"})

    def run(self, task_id: str, *, user_request: str, server_id: str,
            tier: str = TIER_REQUESTED, environment: str = "production",
            title: str | None = None,          # 仅 start_task 使用；此处忽略（容错）
            max_iterations: int = 30, timeout_s: int = 300) -> dict:
        """执行一次会话（阻塞；待审批时返回 waiting_approval）。"""
        if not self.api_key:
            raise RunnerError("缺少模型 API key（.env 或环境变量 DEEPSEEK_API_KEY）")

        from openhands.sdk import LLM, Agent, Conversation
        from pydantic import SecretStr

        import ops_pilot.tools.register_all as tools_reg
        from ops_pilot.security.analyzer import OpsPilotSecurityAnalyzer
        from ops_pilot.security.policy import policy_for_tier

        self._tier[task_id] = tier
        db.update(self.conn, "agenttask", task_id, {"status": "running"})

        llm = LLM(usage_id="agent", model=self.model, base_url=self.base_url,
                  api_key=SecretStr(self.api_key))
        workspace = tempfile.mkdtemp(prefix="opspilot-task-")
        persist_dir = os.path.join(self.persist_root, task_id)
        os.makedirs(persist_dir, exist_ok=True)

        def on_sdk_event(event: Any) -> None:
            internal = normalize(event)
            if internal is not None:
                self._apply(internal, task_id)

        # **关键**：OpenHands 自带的通用开发工具（terminal / file_editor / task_tracker）
        # 必须和我们的运维工具一起注册，否则 Agent 只能做运维、不能自由写代码
        # （规格 §A1.1："保留通用开发能力"）。
        #
        # SDK 1.47 起，`default_tool_specs()` 只返回 **声明**（Tool(name=...)，不注册实现），
        # 其 docstring 明确指向 `openhands.tools.preset.default.get_default_tools`
        # 作为"同时注册实现"的构造函数（来自 openhands-tools 独立包）。
        # 直接用 specs 会在 resolve_tool 抛 KeyError: ToolDefinition 'terminal' is not
        # registered（真实踩过）。
        from openhands.tools.preset.default import get_default_tools

        dev_tools = get_default_tools()
        conversation = Conversation(
            agent=Agent(llm=llm, tools=[*dev_tools, *tools_reg.tool_specs()]),
            callbacks=[on_sdk_event],
            workspace=workspace,
            persistence_dir=persist_dir,      # 不传则框架用 InMemoryFileStore，事件不落盘
        )
        # **必须先装 analyzer**：否则框架把所有动作当 UNKNOWN → 映射成 L4 →
        # 只读工具也要确认，会话会在第一步就停住（真实踩过）。
        conversation.set_security_analyzer(OpsPilotSecurityAnalyzer())
        conversation.set_confirmation_policy(policy_for_tier(tier))

        with self._lock:
            self._live[task_id] = conversation

        started = time.time()
        conversation.send_message(
            f"目标主机 server_id 为 {server_id}。{user_request}\n"
            f"请先用只读工具采集事实再做判断；需要变更时说明影响与回滚方案。"
        )
        return self._drive(task_id, conversation, started=started, tier=tier)

    def resume(self, task_id: str, *, accept: bool, reason: str = "") -> dict:
        """审批后续跑：批准=再 run()；拒绝=reject_pending_actions + run()。"""
        with self._lock:
            conversation = self._live.get(task_id)
        if conversation is None:
            raise RunnerError("该会话已不在内存中（进程重启或已结束），无法恢复")
        tier = self._tier.get(task_id, TIER_REQUESTED)

        if accept:
            self._record(task_id, "approval", TaskState.WAITING_APPROVAL.value,
                         "用户已批准，继续执行", {"accept": True})
        else:
            conversation.reject_pending_actions(reason or "User rejected the action.")
            self._record(task_id, "approval", TaskState.WAITING_APPROVAL.value,
                         f"用户拒绝：{reason or '未说明'}", {"accept": False, "reason": reason})
        db.update(self.conn, "agenttask", task_id, {"status": "running"})
        return self._drive(task_id, conversation, started=time.time(), tier=tier)

    # ---------- 内部：驱动 + 收尾 ----------

    def _drive(self, task_id: str, conversation: Any, *, started: float, tier: str) -> dict:
        conversation.run()
        proj = self._proj.setdefault(task_id, Projection())

        # 兜底：**以框架的 pending action 为准**判断是否在等确认。
        # 这样即使状态事件没送达（我们曾因枚举取值踩过），审批闭环也不会丢。
        if self._pending_action(conversation)[0] is not None and \
                proj.state not in TERMINAL and proj.state != TaskState.WAITING_APPROVAL:
            proj.state = TaskState.WAITING_APPROVAL
            proj.history.append((TaskState.WAITING_APPROVAL.value, "存在待确认动作（框架判定）"))
            proj.approvals += 1

        if proj.state == TaskState.WAITING_APPROVAL:
            approval = self._create_approval(task_id, conversation)
            db.update(self.conn, "agenttask", task_id, {
                "status": "waiting_approval", "current_step": proj.state.value})
            return {"task_id": task_id, "state": proj.state.value,
                    "approval_id": approval["id"], "waiting": True}

        elapsed = round(time.time() - started, 1)
        # 会话循环返回即代表这一轮结束：若停在非终态（通常是 REPORT），补一个终态，
        # 否则任务会永远显示"进行中"（真实踩过）。
        if proj.state not in TERMINAL:
            proj.state = TaskState.COMPLETED
            proj.history.append((TaskState.COMPLETED.value, "会话循环结束"))
        status = {"COMPLETED": "completed", "FAILED": "failed",
                  "CANCELLED": "cancelled", "TIMEOUT": "timeout"}.get(proj.state.value, "running")
        db.update(self.conn, "agenttask", task_id,
                  {"status": status, "current_step": proj.state.value, "completed_at": db.now()})
        # 会话已结束，任何仍处 running 的工具行都不该继续挂着
        self._close_all_open(task_id, status="unknown")
        self._record(task_id, "runner", proj.state.value,
                     f"会话结束，用时 {elapsed}s", {"elapsed_s": elapsed, "tier": tier})
        with self._lock:
            self._live.pop(task_id, None)      # 会话结束后不再持有
        return {"task_id": task_id, "state": proj.state.value, "elapsed_s": elapsed, "waiting": False}

    def _create_approval(self, task_id: str, conversation: Any) -> dict:
        """从会话的 pending action 生成审批单（供前端渲染审批卡，§5.7）。"""
        tool_name, action_args = self._pending_action(conversation)
        level = level_of(tool_name or "")
        template = _APPROVAL_TEMPLATES.get(tool_name or "", {})
        detail = " · ".join(f"{k}={v}" for k, v in action_args.items() if v not in ("", None))
        extra = f"；另有 {self._pending_count - 1} 个动作同时在等待" if self._pending_count > 1 else ""
        row = db.insert(self.conn, "approvalrequest", {
            "task_id": task_id,
            "tool_execution_id": "",
            "operation_description": (f"{tool_name}（{detail}）{extra}" if tool_name
                                      else "待确认的操作"),
            "risk_level": level.value,
            "impact": template.get("impact", "该操作会改变目标系统的状态"),
            "rollback_plan": template.get("rollback", "按工具输出与备份回滚"),
            "status": "pending",
        })
        self._record(task_id, "approval", TaskState.WAITING_APPROVAL.value,
                     "已生成审批单，等待人工确认",
                     {"approval_id": row["id"], "tool": tool_name, "level": level.value,
                      **action_args})
        return row

    #: 永不产生 observation、也永不需确认的动作（与框架 _requires_user_confirmation
    #: L1058-1062 的豁免保持一致）。**不过滤掉的话，会话结束时它们会被当成
    #: "待确认动作"，凭空多出一个审批单**（真实踩过）。
    _NO_CONFIRM_ACTIONS = frozenset({"FinishAction", "ThinkAction"})
    #: 上一次 _pending_action 看到的 pending 动作总数（用于审批单提示）
    _pending_count: int = 0

    @classmethod
    def _pending_action(cls, conversation: Any) -> tuple[str | None, dict[str, Any]]:
        """读取框架里未匹配、且**确实需要确认**的 pending action。"""
        try:
            from openhands.sdk.conversation.state import ConversationState

            state = getattr(conversation, "state", None)
            if state is None:
                return None, {}
            pending = [
                ev for ev in ConversationState.get_unmatched_actions(state.active_branch())
                if type(getattr(ev, "action", None)).__name__ not in cls._NO_CONFIRM_ACTIONS
                and getattr(ev, "tool_name", None) not in ("finish", "think")
            ]
            if not pending:
                return None, {}
            # 框架会把同一条 LLM 响应里的**全部** pending 动作一起扣住，其中可能只有
            # 一个高危。审批单必须展示**风险最高**的那个，否则会出现"审批的是只读工具"
            # 这种荒谬情况（真实踩过）。
            from ops_pilot.security.levels import RiskLevel

            order = {RiskLevel.L0: 0, RiskLevel.L1: 1, RiskLevel.L2: 2,
                     RiskLevel.L3: 3, RiskLevel.L4: 4, RiskLevel.L5: 5}
            ev = max(pending, key=lambda e: order[level_of(getattr(e, "tool_name", "") or "")])
            cls._pending_count = len(pending)
            action = getattr(ev, "action", None)
            args: dict[str, Any] = {}
            if action is not None:
                try:
                    args = {k: v for k, v in action.model_dump().items()
                            if k != "kind" and isinstance(v, (str, int, float, bool))}
                except Exception:  # noqa: BLE001
                    args = {}
            return getattr(ev, "tool_name", None), args
        except Exception:  # noqa: BLE001
            return None, {}

    def cancel(self, task_id: str) -> dict:
        proj = self._proj.get(task_id)
        if proj is not None:
            cancel(proj)
            self._record(task_id, "user", proj.state.value, "用户取消", {})
        db.update(self.conn, "agenttask", task_id, {"status": "cancelled"})
        self._close_all_open(task_id, status="cancelled")
        return {"task_id": task_id, "state": TaskState.CANCELLED.value}

    def _apply(self, ev: InternalEvent, task_id: str) -> None:
        proj = self._proj.setdefault(task_id, Projection())
        before = proj.state
        project(proj, ev)
        payload = dict(ev.payload)
        if ev.text:
            payload.setdefault("text", ev.text)

        if ev.kind == "action":
            tier = self._tier.get(task_id, TIER_REQUESTED)
            tool_row = db.insert(self.conn, "toolexecution", {
                "task_id": task_id,
                "tool_name": ev.tool,
                "target_type": "server",
                "target_id": payload.get("action", {}).get("server_id", ""),
                "arguments": payload.get("action", {}),
                "status": "running",
                "risk_level": level_of(ev.tool or "").value,
                "tier": tier,
                "approval_kind": "manual" if before == TaskState.WAITING_APPROVAL else "tier_auto",
            })
            # 登记待收口的工具行；同一工具可能连续调用多次，用列表保序配对。
            # 一并记住起始时刻，收口时才能落真实的 duration_ms（否则审计里
            # 每条耗时都是空的，"这个操作花了多久"无从回答）。
            self._open_tools.setdefault(task_id, {}).setdefault(ev.tool or "", []).append(
                (tool_row["id"], time.perf_counter()))

        elif ev.kind in ("observation", "tool_error", "reject"):
            # 工具执行已结束 → 收回该工具最早的一条待收口记录（FIFO 配对）。
            self._close_tool(task_id, ev, payload)

        if proj.state != before:
            self._record(task_id, "state", proj.state.value,
                         f"{before.value} → {proj.state.value}", payload)
            db.update(self.conn, "agenttask", task_id, {"current_step": proj.state.value})
        else:
            self._record(task_id, ev.kind, proj.state.value, ev.text or ev.tool or "", payload)

        if self.on_event is not None:
            try:
                self.on_event({"task_id": task_id, "kind": ev.kind, "state": proj.state.value})
            except Exception:  # noqa: BLE001
                pass

    #: 与 tool 状态对应的终态映射
    _CLOSE_STATUS = {"observation": "success", "tool_error": "error", "reject": "rejected"}

    def _close_tool(self, task_id: str, ev: InternalEvent, payload: dict) -> None:
        """把已结束的工具执行行从 running 收口为终态。

        observation → success；tool_error → error；reject → rejected。
        找不到登记（如进程重启后补齐事件）则静默跳过，不影响主流程。
        """
        queue = self._open_tools.get(task_id, {}).get(ev.tool or "")
        if not queue:
            return
        row_id, started = queue.pop(0)
        if not queue:                                  # 该工具已无待收口行，清理空列表
            self._open_tools.get(task_id, {}).pop(ev.tool or "", None)
        patch: dict[str, Any] = {
            "status": self._CLOSE_STATUS.get(ev.kind, "success"),
            "result": payload if isinstance(payload, dict) else {},
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        if ev.text:
            patch["result"] = {**patch["result"], "text": ev.text[:2000]}
        db.update(self.conn, "toolexecution", row_id, patch)

    def _close_all_open(self, task_id: str, status: str = "unknown") -> None:
        """会话结束时收口所有仍处 running 的工具行，避免留下"永远的 running"。"""
        remaining = self._open_tools.pop(task_id, None) or {}
        for queue in remaining.values():
            for row_id, started in queue:
                db.update(self.conn, "toolexecution", row_id,
                          {"status": status,
                           "duration_ms": int((time.perf_counter() - started) * 1000),
                           "result": {"note": "会话结束前未收到结果事件"}})

    def _record(self, task_id: str, kind: str, state: str, message: str, payload: dict) -> None:
        db.insert(self.conn, "taskevent", {
            "task_id": task_id, "kind": kind, "state": state,
            "message": message, "payload": payload,
        })

    def projection(self, task_id: str) -> dict:
        proj = self._proj.get(task_id)
        if proj is None:
            row = db.fetch_one(self.conn, "agenttask", task_id)
            if row is None:
                raise RunnerError("task not found")
            return {"state": row.get("current_step") or TaskState.RECEIVED.value,
                    "internal": False, "terminal": False, "history": [],
                    "tool_calls": 0, "approvals": 0, "rejections": 0}
        return proj.to_dict()

    def events(self, task_id: str, limit: int = 200) -> list[dict]:
        rows = [r for r in db.fetch_all(self.conn, "taskevent") if r["task_id"] == task_id]
        out = []
        for r in reversed(rows[:limit]):
            item = dict(r)
            raw = item.get("payload")
            if isinstance(raw, str):
                try:
                    item["payload"] = json.loads(raw)
                except json.JSONDecodeError:
                    item["payload"] = {}
            out.append(item)
        return out
