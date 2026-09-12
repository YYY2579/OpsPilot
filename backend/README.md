# OpsPilot 后端（M1：第一个运维工具）

> 结构与测试策略见《开发任务拆解.md》M1；工具契约见《OpsPilot-需求开发文档.md》§A5.2 / §A6.4 / §A6.5。

## 分层

| 模块 | 职责 | 依赖 OpenHands SDK？ |
|---|---|---|
| `ops_pilot/credentials.py` | `credential_ref` → SSH 连接信息；`mask` / `assert_no_secrets` | 否 |
| `ops_pilot/ssh/client.py` | SSH 命令执行（paramiko 延迟导入）；错误三分类 auth / network / command | 否（paramiko 延迟导入） |
| `ops_pilot/tools/health.py` | 健康快照采集 + **异常判断（§A5.2：不交给 LLM）** | 否 |
| `ops_pilot/tools/get_server_health/definition.py` | OpenHands SDK 胶水（Action / Observation / Executor / ToolDefinition / register_tool） | **是**（extras `sdk`） |

纯逻辑与 SDK 胶水分离的目的：**单元测试不需要装 SDK**；SDK 契约用 `test_sdk_contract.py` 单独验证。

## 运行测试

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"            # 纯逻辑测试（不需要 SDK）
.venv\Scripts\pytest

# SDK 契约测试（需要 openhands-sdk）
.venv\Scripts\pip install "openhands-sdk==1.47.0"
.venv\Scripts\pytest tests/test_sdk_contract.py
```

## 环境变量（M1 阶段凭据来源）

```text
OPSPILOT_HK_UBUNTU_HOST=192.168.1.10
OPSPILOT_HK_UBUNTU_PORT=22
OPSPILOT_HK_UBUNTU_USERNAME=deploy
OPSPILOT_HK_UBUNTU_KEY_PATH=C:\path\to\id_ed25519     # 或 _PASSWORD
```

> 生产/真实部署时改用密钥环或 SecretRegistry（§A6.4），本模块的 Resolver 接口不变。

## 泄密检查（§A6.4 第 6 条）

`tests/test_credentials.py::test_leak_detector_catches_password_in_prompt` 模拟
"凭据串出现在输出里"的场景；接入 SDK 后，还需用真实会话把**完整 prompt** 打印出来
再跑一次 `assert_no_secrets`（见任务拆解 M1-2）。
