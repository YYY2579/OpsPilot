# OpsPilot 生产级能力盘点

> 更新时间：2026-09-14
> 盘点方式：静态代码审计 + 离线自检脚本，非文档自述
> 自检命令：`python backend/scripts/check_capabilities.py`

---

## 一、当前状态（自检实测）

```
工具总数：26（只读 22 + 写 4），声明与实现完全对齐
能力矩阵：已实现 20 / 部分实现 1 / 缺失 0
错误码：50 个，覆盖 9 个故障层次
```

### 工具清单

| 场景 | 工具 |
|---|---|
| ①日常巡检 | `get_server_health` `get_disk_usage` `get_process_list` `get_service_status` `list_docker_containers` `get_container_logs` `list_databases` `list_tables` `describe_table` `query_readonly` `explain_sql` |
| ②故障排查 | `get_service_logs` `check_port` `check_http` |
| ③K8s 排障 | `list_namespaces` `list_pods` `get_pod_logs` `get_events` `rollout_status` |
| ④变更操作 | `restart_service` `scale_workload` `rollback_deploy` `run_change_script` |
| ⑤告警响应 | `list_alerts` `inspect_alert` `query_metrics` |
| 网络 | `check_port` `check_http` |

> 注：K8s 工具不在本机放 kubeconfig，一律 SSH 到"装有 kubectl 的机器"执行（安全设计）。

---

## 二、本轮补齐的能力

### 1. 诊断结论体系 `backend/ops_pilot/diagnostics/`

统一 `Diagnosis` 结构，**所有工具返回结论而非原始输出**：

| 字段 | 含义 |
|---|---|
| `ok` | 是否成功 |
| `layer` | 故障层次（host/service/container/k8s/database/network/alerting/change/capability） |
| `code` | 错误码（50 个，见 `codes.py`） |
| `summary` | 一句话结论（人话） |
| `evidence` | 证据列表（命令/查询 + 实际返回值，可复核） |
| `fix_steps` | 有序修复步骤（可执行） |
| `impact` | 影响范围 |
| `rollback` | 回滚方案（写操作必填） |

**未实现能力必须显式标注**：`not_implemented(capability, reason)`，禁止编造结果。

### 2. 告警接入 `tools/alerting.py`（此前 0 覆盖）

Prometheus + Alertmanager **真实 HTTP 接入**：

- `list_alerts` —— 查活跃告警（可按级别/服务过滤）
- `inspect_alert` —— 定位单条告警：读详情 + 查关联指标 + **量化影响范围**（`count(up{service=..})` 真实查询）
- `query_metrics` —— 执行 PromQL

原则：**查不到就明确报错，绝不用假数据冒充"没有告警"**。

### 3. 受控变更 `tools/change.py`（此前只有 1 个重启）

- `rollout_status`（只读）—— 滚动更新卡住诊断
- `scale_workload` —— 扩缩容
- `rollback_deploy` —— K8s 回滚（`rollout undo`，支持指定 revision）
- `run_change_script` —— 通用变更（部署/Ansible/自定义脚本）

四条安全红线：

1. **dry_run 默认 True**：不显式传 `dry_run=False` 就只预演
2. **回滚方案必填**：无回滚命令直接拒绝（`CHANGE_NO_ROLLBACK_PLAN`）
3. **L3 审批**：`destructiveHint=True`，人工确认
4. **全程审计**：执行前记录回滚点

### 4. 修复的缺陷

**K8s 4 个工具此前未注册**：`list_pods` / `get_pod_logs` / `get_events` / `list_namespaces` 代码已实现，
但不在 `register_all.py` 的工具列表里，**Agent 根本调用不到**。已修复。

---

## 三、仍然缺失的是「真实接入」，不是代码

代码层已无缺口，现在缺的是**把你真实环境接进来**。

### 必填接入信息

| 项 | 需要什么 | 影响的能力 |
|---|---|---|
| **A. 云服务器 SSH** | IP/域名、端口、登录用户、认证方式（密钥路径或密码）、sudo 方式 | 巡检、故障排查、服务启停、变更 |
| **B. K8s（k3s）** | 在服务器装好 k3s 后提供 kubeconfig 所在主机（工具通过 SSH 到该机执行 kubectl） | K8s 排障、扩缩容、回滚 |
| **C. 监控告警** | Prometheus 地址（:9090）、Alertmanager 地址（:9093）、认证方式 | 告警响应（当前已实现，但无地址即不可用） |
| **D. LLM 凭据** | `LLM_API_KEY` 或 `DEEPSEEK_API_KEY`、模型名、base_url | Agent 大脑（缺失则任务无法执行） |
| **E. 部署方式** | 部署脚本/命令 + 对应回滚命令 | 服务发布（执行通道已就绪，只差脚本） |

### 可选

| 项 | 说明 |
|---|---|
| 数据库只读账号 | 主机、端口、账号、可访问库范围 |
| 堡垒机配置 | 若主机不可直连 |
| 高危命令黑名单 | 你环境绝对禁止执行的命令 |

---

## 四、未完成事项

1. **运行环境未修复**：`.venv` 缺 fastapi 等依赖、pip/pytest 损坏 → 后端起不来（用户选择"先补代码，环境最后统一处理"）
2. **桌面壳未接后端**：`API_BASE` 为空串，且壳内不含 Python 后端 → 需要 sidecar 方案才能真正分发
3. **前端 3 处 mock 未替换**：`Sidebar`(假资源树)、`Stream`(假对话流)、`App`(currentStateId)
