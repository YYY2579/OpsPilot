import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, createProject, createServer, testServer } from "../api/client";
import type { ServerRow } from "../api/types";

export type NewKind = "server" | "project";

const inputCls =
  "w-full h-[30px] px-[9px] rounded-[6px] border border-line bg-field text-[12.5px] text-ink outline-none";
const labelCls = "block mb-[4px] text-[11px] text-ink3";

function Field({ label, children, hint }: {
  label: string; children: React.ReactNode; hint?: string;
}) {
  return (
    <div className="mb-[10px]">
      <label className={labelCls}>{label}</label>
      {children}
      {hint && <div className="mt-[3px] text-[10.5px] text-ink3 leading-[1.4]">{hint}</div>}
    </div>
  );
}

export default function NewResourceDialog({ kind, onClose }: {
  kind: NewKind; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  // 服务器字段
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("22");
  const [username, setUsername] = useState("root");
  const [credentialRef, setCredentialRef] = useState("");
  const [environment, setEnvironment] = useState("production");
  const [authType, setAuthType] = useState<"password" | "ssh_key">("password");

  // 项目字段
  const [path, setPath] = useState("");
  const [repo, setRepo] = useState("");

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      if (kind === "server") {
        if (!name.trim() || !host.trim() || !credentialRef.trim()) {
          setErr("名称 / 主机 / 凭据标识 三项必填");
          setBusy(false);
          return;
        }
        const row = await createServer({
          name: name.trim(), host: host.trim(), port: Number(port) || 22,
          username: username.trim() || "root", auth_type: authType,
          credential_ref: credentialRef.trim(), environment,
        }) as ServerRow;
        // 建完立刻测一次连通，失败也要给出明确原因，而不是静默成功
        let probe = "";
        try {
          const r = await testServer(row.id) as { ok?: boolean; stage?: string; error?: string };
          probe = r.ok ? "连接测试通过" : `连接测试未通过（${r.stage ?? "unknown"}）：${r.error ?? "未知原因"}`;
        } catch (e) {
          probe = `连接测试失败：${e instanceof Error ? e.message : String(e)}`;
        }
        setCreated(probe);
        qc.invalidateQueries({ queryKey: ["servers"] });
      } else {
        if (!name.trim()) { setErr("项目名称必填"); setBusy(false); return; }
        await createProject({
          name: name.trim(), path: path.trim(), repository_url: repo.trim(),
          default_branch: "main", environment,
        });
        setCreated("项目已创建");
        qc.invalidateQueries({ queryKey: ["projects"] });
      }
      if (kind === "server") qc.invalidateQueries({ queryKey: ["servers"] });
      else qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setErr(e instanceof ApiError ? `后端拒绝（${e.status}）：${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center"
         style={{ background: "rgba(0,0,0,.55)" }}
         onClick={onClose}>
      <div className="w-[480px] max-w-[92vw] rounded-[12px] border border-line p-[18px]"
           style={{ background: "var(--panel)" }}
           onClick={(e) => e.stopPropagation()}>
        <div className="text-[14px] font-semibold text-ink mb-[3px]">
          {kind === "server" ? "新建服务器连接" : "新建项目"}
        </div>
        <div className="text-[11.5px] text-ink3 mb-[14px] leading-[1.5]">
          {kind === "server"
            ? "凭据本身走环境变量（OPSPILOT_{凭据标识}_HOST / _USERNAME / _PASSWORD），这里只登记元信息。"
            : "项目用于给任务提供上下文，可后续补充仓库地址。"}
        </div>

        {created ? (
          <>
            <div className="px-[10px] py-[8px] rounded-[6px] text-[12px] mb-[12px]"
                 style={{ background: "var(--ok-soft)", color: "var(--ok)" }}>
              {created}
            </div>
            <div className="flex justify-end">
              <button onClick={onClose}
                      className="h-[30px] px-[14px] rounded-[7px] bg-accent border border-accent text-white text-[12px] font-semibold">
                完成
              </button>
            </div>
          </>
        ) : (
          <>
            <Field label={kind === "server" ? "显示名称" : "项目名称"}>
              <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)}
                     placeholder={kind === "server" ? "生产靶机-jzz18" : "mall 微服务"} />
            </Field>

            {kind === "server" ? (
              <>
                <div className="grid grid-cols-[1fr_90px] gap-[8px]">
                  <Field label="主机 / IP">
                    <input className={inputCls} value={host} onChange={(e) => setHost(e.target.value)}
                           placeholder="156.224.28.147" />
                  </Field>
                  <Field label="端口">
                    <input className={inputCls} value={port} onChange={(e) => setPort(e.target.value)} />
                  </Field>
                </div>
                <div className="grid grid-cols-2 gap-[8px]">
                  <Field label="登录用户">
                    <input className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} />
                  </Field>
                  <Field label="认证方式">
                    <select className={inputCls} value={authType}
                            onChange={(e) => setAuthType(e.target.value as "password" | "ssh_key")}>
                      <option value="password">口令</option>
                      <option value="ssh_key">私钥</option>
                    </select>
                  </Field>
                </div>
                <Field label="凭据标识 credential_ref"
                       hint="决定去读哪一组环境变量。大写、- 和 . 会转成 _，例如 JZZ_18 对应 OPSPILOT_JZZ_18_HOST。">
                  <input className={inputCls} value={credentialRef}
                         onChange={(e) => setCredentialRef(e.target.value)} placeholder="JZZ_18" />
                </Field>
              </>
            ) : (
              <>
                <Field label="本地路径">
                  <input className={inputCls} value={path} onChange={(e) => setPath(e.target.value)}
                         placeholder="/opt/mall" />
                </Field>
                <Field label="仓库地址（可选）">
                  <input className={inputCls} value={repo} onChange={(e) => setRepo(e.target.value)}
                         placeholder="https://github.com/xxx/yyy.git" />
                </Field>
              </>
            )}

            <Field label="环境">
              <select className={inputCls} value={environment}
                      onChange={(e) => setEnvironment(e.target.value)}>
                <option value="production">生产</option>
                <option value="staging">预发</option>
                <option value="development">开发</option>
              </select>
            </Field>

            {err && (
              <div className="px-[10px] py-[8px] rounded-[6px] text-[11.5px] mb-[10px] leading-[1.5]"
                   style={{ background: "var(--err-soft)", color: "var(--err)" }}>{err}</div>
            )}

            <div className="flex justify-end gap-[8px]">
              <button onClick={onClose} disabled={busy}
                      className="h-[30px] px-[14px] rounded-[7px] border border-line bg-surface2 text-[12px] text-ink2 disabled:opacity-50">
                取消
              </button>
              <button onClick={() => void submit()} disabled={busy}
                      className="h-[30px] px-[14px] rounded-[7px] bg-accent border border-accent text-white text-[12px] font-semibold disabled:opacity-50">
                {busy ? "提交中…" : "创建并测试"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
