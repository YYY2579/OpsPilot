# OpsPilot 生产级能力盘点与缺口清单

> 生成时间：2026-09-14
> 盘点方式：静态代码审计（函数/Action 类/注册列表逐项核对），非文档自述

---

## 一、现有真实能力（代码级核实）

### 1. 工具层（`ops_pilot/tools/`）

| 模块 | 工具（Action 类） | 执行方式 | 是否注册到 Agent |
|---|---|---|---|
| `get_server_health/` | `get_server_health` | SSH 真执行 + 解析 loadavg/meminfo/df/ps | ✅ |
| `system.py` | `get_disk_usage` `get_process_list` `get_service_status` `get_service_logs` | SSH 真执行 | ✅ |
| `docker.py` | `list_docker_containers` `get_container_logs` | SSH 调 docker CLI | ✅ |
| `database.py` | `list_databases` `list_tables` `describe_table` `query_readonly` `explain_sql` | pymysql 只读 + SQL 白名单校验 | ✅ |
| `network.py` | `check_port` `check_http` | SSH 真探测 | ✅ |
| `service_ops.py` | `restart_service`（写操作，L3 审批） | SSH systemd | ✅ |
| **`k8s.py`** | `list_pods` `get_pod_logs` `get_events` `list_namespaces` | kubectl | ❌ **未注册（缺陷）** |

统计：**19 个工具（18 只读 / 1 写），其中 4 个 K8s 工具未接入 Agent。**

### 2. 执行骨架（`tools/_base.py`）

- `SshReadOnlyExecutor`：凭据**只在 Executor 内部解析**，不进入 Action / Observation / 日志（凭据纪律已落实）
- 异常已区分三类：认证失败 / 网络不通 / 命令失败 —— 是错误码体系的雏形，但**未形成统一错误码表**
- `JsonObservation`：结构化输出给 LLM

### 3. 安全与治理

| 模块 | 内容 |
|---|---|
| `security/levels.py` | 风险分级（L0–L3） |
| `security/guard.py` `policy.py` | 分级守卫、审批策略 |
| `security/analyzer.py` | OpenHands 安全分析器集成 |
| `server/permission.py` | 会话级权限档位 |
| `server/audit.py` | 审计落库 |
| `server/probe.py` | 后端连通性探测 |
| `runtime/runner.py` | 真接 OpenHands SDK（LLM + Agent + Conversation），16 态状态投影，审批挂起/恢复 |

---

## 二、对照六类真实需求的达成度

| # | 需求 | 达成度 | 缺口 |
|---|---|---|---|
| 1 | 日常巡检（主机健康/磁盘/进程/服务/容器/数据库） | **85%** | 已实现，需接真实机器验证；缺少巡检报告汇总与趋势 |
| 2 | 故障排查（层次定位、日志检索、瓶颈资源、错误码+修复步骤） | **60%** | 日志检索有；**缺统一错误码表与修复步骤建议**；缺跨层次关联定位 |
| 3 | K8s 排障（Pod 异常、事件、滚动更新失败） | **40%** | 工具已写好但**未注册**；缺滚动更新状态诊断与回滚能力 |
| 4 | 变更操作（启停/部署/扩缩容/回滚 + 危险确认 + dry-run + 可回滚） | **20%** | 仅 `restart_service`；**无部署/扩缩容/回滚**；dry-run 与回滚机制缺失 |
| 5 | 告警响应（查告警、定位触发原因、判断影响范围） | **0%** | **完全缺失**，无任何告警/监控接入模块 |
| 6 | 只读诊断 / 受控写入 / 明确标注未实现 | **70%** | 分级+审批+审计已有；**缺 dry-run、缺统一"未实现"标注规范** |

---

## 三、缺口清单（按优先级）

### P0 — 没有就谈不上生产级

1. **告警接入能力为零**：无法查询告警内容、无法定位触发原因、无法判断影响范围
2. **变更能力残缺**：只有重启，没有部署 / 扩缩容 / 回滚
3. **K8s 工具未注册**：4 个已实现的工具 Agent 用不到
4. **无 dry-run**：写操作无法预演
5. **无回滚机制**：写操作不可逆
6. **凭据与真实环境未接入**：当前无任何真实主机/集群配置

### P1 — 影响可用性

7. 无统一错误码体系与修复步骤建议
8. 无「未实现能力」的显式标注规范（容易产生"看起来能用"的假象）
9. 环境不可运行：`.venv` 缺 fastapi 等依赖、pip/pytest 损坏，后端起不来
10. 桌面壳未接后端（`API_BASE` 为空串）

---

## 四、需要你提供的接入信息（缺这些我只能做框架，不能做真实接入）

### 必填（没有则对应能力无法真实化）

| 项 | 需要提供 | 用途 |
|---|---|---|
| **A. 目标主机 SSH** | 主机标识、IP/域名、端口、登录用户、认证方式（密钥路径 / 密码）、sudo 方式 | 巡检、故障排查、服务启停 |
| **B. K8s 集群** | `kubeconfig` 路径或内容、上下文名、默认命名空间、是否允许写操作 | K8s 排障、扩缩容、回滚 |
| **C. 日志来源** | 方式（ journald / 文件路径 / Loki / ELK ）、路径规则或查询地址 | 日志检索与错误定位 |
| **D. 告警/监控系统** | 类型（Prometheus+Alertmanager / Zabbix / 云厂商 / 自研）、API 地址、认证方式、告警查询字段 | 告警响应（当前 0 覆盖） |
| **E. 变更执行通道** | 服务启停用 systemd 还是脚本、部署走什么（脚本 / Ansible / kubectl / CI）、回滚依据（版本/镜像 tag/备份） | 受控写入与回滚 |

### 必填（运行前提）

| 项 | 说明 |
|---|---|
| **F. LLM 凭据** | `DEEPSEEK_API_KEY` 或 `LLM_API_KEY`（`runner.py` 缺失即报错）；模型名与 base_url |

### 可选（有则更贴近你的真实环境）

| 项 | 说明 |
|---|---|
| G. 数据库只读账号 | 主机、端口、账号、可访问库范围 |
| H. 堡垒机 / 跳板机配置 | 若主机不可直连 |
| I. 变更审批方式 | 内置审批流 / 企业 IM 回调 |
| J. 高危命令黑名单 | 你环境里绝对禁止执行的命令 |

---

## 五、不需要你提供、我可以立即开工的部分

1. 注册遗漏的 4 个 K8s 工具（明确缺陷，立即可修）
2. 建立统一错误码体系与修复建议表
3. 写操作 dry-run 框架与回滚登记机制
4. 「未实现能力」显式标注规范 + 自检脚本
5. 修复运行环境（重建 venv、补依赖、拉起服务、用真实接口自证）
6. 告警接入抽象层（适配 Prometheus/Alertmanager，等 D 项信息后填充实现）
