"""把 OpenHands SDK 事件归一化成内部 Event（states.py 的输入）。

归一化的意义：状态投影层不依赖 SDK，换框架/升版本时只改本文件。
事件类型依据《源码索引》§2.1。
"""
from __future__ import annotations

from typing import Any

from ops_pilot.runtime.states import Event


def _name(event: Any) -> str:
    return type(event).__name__


def normalize(event: Any) -> Event | None:
    """SDK 事件 → 内部 Event；与任务状态无关的事件返回 None。

    **按属性判断优于按类名判断**：状态同步事件的类名可能随版本变化，
    但它一定带 `key`/`value` 两个字段。
    """
    # 状态同步事件（优先级最高，且不依赖类名）
    key = getattr(event, "key", None)
    if key == "execution_status":
        value = getattr(event, "value", None)
        # **坑**：ConversationExecutionStatus 是 (str, Enum)。Python 3.11+ 下
        # str(member) 会得到 "ConversationExecutionStatus.WAITING_FOR_CONFIRMATION"，
        # 不是 "waiting_for_confirmation" —— 必须取 .value，否则状态事件全被丢掉。
        raw = getattr(value, "value", value)
        return Event(kind="status", status=str(raw).lower() if raw is not None else None)

    name = _name(event)

    if name == "ActionEvent":
        tool = getattr(event, "tool_name", None)
        action = getattr(event, "action", None)
        payload: dict[str, Any] = {}
        if action is not None:
            try:
                payload = action.model_dump()
            except Exception:  # noqa: BLE001
                payload = {}
        summary = getattr(event, "summary", "") or ""
        risk = getattr(event, "security_risk", None)
        return Event(
            kind="action", tool=tool, text=summary, ok=True,
            payload={"action": payload, "security_risk": getattr(risk, "value", str(risk) if risk else None)},
        )

    if name == "ObservationEvent":
        tool = getattr(event, "tool_name", None)
        observation = getattr(event, "observation", None)
        payload: dict[str, Any] = {}
        if observation is not None:
            try:
                payload = observation.model_dump()
            except Exception:  # noqa: BLE001
                payload = {}
        return Event(kind="observation", tool=tool, payload=payload)

    if name == "AgentErrorEvent":
        return Event(kind="tool_error", tool=getattr(event, "tool_name", None),
                     text=getattr(event, "error", "") or "", ok=False)

    if name == "UserRejectObservation":
        return Event(kind="reject", tool=getattr(event, "tool_name", None),
                     text=getattr(event, "rejection_reason", "") or "")

    if name == "MessageEvent":
        source = getattr(event, "source", "")
        if source != "agent":
            return None                      # 用户消息不推进状态（由 runner 显式处理）
        try:
            text = event.to_llm_message().content[0].text  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            text = ""
        return Event(kind="message", text=(text or "")[:2000])

    return None
