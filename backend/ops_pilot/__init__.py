"""OpsPilot 运维工具包。

分层（测试策略见 docs/开发任务拆解.md M1）：
- ops_pilot.credentials   凭据解析与脱敏（纯逻辑，无 SDK 依赖）
- ops_pilot.ssh           SSH 命令执行适配器（paramiko 延迟导入）
- ops_pilot.tools.health  健康快照采集 + 异常判断（纯逻辑，无 SDK 依赖）
- ops_pilot.tools.get_server_health.definition  OpenHands SDK 胶水层

铁律（需求开发文档 §A6.4）：凭据只在 Executor 内部使用，禁止进入
prompt / Observation / 日志；异常判断在 Executor 内完成，不交给 LLM。
"""
