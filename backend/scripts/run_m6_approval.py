"""M6-3 端到端验证：审批闭环（用 dry_run 保证不动真实服务）。

流程：
1. 起任务，明确要求用 restart_service 的 dry_run=true 演练（不真重启）
2. 因该工具是 L3，在"请求审批"档下必须人工确认 → 任务挂起在 WAITING_APPROVAL
3. 通过 API 查审批单 → 批准
4. 观察会话恢复：EXECUTE → VERIFY → REPORT/COMPLETED

安全：全程 dry_run=true，不会重启任何服务。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from ops_pilot.server import db, settings  # noqa: E402

settings.load_env()

from fastapi.testclient import TestClient  # noqa: E402

from ops_pilot.server.app import app  # noqa: E402

DB_FILE = BACKEND / "opspilot_m63_test.db"
if DB_FILE.exists():
    DB_FILE.unlink()
app.state.conn = db.connect(str(DB_FILE))
client = TestClient(app)

BAR = "=" * 92


def show_state(task_id: str, label: str) -> dict:
    st = client.get(f"/api/tasks/{task_id}/state").json()
    print(f"[{label}] state={st['state']}  tool_calls={st['tool_calls']}  approvals={st['approvals']}")
    return st


print(BAR)
resp = client.post("/api/tasks/run", json={
    "server_id": "hk-ubuntu",
    "user_request": ("请用 restart_service 工具、参数 dry_run=true 检查 nginx 服务是否可重启；"
                     "只做演练，不要真的重启。给出结论即可"),
    "tier": "requested_approval",
    "environment": "production",
    "async_run": False,
})
print("POST /api/tasks/run ->", resp.status_code)
task = resp.json()
task_id = task["id"]
print(json.dumps({k: task.get(k) for k in ("id", "status", "state", "approval_id", "waiting")},
                 ensure_ascii=False, indent=2))

print("-" * 92)
st = show_state(task_id, "挂起后")

print("-" * 92)
approvals = [a for a in client.get("/api/approvals").json() if a["task_id"] == task_id]
if not approvals:
    print("!! 没有生成审批单 —— 审批闭环未触发，检查 analyzer/策略")
    sys.exit(1)
ap = approvals[0]
print("审批单：")
print(json.dumps({k: ap[k] for k in
                  ("id", "task_id", "operation_description", "risk_level", "impact",
                   "rollback_plan", "status")}, ensure_ascii=False, indent=2))

print("-" * 92)
print(f"POST /api/approvals/{ap['id']}/approve ...")
res = client.post(f"/api/approvals/{ap['id']}/approve")
print("审批返回：", res.status_code)
body = res.json()
print("  审批状态:", body["status"], "| 恢复结果:", json.dumps(body["resume"], ensure_ascii=False))

print("-" * 92)
show_state(task_id, "批准后")

print("-" * 92)
events = client.get(f"/api/tasks/{task_id}/events").json()
print(f"事件数：{len(events)}")
for e in events:
    print(f"  [{e['state']:<16}] {e['kind']:<10} {str(e['message'])[:66]}")

print("-" * 92)
rows = [r for r in db.fetch_all(app.state.conn, "toolexecution") if r["task_id"] == task_id]
print(f"工具执行记录：{len(rows)} 条")
for r in rows:
    print(f"  {r['tool_name']:<18} 风险 {r['risk_level']:<4} tier={r['tier']:<20} 批准方式={r['approval_kind']}")

task_row = db.fetch_one(app.state.conn, "agenttask", task_id)
print("-" * 92)
print("任务落库：", json.dumps({k: task_row[k] for k in ("status", "current_step")}, ensure_ascii=False))
print(BAR)
