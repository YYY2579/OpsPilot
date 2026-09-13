import type { ReactElement } from "react";

import { useState } from "react";
import { useShell, type Tier } from "../state/shell";
import { useChangeTier, useRunTask } from "../api/hooks";
import { Icon } from "./icons";
import Stream from "../components/Stream";
import RealStream from "../components/RealStream";

const TIER_META: Record<Tier, { label: string; color: string; soft: string; icon: (p: { size?: number }) => ReactElement; note: string }> = {
  requested_approval: { label: "请求审批", color: "var(--ok)", soft: "var(--ok-soft)", icon: Icon.lock, note: "每次写操作都需要你确认" },
  approve_for_me: { label: "帮我批准", color: "var(--accent)", soft: "var(--accent-soft)", icon: Icon.shieldOk, note: "L2–L3 自动执行，L4 仍会询问" },
  full_access: { label: "完全访问", color: "var(--warn)", soft: "var(--warn-soft)", icon: Icon.shieldWarn, note: "L0–L4 自动执行，L5 仍会拦截" },
};

export function ContextRing({ pct, used = "48.6K", total = "128K", hit = 91, turnsLeft = 26, condensed = false }:
  { pct: number; used?: string; total?: string; hit?: number; turnsLeft?: number; condensed?: boolean }) {
  const color = pct > 90 ? "var(--err)" : pct >= 70 ? "var(--warn)" : "var(--accent)";
  const C = 2 * Math.PI * 12;
  return (
    <div className="relative w-[30px] h-[30px] grid place-items-center group shrink-0">
      <svg width="30" height="30" viewBox="0 0 30 30" className="absolute inset-0">
        <circle cx="15" cy="15" r="12" fill="none" stroke="var(--border)" strokeWidth="3" />
        <circle cx="15" cy="15" r="12" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${(C * pct) / 100} ${C}`} transform="rotate(-90 15 15)" />
      </svg>
      <span className="text-[8px] font-medium relative" style={{ color }}>{pct}%</span>

      <div className="hidden group-hover:block absolute bottom-[36px] right-[-6px] z-[60] w-[252px] p-[11px]
                      rounded-[9px] border border-line2 bg-surface text-left"
           style={{ boxShadow: "0 12px 34px rgba(0,0,0,.5)" }}>
        <div className="flex items-center gap-[6px] text-[11px] font-medium text-ink mb-[7px]">
          <Icon.server size={11} />上下文占用 · {used} / {total} tokens
        </div>
        <div className="h-[4px] rounded-full bg-surface2 overflow-hidden mb-[8px]">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
        </div>
        <div className="flex justify-between text-[11.5px] text-ink2 py-[2px]"><span>输入 · 输出</span><b className="text-ink font-medium">21.2K · 6.8K</b></div>
        <div className="flex justify-between text-[11.5px] text-ink2 py-[2px]"><span>缓存命中</span><b className="text-ink font-medium">{hit}%（18.9K / 未命中 2.3K）</b></div>
        <div className="flex justify-between text-[11.5px] text-ink2 py-[2px]"><span>上次压缩</span><b className="text-ink font-medium">{condensed ? "已发生" : "未发生"}</b></div>
        <div className="mt-[7px] pt-[7px] border-t border-line text-[10.5px] text-ink3 leading-[1.7]">
          按最近 5 轮增量估算，还可容纳约 {turnsLeft} 轮。<br />
          压缩发生时前缀变化 → 缓存命中率骤降（本轮成本上升）。
        </div>
      </div>
    </div>
  );
}

export function DangerBanner({ target, env }: { target: string; env: string }) {
  return (
    <div className="flex items-center gap-[8px] mb-[8px] px-[11px] py-[7px] rounded-[8px] text-[12px] font-medium"
         style={{ border: "1px solid var(--warn)", background: "var(--warn-soft)", color: "var(--warn)" }}>
      <Icon.shieldWarn size={13} />完全访问已开启 · 目标 {target}（{env}）
      <span className="ml-auto font-normal text-ink2">29:41 后自动回落</span>
    </div>
  );
}

type Mode = "Auto" | "Plan" | "Execute" | "Review";

function Composer({ disabled, mode = "Auto", ringPct = 38, value, onChange, onSend, onTierChange }:
  { disabled?: boolean; mode?: Mode; ringPct?: number;
    value?: string; onChange?: (v: string) => void; onSend?: () => void;
    onTierChange?: (next: Tier) => void }) {
  // 注意：zustand v5 的选择器不能返回新对象（会触发 getSnapshot 无限循环），必须逐项取
  const tier = useShell((s) => s.tier);
  const setTier = useShell((s) => s.setTier);
  const meta = TIER_META[tier];
  const TierIcon = meta.icon;
  const modes: Mode[] = ["Auto", "Plan", "Execute", "Review"];

  // 档位切换的**规则由调用方决定**（live 走真 API + 闸门；mock 走本地循环）
  const onTierClick = () => {
    const next: Tier = tier === "requested_approval" ? "approve_for_me"
      : tier === "approve_for_me" ? "full_access" : "requested_approval";
    if (onTierChange) onTierChange(next);
    else setTier(next);
  };

  return (
    <div className="composer">
      {tier === "full_access" && <DangerBanner target="HK-Ubuntu" env="生产" />}
      <div className="rounded-[11px] border border-line2 bg-field" style={disabled ? { opacity: 0.55 } : undefined}>
        <div className="px-[13px] py-[12px]">
          {onSend ? (
            <textarea
              value={value ?? ""} onChange={(e) => onChange?.(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !disabled) { e.preventDefault(); onSend(); } }}
              rows={2}
              placeholder={disabled ? "等待你批准后继续…" : "描述你想完成的任务，例如：检查 Nginx 502 的原因"}
              className="w-full resize-none bg-transparent text-[13px] text-ink outline-none placeholder:text-ink3" />
          ) : (
            <div className="text-[13px] text-ink3">
              {disabled ? "等待你批准后继续…" : "描述你想完成的任务，例如：检查 Nginx 502 的原因"}
            </div>
          )}
        </div>

        <div className="flex items-center gap-[6px] px-[10px] py-[7px] border-t border-line">
          {["添加文件", "选择服务器", "选择数据库", "添加上下文"].map((x) => (
            <button key={x} className="h-[26px] px-[9px] rounded-[6px] border border-line text-[11.5px] text-ink2 hover:text-ink hover:bg-surface2">{x}</button>
          ))}
          <button className="h-[26px] px-[9px] rounded-[6px] border border-line text-[11.5px] text-ink2 hover:text-ink hover:bg-surface2 flex items-center gap-[5px]">
            <Icon.terminal size={12} />使用终端
          </button>
        </div>

        <div className="flex items-center gap-[6px] px-[10px] py-[6px] border-t border-line">
          <button
            onClick={onTierClick}
            title="点击切换档位：升级到完全访问会先弹出确认面板；降级即时生效"
            className="inline-flex items-center gap-[5px] h-[26px] px-[9px] rounded-[7px] text-[11.5px] font-medium shrink-0"
            style={{ background: meta.soft, color: meta.color, border: `1px solid ${meta.color}` }}>
            <TierIcon size={11} />{meta.label}<Icon.chevronDown size={10} />
          </button>

          <div className="inline-flex items-center gap-[4px] h-[26px] px-[9px] rounded-[7px] bg-surface2 border border-line text-[11.5px] text-ink shrink-0">
            DeepSeek-V3<Icon.chevronDown size={10} className="text-ink3" />
          </div>
          <div className="inline-flex items-center gap-[4px] h-[26px] px-[9px] rounded-[7px] bg-surface2 border border-line text-[11.5px] text-ink2 shrink-0">
            思考 <span className="text-ink font-medium">中</span><Icon.chevronDown size={10} className="text-ink3" />
          </div>
          <div className="ml-auto flex items-center gap-[6px] shrink-0">
            <div className="inline-flex items-center h-[26px] rounded-[7px] bg-surface2 border border-line overflow-hidden">
              {modes.map((m) => (
                <span key={m} className={`px-[8px] h-full grid place-items-center text-[11.5px] whitespace-nowrap ${m === mode ? "bg-accent text-white font-medium" : "text-ink2"}`}>{m}</span>
              ))}
            </div>
            <ContextRing pct={ringPct} />
            <button onClick={onSend}
                    className="w-[30px] h-[30px] rounded-[8px] flex items-center justify-center text-white"
                    style={{ background: disabled ? "var(--border2)" : "var(--accent)" }}>
              <Icon.send size={14} />
            </button>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-[6px] mt-[7px] text-[11px] text-ink3">
        <span className="px-[6px] py-[1px] rounded border border-line font-medium" style={{ color: meta.color }}>{meta.label}</span>
        <span>{meta.note}</span>
      </div>
    </div>
  );
}

/** 实况模式：后端在线且未强制指定设计状态时使用（M6-1/M6-2） */
function LiveCenter() {
  const sessionId = useShell((s) => s.sessionId);
  const tier = useShell((s) => s.tier);
  const setTier = useShell((s) => s.setTier);
  const activeServerId = useShell((s) => s.activeServerId);
  const activeTaskId = useShell((s) => s.activeTaskId);
  const setActiveTask = useShell((s) => s.setActiveTask);
  const changeTier = useChangeTier();
  const [text, setText] = useState("");
  const runTask = useRunTask();
  const serverId = activeServerId ?? "hk-ubuntu";
  const meta = TIER_META[tier];

  const onSend = () => {
    const text2 = text.trim();
    if (!text2 || runTask.isPending) return;
    setText("");
    runTask.mutate({
      server_id: serverId, user_request: text2, tier,
      environment: "production", async_run: true,
    });
    setActiveTask(null);      // runner 会写入新 task 行；由任务列表选择激活
  };

  // 档位切换（真 API）：升级需要确认；完全访问必须过 EscalationDialog 闸门
  const onTierChange = (next: Tier) => {
    if (next === "full_access") { setTier("full_access"); return; }
    if (tier === "requested_approval" && next === "approve_for_me") {
      if (!window.confirm("升级到「帮我批准」：L2–L3 将自动执行（L4 仍会询问）。确认？")) return;
    }
    changeTier.mutate(
      { sessionId, environment: "production", target: next },
      { onSuccess: () => setTier(next) },
    );
  };

  return (
    <div className="center">
      <div className="ctx">
        <Icon.server size={13} className="text-ink2" />
        <b className="text-ink font-medium">{serverId}</b>
        <span className="text-[11px] font-medium px-[7px] rounded-full"
              style={{ color: "var(--err)", background: "var(--err-soft)" }}>生产</span>
        <span className="flex items-center gap-[5px] text-[12px]" style={{ color: "var(--ok)" }}>
          <span className="w-[6px] h-[6px] rounded-full bg-current" />后端已连接
        </span>
      </div>

      {activeTaskId
        ? <RealStream taskId={activeTaskId} />
        : (
          <div className="stream">
            <div className="welcome">
              <div className="w-[46px] h-[46px] rounded-[12px] bg-accent text-white grid place-items-center font-semibold text-[15px] mb-[10px]">OP</div>
              <h2>今天想检查哪台机器？</h2>
              <p>后端已连接。描述任务后，Agent 会用只读工具采集事实；需要变更时先请求你的批准。</p>
            </div>
          </div>
        )}

      <Composer
        disabled={runTask.isPending}
        mode="Auto"
        value={text} onChange={setText} onSend={onSend}
        onTierChange={onTierChange}
      />
      <div className="flex items-center gap-[6px] mt-[7px] text-[11px] text-ink3">
        <span className="px-[6px] py-[1px] rounded border border-line font-medium" style={{ color: meta.color }}>{meta.label}</span>
        <span>{meta.note} · 当前目标 {serverId}</span>
      </div>
    </div>
  );
}

export default function Center({ stateId, mode, ringPct, live }: {
  stateId: string; mode?: Mode; ringPct?: number; live?: boolean;
}) {
  const openDialog = useShell((s) => s.openDialog);
  const setTierLocal = useShell((s) => s.setTier);
  if (live) return <LiveCenter />;
  const waiting = stateId === "05";
  const onTierChangeMock = (next: Tier) => {
    if (next === "full_access") { openDialog(); return; }
    setTierLocal(next);
  };

  return (
    <div className="center">
      {stateId !== "01" && (
        <div className="ctx">
          <Icon.server size={13} className="text-ink2" />
          <b className="text-ink font-medium">HK-Ubuntu</b>
          <span className="text-[11px] font-medium px-[7px] rounded-full" style={{ color: "var(--err)", background: "var(--err-soft)" }}>生产</span>
          <span className="text-ink2">156.224.28.147</span>
          <span className="w-px h-[16px] bg-line mx-[2px]" />
          <span className="flex items-center gap-[5px] text-[12px]" style={{ color: "var(--ok)" }}>
            <span className="w-[6px] h-[6px] rounded-full bg-current" />已连接
          </span>
        </div>
      )}

      {stateId === "01" ? (
        <div className="stream">
          <div className="welcome">
            <div className="w-[46px] h-[46px] rounded-[12px] bg-accent text-white grid place-items-center font-semibold text-[15px] mb-[10px]">OP</div>
            <h2>今天想检查哪台机器？</h2>
            <p>用自然语言描述任务，OpsPilot 会识别目标、调用只读工具、给出结论；需要变更时先征求你的确认。</p>
            <div className="quick">
              {[
                { t: "检查这台服务器为什么 CPU 很高", i: Icon.server },
                { t: "看看 Docker 容器是否正常", i: Icon.tools },
                { t: "查一下最近的错误日志", i: Icon.logs },
              ].map((q) => (
                <div className="q" key={q.t}><span className="ic" style={{ color: "var(--accent)" }}><q.i size={14} /></span>{q.t}</div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <Stream stateId={stateId} />
      )}

      <Composer disabled={waiting} mode={mode} ringPct={ringPct} onTierChange={onTierChangeMock} />
    </div>
  );
}
