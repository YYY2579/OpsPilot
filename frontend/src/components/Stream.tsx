import { STREAMS, type Block } from "../mock/streams";
import {
  ApprovalCard, ErrorCard, KV, PlanCard, SummaryCard, Term, ToolBody, ToolCard,
} from "./cards";
import { Icon } from "../shell/icons";

function ToolBodies({ body }: { body: NonNullable<Extract<Block, { kind: "tool" }>["body"]> }) {
  if (body === "ps_output") {
    return (
      <ToolBody>
        <Term>{`  PID    USER   %CPU   %MEM   COMMAND
 2143   app     62.1   18.4   java -jar backend.jar
  882   root     8.6    1.2   containerd
 1174   www      4.2    2.1   nginx
  301   root     3.1    0.8   dockerd`}</Term>
      </ToolBody>
    );
  }

  if (body === "docker_ps") {
    return (
      <ToolBody>
        <KV rows={[
          { k: "工具名称", v: <span className="font-mono">list_docker_containers</span> },
          { k: "目标资源", v: <>HK-Ubuntu <span className="text-ink3 text-[11.5px]">（hk-ubuntu）</span></> },
          { k: "参数", v: <span className="text-ink3">—</span> },
          { k: "风险等级", v: <span className="badge l">L1 · 只读</span> },
          { k: "执行命令", v: <span className="font-mono">{"docker ps -a --format '{{.Names}}\\t{{.Status}}'"}</span>, mono: true },
          { k: "执行耗时", v: "1.5s" },
          { k: "审批", v: <span className="s-dim">无需审批</span> },
        ]} />
        <div className="mt-[9px] text-[11px] text-ink3 mb-[4px]">标准输出</div>
        <Term>{`NAME                 STATUS
opspilot-gateway  Up 6 days (healthy)
opspilot-backend  Up 6 days (unhealthy)  cpu 182%
opspilot-mysql    Up 12 days (healthy)
nginx             Up 6 days (healthy)`}</Term>
        <div className="mt-[8px] text-[11px] text-ink3">错误输出　<span className="text-ink3">(空)</span></div>
      </ToolBody>
    );
  }

  if (body === "container_logs") {
    return (
      <ToolBody>
        <Term>{`10:23:07 ERROR  GC overhead limit exceeded — Full GC 连续 5 次
10:23:07 ERROR  OutOfMemoryError: Java heap space`}</Term>
      </ToolBody>
    );
  }

  if (body === "restart_one_line") {
    return (
      <ToolBody>
        <Term><span className="m">$ docker restart opspilot-backend</span>　<span className="g">exit 0</span> · 容器已重启，健康检查通过</Term>
      </ToolBody>
    );
  }

  // list_pods_expanded：失败工具卡的 8 字段（含错误输出 / 标准输出一行）
  return (
    <ToolBody>
      <dl className="kv" style={{ gridTemplateColumns: "64px 1fr 64px 1fr", marginBottom: 9 }}>
        <dt>目标资源</dt><dd>Rocky-K8s-Master</dd>
        <dt>风险等级</dt><dd><span className="badge l">L1 · 只读</span></dd>
        <dt>执行命令</dt><dd className="font-mono" style={{ gridColumn: "2 / span 3" }}>kubectl get pods -A -o wide</dd>
      </dl>
      <div className="mt-[9px] text-[11px] text-ink3 mb-[4px]">错误输出</div>
      <Term tone="fail"><span className="r">{`E0912 11:26:03.417  memcache.go:265] couldn't get resource list for metrics.k8s.io/v1beta1
E0912 11:26:08.436  dial tcp 192.168.1.153:6443: i/o timeout`}</span>
<span className="y">error: unable to connect to the server: dial tcp 192.168.1.153:6443: i/o timeout</span></Term>
      <div className="mt-[8px] text-[11px] text-ink3">标准输出　<span className="text-ink3">(空)</span></div>
    </ToolBody>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "user":
      return <div className="msg-user">{block.text}</div>;

    case "ai":
      return <div className="msg-ai">{block.text.startsWith("✓")
        ? <span className="flex items-center gap-[7px] text-[12.5px] text-ink2">
            <Icon.check size={12} className="s-ok" />{block.text.replace(/^✓\s*/, "")}
          </span>
        : block.text}</div>;

    case "plan":
      return <PlanCard title={block.title} steps={block.steps} />;

    case "tool":
      return (
        <ToolCard name={block.name} desc={block.desc} status={block.status}
                  duration={block.duration} badge={block.badge}>
          {block.body && <ToolBodies body={block.body} />}
        </ToolCard>
      );

    case "approval":
      return (
        <ApprovalCard
          operation="重启 backend 容器"
          target="HK-Ubuntu"
          targetId="hk-ubuntu"
          cause="根因：backend 容器 JVM 堆内存打满，连续 Full GC 是 CPU 飙高的直接原因。修复动作需你确认。"
          riskLevel="L3 · 中风险"
          command="docker restart opspilot-backend"
          impact="服务中断 5～15 秒"
          rollback="重新启动原容器；失败则回滚上一镜像 tag"
        />
      );

    case "summary":
      return (
        <SummaryCard
          problem="backend 容器 CPU 182%，服务响应变慢"
          cause="JVM 堆内存打满，连续 5 次 Full GC"
          action="已获批重启 backend 容器（L3 · 中风险）"
          verify="健康检查通过，CPU 回落，无新 ERROR 日志"
          stats={[
            { label: "CPU 使用率", value: "182% → 24%" },
            { label: "内存占用", value: "91% → 46%" },
            { label: "Full GC 次数", value: "5 → 0" },
          ]}
          suggestions={[
            "当前堆上限 2 GiB 已不够用，建议调到 3 GiB；",
            "容器 healthcheck 的失败阈值偏松，建议收紧；",
            "给堆内存使用率加一条 Prometheus 告警规则（>85% 持续 5 分钟）。",
          ]}
        />
      );

    case "error":
      return (
        <ErrorCard
          reason={<><b className="s-err">失败原因</b>：连接 apiserver <span className="font-mono">192.168.1.153:6443</span> 超时 —— 不是权限问题，是网络不通。</>}
          evidence="已排除：SSH 正常 · kubectl 已安装 · 凭据解析正常（credential_ref 未泄露到上下文）。"
          next="接下来我可以：① 用 check_port 探测 6443 端口；② 用 check_route 确认路由；③ 查看 apiserver 容器是否在运行。"
        />
      );
  }
}

export default function Stream({ stateId }: { stateId: string }) {
  const blocks = STREAMS[stateId] ?? STREAMS["03"];
  const failBlock = stateId === "07";

  return (
    <div className="stream">
      {blocks.map((b, i) => <BlockView key={i} block={b} />)}
      {failBlock && (
        <div className="acts">
          <button className="b go"><Icon.check size={12} />重试本次工具调用</button>
          <button className="b">先探测 6443 端口</button>
          <button className="b no">跳过这一步</button>
        </div>
      )}
    </div>
  );
}
