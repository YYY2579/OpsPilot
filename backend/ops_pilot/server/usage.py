"""LLM 用量归一化（规格 §B5.1 / ContextRing 数据源）。

三家提供商的缓存字段名不同，必须在这里统一：
- DeepSeek : prompt_cache_hit_tokens / prompt_cache_miss_tokens
- Anthropic: cache_read_input_tokens / cache_creation_input_tokens
- OpenAI   : prompt_tokens_details.cached_tokens（未命中 = prompt_tokens - cached）
"""
from __future__ import annotations

from typing import Any


def _get(d: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in d and d[key] is not None:
            return int(d[key])
    return None


def normalize_usage(raw: dict[str, Any], *, model_context_limit: int | None = None) -> dict[str, Any]:
    """把任意提供商的 usage 字典归一化成统一结构。"""
    input_tokens = _get(raw, "prompt_tokens", "input_tokens") or 0
    output_tokens = _get(raw, "completion_tokens", "output_tokens") or 0

    hit = _get(raw, "prompt_cache_hit_tokens", "cache_read_input_tokens")
    miss = _get(raw, "prompt_cache_miss_tokens", "cache_creation_input_tokens")
    if hit is None:
        details = raw.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens") if isinstance(details, dict) else None
        if cached is not None:
            hit = int(cached)
            miss = max(0, input_tokens - hit)
    if hit is None:
        hit = 0
    if miss is None:
        miss = max(0, input_tokens - hit)

    total_measured = hit + miss
    ratio = round(hit / total_measured * 100, 2) if total_measured else None

    used = input_tokens + output_tokens
    pct = None
    if model_context_limit:
        pct = round(used / model_context_limit * 100, 1)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "context_used_tokens": used,
        "model_context_limit": model_context_limit,
        "context_used_percent": pct,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        "cache_hit_ratio": ratio,
    }


def ring_state(percent: float | None) -> str:
    """ContextRing 颜色档（§B5.1 阈值：<70 绿 / 70–90 琥珀 / >90 红）。"""
    if percent is None:
        return "unknown"
    if percent > 90:
        return "critical"
    if percent >= 70:
        return "warning"
    return "ok"
