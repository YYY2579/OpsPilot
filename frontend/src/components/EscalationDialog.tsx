import { useEffect, useRef, useState } from "react";

import { Icon } from "../shell/icons";

/**
 * 升级确认面板（规格 §A6.5.3 / 前端规格 §5.13）。
 *
 * 硬性行为（不得改）：
 * 1. 未勾选警告 → 确认按钮禁用；
 * 2. 生产环境额外要求输入环境名，输入不符 → 仍禁用；
 * 3. 默认焦点在「取消」；Esc 关闭等于取消，不产生任何变更；
 * 4. 「取消」在左、「开启完全访问」在右（错误色实心）。
 */
export default function EscalationDialog({
  open, target = "—", serverId = "—", host = "—",
  environment = "production", onCancel, onConfirm,
}: {
  open: boolean;
  target?: string;
  serverId?: string;
  host?: string;
  environment?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [ack, setAck] = useState(false);
  const [envInput, setEnvInput] = useState("");
  const cancelRef = useRef<HTMLButtonElement>(null);

  const envLabel = environment === "production" ? "生产环境" : environment === "staging" ? "预发环境" : "非生产环境";
  const needEnvName = environment === "production";
  const envOk = !needEnvName || envInput.trim() === "生产";
  const canConfirm = ack && envOk;

  // 每次打开重置；焦点给「取消」
  useEffect(() => {
    if (!open) return;
    setAck(false);
    setEnvInput("");
    const t = window.setTimeout(() => cancelRef.current?.focus(), 30);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="mh">
          <Icon.shieldWarn size={15} />开启「完全访问」
          <button className="x" title="取消" onClick={onCancel}><Icon.close size={14} /></button>
        </div>

        <div className="mb">
          <div className="lead">开启后，Agent 将<b>不再逐项询问</b>，可直接在你的目标环境执行下列操作。</div>

          <div className="envbox">
            <Icon.server size={14} style={{ color: "var(--err)" }} />
            <div>
              <div className="nm">{target}</div>
              <div className="sub">server_id: {serverId} · {host}</div>
            </div>
            <div className="tg">{envLabel}</div>
          </div>

          <div className="blk dng">
            <div className="bl">将失去的保护</div>
            <div className="li"><span className="s-warn">●</span>重启服务 / 重启容器<span className="lv">L3</span></div>
            <div className="li"><span className="s-err">●</span>删除文件<span className="lv">L4</span></div>
            <div className="li"><span className="s-err">●</span>修改配置文件<span className="lv">L4</span></div>
            <div className="li"><span className="s-err">●</span>修改防火墙 / SSH 配置<span className="lv">L4</span></div>
          </div>

          <div className="blk">
            <div className="bl">仍然会被拦截（L5 · 不可逆操作）</div>
            <div className="li"><span className="s-err">✕</span>删除数据库 · 清空数据表 · 重建集群<span className="lv">一律人工确认</span></div>
          </div>

          {needEnvName && (
            <div className="inp">
              <div className="lb">请输入目标环境名以确认（防误操作）</div>
              <div className="fld">
                <input value={envInput} onChange={(e) => setEnvInput(e.target.value)}
                       placeholder="请输入「生产」" aria-label="环境名确认" />
              </div>
            </div>
          )}

          <label className="check">
            <span className={`bx${ack ? " on" : ""}`} onClick={(e) => { e.preventDefault(); setAck(!ack); }}>
              {ack && <Icon.check size={10} />}
            </span>
            <input type="checkbox" className="hidden" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>我已了解上述风险，并确认当前环境可承受不逐项确认的执行</span>
          </label>

          <div className="tip"><Icon.history size={12} />完全访问将在 <b className="text-ink2">30 分钟</b>后自动回落；切换会话或关闭应用也会回落。</div>
          <div className="tip"><Icon.gear size={12} />档位变更与期间的全部自动执行操作都会写入审计记录。</div>
        </div>

        <div className="mf">
          <button ref={cancelRef} className="b" onClick={onCancel}>取消</button>
          <button className={`b dng${canConfirm ? "" : " dim"}`} disabled={!canConfirm}
                  title={canConfirm ? "开启完全访问" : "需先勾选风险确认（生产环境还需输入环境名）"}
                  onClick={onConfirm}>
            开启完全访问
          </button>
        </div>
      </div>
    </div>
  );
}
