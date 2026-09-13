"""用量归一化与 ContextRing 端点测试（§B5.1）。"""
from __future__ import annotations

import pytest

from ops_pilot.server.usage import normalize_usage, ring_state


def test_deepseek_fields():
    out = normalize_usage(
        {"prompt_tokens": 21200, "completion_tokens": 6800,
         "prompt_cache_hit_tokens": 18900, "prompt_cache_miss_tokens": 2300},
        model_context_limit=131072,
    )
    assert out["cache_hit_tokens"] == 18900
    assert out["cache_miss_tokens"] == 2300
    assert out["cache_hit_ratio"] == pytest.approx(89.15, abs=0.01)
    assert out["context_used_tokens"] == 28000
    assert out["context_used_percent"] == pytest.approx(21.4, abs=0.1)


def test_anthropic_fields():
    out = normalize_usage(
        {"input_tokens": 1000, "output_tokens": 200,
         "cache_read_input_tokens": 800, "cache_creation_input_tokens": 200}
    )
    assert (out["cache_hit_tokens"], out["cache_miss_tokens"]) == (800, 200)
    assert out["cache_hit_ratio"] == 80.0
    assert out["context_used_percent"] is None      # 未提供上限时不给百分比


def test_openai_nested_details():
    out = normalize_usage(
        {"prompt_tokens": 1000, "completion_tokens": 100,
         "prompt_tokens_details": {"cached_tokens": 600}}
    )
    assert out["cache_hit_tokens"] == 600
    assert out["cache_miss_tokens"] == 400
    assert out["cache_hit_ratio"] == 60.0


def test_no_cache_info_is_zero_not_error():
    out = normalize_usage({"prompt_tokens": 500, "completion_tokens": 50})
    assert out["cache_hit_tokens"] == 0
    assert out["cache_miss_tokens"] == 500
    assert out["cache_hit_ratio"] == 0.0


@pytest.mark.parametrize("pct,expected", [
    (None, "unknown"), (0, "ok"), (69.9, "ok"), (70, "warning"),
    (90, "warning"), (90.1, "critical"), (100, "critical"),
])
def test_ring_state_thresholds(pct, expected):
    assert ring_state(pct) == expected


def test_endpoint_roundtrip():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from ops_pilot.server import db
    from ops_pilot.server.app import app

    app.state.conn = db.connect()
    client = TestClient(app)

    body = {
        "task_id": "task-1", "session_id": "s1", "model": "deepseek-chat",
        "model_context_limit": 131072,
        "usage": {"prompt_tokens": 21200, "completion_tokens": 6800,
                  "prompt_cache_hit_tokens": 18900, "prompt_cache_miss_tokens": 2300},
    }
    r = client.post("/api/tasks/task-1/context-usage", json=body)
    assert r.status_code == 200
    assert r.json()["ring_state"] == "ok"

    r = client.get("/api/tasks/task-1/context-usage")
    assert r.status_code == 200
    assert r.json()["cache_hit_ratio"] == pytest.approx(89.15, abs=0.01)

    # 高占用 → 环变红
    body["usage"] = {"prompt_tokens": 120000, "completion_tokens": 8000}
    body["model_context_limit"] = 131072
    r = client.post("/api/tasks/task-1/context-usage", json=body)
    assert r.json()["ring_state"] == "critical"

    # 未上报过的任务 → 404
    assert client.get("/api/tasks/none/context-usage").status_code == 404
