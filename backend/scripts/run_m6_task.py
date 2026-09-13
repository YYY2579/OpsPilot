"""M6 端到端验证：通过后端 API 创建并同步运行一次任务，检查 16 态投影与落库。

用法（backend/ 下）：
    python scripts/run_m6_task.py

会真实调用模型与目标主机（消耗少量 token）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from ops_pilot.server import db, settings  # noqa: E402

settings.load_env()

from fastapi.testclient import TestClient  # noqa: E402

from ops_pilot.server.app import app  # noqa: E402

DB_FILE = BACKEND / "opspilot_m6_test.db"
if DB_FILE.exists():
    DB_FILE.unlink()
app.state.conn = db.connect(str(DB_FILE))
client = TestClient(app)

print("=" * 90)
resp = client.post("/api/tasks/run", json={
    "server_id": "hk-ubuntu",
    "user_request": "检查这台服务器的健康状态，用 anomalies 判断是否正常",
    "tier": "requested_approval",
    "environment": "production",
    "async_run": False,          # 同步，便于直接看最终状态
})
print("POST /api/tasks/run ->", resp.status_code)
task = resp.json()
task_id = task["id"]
print(json.dumps({k: v for k, v in task.items() if k in
                  ("id", "title", "status", "current_step", "state", "elapsed_s", "mode")},
                 ensure_ascii=False, indent=2))

print("-" * 90)
state = client.get(f"/api/tasks/{task_id}/state").json()
print("最终状态投影：", json.dumps(state, ensure_ascii=False))
print("状态迁移链：")
for step in state.get("history", []):
    print(f"  {step['state']:<16} {step['reason']}")

print("-" * 90)
events = client.get(f"/api/tasks/{task_id}/events").json()
print(f"事件数：{len(events)}")
for e in events[:12]:
    print(f"  [{e['state']:<16}] {e['kind']:<12} {str(e['message'])[:70]}")

print("-" * 90)
rows = [r for r in db.fetch_all(app.state.conn, "toolexecution") if r["task_id"] == task_id]
print(f"工具执行记录：{len(rows)} 条")
for r in rows:
    print(f"  {r['tool_name']:<24} 风险 {r['risk_level']:<4} tier={r['tier']:<20} 批准方式={r['approval_kind']}")

print("-" * 90)
task_row = db.fetch_one(app.state.conn, "agenttask", task_id)
print("任务落库：", json.dumps({k: task_row[k] for k in
      ("id", "status", "current_step", "risk_level")}, ensure_ascii=False))

persist = BACKEND / "conversations" / task_id
print("会话事件落盘目录存在：", persist.exists(),
      "| 文件数：", len(list(persist.rglob("*"))) if persist.exists() else 0)
print("=" * 90)
