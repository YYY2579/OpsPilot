import type { ReactNode } from "react";

import { Icon } from "../shell/icons";

export type Status = "done" | "run" | "todo" | "fail";

const STATUS_ICON: Record<Status, ReactNode> = {
  done: <Icon.check size={12} className="s-ok" />,
  run: <span className="s-run text-[10px] leading-none">●</span>,
  todo: <span className="s-dim text-[10px] leading-none">○</span>,
  fail: <Icon.close size={12} className="s-err" />,
};

/** 步骤链卡片（CLASSIFY_TASK / PLAN / INSPECT 的业务投影） */
export function PlanCard({ title, steps }: {
  title: string;
  steps: { name: string; status: Status; note: string }[];
}) {
  const done = steps.filter((s) => s.status === "done").length;
  return (
    <div className="card">
      <div className="hd">
        <Icon.doc size={13} />
        <span className="ttl">{title}</span>
        <span className="ml-auto">{done}/{steps.length} 已完成</span>
      </div>
      <div className="plan">
        {steps.map((s) => (
          <div className="pj" key={s.name}>
            {STATUS_ICON[s.status]}
            <span>{s.name}</span>
            <span className={`st ${s.status === "done" ? "s-ok" : s.status === "run" ? "s-run" : s.status === "fail" ? "s-err" : "s-dim"}`}>{s.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 工具调用卡片（§5.6：折叠态只看行为，展开态看 8 个字段） */
export function ToolCard({
  name, desc, status = "done", duration, badge = "L1", children,
}: {
  name: string;
  desc: string;
  status?: Status;
  duration: string;
  badge?: string;
  children?: ReactNode;
}) {
  const statText = status === "fail" ? "执行失败" : status === "run" ? "进行中" : "已完成";
  const statCls = status === "fail" ? "s-err" : status === "run" ? "s-run" : "s-ok";

  // 失败态用 .hd 结构（警示图标 + 红色工具名），与效果图-07 一致
  if (status === "fail") {
    return (
      <div className="card fail">
        <div className="hd">
          <Icon.alert size={13} />
          <span className="ttl" style={{ color: "var(--err)" }}>{name}</span>
          <span>{desc}</span>
          <span className="ml-auto s-err flex items-center gap-[5px]"><Icon.close size={12} />{statText} · {duration}</span>
          <span className={`badge ${badge.startsWith("L1") ? "l" : badge.startsWith("L3") ? "m" : "h"}`}>{badge}</span>
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className="card">
      <div className="toolhd">
        <Icon.server size={13} className="s-dim" />
        <div className="min-w-0">
          <div className="nm">{name}</div>
          <div className="desc">{desc}</div>
        </div>
        <div className={`stat ${statCls}`}>
          <Icon.check size={12} />
          {statText} · {duration}
        </div>
        <span className={`badge ${badge.startsWith("L1") ? "l" : badge.startsWith("L3") ? "m" : "h"}`}>{badge}</span>
      </div>
      {children}
    </div>
  );
}

/** 工具卡展开内容的外壳（与 .toolhd 之间有一条分隔线） */
export function ToolBody({ children }: { children: ReactNode }) {
  return <div className="px-[11px] py-[9px] border-t border-line">{children}</div>;
}

/** 键值对表（工具卡、确认卡通用） */
export function KV({ rows }: { rows: { k: string; v: ReactNode; mono?: boolean }[] }) {
  return (
    <dl className="kv">
      {rows.map((r) => (
        <div key={r.k} className="contents">
          <dt>{r.k}</dt>
          <dd className={r.mono ? "font-mono text-[12px]" : undefined}>{r.v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 终端输出块 */
export function Term({ children, tone }: { children: ReactNode; tone?: "fail" }) {
  return <div className="term" style={tone === "fail" ? { borderColor: "var(--err)" } : undefined}>{children}</div>;
}

/** 审批卡片（§5.7：必须给"拒绝"与"修改方案"，不能只放一个执行按钮） */
export function ApprovalCard({
  operation, target, targetId, cause, riskLevel, command, impact, rollback,
}: {
  operation: string;
  target: string;
  targetId: string;
  cause: string;
  riskLevel: string;
  command: string;
  impact: string;
  rollback: string;
}) {
  return (
    <div className="approve">
      <h4><Icon.alert size={14} />需要你的批准</h4>
      <div className="text-[12px] text-ink2 mb-[8px]">{cause}</div>
      <dl className="grid">
        <dt>操作</dt><dd>{operation}</dd>
        <dt>目标</dt><dd>{target} · <span className="font-mono">server_id: {targetId}</span></dd>
        <dt>风险等级</dt><dd><span className="badge m">{riskLevel}</span></dd>
        <dt>执行内容</dt><dd className="font-mono text-[12px]">{command}</dd>
        <dt>预计影响</dt><dd>{impact}</dd>
        <dt>回滚方案</dt><dd>{rollback}</dd>
      </dl>
      <div className="acts">
        <button className="b">查看命令</button>
        <button className="b go"><Icon.check size={12} />批准执行</button>
        <button className="b no">拒绝</button>
        <button className="b warn">修改方案</button>
      </div>
    </div>
  );
}

/** 总结卡片（REPORT 状态的载体） */
export function SummaryCard({
  problem, cause, action, verify, stats, suggestions,
}: {
  problem: string;
  cause: string;
  action: string;
  verify: string;
  stats: { label: string; value: string }[];
  suggestions: string[];
}) {
  return (
    <div className="summary">
      <h4><Icon.check size={15} />任务已完成</h4>
      <dl className="grid">
        <dt>问题</dt><dd>{problem}</dd>
        <dt>原因</dt><dd>{cause}</dd>
        <dt>处理</dt><dd>{action}</dd>
        <dt>验证</dt><dd>{verify}</dd>
      </dl>
      <div className="stats">
        {stats.map((s) => (
          <div className="s" key={s.label}>
            <div className="lb">{s.label}</div>
            <div className="vl s-ok">{s.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-[12px] pt-[10px] border-t border-line text-[12px] text-ink2">
        <b className="text-ink">后续建议</b>
        {suggestions.map((t, i) => <div key={t}>{i + 1}. {t}</div>)}
      </div>
      <div className="acts">
        <button className="b go">按建议整改</button>
        <button className="b">导出报告</button>
        <button className="b no">查看完整执行记录</button>
      </div>
    </div>
  );
}

/** 失败后的 AI 分析块（对应效果图-07 卡片下方那段） */
export function ErrorCard({ reason, evidence, next }: {
  reason: ReactNode; evidence: string; next: string;
}) {
  return (
    <div className="msg-ai">
      {reason}
      <div className="mt-[6px] text-[12.5px]">{evidence}</div>
      <div className="mt-[6px] text-[12.5px]">{next}</div>
    </div>
  );
}
