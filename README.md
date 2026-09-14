# OpsPilot

> 以 AI 聊天为核心的**通用工程 Agent 工作台**。基于 [OpenHands](https://github.com/OpenHands/OpenHands)（MIT）二次开发，在保留其代码生成 / 文件操作 / 终端执行 / Git / 测试等通用工程能力之上，叠加 SSH、数据库、Docker、Kubernetes、日志与监控的运维能力。

**一句话定位**：不是为了做"只能做运维的 Agent"，而是让服务器、数据库、容器、集群和监控成为 Agent 的重要工作上下文。

| 项 | 值 |
|---|---|
| 版本 | `v0.1.0`（2026-09-14） |
| 仓库 | <https://github.com/YYY2579/OpsPilot>（public） |
| 后端 | Python ≥3.10 + FastAPI 0.141.1 + OpenHands SDK 1.47.0 |
| 前端 | React 19 + TypeScript(strict) + Vite + Tauri |
| 后端测试 | **199 passed** |
| 前端类型检查 | `tsc -b --force` **0 error** |
| 许可 | 上游 MIT；本项目自身许可 `待定` |

---

## 目录

| § | 章节 |
|---|---|
| 1 | [当前状态](#1-当前状态真实进度) |
| 2 | [快速开始](#2-快速开始5-分钟跑起来) |
| 3 | [目录结构](#3-目录结构) |
| 4 | [架构与数据流](#4-架构与数据流) |
| 5 | [后端 API 一览](#5-后端-api-一览27-条) |
| 6 | [环境变量](#6-环境变量) |
| 7 | [运维工具清单](#7-运维工具清单26-个) |
| 8 | [开发路线](#8-开发路线) |
| 9 | [构建与出包](#9-构建与出包) |
| 10 | [已知限制与未实现](#10-已知限制与未实现如实) |
| 11 | [上游版本基线](#11-上游版本基线已-pin勿随意升级) |
| 12 | [已定技术决策](#12-已定技术决策) |
| 13 | [效果图与原型](#13-效果图与原型) |
| 14 | [文档索引](#14-文档索引) |

---

## 1. 当前状态（真实进度）

> 以下全部来自 2026-09-14 在真实服务器（`156.224.28.147`，Ubuntu 24.04.1 LTS）上的端到端验证，不是原型演示。

| 验证项 | 结果 | 证据 |
|---|---|---|
| SSH 连通性 | ✅ | `ok=True stage=ok latency=1986ms` |
| 服务器健康采集 | ✅ | CPU 2.5% / 内存 38.0% / 磁盘 16.0% / `redis=inactive` |
| 审批拒绝理由落库 | ✅ | `?rejected_reason=…` → 库中存 `磁盘不足且该命令为本地终端探测…` |
| 上下文用量上报 | ✅ | 进行中 `33411/131072 = 25.5%`，命中率 65.1%；终态 `115903/131072 = 88.4%`，命中率 86.84% |
| Agent 工具全链路 | ✅ | 任务终态 `COMPLETED`，10 次工具调用全部返回 observation，0 错误，耗时 42.8s |
| 后端测试 | ✅ | 199 passed（含凭据别名 6 例新增） |
| 前端类型检查 | ✅ | `tsc -b --force` 0 error |

**架构硬约束（已通过测试守护）**

- **凭据边界**：工具 Action 的 schema 只带 `server_id`，**永不出现** ip / user / password / private_key；真实凭据只在 Executor 内部解析，输出必须脱敏。
- **12 态任务状态机**：`RECEIVED → CLASSIFY_TASK → SELECT_CONTEXT → PLAN → INSPECT → ANALYZE → PROPOSE_FIX → WAITING_APPROVAL → EXECUTE → VERIFY → REPORT → COMPLETED`（另有 `FAILED` / `CANCELLED` / `TIMEOUT` / `WAITING_USER`）。
- **风险分级 L0–L5**：L0 纯分析 · L1 只读 · L2 低风险 · L3 中风险（需确认）· L4 高风险（二次确认）· **L5 禁止自动执行**（所有权限档位下都不自动执行）。

**版本与发布状态（2026-09-14 更新）**

| 版本 | 状态 | 说明 |
|---|---|---|
| `v0.1.0` | ⛔ **已作废并删除** | 安装包只含前端静态资源，**后端未打进包**；`API_BASE` 默认空串导致 `tauri://` 下 27 条接口全部静默失败 → 表现为"点哪哪不动"。Release 与 tag 均已从远端删除，**不要用**。 |
| `v0.1.1` / `v0.1.2` / `v0.1.3` | ⚠️ 中间态，未发布 Release | 逐轮修 `API_BASE` 探测（环境判定 → 多候选实连探测），实机均未命中。仅保留构建记录。 |
| `v0.1.4` | ⚠️ 未发布 Release | 试图让桌壳 `url` 直接指向后端地址。**实机验证同样失败**：进程在（PID 11528），但 `netstat :8791` 仍只有 `LISTENING`、零 `ESTABLISHED`。根因见下。 |
| `v0.1.5` | ✅ 当前版本 | **跳转壳**：`dist` 只放一个跳转页，加载即跳 `http://127.0.0.1:8791`。不再与 Tauri 的 url 覆盖行为对抗。 |

**根因（一句话）**：Tauri v2 只要配了 `build.frontendDist`，构建时就会把 `windows[].url` **覆盖回本地资源**。所以 v0.1.4 加的 `url` 从来没生效过 —— 前四轮全是在跟这个行为打架。

> **一句话记住**：桌面壳**不含后端**。它只是一个窗口（v0.1.5 起是一个会自动跳到后端的窗口）。后端没起，桌面端就停在提示页 —— 这是设计，不是故障。见 §2.4。

---

## 2. 快速开始（5 分钟跑起来）

### 2.1 前置

| 依赖 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.10 | 后端 |
| Node.js | ≥ 20 | 前端 |
| Rust 工具链 | stable | **仅打包 Tauri 桌面端时需要**，开发调试不需要 |

### 2.2 后端

```bash
cd OpsPilot/backend

python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[sdk,dev]"                            # sdk = openhands-sdk/tools 1.47.0

python -m uvicorn ops_pilot.server.app:app --port 8791 --reload
```

启动后 <http://127.0.0.1:8791/docs> 可查看全部 27 条路由的 OpenAPI 文档。

### 2.3 前端

```bash
cd OpsPilot/frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

后端 CORS 已放行 `5173` 与 `5199`，无需额外配置。

### 2.4 桌面端（必须先起后端）

> ⚠️ **桌面壳不含后端。** 它只是一个窗口：打开后自动跳转到 `http://127.0.0.1:8791`
> （后端同源托管的真正前端）。**后端没启动，就停在跳转页的排查提示** —— 这是设计，不是故障。

**双击仓库根的 `启动 OpsPilot.bat`**，它按顺序做三件事：

1. 启动后端（`backend/.venv` → uvicorn → `127.0.0.1:8791`）
2. 轮询等待端口就绪（最多 30 秒）
3. 拉起桌面端；没装桌面端就直接用浏览器打开

后端首次使用需装依赖（约 5–10 分钟，一次性）：

```bash
cd backend
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[sdk,dev]"
```

> 也可以不装桌面端：后端起来后浏览器直接开 <http://127.0.0.1:8791>，
> 功能完全一致（同源，无 CORS 与协议问题）。

### 2.5 配一台真实服务器

```bash
# .env（仓库根，已 gitignore）
OPSPILOT_JZZ_18_HOST=156.224.28.147
OPSPILOT_JZZ_18_PORT=22
OPSPILOT_JZZ_18_USERNAME=root
OPSPILOT_JZZ_18_PASSWORD=<你的密码>
# 或用私钥：OPSPILOT_JZZ_18_KEY_PATH=/path/to/id_rsa

# LLM（三选一即可，runner 会依次回退）
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.deepseek.com
```

然后在 UI「资源 → 服务器」新建连接，`credential_ref` 填 `JZZ_18`，点「连接测试」。

> ⚠️ **凭据 ID 规范化**：大写，`-` 与 `.` 转 `_`（`hk-ubuntu` → `HK_UBUNTU`）。
> 环境变量必须按 `credential_ref` 配置，不是按界面上看到的主键。

### 2.6 跑测试

```bash
cd backend && python -m pytest -q          # 199 passed
cd frontend && npx tsc -b --force          # 0 error
```

---

## 3. 目录结构

```text
OpsPilot/
├── README.md                    ← 本文件（项目唯一入口说明）
├── .env                         凭据与本地配置（gitignore）
├── key.txt                      裸模型密钥兼容文件（gitignore）
├── docs/                        设计规格与决策记录（见 §14）
├── assets/                      效果图 00–15（界面示意，**不是规格**）
├── prototype/                   HTML 原型（**不是规格**）
├── upstream/                    上游浅克隆，只读，不入库（gitignore）
├── backend/
│   ├── pyproject.toml
│   ├── ops_pilot/
│   │   ├── credentials.py        SSH 凭据解析 + 别名表
│   │   ├── db/                   数据库凭据与只读客户端
│   │   ├── diagnostics/          错误码体系（50 码）+ 结论生成
│   │   ├── runtime/              Agent 驱动、事件流、状态机
│   │   ├── security/             风险分级、确认策略、护栏
│   │   ├── server/               FastAPI（app / audit / permission / usage / probe）
│   │   ├── ssh/                  paramiko 封装
│   │   └── tools/                26 个运维工具 + register_all
│   ├── scripts/                  能力与端到端验证脚本
│   └── tests/                    12 个测试模块
├── frontend/
│   ├── src/
│   │   ├── api/                  client.ts / hooks.ts / types.ts
│   │   ├── components/           RealStream（实况）/ Stream（设计态）/ cards / RailPanels
│   │   ├── shell/                MenuBar / TopBar / Sidebar / Rail / Center
│   │   ├── lib/                  viewState / useViewport
│   │   ├── mock/                 **仅用于 ?state=NN 设计态预览**
│   │   ├── state/                Zustand
│   │   └── styles/tokens.css     设计令牌
│   └── src-tauri/                Tauri 壳（不含业务逻辑）
└── .github/workflows/
    └── tauri-build.yml           四平台打包
```

> **数据源纪律**：`frontend/src/mock/` 的剧本**只服务于 `?state=NN` 设计态预览**。产品运行路径必须走真实 API。历史上曾发生"演示数据冒充真实规格"的问题，现在由这条规则约束。

---

## 4. 架构与数据流

```text
  桌面壳（无业务逻辑）                      浏览器（等价入口）
  tauri://localhost/index.html              直接打开
  └─ 仅一个跳转页                             ↓
        │ location.replace()                  │
        └──────────────┬──────────────────────┘
                       ▼  http://127.0.0.1:8791   ← 跳转后页面与 API 完全同源
┌─────────────────────────────────────────────────────────────────────────────────────┐
│   OpsPilot FastAPI :8791                                                             │
│   ├─ app.mount("/", StaticFiles(frontend/dist))   ← 前端由后端同源托管                │
│   └─ 27 条 API：资源（服务器/数据库/项目）· 任务 · 审批 · 审计 · 用量 · 权限           │
└───────────────────────────────┬─────────────────────────────────────────────────────┘
                                │ OpenHands SDK 1.47
┌───────────────────────────────▼─────────────────────────────────────────────────────┐
│   Agent（Conversation）+ 26 个运维工具                                               │
│   ├─ SSH 工具 → paramiko → 目标服务器                                                │
│   ├─ K8s 工具 → SSH 到装有 kubectl 的机器（本机不放 kubeconfig）                      │
│   ├─ 告警工具 → Prometheus + Alertmanager                                            │
│   └─ 数据库工具 → pymysql（只读）                                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**关键设计：为什么要有"凭据别名表"**

Agent 的 Action 里只有 `server_id`，而它拿到的是 `serverconnection` 的**主键**（如 `4d6cc8bd599d`）；但环境变量是按 `credential_ref`（如 `JZZ_18`）配置的。如果直接拿主键去查 `OPSPILOT_4D6CC8BD599D_HOST`，必然找不到并报 `SSH missing`。

`credentials.py` 维护一张 `主键 / name / host → credential_ref` 的别名表（启动时从 DB 灌入，新建连接后即时刷新），`resolve()` 先精确匹配、再回退别名。

> **踩过的坑**：`/api/servers/{id}/health` 一直是通的（它先 `resolve_server()` 取 `credential_ref`），唯独 Agent 调工具全挂 —— 极易误判成"工具坏了"。已由 `backend/tests/test_credentials.py` 6 个用例守护。

**框架已提供、不要自建的能力**

| 能力 | 上游提供物 |
|---|---|
| Agent 循环 / 多步规划 / 工具调用 | SDK `Agent` + `Conversation` |
| 工具定义与注册 | `Action` / `Observation` / `ToolExecutor` / `ToolRegistry` |
| 扩展方式 | MCP 原生支持（stdio / SSE / Streamable HTTP / OAuth） |
| 危险分级底层 | `ToolAnnotations`（readOnly / destructive / idempotent / openWorld） |
| 风险评级 + 确认策略 | `SecurityAnalyzer` + `ConfirmationPolicy` |
| 事件流 / 持久化 / 暂停恢复 | REST + WebSocket + append-only EventLog + Condenser |
| 执行隔离 | `LocalWorkspace` / `DockerWorkspace` / `RemoteAPIWorkspace` |
| 行为约束 | `Skills` / `Hooks` / `Plugin` |

**自建部分**：前端三栏工作台、资源管理后端、任务状态投影、业务级审计表。

---

## 5. 后端 API 一览（27 条）

服务启动后 `/docs` 为权威来源；下表用于快速检索。

### 资源

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/connections/servers` | 新建服务器连接 |
| GET | `/api/connections/servers` | 服务器列表 |
| GET | `/api/connections/servers/{server_id}` | 服务器详情 |
| POST | `/api/connections/servers/{server_id}/test` | SSH 连接测试 |
| POST | `/api/connections/databases` | 新建数据库连接 |
| GET | `/api/connections/databases` | 数据库列表 |
| POST | `/api/connections/databases/{database_id}/test` | 数据库连接测试 |
| GET | `/api/connections/databases/{database_id}/tree` | 库/表树 |
| GET | `/api/servers/{server_id}/health` | 服务器健康快照 |

### 项目与任务

| 方法 | 路径 | 说明 |
|---|---|---|
| POST / GET | `/api/projects` | 新建 / 列表 |
| POST / GET | `/api/tasks` | 创建任务 / 任务列表 |
| GET | `/api/tasks/{task_id}` | 任务详情 |
| POST | `/api/tasks/run` | 启动任务（驱动 Agent） |
| GET | `/api/tasks/{task_id}/state` | 当前状态机状态 |
| GET | `/api/tasks/{task_id}/events` | 事件流（工具调用 / 观察 / 错误） |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |

### 审批

| 方法 | 路径 | 说明 |
|---|---|---|
| POST / GET | `/api/approvals` | 创建 / 列表 |
| POST | `/api/approvals/{approval_id}/approve` | 批准 |
| POST | `/api/approvals/{approval_id}/reject` | 拒绝，**参数名为 `rejected_reason`** |

### 用量 / 权限 / 审计

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tasks/{task_id}/context-usage` | 上报上下文用量（由 runner 内部调用） |
| GET | `/api/tasks/{task_id}/context-usage` | 读取用量（前端 ContextRing 数据源；**未上报时返回 404，属正常**） |
| GET / POST | `/api/session/{session_id}/permission` | 读取 / 变更权限档位 |
| GET | `/api/audit` | 审计查询 |

---

## 6. 环境变量

加载顺序（**已存在的环境变量优先，不覆盖**）：`<仓库根>/.env` → `<仓库根>/key.txt`。只读入内存，不打印、不落库。

### LLM

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_MODEL` | ✅ | 如 `deepseek/deepseek-chat` |
| `LLM_API_KEY` | ✅ | 模型密钥（也可放 `key.txt` 裸 `sk-` 行） |
| `LLM_BASE_URL` | ⬜ | 自定义网关 |
| `DEEPSEEK_API_KEY` | ⬜ | DeepSeek 专用回退键 |

### 服务

| 变量 | 默认 | 说明 |
|---|---|---|
| `OPSPILOT_DB` | `ops_pilot.db` | SQLite 库文件路径 |
| `OPSPILOT_CORS_ORIGINS` | `127.0.0.1:5173/5199` | 逗号分隔的允许来源 |

### SSH 凭据（按 `credential_ref` 配置）

| 变量 | 必填 | 说明 |
|---|---|---|
| `OPSPILOT_{REF}_HOST` | ✅ | 主机 / IP |
| `OPSPILOT_{REF}_PORT` | ⬜ | 默认 22 |
| `OPSPILOT_{REF}_USERNAME` | ✅ | 登录用户 |
| `OPSPILOT_{REF}_PASSWORD` | 二选一 | 口令 |
| `OPSPILOT_{REF}_KEY_PATH` | 二选一 | 私钥文件路径 |

`{REF}` = `credential_ref` 大写、`-`/`.` 转 `_`。数据库凭据同构（`OPSPILOT_{REF}_DB_*`）。

---

## 7. 运维工具清单（26 个）

注册入口 `backend/ops_pilot/tools/register_all.py`。

### 只读（22 个，Agent 可直接调用）

| 分组 | 工具 |
|---|---|
| 系统 | `get_server_health`、`get_disk_usage`、`get_process_list` |
| 服务 | `get_service_status`、`get_service_logs` |
| 网络 | `check_port`、`check_http` |
| 容器 | `list_docker_containers`、`get_container_logs` |
| 数据库 | `list_databases`、`list_tables`、`describe_table`、`query_readonly`、`explain_sql` |
| Kubernetes | `list_namespaces`、`list_pods`、`get_pod_logs`、`get_events`、`rollout_status` |
| 告警 | `list_alerts`、`inspect_alert`、`query_metrics` |

> K8s 工具**不在本机放 kubeconfig**，而是 SSH 到装有 `kubectl` 的机器上执行。

### 写工具（4 个，需审批，L3+）

`restart_service`、`scale_workload`、`rollback_deploy`、`run_change_script`

默认 `dry_run=true`，且必须给出回滚方案，否则拒绝执行。

---

## 8. 开发路线

| 阶段 | 目标 | 状态 |
|---|---|---|
| 一 | 运行并理解 OpenHands：跑通、定位工具注册/执行、完成对话验收 | ✅ 2026-09-12 |
| 二 | 第一个运维工具 `get_server_health` | ✅ |
| 三 | SSH 资源管理（增删改查 / 连接测试 / 上下文 / 凭据安全存储） | ✅ |
| 四 | 只读运维工具集（系统 / 服务 / 容器 / 网络） | ✅ |
| 五 | 审批与审计（风险分级 / 操作预览 / 批准拒绝 / 执行记录 / 执行后验证） | ✅ |
| 六 | 前端三栏工作台 | ✅ 骨架与实况路径完成，细节见 §10 |
| 七 | 扩展数据库与 Kubernetes（先只读） | ✅ 已扩展至告警响应 |

**第一个可运行目标（已达成）**：用户输入「检查 HK-Ubuntu 的健康状态」→ Agent 识别服务器 → 调用 `get_server_health` → 返回 CPU/内存/磁盘/负载/服务状态 → Agent 汇总输出。

验收标准逐条对照：

| 标准 | 状态 |
|---|---|
| Agent 能识别服务器 | ✅ |
| 能调用结构化工具 | ✅ |
| SSH 异常时返回清晰错误 | ✅（`diagnostics/codes.py` 50 个错误码） |
| 工具执行有超时 | ✅ |
| 工具结果不泄露密码和私钥 | ✅（`mask()` / `assert_no_secrets()`，测试守护） |
| 能区分正常项与异常项 | ✅ |
| 所有调用有任务 ID | ✅ |
| 可查看执行记录 | ✅（`/api/audit` + 事件流） |

---

## 9. 构建与出包

### 9.1 本地前端构建

```bash
cd frontend && npm run build        # tsc -b && vite build → dist/
```

### 9.2 四平台桌面包（GitHub Actions）

工作流：`.github/workflows/tauri-build.yml`

**触发方式（二选一）**

| 方式 | 操作 |
|---|---|
| 打 tag（推荐） | `git tag v0.1.5 && git push origin v0.1.5`（tag 即版本号，需与 `tauri.conf.json` / `Cargo.toml` 一致） |
| 手动 | GitHub → Actions → `tauri-build` → Run workflow |

**构建矩阵与产物**

| 平台 | Runner | 产物名 |
|---|---|---|
| Windows x64 | `windows-latest` | `opspilot-windows-x64` |
| macOS ARM64 | `macos-latest` (`--target aarch64-apple-darwin`) | `opspilot-macos-arm64` |
| macOS x64 | `macos-latest` (`--target x86_64-apple-darwin`) | `opspilot-macos-x64` |
| Linux x64 | `ubuntu-22.04` | `opspilot-linux-x64` |

**历史构建记录**

| 版本 | Run | 结果 |
|---|---|---|
| `v0.1.4` | `34873625970` | ✅ 四平台 success |
| `v0.1.3` | `34869611582` | ✅ success（未发布 Release） |
| `v0.1.2` | `34868926501` | ✅ success（未发布 Release） |
| `v0.1.0` | `34863672023` | ⛔ 已删除 Release 与 tag，勿用 |

**前置条件**：仓库必须为 **public**（否则消耗 Actions 额度）；构建机由 GitHub 托管，Rust 工具链由工作流自行安装。

### 9.3 安装包里到底有什么（重要）

| 内容 | 是否打包 | 说明 |
|---|---|---|
| 跳转页（`frontend/shell/index.html` → `dist/index.html`） | ✅ 是 | **v0.1.5 起**：`dist` 只放这一个文件。加载后立刻 `location.replace("http://127.0.0.1:8791")`。 |
| 真正的 React 前端 | ❌ 否 | 由后端 `app.mount("/", StaticFiles(frontend/dist))` **同源托管**，不进安装包 |
| **Python 后端** | ❌ **否** | 当前 **未** 用 PyInstaller 打 sidecar。安装包里没有后端。 |
| LLM / SSH 凭据 | ❌ 否 | 运行时从仓库根 `.env` 读取 |

所以：**安装完必须自己起后端**，桌面端才有内容。见 §2.4。

> 为什么不直接把 React 前端打进壳？因为 Tauri v2 配了 `frontendDist` 就会**覆盖 `windows[].url`**，壳会去加载 `tauri://localhost` 上的本地资源，而那里的 `fetch("/api/...")` 是跨源的、且**静默失败**。与其对抗，不如让本地资源只有一个跳转页 —— 跳到同源的后端地址后，一切请求都是同源的。

> 后续正解（未做）：用 PyInstaller 把 `ops_pilot.server.app` 打成 sidecar 二进制，通过 Tauri `externalBin` + `Command.sidecar()` 随应用启动/退出。做完之后桌面端才是真正"双击即用"。

### 9.4 发布 Release

```bash
# 1. 下载四平台产物
set REL_TAG=v0.1.4
python backend/scripts/_dl_artifacts.py <RUN_ID>      # → dist-release/artifacts-v0.1.4/

# 2. 建 Release 并上传产物
python backend/scripts/_mk_release.py

# 3. 复核
python backend/scripts/_verify_release.py
```

或手动：在 <https://github.com/YYY2579/OpsPilot/releases> 新建 Release，绑定对应 tag 并附上四平台包。

**发布前必须完成的实机验收（缺一不可）**

1. 后端已启动：`netstat -ano | findstr :8791` 有 `LISTENING`
2. 启动桌面端 → `netstat -ano | findstr :8791` **出现 `ESTABLISHED`**
3. 后端 uvicorn 访问日志出现新请求（`"GET /api/connections/servers HTTP/1.1" 200`）
4. 界面能列出真实服务器（如 `156.224.28.147`）

> v0.1.0 就是因为跳过了第 2、3 步直接发布，才出现"点哪哪不动"。**只有 `ESTABLISHED` 才是壳内前端真连上后端的证据，界面"看起来正常"不算。**

---

## 10. 已知限制与未实现（如实）

> 这一节是**当前代码的事实**，不是路线图。有意写成负面清单，避免误判完成度。

### 10.0 桌面端限制（最重要，先看这条）

| # | 项 | 现状 |
|---|---|---|
| 1 | **桌面壳不含 Python 后端** | 安装包只含一个跳转页。**必须自己先起后端**（`启动 OpsPilot.bat` 或 `uvicorn ... --port 8791`），否则桌面端是空白页。未做 PyInstaller sidecar。 |
| 2 | 桌面端无"后端没起"的自愈 | 后端挂掉后前端每 5s 轮询并在顶部显示离线横幅 + 「重试」按钮，但**不会自己去拉起后端**。 |
| 3 | 无系统托盘 / 开机自启 | 未实现，需 Rust 或 sidecar。 |
| 4 | 单实例无保护 | 同时开多个窗口都指向同一后端，共享同一份数据。 |

### 10.1 未实现（需要产品决策，或明确留白）

| # | 项 | 现状 |
|---|---|---|
| 1 | **认证（JWT）** | 开源版 OpenHands 无内置认证、单租户。**面向多人开放前必须补 JWT**，未登录不可访问任何 API。当前仅限本机/内网单机使用。 |
| 2 | 底部面板（实时终端 + 原始日志流） | **MVP 已定置灰**，v2 再做（见 §12 决策 3） |
| 3 | 日志 Tab 筛选交互 / 多目标标签 | 文字规格已定义，效果图未覆盖，实现时按文字做 |
| 4 | 移动端 / 平板 | 响应式只覆盖到 960px（左右栏双双收起）；上平板需补抽屉式浮层方案 |
| 5 | 系统托盘 / 开机自启 / 本地 kubectl | Tauri 壳未实现，需 Rust 或 sidecar |

### 10.2 前端「点了没反应」的入口（已显式置灰）

以下按钮**已改为 `disabled` + `title` 提示未实现**，不再伪装成可用：

`添加文件` · `添加上下文` · `使用终端`

### 10.3 2026-09-14 本轮修复清单

| 编号 | 问题 | 修复 |
|---|---|---|
| P0-1 | 审批拒绝理由被静默丢弃（前端发 `reason`，后端只认 `rejected_reason`） | 前端参数名改为 `rejected_reason` |
| P0-2 | `ApprovalCard` 4 个死按钮导致"双份批准按钮" | 改为 `actions` props，**只渲染有回调的按钮**；删除卡片外重复按钮组 |
| P0-3 | `ContextRing` 是硬编码假数据，且后端 `contextusage` 表无任何生产者 | 后端 `runner._record_usage()` 上报；前端接真实端点；**无数据时显示 `—` 而非假值** |
| P1 | 实况路径 13 个死按钮 | 选择服务器/数据库接真实行为；其余置灰 |
| **新发现** | Agent 调 SSH 工具全报 `SSH missing`（凭据别名缺失） | `credentials.py` 增加别名表 + 回退解析 |
| **P0-4** | **桌面端"点哪哪不动"**（v0.1.0 事故）：`API_BASE` 默认空串 → Tauri 下 `/api/...` 打到 `tauri://localhost/api/...`，被 WebView 跨源拦截，27 条接口全部静默失败 | `client.ts` 增加 `DEFAULT_API_BASE` + `isTauri()` 判定 + `localStorage` 持久化；后端离线时前端顶部横幅明示 |
| **P0-5** | 侧栏「新建连接 / 新建项目 / 连接管理」三个按钮只弹提示不落库 | 新建 `NewResourceDialog.tsx` 真正建库并立即测连；`连接管理·凭据管理` 改为 `后端设置`（可改 `API_BASE`） |
| **P1-2** | 离线提示里的端口写错（`8700` 应为 `8791`） | 统一改为 `DEFAULT_API_BASE` 常量 |
| **P0-6** | v0.1.1 / v0.1.3 实机仍连不上（`isTauri()` 与多候选探测均未命中，`tauri://` 下 fetch 根本没发出） | 见下条 P0-7 |
| **P2** | `uvicorn==0.34.0` 锁死导致 pip 依赖解析失败（`fastmcp` 要求 `>=0.35`） | 改为 `uvicorn>=0.34.0` |

### 10.4 审查结论基线

2026-09-14 全量审查（commit `c12e21e`）评级：后端工程质量 **A** / 前后端契约 **B−** / 前端实况完成度 **C+** / 整体 **B**。本轮修复后 P0 与 P1 均已关闭；详细过程见审查报告。

### 10.5 桌面端事故复盘（v0.1.0，值得记一辈子）

**现象**：装完双击打开，界面渲染正常，但"点哪哪不动"。

**根因链**

```text
安装包只含 frontend/dist（8.2MB），Python 后端完全没打进包
        ↓
client.ts 的 API_BASE 默认 "" （为浏览器同源场景设计）
        ↓
Tauri 下 fetch("/api/...") → tauri://localhost/api/...
        ↓
WebView 跨源拦截 → 27 条接口全部静默失败（无 CORS 报错、无网络面板记录）
        ↓
界面渲染正常但没有数据 → 表现为"点了没反应"
```

**为什么连续三轮没修好**

| 轮次 | 做法 | 为什么失败 |
|---|---|---|
| v0.1.1 | `isTauri()` 环境判定命中则用 `127.0.0.1:8791` | 实机未命中该判定 |
| v0.1.3 | 多候选实连探测（同源 / `127.0.0.1:8791` / `localhost:8791`） | 在 exe 二进制里搜新代码特征串命中数 **为 0** → `tauri://` 下 fetch 根本没发出 |
| v0.1.4 | 窗口 URL 直接指向 `http://127.0.0.1:8791` | **实机同样失败**：进程在（PID 11528，26MB），但 `netstat :8791` 零 `ESTABLISHED`。根因是 **Tauri v2 配了 `frontendDist` 就会覆盖 `windows[].url`**，配置从未生效 |
| v0.1.5 | **跳转壳**：`dist` 只放一个 `index.html`，加载即跳后端地址 | —（不与框架行为对抗，顺它走） |

**教训（写进流程）**

1. **不要靠"看起来正常"判定成功。** 唯一可靠证据是 `netstat -ano | findstr :8791` 出现 **`ESTABLISHED`**，以及后端 uvicorn 访问日志有新请求。v0.1.0～v0.1.4 全栽在"界面渲染出来了就以为好了"。
2. **改了前端代码，要能在产物二进制里搜到特征串**；搜不到说明没打进去或没执行到。
3. **先确认框架到底听不听你的配置。** 在框架行为上叠加三层兼容代码，不如顺着框架行为重新设计 —— v0.1.4 就是被"我以为 url 会生效"骗了一整轮。
4. **纯前端功能能用 ≠ 连上了后端。** 主题切换是 localStorage 逻辑，它能在完全离线的壳里工作，不能作为验收依据。

---

## 11. 上游版本基线（已 pin，勿随意升级）

| 仓库 | 版本 / 提交 | 说明 |
|---|---|---|
| `OpenHands/OpenHands` | **`@openhands/agent-canvas` v1.18.0**<br>commit `de5a79b4ce578c56f5fef330551a0c1fb8bd12bc` | 主仓（前端 Agent Canvas、`electron/`、`docker/`、`helm/`） |
| `OpenHands/software-agent-sdk` | commit `2da2e9b342f4b89ba02a21285cdc4b202b4904b1` | 四个 Python 包 |
| Python SDK 实际使用 | **`openhands-sdk == 1.47.0`** + **`openhands-tools == 1.47.0`** | `backend/pyproject.toml` 的 `sdk` extra |
| 许可 | **MIT** | 允许商用、修改、分发 |

**两个真实依赖坑**

1. **`agent-client-protocol` 必须锁 `<0.11`** —— `openhands-sdk 1.35.0` 声明无上限，但 `acp 0.11.0` 重排了 `prompt()` 参数，会导致 `ACP error: 2 validation errors for PromptRequest`。
2. **`openhands-tools` 不可省** —— SDK 1.47 起 `default_tool_specs()` 只返回声明（`Tool(name=...)`）不注册实现；缺它会在 `Conversation` 初始化时抛 `KeyError: ToolDefinition 'terminal' is not registered`。

> 两个上游仓库均为 `--depth 1` 浅克隆。需要完整历史时：
> ```bash
> git -C upstream/openhands fetch --unshallow
> git -C upstream/software-agent-sdk fetch --unshallow
> ```

**上游 patch 策略**：`upstream/` 只读，提 PR 优先，**禁止静默 fork**；PR 合并前用 patch 过渡并登记 issue；升版本第一件事是检查 patch 是否仍需要。

---

## 12. 已定技术决策

| # | 决策 | 结论 | 理由 |
|---|---|---|---|
| 1 | 桌面封装 | **Tauri** | 壳里无业务逻辑（重活全在 Python 侧 + agent-server），前端与壳完全解耦；安装包 ≤30MB；常驻工具的内存/体积用户可感知 |
| 2 | 菜单栏 | **自绘** | 三平台视觉一致 + 与效果图对齐 + 菜单项承载业务语义；快捷键归系统 |
| 3 | 底部面板 / 打开终端 | **MVP 置灰，v2 再做** | 聊天区是唯一主入口；工具卡已提供终端可视性 |
| 4 | 上游 patch 策略 | **提 PR 优先，禁止静默 fork** | 见 §11 |

**Tauri 的代价（已接受）**：构建机需 Rust 工具链（一次性，CI 已覆盖）；Windows 依赖 WebView2（Win10 1803+ 与 Win11 自带）。

**何时重开评估（满足任一且需同步更新规格 §A3）**：

- 需要**在桌面壳里直接写逻辑**（系统托盘、开机自启、本地 kubectl、本地文件监控）—— Electron 的 Node 主进程更顺。
- 需要**打包 OpenHands 官方 Agent Canvas 原版应用**——上游 Electron 配置现成。

---

## 13. 效果图与原型

| # | 状态 | 文件 |
|---|---|---|
| 1 | 空白欢迎页 | `assets/效果图-01-空白欢迎页.png` |
| 2 | 已选择服务器但还没有聊天 | `assets/效果图-02-已选服务器未聊天.png` |
| 3 | Agent 正在执行任务 | `assets/效果图-03-Agent执行中-深色.png` |
| 4 | 工具调用展开状态 | `assets/效果图-04-工具调用展开.png` |
| 5 | 等待用户审批状态 | `assets/效果图-05-等待用户审批.png` |
| 6 | 任务完成状态 | `assets/效果图-06-任务完成.png` |
| 7 | 工具执行失败状态 | `assets/效果图-07-工具执行失败.png` |
| 8 | 数据库连接与数据库树展开 | `assets/效果图-08-数据库树展开.png` |
| 9 | 右侧面板收起状态 | `assets/效果图-09-右侧面板收起.png` |
| 10 | 浅色主题 | `assets/效果图-10-浅色主题.png` |
| 11 | 响应式 · 窄窗自动折叠（1180×820） | `assets/效果图-11-窄窗自动折叠.png` |
| 12 | 响应式 · 超宽屏居中（1920×900） | `assets/效果图-12-超宽屏居中.png` |
| 13 | 桌面菜单栏展开态 | `assets/效果图-13-顶部菜单展开.png` |
| 14 | 完全访问升级确认面板 | `assets/效果图-14-完全访问升级确认.png` |
| 15 | 完全访问已开启 | `assets/效果图-15-完全访问已开启.png` |

统一尺寸 1440×920（11/12 为响应式示意）。原始参考图 `assets/效果图-00-原始参考图.jpg`。

**原型总览**：浏览器打开 `prototype/OpsPilot-原型总览.html`，可切换 13 个状态、深/浅色、1180 / 1440 / 1920 三种窗口尺寸。

> 效果图中的主机名、IP、百分比、耗时、日志内容**全部是演示占位**。与规格冲突时以规格为准。

---

## 14. 文档索引

| 文档 | 优先级 | 内容 |
|---|---|---|
| `docs/交接文档.md` | ★★★ | 接手者第一个读：项目是什么 / 红线 / FAQ / 第一天做什么 |
| `docs/OpsPilot-需求开发文档.md` | ★★★ | **唯一真相源**：产品 + 工程 + UI 规格 |
| `docs/前端实现规格与开发提示词.md` | ★★★ | 设计令牌 / 组件规格 / 状态映射 / 可复制提示词 |
| `docs/开发任务拆解.md` | ★★ | M0–M7 任务、依赖、顺序、验收标准 |
| `docs/开发提示词.md` | ★★ | 给 AI 派活的提示词包 |
| `docs/开发环境准备.md` | ★ | 要装哪些软件、什么版本、怎么验证 |
| `docs/源码索引.md` | ★ | 上游源码定位 |
| `docs/决策记录-001-代码组织.md` | ★ | 为什么这样组织代码 |
| `docs/PRODUCTION_READINESS.md` | ★ | 生产就绪度评估 |
| `OpsPilot-审查报告-2026-09-14.md` | ★ | 代码审查报告（本轮修复的依据） |
| `启动 OpsPilot.bat` | ★★ | 一键启动：先起后端、等端口就绪、再拉桌面端 |

### 文档使用规则（给人和 AI 都适用）

1. **`docs/OpsPilot-需求开发文档.md` 是唯一真相源。** 不得新增、删除、改名任何工具名 / 状态名 / 风险等级 / 字段名 / API 路径。
2. **`assets/` 里的效果图是界面示意，不是规格。**
3. **`prototype/` 里的 HTML 是原型稿，不是规格。**
4. **`frontend/src/mock/` 只服务设计态预览，不是产品数据源。**
5. **README 的「当前状态」表必须写真实验证结果与证据**，不得把未验证项写成"已完成"。
6. 把本目录交给任何 AI 时，附件带 `docs/` + `assets/` + `prototype/`，并在提示词开头声明第 1 条。

---

## 许可与合规

- OpenHands 及 Software Agent SDK 均为 **MIT**，允许商用、修改与分发。
- 本项目自身许可：**待定**。
