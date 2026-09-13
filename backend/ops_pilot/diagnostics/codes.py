"""统一错误码表。

每个错误码固定携带：故障层次(layer)、默认结论(summary)、修复步骤(fix_steps)。
目的：Agent 输出的是**可执行的诊断结论**，而不是一坨原始命令输出。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------- 故障层次 ----------
LAYER_HOST = "host"              # 主机/OS 层
LAYER_SERVICE = "service"        # systemd 服务
LAYER_CONTAINER = "container"    # Docker 容器
LAYER_K8S = "k8s"                # Kubernetes
LAYER_DB = "database"            # 数据库
LAYER_NETWORK = "network"        # 网络/端口/HTTP
LAYER_ALERTING = "alerting"      # 告警与监控
LAYER_CHANGE = "change"          # 变更操作
LAYER_CAPABILITY = "capability"  # 能力本身（未实现）

ALL_LAYERS = (
    LAYER_HOST, LAYER_SERVICE, LAYER_CONTAINER, LAYER_K8S,
    LAYER_DB, LAYER_NETWORK, LAYER_ALERTING, LAYER_CHANGE, LAYER_CAPABILITY,
)


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    layer: str
    summary: str
    fix_steps: tuple[str, ...]


# ---------- 连接与权限 ----------
HOST_SSH_AUTH_FAILED = "HOST_SSH_AUTH_FAILED"
HOST_SSH_UNREACHABLE = "HOST_SSH_UNREACHABLE"
HOST_CMD_FAILED = "HOST_CMD_FAILED"
HOST_PERMISSION_DENIED = "HOST_PERMISSION_DENIED"
HOST_CREDENTIAL_MISSING = "HOST_CREDENTIAL_MISSING"

# ---------- 主机资源 ----------
HOST_DISK_FULL = "HOST_DISK_FULL"
HOST_DISK_WARN = "HOST_DISK_WARN"
HOST_MEM_EXHAUSTED = "HOST_MEM_EXHAUSTED"
HOST_LOAD_HIGH = "HOST_LOAD_HIGH"
HOST_SWAP_USED = "HOST_SWAP_USED"

# ---------- 服务 ----------
SERVICE_NOT_FOUND = "SERVICE_NOT_FOUND"
SERVICE_INACTIVE = "SERVICE_INACTIVE"
SERVICE_FAILED = "SERVICE_FAILED"
SERVICE_RESTART_FAILED = "SERVICE_RESTART_FAILED"

# ---------- 容器 ----------
CONTAINER_NOT_FOUND = "CONTAINER_NOT_FOUND"
CONTAINER_EXITED = "CONTAINER_EXITED"
CONTAINER_RESTARTING = "CONTAINER_RESTARTING"
CONTAINER_OOM = "CONTAINER_OOM"
DOCKER_MISSING = "DOCKER_MISSING"

# ---------- Kubernetes ----------
K8S_KUBECTL_MISSING = "K8S_KUBECTL_MISSING"
K8S_FORBIDDEN = "K8S_FORBIDDEN"
K8S_POD_NOT_READY = "K8S_POD_NOT_READY"
K8S_POD_CRASH_LOOP = "K8S_POD_CRASH_LOOP"
K8S_POD_IMAGE_PULL = "K8S_POD_IMAGE_PULL"
K8S_POD_PENDING = "K8S_POD_PENDING"
K8S_POD_EVICTED = "K8S_POD_EVICTED"
K8S_ROLLOUT_STUCK = "K8S_ROLLOUT_STUCK"
K8S_SCALE_FAILED = "K8S_SCALE_FAILED"
K8S_ROLLBACK_FAILED = "K8S_ROLLBACK_FAILED"

# ---------- 数据库 ----------
DB_CONN_FAILED = "DB_CONN_FAILED"
DB_AUTH_FAILED = "DB_AUTH_FAILED"
DB_SLOW_QUERY = "DB_SLOW_QUERY"
DB_LOCK_WAIT = "DB_LOCK_WAIT"
DB_POOL_FULL = "DB_POOL_FULL"
DB_READONLY_VIOLATION = "DB_READONLY_VIOLATION"

# ---------- 网络 ----------
NET_PORT_CLOSED = "NET_PORT_CLOSED"
NET_HTTP_ERROR = "NET_HTTP_ERROR"
NET_DNS_FAILED = "NET_DNS_FAILED"
NET_TLS_ERROR = "NET_TLS_ERROR"

# ---------- 告警 ----------
ALERT_FIRING = "ALERT_FIRING"
ALERT_NO_DATA = "ALERT_NO_DATA"
ALERTMANAGER_UNREACHABLE = "ALERTMANAGER_UNREACHABLE"
PROMETHEUS_UNREACHABLE = "PROMETHEUS_UNREACHABLE"
PROMQL_INVALID = "PROMQL_INVALID"

# ---------- 变更 ----------
CHANGE_DRYRUN_FAILED = "CHANGE_DRYRUN_FAILED"
CHANGE_NO_ROLLBACK_PLAN = "CHANGE_NO_ROLLBACK_PLAN"
CHANGE_EXEC_FAILED = "CHANGE_EXEC_FAILED"
CHANGE_ROLLBACK_FAILED = "CHANGE_ROLLBACK_FAILED"
CHANGE_APPROVAL_REQUIRED = "CHANGE_APPROVAL_REQUIRED"

# ---------- 能力未实现 ----------
CAPABILITY_NOT_IMPLEMENTED = "CAPABILITY_NOT_IMPLEMENTED"

ERRORS: dict[str, ErrorSpec] = {
    # 连接与权限
    HOST_SSH_AUTH_FAILED: ErrorSpec(
        HOST_SSH_AUTH_FAILED, LAYER_HOST, "SSH 认证失败（密钥或账号不被接受）", (
            "确认目标主机上的 ~/.ssh/authorized_keys 含本系统使用的公钥",
            "确认登录用户名正确（常见坑：应为 root 还是普通用户）",
            "确认密钥文件权限为 600，且未设置 passphrase 阻碍非交互登录",
            "若经堡垒机，确认堡垒机配置与端口正确",
        )),
    HOST_SSH_UNREACHABLE: ErrorSpec(
        HOST_SSH_UNREACHABLE, LAYER_HOST, "SSH 网络不可达（端口不通或被防火墙拦截）", (
            "从控制机执行 nc -vz <host> <port> 验证端口连通性",
            "检查安全组/防火墙是否放通来源 IP",
            "确认主机 SSH 服务在运行：systemctl status sshd",
            "确认主机未宕机（云控制台查看实例状态）",
        )),
    HOST_CMD_FAILED: ErrorSpec(
        HOST_CMD_FAILED, LAYER_HOST, "命令执行失败（非认证、非网络问题）", (
            "查看返回的 stderr 定位具体报错",
            "确认命令在目标主机存在（如 kubectl/docker 是否安装）",
            "确认执行用户具备该命令权限（必要时 sudo -n）",
        )),
    HOST_PERMISSION_DENIED: ErrorSpec(
        HOST_PERMISSION_DENIED, LAYER_HOST, "权限不足，命令被拒绝", (
            "确认执行用户是否为目标操作所需的用户（如 docker 组）",
            "配置免密 sudo：visudo 添加 '<user> ALL=(ALL) NOPASSWD: <cmd>'",
            "避免直接用 root 之外用户操作系统级命令",
        )),
    HOST_CREDENTIAL_MISSING: ErrorSpec(
        HOST_CREDENTIAL_MISSING, LAYER_HOST, "未找到该主机的凭据配置", (
            "在连接管理中登记该主机（标识、地址、端口、用户、认证方式）",
            "确认传入的 server_id 与登记的一致（server_id 不是 IP）",
        )),

    # 主机资源
    HOST_DISK_FULL: ErrorSpec(
        HOST_DISK_FULL, LAYER_HOST, "磁盘使用率达到危险水平", (
            "定位大目录：du -sh /path/* 逐层下钻（先看 /var/log、/var/lib/docker）",
            "清理可删内容：日志轮转 journalctl --vacuum-size=500M；清理旧镜像 docker image prune",
            "确认无被删除但未释放的句柄：lsof +L1",
            "若确需扩容，先做快照再扩盘",
        )),
    HOST_DISK_WARN: ErrorSpec(
        HOST_DISK_WARN, LAYER_HOST, "磁盘使用率偏高，需关注增长趋势", (
            "记录当前用量，观察增长速度判断是否会在短期内打满",
            "配置日志轮转与清理策略",
            "设置磁盘告警阈值（建议 warn 80% / crit 90%）",
        )),
    HOST_MEM_EXHAUSTED: ErrorSpec(
        HOST_MEM_EXHAUSTED, LAYER_HOST, "内存不足，存在 OOM 风险", (
            "查看占用最高的进程：ps aux --sort=-%mem | head",
            "确认是否有内存泄漏（观察该进程 RSS 是否持续增长）",
            "检查是否 cache/buffer 占用（available 才是可用量）",
            "应急可重启问题进程，根治需调整配置或扩容",
        )),
    HOST_LOAD_HIGH: ErrorSpec(
        HOST_LOAD_HIGH, LAYER_HOST, "系统负载高于 CPU 核数，存在排队", (
            "区分 CPU 密集还是 IO 等待：vmstat 1 看 wa 与 us 列",
            "CPU 密集：ps aux --sort=-%cpu | head 定位进程",
            "IO 等待：iostat -x 1 看 %util 与 await",
            "确认是否为常态峰值，必要时扩容或限流",
        )),
    HOST_SWAP_USED: ErrorSpec(
        HOST_SWAP_USED, LAYER_HOST, "已开始使用 swap，性能会明显下降", (
            "确认哪些进程被换出，评估内存是否真的不够",
            "临时降低 swappiness：sysctl vm.swappiness=10",
            "根治需扩容内存或限制进程内存上限",
        )),

    # 服务
    SERVICE_NOT_FOUND: ErrorSpec(
        SERVICE_NOT_FOUND, LAYER_SERVICE, "目标服务不存在", (
            "systemctl list-units --type=service 确认真实服务名",
            "确认部署方式（可能是容器或 K8s，而非 systemd）",
            "注意服务名后缀（如 nginx.service 与 nginx 的差别）",
        )),
    SERVICE_INACTIVE: ErrorSpec(
        SERVICE_INACTIVE, LAYER_SERVICE, "服务未在运行", (
            "查看失败原因：systemctl status <svc> 与 journalctl -u <svc> -n 100",
            "确认是否配置了开机自启：systemctl is-enabled <svc>",
            "启动前先确认配置文件语法正确（如 nginx -t）",
        )),
    SERVICE_FAILED: ErrorSpec(
        SERVICE_FAILED, LAYER_SERVICE, "服务处于 failed 状态", (
            "journalctl -u <svc> -n 200 --no-pager 查看退出原因",
            "常见原因：配置错误、端口被占用、依赖服务未起、权限不足",
            "修复后先 systemctl daemon-reload 再启动",
        )),
    SERVICE_RESTART_FAILED: ErrorSpec(
        SERVICE_RESTART_FAILED, LAYER_SERVICE, "重启失败", (
            "检查 systemctl status 与 journalctl 输出",
            "确认端口未被其他进程占用：ss -lntp | grep <port>",
            "确认配置无误后再试；重启前记录当前版本以便回滚",
        )),

    # 容器
    CONTAINER_NOT_FOUND: ErrorSpec(
        CONTAINER_NOT_FOUND, LAYER_CONTAINER, "未找到指定容器", (
            "docker ps -a 确认容器名（注意 name 与 id 的区别）",
            "确认容器是否被清理（docker ps -a 也看不到说明已删除）",
        )),
    CONTAINER_EXITED: ErrorSpec(
        CONTAINER_EXITED, LAYER_CONTAINER, "容器已退出", (
            "docker logs <container> --tail 200 查看退出前输出",
            "docker inspect <container> 看 ExitCode（137=OOM被杀，1=应用异常）",
            "确认重启策略：docker inspect 看 RestartPolicy",
        )),
    CONTAINER_RESTARTING: ErrorSpec(
        CONTAINER_RESTARTING, LAYER_CONTAINER, "容器处于反复重启状态", (
            "docker logs --previous 看上一次崩溃日志",
            "若 ExitCode=137 多为内存超限，检查 memory limit 与应用实际用量",
            "确认健康检查与依赖服务（数据库、配置中心）是否可用",
        )),
    CONTAINER_OOM: ErrorSpec(
        CONTAINER_OOM, LAYER_CONTAINER, "容器因内存超限被终止（OOMKilled）", (
            "docker inspect 确认 Memory 限制与实际峰值",
            "调整 -m/--memory 限制，或优化应用内存占用",
            "同时检查宿主机内存是否充足",
        )),
    DOCKER_MISSING: ErrorSpec(
        DOCKER_MISSING, LAYER_CONTAINER, "目标主机未安装或无法执行 docker", (
            "确认 docker 已安装：which docker",
            "确认执行用户在 docker 组，或有 sudo 权限",
            "确认 docker daemon 在运行：systemctl status docker",
        )),

    # Kubernetes
    K8S_KUBECTL_MISSING: ErrorSpec(
        K8S_KUBECTL_MISSING, LAYER_K8S, "目标主机没有可用的 kubectl", (
            "在该主机安装 kubectl 并配置 kubeconfig",
            "或改用装有 kubectl 的跳板机作为 server_id",
        )),
    K8S_FORBIDDEN: ErrorSpec(
        K8S_FORBIDDEN, LAYER_K8S, "kubectl 返回权限不足（RBAC 拒绝）", (
            "确认当前 context 与 serviceaccount 权限",
            "kubectl auth can-i <verb> <resource> -n <ns> 验证",
            "按需向集群管理员申请 Role/ClusterRole 绑定",
        )),
    K8S_POD_NOT_READY: ErrorSpec(
        K8S_POD_NOT_READY, LAYER_K8S, "Pod 未就绪（Readiness 探针未通过）", (
            "kubectl describe pod 看 Events 与 Conditions",
            "看 readinessProbe 配置是否过严（initialDelaySeconds/timeoutSeconds）",
            "确认依赖的下游服务是否可达",
        )),
    K8S_POD_CRASH_LOOP: ErrorSpec(
        K8S_POD_CRASH_LOOP, LAYER_K8S, "Pod 处于 CrashLoopBackOff", (
            "kubectl logs <pod> --previous 看上次崩溃日志",
            "常见原因：启动参数/配置错误、依赖不可达、内存 limit 过小（ExitCode 137）",
            "确认镜像 tag 是否为预期版本",
        )),
    K8S_POD_IMAGE_PULL: ErrorSpec(
        K8S_POD_IMAGE_PULL, LAYER_K8S, "镜像拉取失败（ImagePullBackOff / ErrImagePull）", (
            "kubectl describe pod 看具体原因（仓库认证/镜像不存在/网络不通）",
            "确认 imagePullSecrets 是否正确配置",
            "确认镜像 tag 存在且仓库可访问",
        )),
    K8S_POD_PENDING: ErrorSpec(
        K8S_POD_PENDING, LAYER_K8S, "Pod 一直 Pending，无法调度", (
            "kubectl describe pod 看 Events 的调度失败原因",
            "常见：资源不足(Insufficient cpu/memory)、节点选择器/污点不匹配、PVC 未绑定",
            "kubectl get nodes 看节点可分配资源与污点",
        )),
    K8S_POD_EVICTED: ErrorSpec(
        K8S_POD_EVICTED, LAYER_K8S, "Pod 被驱逐（节点资源压力）", (
            "kubectl describe node 看是否有 MemoryPressure/DiskPressure",
            "kubectl get events --field-selector reason=Evicted 看被驱逐的 Pod",
            "清理节点磁盘或扩容节点后再重建 Pod",
        )),
    K8S_ROLLOUT_STUCK: ErrorSpec(
        K8S_ROLLOUT_STUCK, LAYER_K8S, "滚动更新卡住，未进入完成状态", (
            "kubectl rollout status deploy/<name> -n <ns> 看当前进度",
            "kubectl describe deploy 看 Conditions（常见：ProgressDeadlineExceeded）",
            "确认新副本是否能通过就绪探针；否则回滚：kubectl rollout undo deploy/<name>",
        )),
    K8S_SCALE_FAILED: ErrorSpec(
        K8S_SCALE_FAILED, LAYER_K8S, "扩缩容失败", (
            "确认目标副本数在合理范围且未超过资源配额",
            "kubectl describe deploy 看事件",
            "确认集群有足够可调度资源（kubectl describe node）",
        )),
    K8S_ROLLBACK_FAILED: ErrorSpec(
        K8S_ROLLBACK_FAILED, LAYER_K8S, "回滚失败", (
            "kubectl rollout history deploy/<name> 确认有可回滚的历史版本",
            "kubectl rollout undo deploy/<name> --to-revision=<n>",
            "若无历史版本，需用上一版镜像 tag 重新 apply",
        )),

    # 数据库
    DB_CONN_FAILED: ErrorSpec(
        DB_CONN_FAILED, LAYER_DB, "数据库连接失败", (
            "确认地址、端口、网络可达（含安全组）",
            "确认数据库服务在运行且允许来源 IP",
            "确认连接数是否打满（详见连接池问题）",
        )),
    DB_AUTH_FAILED: ErrorSpec(
        DB_AUTH_FAILED, LAYER_DB, "数据库账号或权限校验失败", (
            "确认账号密码正确且未过期",
            "确认账号允许从当前来源主机连接（MySQL 的 host 白名单）",
            "确认账号具备所需库表的只读权限",
        )),
    DB_SLOW_QUERY: ErrorSpec(
        DB_SLOW_QUERY, LAYER_DB, "存在慢查询", (
            "用 EXPLAIN 分析执行计划，关注 type=ALL（全表扫描）与 rows 估算",
            "检查 WHERE/ORDER BY 字段是否命中索引",
            "避免 SELECT *、大分页深翻、在索引列上做函数运算",
        )),
    DB_LOCK_WAIT: ErrorSpec(
        DB_LOCK_WAIT, LAYER_DB, "出现锁等待，查询被阻塞", (
            "查当前锁：SHOW ENGINE INNODB STATUS 或 information_schema.INNODB_LOCKS",
            "定位持锁长事务，评估是否可以终止（KILL <id>）",
            "优化事务粒度，避免长事务持锁",
        )),
    DB_POOL_FULL: ErrorSpec(
        DB_POOL_FULL, LAYER_DB, "连接池打满", (
            "确认应用侧连接是否未正确归还（连接泄漏）",
            "调大 max_connections 前先确认内存是否够",
            "引入连接池上限与超时，排查慢查询占用连接",
        )),
    DB_READONLY_VIOLATION: ErrorSpec(
        DB_READONLY_VIOLATION, LAYER_DB, "提交了非只读语句，已被拒绝", (
            "本系统只允许 SELECT/SHOW/DESCRIBE/EXPLAIN 类只读语句",
            "写库操作请走变更流程并经过审批",
        )),

    # 网络
    NET_PORT_CLOSED: ErrorSpec(
        NET_PORT_CLOSED, LAYER_NETWORK, "目标端口未监听或不可达", (
            "在目标机确认监听：ss -lntp | grep <port>",
            "确认进程存活且绑定地址非 127.0.0.1（如需外部访问应绑 0.0.0.0）",
            "检查本机与中间的防火墙/安全组",
        )),
    NET_HTTP_ERROR: ErrorSpec(
        NET_HTTP_ERROR, LAYER_NETWORK, "HTTP 探测返回非预期状态码", (
            "根据状态码判断：4xx 多为请求或权限问题，5xx 多为服务端异常",
            "看服务端日志定位 5xx 原因",
            "确认健康检查路径是否正确",
        )),
    NET_DNS_FAILED: ErrorSpec(
        NET_DNS_FAILED, LAYER_NETWORK, "域名解析失败", (
            "nslookup/dig 验证解析结果",
            "检查 /etc/resolv.conf 与 DNS 服务",
            "确认是否为内网域名且 DNS 可达",
        )),
    NET_TLS_ERROR: ErrorSpec(
        NET_TLS_ERROR, LAYER_NETWORK, "TLS/证书校验失败", (
            "确认证书是否过期：openssl x509 -in cert.pem -noout -dates",
            "确认证书域名与访问域名匹配",
            "确认客户端信任该 CA（自签证书需加信任）",
        )),

    # 告警
    ALERT_FIRING: ErrorSpec(
        ALERT_FIRING, LAYER_ALERTING, "存在正在触发的告警", (
            "读取告警的 labels/annotations 确定对象与阈值",
            "用 PromQL 查关联指标确认当前值与趋势",
            "结合同时间段的其他告警判断是否为同一根因",
        )),
    ALERT_NO_DATA: ErrorSpec(
        ALERT_NO_DATA, LAYER_ALERTING, "告警规则无数据（NoData），可能是采集中断", (
            "确认 exporter 是否存活、是否被抓取",
            "在 Prometheus 的 Targets 页确认目标状态",
            "确认采集任务配置是否变更",
        )),
    ALERTMANAGER_UNREACHABLE: ErrorSpec(
        ALERTMANAGER_UNREACHABLE, LAYER_ALERTING, "无法连接 Alertmanager", (
            "确认 Alertmanager 地址与端口可访问",
            "确认认证方式（Basic Auth / Token / 反向代理）",
            "检查 Alertmanager 自身健康：/-/healthy",
        )),
    PROMETHEUS_UNREACHABLE: ErrorSpec(
        PROMETHEUS_UNREACHABLE, LAYER_ALERTING, "无法连接 Prometheus", (
            "确认 Prometheus 地址可访问（注意是否经过网关或需要认证）",
            "确认 /api/v1/query 可正常响应",
            "检查网络策略与代理设置",
        )),
    PROMQL_INVALID: ErrorSpec(
        PROMQL_INVALID, LAYER_ALERTING, "PromQL 语句无法执行", (
            "检查指标名与标签是否拼写正确（可用 /api/v1/label/__name__/values 查可用指标）",
            "检查函数用法与括号匹配",
            "确认时间范围参数合法",
        )),

    # 变更
    CHANGE_DRYRUN_FAILED: ErrorSpec(
        CHANGE_DRYRUN_FAILED, LAYER_CHANGE, "变更预演（dry-run）未通过，不能执行", (
            "按 dry-run 返回的具体问题修正后再试",
            "确认目标对象存在、参数合法、权限足够",
            "预演不通过时严禁直接执行",
        )),
    CHANGE_NO_ROLLBACK_PLAN: ErrorSpec(
        CHANGE_NO_ROLLBACK_PLAN, LAYER_CHANGE, "缺少回滚方案，已拒绝执行", (
            "执行前必须能回答：如何撤回到变更前状态",
            "记录当前版本/镜像 tag/配置快照作为回滚点",
            "补充回滚方案后重新发起",
        )),
    CHANGE_EXEC_FAILED: ErrorSpec(
        CHANGE_EXEC_FAILED, LAYER_CHANGE, "变更执行失败", (
            "先确认当前实际状态，避免重复执行造成叠加影响",
            "按记录的回滚点执行回滚",
            "定位失败原因后再决定是否重试",
        )),
    CHANGE_ROLLBACK_FAILED: ErrorSpec(
        CHANGE_ROLLBACK_FAILED, LAYER_CHANGE, "回滚失败，需人工介入", (
            "立即停止后续自动化操作",
            "按预先记录的版本/配置手工恢复",
            "保留现场日志用于事后复盘",
        )),
    CHANGE_APPROVAL_REQUIRED: ErrorSpec(
        CHANGE_APPROVAL_REQUIRED, LAYER_CHANGE, "该操作需要人工审批后才能执行", (
            "向负责人说明：操作内容、影响范围、回滚方案",
            "审批通过后再发起执行",
        )),

    # 能力未实现
    CAPABILITY_NOT_IMPLEMENTED: ErrorSpec(
        CAPABILITY_NOT_IMPLEMENTED, LAYER_CAPABILITY, "该能力当前未实现", (
            "本系统不会编造结果来冒充已实现",
            "如需该能力，请补充接入信息后实现",
        )),
}


def spec_of(code: str) -> ErrorSpec:
    """取错误码定义；未知码回退到通用定义，避免 KeyError 中断诊断。"""
    return ERRORS.get(code) or ErrorSpec(
        code, LAYER_CAPABILITY, f"未归类的错误：{code}", ("查看返回的证据字段定位具体原因",))


def all_codes() -> tuple[str, ...]:
    return tuple(ERRORS)
