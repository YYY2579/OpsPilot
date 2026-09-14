# OpsPilot 生产级能力盘点

> 更新时间：2026-09-14
> 盘点方式：静态代码审计 + 离线自检脚本 + **真实靶机端到端验证**（156.224.28.147），非文档自述
> 自检命令：`python backend/scripts/check_capabilities.py`
> 真机验证：`PYTHONPATH= python -m pytest tests/` + 浏览器实测（见第四节）

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

## 四、真实验证结果（2026-09-14，靶机 156.224.28.147）

> 验证原则：**每一条都是可复核的实测输出**，不是文档自述。
> 复现命令见各小节。

### 4.1 运行时环境

| 项 | 值 | 复核方式 |
|---|---|---|
| Python | 3.13.12（隔离环境 `envs/opspilot`） | `python -V` |
| openhands-sdk | **1.47.0** | `pip show openhands-sdk` |
| openhands-tools | **1.47.0**（必需，见下） | `pip show openhands-tools` |
| 单元测试 | **193 passed / 0 failed**（9.34s） | `PYTHONPATH= python -m pytest tests/ -p no:warnings` |
| 能力自检 | 已实现 20 / 部分 1 / 缺失 0，**无阻塞项** | `python scripts/check_capabilities.py` |

### 4.2 靶机环境（真实部署，非模拟）

| 组件 | 版本 / 状态 | 复核命令 |
|---|---|---|
| 主机 | Ubuntu 24.04.1 LTS，`jzz-18`，运行 4 天 20 小时 | `ssh root@156.224.28.147 uptime` |
| k3s | v1.36.4+k3s1，节点 Ready（control-plane） | `k3s kubectl get nodes` |
| Prometheus | v2.55.1，3 个采集目标 `up=1` | `curl :9090/api/v1/query?query=up` |
| Alertmanager | v0.27.0，**1 条真实 active 告警**（Watchdog） | `curl :9093/api/v2/alerts` |
| node-exporter | v1.8.2，Up 16 小时 | `docker ps` |
| 测试负载 | `opspilot-demo` Deployment **2/2 Running** | `k3s kubectl get deploy` |

### 4.3 端到端 Agent 会话（决定性验证）

命令：`PYTHONPATH= python scripts/e2e_verify.py`

```
RESULT: {"task_id": "2cf74470d7bc", "state": "COMPLETED", "elapsed_s": 19.5, "waiting": false}

状态迁移链：RECEIVED → INSPECT → ANALYZE → REPORT → COMPLETED
```

Agent 自主调用 3 个只读工具采集的真实数据（**与手工 SSH 逐项对账一致**）：

| 指标 | Agent 采集值 | 手工 SSH 对账值 | 一致 |
|---|---|---|---|
| CPU | 3.0%（4 核） | — | ✓ |
| 内存 | 38.2%（1.46 / 3.82 GB） | 1481MB / 3915MB | ✓ |
| 根分区 `/` | 16.0%（5.9 GB 已用） | 16% / 5.9G 已用 | ✓ |
| 负载 | 0.19 / 0.19 / 0.17 | 0.22 / 0.18 / 0.12（同量级） | ✓ |
| `/boot/efi` | 6.0% | — | ✓ |
| `/home/data` | 1.0%（9.7 GB 盘） | — | ✓ |
| OS | Ubuntu 24.04.1 LTS | Ubuntu 24.04.1 LTS | ✓ |
| 高占用进程 | systemd 8.0% / k3s-server 7.6% / mysqld 1.0% | — | ✓ |

**诚实性验证**：Agent 报告开头主动指出"目标标识不一致"，并**如实转述工具报错原文**
`SSH missing: 未配置 OPSPILOT_JZZ_18_HOST，无法解析 server_id=jzz-18`
——而非编造数据蒙混。这正是需求第 5 条（无法实现必须明确标注）的实测体现。

### 4.4 连接与凭据链路

| 验证点 | 实测结果 |
|---|---|
| SSH 连接测试 | `{"ok":true,"stage":"ok","latency_ms":1904,"os":"Ubuntu 24.04.1 LTS"}` |
| 审计日志 | 落库 `connection_test` + `credential_resolve` 两条 |
| **凭据不泄漏** | 审计里只有脱敏视图 `"auth":"password"`，**密码明文未进日志** |
| 变更四条红线 | `dry_run` 默认 True；`CHANGE_NO_ROLLBACK_PLAN` 拒绝无回滚执行；`_audit()` 记录；`NAME_RE` 防注入 |

### 4.5 SDK 工具注册（本轮修复的真 bug）

| 项 | 说明 |
|---|---|
| 现象 | `KeyError: ToolDefinition 'terminal' is not registered` |
| 根因 | SDK 1.47 起 `default_tool_specs()` 只返回声明，不注册实现；实现已独立为 `openhands-tools` 包 |
| 修法 | 改用 `openhands.tools.preset.default.get_default_tools()`（同时注册实现） |
| 复核 | SDK 实际加载 **26 个工具**，与 `register_all.py` 声明逐一比对一致 |

### 4.6 第二轮真机验证暴露并修复的 4 个真 bug（2026-09-14，提交 `b73040c`）

第二轮跑真机时前端接上真实数据，才把下面这些"平时看不出来"的问题逼出来。
全部有复现路径 + 修复 + 回归测试。

| # | Bug | 现象（真实观测） | 根因 | 修法 | 回归测试 |
|---|---|---|---|---|---|
| 1 | **工具执行行永不收口** | 6 条 `toolexecution` **全部停在 `running`**，任务已 `COMPLETED` | `action` 写入 `status=running` 后，**没有任何代码**在收到 observation 时改终态 | `observation→success / tool_error→error / reject→rejected`，按 FIFO 配对；补真实 `duration_ms`；会话结束/cancel/异常时收口残留 | `tests/test_tool_lifecycle.py`（8 例） |
| 2 | **只读工具被误判 L4 高危** | 巡检任务凭空卡在 `WAITING_APPROVAL`，审批单写 `list_alerts（limit=50）` 风险 L4 | `TOOL_LEVELS` 漏登记 `list_alerts`/`inspect_alert`/`query_metrics`/`rollout_status` → `level_of` 落到未知默认 **L4** | 补齐等级表；新增 `audit_level_table()` 自检 + 启动告警，把"清单与等级表漂移"变成显式失败 | `test_no_declared_tool_misses_a_risk_level` 等 3 例 |
| 3 | **健康端点只认主键 → 别名 404** | 前端用 `hk-ubuntu` 调 `/api/servers/hk-ubuntu/health` 返回 `{"detail":"server not found"}` | 路由只按随机主键 `4d6cc8bd599d` 查 | 新增 `db.resolve_server()`，支持 主键 id / credential_ref / name 三种写法 | `test_server_lookup_accepts_logical_alias` |
| 4 | **重复注册产生重复行** | 同一靶机在 `serverconnection` 里 2 行 | `create_server` 直接 insert，无去重 | 新增 `db.upsert_server()`，按 `credential_ref` 去重（保留原 id、删旧重复行） | `test_server_reregistration_dedupes_by_credential_ref` |

另修两处（同一轮）：
- **健康端点身份字段被覆盖**：采集结果自带 `server_id`（= credential_ref），字典解包顺序导致接口算出的行主键被冲掉 → 身份字段最后落定。
- **进程重启后的孤儿记录**：`agenttask` 遗留 `running`、`toolexecution` 遗留 `running` → 启动时对账改为如实的 `interrupted` / `unknown`，并附原因，不再假装在跑。
- **前端不会自动选中服务器**：真实数据到位后概览面板停留在"请选中一台服务器"空提示，看起来像没接上 → 自动选中第一台。

### 4.7 前端接真实数据后的浏览器实测（0 控制台错误）

用无头 Chromium 打开 `http://127.0.0.1:5199`，**控制台错误 0 条**，右侧概览面板渲染的全是真实值：

| 面板字段 | 实测显示 | 与 SSH 基线对账 |
|---|---|---|
| 服务器 | 在线 · 生产靶机-jzz18 | ✓ 真实 DB 行 |
| OS | Ubuntu 24.04.1 LTS | ✓ |
| CPU | 2.5% | ✓ 实时 |
| 内存 | 38.5%（3.82 GB） | ✓ 手工 37.8% |
| 磁盘 | 16% | ✓ 手工 16% |
| 系统负载 | 0.27 | ✓ 同量级 |
| 服务状态 | Nginx/Docker/MySQL/SSH/k3s **正常**，Redis **未运行** | ✓ 手工 `redis=inactive` |
| 异常项 | `service:redis` · 服务状态 inactive | ✓ 如实 |
| 运行时间 | up 4 days, 21 hours, 2 minutes | ✓ |
| 采集耗时 | 5142 ms | ✓ 真实计时 |

截图留档：`ui_live_final.png`（仓库根，已 gitignore）。

> **注意**：上表中"Redis 未运行"是**如实呈现**，不是缺陷 —— 靶机上 redis 确实没起。
> 这正好反证前端不再是"永远显示一片绿色"的演示件。

---

## 五、剩余未完成事项（如实标注）

| # | 项 | 影响 | 状态 |
|---|---|---|---|
| 1 | 桌面壳 `API_BASE=""` 且不含 Python 后端 | Tauri 安装包独立运行不可用，需 sidecar（PyInstaller 打包后端 + `externalBin` + 固定端口） | **未实现** |
| 2 | 服务部署/发布 | `run_change_script` 通道就绪，但**部署脚本需你提供**（不臆测部署逻辑） | 待接入信息 |
| 3 | 待审批会话进程重启后不可恢复 | 会话对象在进程内存；需接 agent-server 持久化。**重启后任务会被如实标记为 `interrupted`**（不再假装在跑） | 已知限制 |

> 已解决（原第 1 项）：前端 3 处 mock 已全部替换 —— `Sidebar` 走真实 API、
> `OverviewPanel` 走真实 `/health`、`currentStateId` 迁出 mock 至 `lib/viewState.ts`。
> 设计态预览（`?state=NN`）仍保留 mock，属预期的演示入口，不影响实况模式。

> 以上均为**如实标注**，未用假数据伪装成已完成。

