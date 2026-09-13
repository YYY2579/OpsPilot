"""调试：确认判定为什么没触发（插桩 analyzer + policy）。"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from ops_pilot.server import db, settings  # noqa: E402

settings.load_env()

from ops_pilot.security.analyzer import OpsPilotSecurityAnalyzer  # noqa: E402
from ops_pilot.security.policy import OpsPilotConfirmationPolicy  # noqa: E402

_orig_risk = OpsPilotSecurityAnalyzer.security_risk
_orig_confirm = OpsPilotConfirmationPolicy.should_confirm


def traced_risk(self, action_event):           # noqa: ANN001
    risk = _orig_risk(self, action_event)
    print(f"  [analyzer] tool={getattr(action_event, 'tool_name', None)!r} → {risk}", flush=True)
    return risk


def traced_confirm(self, risk=None):           # noqa: ANN001
    result = _orig_confirm(self, risk)
    print(f"  [policy] tier={getattr(self, 'tier', None)} risk={risk} → should_confirm={result}",
          flush=True)
    return result


OpsPilotSecurityAnalyzer.security_risk = traced_risk
OpsPilotConfirmationPolicy.should_confirm = traced_confirm

from fastapi.testclient import TestClient  # noqa: E402

from ops_pilot.runtime.runner import ConversationRunner  # noqa: E402
from ops_pilot.server.app import app  # noqa: E402

DB = BACKEND / "opspilot_debug.db"
if DB.exists():
    DB.unlink()
conn = db.connect(str(DB))
app.state.conn = conn
client = TestClient(app)

print("=" * 80)
resp = client.post("/api/tasks/run", json={
    "server_id": "hk-ubuntu",
    "user_request": "用 restart_service、dry_run=true 检查 nginx 能否重启，只演练不真重启",
    "tier": "requested_approval",
    "async_run": False,
})
task = resp.json()
print("结果：", {k: task.get(k) for k in ("state", "status", "approval_id", "waiting")})
print("投影：", client.get(f"/api/tasks/{task['id']}/state").json()["state"])
print("审批单数：", len(client.get("/api/approvals").json()))
print("=" * 80)
