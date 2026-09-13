"""会话执行器（M6-2 的后端半边）。

职责：起一次真会话（OpenHands SDK 进程内），把事件投影成 16 态并落库。

**架构位置**：规格 §A3 的组装式方案里，"跑 Agent"这件事最终归属
agent-server（HTTP/WebSocket）。本次先做**进程内实现**把端到端链路打通，
`ConversationRunner` 就是那个接缝 —— 将来换成 agent-server 客户端时，
只需另写一个实现，上层 API 与前端不用改。

落库：agenttask（状态/进度）+ toolexecution（每次工具调用）+ taskevent（事件流）。
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


class ConversationRunner:
    """一次任务 = 一次会话。默认在后台线程里跑，不阻塞 API。"""

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
        # 会话事件落盘目录：不设的话框架会用 InMemoryFileStore，事件不持久化
        self.persist_root = persist_root or os.path.join(workspace_root or os.getcwd(), "conversations")
        self.on_event = on_event
        self._lock = threading.Lock()
        self._proj: dict[str, Projection] = {}

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
        self._record(row["id"], "status", TaskState.RECEIVED.value, "任务已创建", {})
        return row

    def start_task_async(self, **kwargs: Any) -> dict:
        row = self.start_task(**kwargs)
        thread = threading.Thread(target=self._run_guarded, args=(row["id"], kwargs), daemon=True)
        thread.start()
        return row

    def _run_guarded(self, task_id: str, kwargs: dict) -> None:
        try:
            self.run(task_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 线程里必须兜底，否则状态永远停在 running
            self._apply(InternalEvent(kind="tool_error", tool="runner", text=str(exc)), task_id)
            db.update(self.conn, "agenttask", task_id, {"status": "failed"})

    def run(self, task_id: str, *, user_request: str, server_id: str,
            tier: str = TIER_REQUESTED, environment: str = "production",
            title: str | None = None,          # 仅 start_task 使用；此处忽略（容错）
            max_iterations: int = 30, timeout_s: int = 300) -> dict:
        """阻塞执行一次会话（由 start_task_async 在后台线程调用）。"""
        if not self.api_key:
            raise RunnerError("缺少模型 API key（.env 或环境变量 DEEPSEEK_API_KEY）")

        from openhands.sdk import LLM, Agent, Conversation
        from pydantic import SecretStr

        import ops_pilot.tools.register_all as tools_reg
        from ops_pilot.security.analyzer import OpsPilotSecurityAnalyzer
        from ops_pilot.security.policy import policy_for_tier

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

        conversation = Conversation(
            agent=Agent(llm=llm, tools=tools_reg.tool_specs()),
            callbacks=[on_sdk_event],
            workspace=workspace,
            persistence_dir=persist_dir,      # 不传则框架用 InMemoryFileStore，事件不落盘
        )
        # 权限档位 → 确认策略（§A6.5.1）。
        # **必须先装 analyzer**：否则框架把所有动作当 UNKNOWN → 映射成 L4 →
        # 只读工具也要确认，会话会在第一步就停住（真实踩过）。
        conversation.set_security_analyzer(OpsPilotSecurityAnalyzer())
        conversation.set_confirmation_policy(policy_for_tier(tier))

        started = time.time()
        conversation.send_message(
            f"目标主机 server_id 为 {server_id}。{user_request}\n"
            f"请先用只读工具采集事实再做判断；需要变更时说明影响与回滚方案。"
        )
        conversation.run()

        elapsed = round(time.time() - started, 1)
        proj = self._proj.setdefault(task_id, Projection())
        # 会话循环返回即代表这一轮结束：若停在非终态（通常是 REPORT），补一个终态，
        # 否则任务会永远显示"进行中"（真实踩过）。
        if proj.state not in TERMINAL:
            if proj.state == TaskState.FAILED:
                pass
            else:
                proj.state = TaskState.COMPLETED
                proj.history.append((TaskState.COMPLETED.value, "会话循环结束"))
        status = {"COMPLETED": "completed", "FAILED": "failed",
                  "CANCELLED": "cancelled", "TIMEOUT": "timeout"}.get(proj.state.value, "running")
        db.update(self.conn, "agenttask", task_id,
                  {"status": status, "current_step": proj.state.value, "completed_at": db.now()})
        self._record(task_id, "runner", proj.state.value,
                     f"会话结束，用时 {elapsed}s", {"elapsed_s": elapsed, "cost": getattr(llm.metrics, "accumulated_cost", None)})
        return {"task_id": task_id, "state": proj.state.value, "elapsed_s": elapsed}

    def cancel(self, task_id: str) -> dict:
        proj = self._proj.get(task_id)
        if proj is not None:
            cancel(proj)
            self._record(task_id, "user", proj.state.value, "用户取消", {})
        db.update(self.conn, "agenttask", task_id, {"status": "cancelled"})
        return {"task_id": task_id, "state": TaskState.CANCELLED.value}

    # ---------- 内部 ----------

    def _apply(self, ev: InternalEvent, task_id: str) -> None:
        proj = self._proj.setdefault(task_id, Projection())
        before = proj.state
        project(proj, ev)
        payload = dict(ev.payload)
        if ev.text:
            payload.setdefault("text", ev.text)

        if ev.kind == "action":
            payload["tier"] = None      # 由 runner 补充（见 run 里 set_confirmation_policy）
            db.insert(self.conn, "toolexecution", {
                "task_id": task_id,
                "tool_name": ev.tool,
                "target_type": "server",
                "target_id": payload.get("server_id", ""),
                "arguments": payload.get("action", {}),
                "status": "running",
                "risk_level": level_of(ev.tool or "").value,
                "tier": os.environ.get("OPSPILOT_TIER", TIER_REQUESTED),
                "approval_kind": "tier_auto" if before != TaskState.WAITING_APPROVAL else "manual",
            })

        if proj.state != before:
            self._record(task_id, "state", proj.state.value, f"{before.value} → {proj.state.value}", payload)
            db.update(self.conn, "agenttask", task_id, {"current_step": proj.state.value})
        else:
            self._record(task_id, ev.kind, proj.state.value, ev.text or ev.tool or "", payload)

        if self.on_event is not None:
            try:
                self.on_event({"task_id": task_id, "kind": ev.kind, "state": proj.state.value})
            except Exception:  # noqa: BLE001
                pass

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
