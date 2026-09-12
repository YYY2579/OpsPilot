# OpsPilot

> 以 AI 聊天为核心的**通用工程 Agent 工作台**。基于 [OpenHands](https://github.com/OpenHands/OpenHands)（MIT）二次开发，在保留其代码生成 / 文件操作 / 终端执行 / Git / 测试等通用工程能力之上，叠加 SSH、数据库、Docker、Kubernetes、日志与监控的运维能力。

**一句话定位**：不是为了做"只能做运维的 Agent"，而是让服务器、数据库、容器、集群和监控成为 Agent 的重要工作上下文。

---

## 目录结构

```text
OpsPilot/
├── README.md                          ← 本文件：项目说明与入口
├── docs/
│   ├── 交接文档.md                     ★★★ 接手者第一个读（项目是什么/红线/FAQ/第一天做什么）
│   ├── OpsPilot-需求开发文档.md         ★★★ 唯一真相源（产品 + 工程 + UI 规格）
│   ├── 前端实现规格与开发提示词.md       ★★★ 设计令牌 / 组件规格 / 状态映射 / 可复制提示词
│   ├── 开发任务拆解.md                  ★★ M0–M7 任务、依赖、顺序、验收标准
│   ├── 开发提示词.md                   ★★ 给 AI 派活的提示词包（7 段，直接复制）
│   └── 开发环境准备.md                 ★ 要装哪些软件、什么版本、怎么验证
├── assets/
│   ├── 效果图-00-原始参考图.jpg          （已认可的视觉参考）
│   ├── 效果图-01 ~ 10-*.png             10 个页面状态，1440×920
│   ├── 效果图-11 ~ 12-*.png             响应式示意（1180×820 / 1920×900）
│   ├── 效果图-13-顶部菜单展开.png        桌面菜单栏展开态
│   └── 效果图-14 ~ 15-*.png             完全访问升级确认 / 完全访问已开启
├── prototype/
│   ├── OpsPilot-原型总览.html            总入口，浏览器打开可切换 10 个状态
│   └── state-01 ~ 10-*.html              各状态的可运行 DOM 参考
└── upstream/                          二开源代码
    ├── openhands/                     OpenHands 主仓（含 Agent Canvas 前端）
    └── software-agent-sdk/            SDK + agent-server + tools + workspace
```

---

## 上游版本基线（已 pin，勿随意升级）

| 仓库 | 版本 / 提交 | 说明 |
|---|---|---|
| `OpenHands/OpenHands` | **`@openhands/agent-canvas` v1.18.0**<br>commit `de5a79b4ce578c56f5fef330551a0c1fb8bd12bc` | 主仓。含前端 Agent Canvas（`src/`）、`electron/`、`docker/`、`helm/`、`specs/`、`tools/` |
| `OpenHands/software-agent-sdk` | commit `2da2e9b342f4b89ba02a21285cdc4b202b4904b1` | 四个 Python 包：`openhands-sdk` / `openhands-tools` / `openhands-workspace` / `openhands-agent-server` |
| 许可 | **MIT** | 允许商用、修改、分发 |

**上游三服务的版本锁定**（来自 `upstream/openhands/config/defaults.json`，这是上游的单一版本真相源）：

| 服务 | 锁定版本 | 镜像 |
|---|---|---|
| agent-server | **1.46.0**（最低兼容 1.28.0） | `ghcr.io/openhands/agent-server` |
| agent-canvas | **1.18.0** | `ghcr.io/openhands/agent-canvas` |
| automation | **1.11.1** | — |

> ⚠️ **已知依赖坑（上游自己标的）**：必须把 `agent-client-protocol` 锁在 `<0.11`。
> 原因：`openhands-sdk 1.35.0` 要求 `agent-client-protocol>=0.10.1` 且无上限，但
> `acp 0.11.0` 重排了 ACP `prompt()` 的参数，会导致 SDK 的 ACP 客户端报
> `PromptRequest` 校验错误（表现为 "ACP error: 2 validation errors for PromptRequest"）。
> 安装 agent-server 时务必带上这个约束。

> 两个仓库均为 `--depth 1` 浅克隆（仅当前快照，不含完整历史）。需要完整历史或要 fork 时执行：
> ```bash
> git -C upstream/openhands fetch --unshallow
> git -C upstream/software-agent-sdk fetch --unshallow
> ```

**开工前必做**：确认上表三个版本与你本地实际安装的一致，并把结果记回本文件。上游活跃（最近推送 2026-09-11），**禁止浮动升级**。

**本地验证记录（M0-1 / M0-2，2026-09-12，Windows 10 本机）**：

- `@openhands/agent-canvas --info` 输出：agent-canvas **1.18.0** / agent-server **1.46.0** / automation **1.11.1**，与上表一致 ✅
- agent-server 根端点 `http://127.0.0.1:18000/` 实测返回：`"version":"1.46.0","sdk_version":"1.46.0","tools_version":"1.46.0","workspace_version":"1.46.0"` ✅
- 安装方式：`npm install -g @openhands/agent-canvas@1.18.0`（固定版本，非 `^`）；agent-server / automation 由 CLI 经 uvx 按 defaults.json 的 pin 从 PyPI 拉取，`agent-client-protocol<0.11` 约束由 CLI 内置消费（`config/defaults.json` → `constraints.agentClientProtocol`）
- 三服务均已启动：ingress `:8000`（HTTP 200，`/canvas` 正常渲染）、agent-server `:18000`（HTTP 200）、automation `:18001`（`/health` 返回 `{"status":"ok"}`）
- ~~待办：完成一次对话验收（需在 UI 设置中配置 LLM API key）~~ ✅ **已完成（2026-09-12）**
- 启动命令：`agent-canvas`（PATH 需含 Node.js 与 uv；uv 0.12.13 经 `pip install uv` 装于用户 Scripts 目录）

**M0-1 对话验收记录（2026-09-12）**：LLM 配置为 DeepSeek（`deepseek/deepseek-chat`，provider connection `31de8ff9…`，key 经 `/api/llm/provider-connections` 写入，认证头 `X-Session-API-Key`，自动生成 key 存于 `~/.openhands/agent-canvas/api-key.txt`）。通过 agent-server API 创建会话 `944ccb91-41a6-498b-98e2-fddb1347618a`（workspace `m0-1-test`，CodeActAgent，NeverConfirm），Agent 实际调用 LLM 完成一轮对话，最终回复：*"I'm OpenHands, an AI coding agent, and yes, I can hear you clearly."*，`execution_status: finished`。UI 入口 `http://localhost:8000/canvas` 与该 API 同源同后端。

---

## 规格速览

| 项 | 内容 |
|---|---|
| 形态 | 桌面端三栏工作台：左资源树 260px ｜ 中间聊天（弹性）｜ 右辅助面板 320px |
| 桌面菜单栏 | 30px 最顶层：`文件 / 编辑 / 视图 / 设置 / 帮助` + 快捷键 + 窗口控制（─ □ ✕） |
| 顶部栏 | 56px；工作区 / 当前任务与状态 / 主题切换 / 面板折叠 / 设置齿轮 / 头像 |
| 侧栏分组 | **资源**（服务器·数据库）／**工作**（项目·任务历史·收藏） |
| 输入框参数行 | 从左到右：**权限档位** · 模型下拉 · 思考等级（低/中/高）· Agent 模式（`Auto`·`Plan`·`Execute`·`Review`）· 发送 |
| **权限档位** | **请求审批**（绿）/ **帮我批准**（蓝）/ **完全访问**（琥珀）。档位决定"默认要不要问"，风险等级决定"能不能被豁免"；**L5 不可逆操作在所有档位下都不自动执行**。升级到完全访问需勾选警告 + 生产环境输环境名；降级不弹窗；按会话作用域，30 分钟自动回落 |
| 右侧四 Tab | 概览 / 工具 / 任务 / 日志 |
| 主题 | **深色为主**（背景 `#111318`、面板 `#181B22`、边框 `#303641`），顶栏右侧有深/浅切换按钮，浅色主题并存 |
| 响应式 | 面板让位优先级「右栏 → 左栏」；窄窗自动收起为 44px / 48px 图标条；超宽屏聊天列限宽 1120px 居中；**任何尺寸下都无横向滚动条、不裁切内容**，输入框常驻底部 |
| 风险分级 | **L0–L5**：L0 纯分析 · L1 只读 · L2 低风险 · L3 中风险（需确认）· L4 高风险（二次确认）· L5 禁止自动执行 |
| 任务状态机 | `RECEIVED → CLASSIFY_TASK → SELECT_CONTEXT → PLAN → INSPECT → ANALYZE → PROPOSE_FIX → WAITING_APPROVAL → EXECUTE → VERIFY → REPORT → COMPLETED`（+ `FAILED`/`CANCELLED`/`TIMEOUT`/`WAITING_USER`） |
| 凭据边界 | 工具 Action 只带 `server_id` 等逻辑标识；私钥/密码/真实 IP **永不进入 prompt**；解析只在工具层内部；输出必须脱敏 |
| 技术栈 | 后端 Python + FastAPI；前端 React 19 + TypeScript + Vite + Tauri；Agent 底座 OpenHands |
| 部署 | Docker Compose 起步 |

完整内容见 [`docs/OpsPilot-需求开发文档.md`](docs/OpsPilot-需求开发文档.md)。

---

## 文档使用规则（给人和 AI 都适用）

1. **`docs/OpsPilot-需求开发文档.md` 是唯一真相源。** 不得新增、删除、改名任何工具名 / 状态名 / 风险等级 / 字段名 / API 路径。
2. **`assets/` 里的效果图是界面示意，不是规格。** 其中的主机名、IP、百分比、耗时、日志内容全部是**演示占位**；与规格冲突时以规格为准。
3. **`prototype/` 里的 HTML 是原型稿，不是规格。**
4. 把本目录交给任何 AI 时，附件带 `docs/` + `assets/` + `prototype/`，并在提示词开头声明第 1 条。

---

## 技术底座现状（决定了怎么改）

OpenHands V1 已经不是单体仓库，而是一套 SDK + 多个可组合服务 + 一个**可嵌入的前端包**：

```text
Agent Canvas（React 19 + Vite + Tailwind + Zustand + TanStack Query，npm: @openhands/agent-canvas）
        │  REST + WebSocket
Agent Server（Python，默认 :18000）── 跑 Agent 与工具
Automation Backend（:18001）──────── 定时 / 事件触发工作流
```

**框架已提供、不要自建的能力**（自建会白干一遍）：

| 能力 | 框架提供物 |
|---|---|
| Agent 循环 / 多步规划 / 工具调用 | SDK Agent + Conversation |
| 工具定义与注册 | `Action` / `Observation` / `ToolExecutor` / `ToolDefinition` + `ToolRegistry` |
| 扩展方式 | **MCP 原生支持**（stdio / SSE / Streamable HTTP / OAuth），运维工具可做成 MCP Server 而不动核心 |
| 危险分级底层 | `ToolAnnotations`（readOnly / destructive / idempotent / openWorld） |
| **风险评级 + 确认策略** | `SecurityAnalyzer` + `ConfirmationPolicy`（默认高风险需审批） |
| **凭据隔离与脱敏** | `SecretRegistry`（会话级隔离、输出自动脱敏、动态轮换） |
| 事件流 / 持久化 / 暂停恢复 | REST + WebSocket + append-only EventLog + Condenser |
| 执行隔离 | `LocalWorkspace` / `DockerWorkspace` / `RemoteAPIWorkspace` |
| 行为约束 | `Skills` / `Hooks`（可阻断危险命令）/ `Plugin` |

**需要自建的**：前端三栏工作台、资源管理后端（服务器/数据库/项目）、任务状态投影、业务级审计表。

**推荐落地路线（组装式）**：自建 FastAPI（资源 / 任务 / 审批 / 审计）+ 直接使用 OpenHands Agent Server（**不 fork**）+ 自建前端（可复用 `@openhands/agent-canvas` 组件库）。

---

## 开发路线（阶段一 → 阶段七）

| 阶段 | 目标 | 状态 |
|---|---|---|
| 一 | 运行并理解 OpenHands：本地跑通、找到工具注册与执行位置、完成一次代码任务与一次终端任务 | ✅ 跑通 + 对话验收（2026-09-12）；工具注册/执行定位见 `docs/源码索引.md` |
| 二 | 实现第一个运维工具 `get_server_health` | ⬜ |
| 三 | SSH 资源管理：新增 / 列表 / 连接测试 / 当前服务器上下文 / 凭据安全存储 | ⬜ |
| 四 | 只读运维工具：`get_disk_usage`、`get_service_status`、`get_service_logs`、`get_process_list`、`list_docker_containers`、`get_container_logs`、`check_port`、`check_http` | ⬜ |
| 五 | 审批与审计：风险等级、操作预览、批准 / 拒绝、执行记录、执行后验证 | ⬜ |
| 六 | 前端三栏工作台（按 `docs/前端实现规格与开发提示词.md` 实现） | ⬜ |
| 七 | 扩展数据库与 Kubernetes（先只读） | ⬜ |

**第一个可运行目标**（不需要完整 UI）：

```text
用户输入：检查 HK-Ubuntu 的健康状态
Agent：识别目标服务器
工具：get_server_health
工具返回：CPU、内存、磁盘、负载、服务状态
Agent：分析结果并输出总结
```

成功标准：Agent 能识别服务器 ▸ 能调用结构化工具 ▸ SSH 异常时返回清晰错误 ▸ 工具执行有超时 ▸ **工具结果不泄露密码和私钥** ▸ 能区分正常项与异常项 ▸ 所有调用有任务 ID ▸ 可查看执行记录。

---

## 效果图覆盖情况（10 个状态 + 3 个补充态 + 2 张响应式示意）

| # | 状态 | 文件 |
|---|---|---|
| 1 | 空白欢迎页 | `效果图-01-空白欢迎页.png` |
| 2 | 已选择服务器但还没有聊天 | `效果图-02-已选服务器未聊天.png` |
| 3 | Agent 正在执行任务 | `效果图-03-Agent执行中-深色.png` |
| 4 | 工具调用展开状态 | `效果图-04-工具调用展开.png` |
| 5 | 等待用户审批状态 | `效果图-05-等待用户审批.png` |
| 6 | 任务完成状态 | `效果图-06-任务完成.png` |
| 7 | 工具执行失败状态 | `效果图-07-工具执行失败.png` |
| 8 | 数据库连接与数据库树展开 | `效果图-08-数据库树展开.png` |
| 9 | 右侧面板收起状态 | `效果图-09-右侧面板收起.png` |
| 10 | 浅色主题 | `效果图-10-浅色主题.png` |
| 11 | 响应式 · 窄窗自动折叠（1180×820） | `效果图-11-窄窗自动折叠.png` |
| 12 | 响应式 · 超宽屏居中（1920×900） | `效果图-12-超宽屏居中.png` |
| 13 | 桌面菜单栏展开态 | `效果图-13-顶部菜单展开.png` |
| 14 | **完全访问升级确认面板** | `效果图-14-完全访问升级确认.png` |
| 15 | **完全访问已开启**（横幅 + 档位） | `效果图-15-完全访问已开启.png` |

1~10 按需求开发文档 §B9 的清单出图，深色规范见 §B8，尺寸统一 1440×920；11、12 演示 §B12.2 的响应式行为；13~15 为补充态（菜单栏、权限升级闸门、高危档位提示）。原始参考图见 `效果图-00-原始参考图.jpg`。

**原型总览**：浏览器打开 `prototype/OpsPilot-原型总览.html`，可直接切换 13 个状态、一键切换深/浅色、并实时切换 **1180 / 1440 / 1920** 三种窗口尺寸观察响应式行为。

---

## 桌面封装选型（Tauri vs Electron）

"封装方式"指的是用哪个壳把网页界面变成桌面应用——**它只影响打包和分发，不影响界面代码本身**（两种方式跑的是同一套前端）。所以要判断的只有一件事：这个壳要不要承担业务逻辑。

| 维度 | Tauri | Electron |
|---|---|---|
| 技术 | Rust 后端 + 系统 WebView | Node.js + 内置 Chromium |
| 安装包体积 | 约 10~20 MB | 约 120~200 MB |
| 内存占用 | 低（复用系统 WebView） | 高（每个窗口一个 Chromium） |
| 主进程可写的语言 | Rust（或外挂 sidecar 进程） | Node.js |
| 生态与文档 | 较新，插件少于 Electron | 最成熟，问题好搜 |
| 上游复用 | 无 | **OpenHands 官方仓库自带 `electron/` 配置**，可直接抄 |
| 系统依赖 | Windows 需 WebView2（Win10 1803+ 与 Win11 自带）；构建机需装 Rust 工具链 | 无额外要求（Node 本来就要） |

**推荐：Tauri。** 理由是三条硬事实：

1. **OpsPilot 的壳里没有任何业务逻辑。** 重活全在 Python 侧——FastAPI（资源/任务/审批）+ OpenHands agent-server。桌面壳只干一件事：加载前端。这正好是 Tauri 的甜区，同时**完全绕开了它"Docker 后端要写 Rust"这个短板**。
2. **它已经是规格的一部分。** 需求开发文档 §A3 已定稿 `React + TypeScript + Vite + Tauri`，改选 Electron 要同步改文档、改验收。
3. **对"常驻开发工具"这个品类，体积和内存是真实体验。** 一个天天开着的运维工作台，200MB 内存和 20MB 内存的区别用户能感知。

**什么情况下应该改选 Electron（两个条件满足任一）：**

- 你希望**直接在桌面壳里写逻辑**（本地文件监控、系统托盘、开机自启、调用本地 kubectl 等）。这些用 Electron 的 Node 主进程写会顺很多；Tauri 得写 Rust 或另起 sidecar。
- 你打算把 **OpenHands 官方那套 Agent Canvas 原版应用一起打包**给别人用。上游的 Electron 配置是现成的，改造成本几乎为零。

> ⚠️ 选 Tauri 的唯一前置成本：构建机要装 **Rust 工具链**（一次性），以及 Windows 端依赖 **WebView2**（现代系统自带，老系统需随包分发）。

**本项目已定：Tauri。** 理由三条：

1. **OpsPilot 的壳里没有任何业务逻辑。** 重活全在 Python 侧 —— FastAPI（资源 / 任务 / 审批）+ OpenHands agent-server。桌面壳只干一件事：加载前端。这正好是 Tauri 的甜区，同时**完全绕开了它"Docker 后端要写 Rust"这个短板**。
2. **它已经是规格的一部分**（需求开发文档 §A3 定稿 `React + TypeScript + Vite + Tauri`），改选要同步改文档与验收。
3. **对"常驻开发工具"这个品类，体积和内存是真实体验。** 一个天天开着的运维工作台，200MB 内存和 20MB 内存的区别用户能感知。

**代价（已接受）**：构建机要装 Rust 工具链（一次性）；Windows 依赖 WebView2（现代系统自带，老系统需随包分发）。

**什么情况下重开评估**（满足任一，且需同步更新规格 §A3）：

- 需要**直接在桌面壳里写逻辑**：系统托盘、开机自启、调用本地 kubectl、监控本地文件。这些用 Electron 的 Node 主进程写会顺很多。
- 需要**把 OpenHands 官方那套 Agent Canvas 原版应用一起打包**给别人用 —— 上游的 Electron 配置是现成的。

详见 `docs/交接文档.md` §九「四项已定技术决策」。

---

## 待定项

1. **认证（JWT）**：开源版 OpenHands 无内置认证、单租户。面向多人开放前必须按需求开发文档 §A10 补 JWT 认证，未登录不可访问任何 API。
2. **日志 Tab 筛选交互**与**多目标标签**：文字规格已定义（§B6 / §B7），效果图未覆盖，实现时按文字做。
3. **移动端 / 平板**：当前响应式只覆盖到 960px 宽度（左右栏双双收起）。若未来要上平板，需补一套"面板改为抽屉式浮层"的方案。
4. **底部面板（v2）**：MVP 已定**置灰**（见下方「桌面封装选型」与 `docs/交接文档.md` §九）。v2 引入实时终端 + 原始日志流，并与聊天区联动。

> 桌面封装（**Tauri**）与菜单栏实现方式（**自绘**）已定，不再是待办；理由与理想态见 `docs/交接文档.md` §九「四项已定技术决策」。

### 四项已定技术决策（M0-5 落档 ✅，2026-09-12）

| # | 决策 | 结论 | 理由与理想态 |
|---|---|---|---|
| 1 | 桌面封装 | ✅ **Tauri** | 壳里无业务逻辑，前端代码与壳完全解耦；安装包 ≤30MB；见上文选型分析 |
| 2 | 菜单栏 | ✅ **自绘** | 三平台视觉一致 + 与效果图对齐 + 菜单项承载业务语义；快捷键归系统 |
| 3 | 底部面板 / 打开终端 | ✅ **MVP 置灰，v2 再做** | 聊天区是唯一主入口；工具卡已提供终端可视性；v2 做可折叠底栏并与聊天联动 |
| 4 | 上游 patch 策略 | ✅ **提 PR 优先，禁止静默 fork** | `upstream/` 只读；PR 合并前用 patch 过渡并登记 issue；升版本第一件事检查 patch |

如需推翻某条：必须在 **M5 开工前**提出，并同步更新规格与效果图（见交接文档 §九、§十二）。

---

## 许可与合规

- OpenHands 及 Software Agent SDK 均为 **MIT**，允许商用、修改与分发。
- 本项目自身许可：`待定`。
