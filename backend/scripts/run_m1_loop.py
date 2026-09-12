"""M1 闭环脚本：在 SDK 进程内直接起一次真会话，跑通 get_server_health。

用法（在 backend/ 下）：
    python scripts/run_m1_loop.py

前置：
- key.txt（OpsPilot 根目录）：DEEPSEEK_API_KEY=... 或裸 sk-...（脚本读取，绝不打印）
- OpsPilot/.env（可选）：OPSPILOT_HK_UBUNTU_HOST / _USERNAME / _PASSWORD 或 _KEY_PATH

验收对应（任务拆解 M1-4）：
识别服务器 → 调结构化工具 → SSH 异常清晰报错 → 不泄密 → 有任务/成本记录。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # OpsPilot/
BACKEND = Path(__file__).resolve().parents[1]       # OpsPilot/backend
sys.path.insert(0, str(BACKEND))

# ---------- 1. 密钥装载（绝不打印内容） ----------
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file(ROOT / "key.txt")
_load_env_file(ROOT / ".env")

api_key = (
    os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("LLM_API_KEY")
    or next((ln.strip() for ln in (ROOT / "key.txt").read_text(encoding="utf-8").splitlines()
             if ln.strip().startswith("sk-")), None)
)
if not api_key:
    sys.exit("缺少 DeepSeek API key（key.txt 或 DEEPSEEK_API_KEY）")

os.environ.setdefault("DEEPSEEK_API_KEY", api_key)

# SSH 凭据（可能没有——没有也能跑：工具会返回清晰的 SSH 错误，Agent 如实上报）
ssh_secrets: list[str] = []
prefix = "OPSPILOT_HK_UBUNTU"
if os.environ.get(f"{prefix}_PASSWORD"):
    ssh_secrets.append(os.environ[f"{prefix}_PASSWORD"])
key_path = os.environ.get(f"{prefix}_KEY_PATH")
if key_path and os.path.isfile(key_path):
    ssh_secrets.append(Path(key_path).read_text(encoding="utf-8"))

# ---------- 2. SDK ----------
from openhands.sdk import (  # noqa: E402
    Agent,
    Conversation,
    Event,
    LLM,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.tool import Tool  # noqa: E402
from pydantic import SecretStr  # noqa: E402

import ops_pilot.tools.get_server_health.definition  # noqa: F401,E402  注册工具
from ops_pilot.credentials import assert_no_secrets  # noqa: E402

logger = get_logger(__name__)

llm = LLM(
    usage_id="agent",
    model=os.environ.get("LLM_MODEL", "deepseek/deepseek-chat"),
    base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
    api_key=SecretStr(api_key),
)

tools = [Tool(name="get_server_health")]
agent = Agent(llm=llm, tools=tools)

serialized_events: list[str] = []


def on_event(event: Event) -> None:
    try:
        serialized_events.append(event.model_dump_json())
    except Exception:  # noqa: BLE001 - 序列化失败不中断会话
        pass
    if isinstance(event, LLMConvertibleEvent):
        logger.info("event: %s", type(event).__name__)
    else:
        logger.info("state update: %s", type(event).__name__)


workspace = tempfile.mkdtemp(prefix="opspilot-m1-")
conversation = Conversation(agent=agent, callbacks=[on_event], workspace=workspace)

# 凭据进 SecretRegistry（框架负责 env 注入与 <secret-hidden> 脱敏）
if ssh_secrets:
    conversation.update_secrets({"HK_UBUNTU_SECRET": ssh_secrets[0]})

conversation.send_message(
    "用 get_server_health 工具检查 server_id 为 hk-ubuntu 的主机健康状态，"
    "读取返回的 JSON 并给出结论：如果 anomalies 非空，按条列出原因和建议。"
)
conversation.run()

print("=" * 90)
print("会话结束。")

# ---------- 3. 泄密检查（§A6.4 第 6 条） ----------
all_text = "\n".join(serialized_events)
try:
    assert_no_secrets(all_text, tuple(ssh_secrets) + (api_key,))
    print("泄密检查：通过（所有事件中不含 API key 与 SSH 凭据）")
except AssertionError as exc:
    print("泄密检查：失败！")
    print(exc)
    sys.exit(2)

print(f"成本：{llm.metrics.accumulated_cost}")
print("会话目录：", workspace)
