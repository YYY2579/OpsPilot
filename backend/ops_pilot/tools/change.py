"""受控变更工具（④变更操作）+ 滚动更新诊断（③K8s排障）。

安全红线（任何一条不满足就拒绝执行）：
1. **dry_run 默认 True**：不显式传 dry_run=False，就只预演不落地。
2. **回滚方案必填**：没有回滚命令/回滚点，直接拒绝（CHANGE_NO_ROLLBACK_PLAN）。
3. **L3 审批**：destructiveHint=True，走人工确认（见 security/analyzer.py）。
4. **全程审计**：执行前记录回滚点，执行后记录结果。

K8s 命令一律 SSH 到"装有 kubectl 的机器"执行（不在本机放 kubeconfig，与 k8s.py 一致）。
"""
from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Any

from openhands.sdk.tool import (
    Action, ToolAnnotations, ToolDefinition, register_tool,
)
from pydantic import Field

from ops_pilot.diagnostics.codes import (
    CHANGE_DRYRUN_FAILED, CHANGE_EXEC_FAILED, CHANGE_NO_ROLLBACK_PLAN,
    K8S_ROLLBACK_FAILED, K8S_ROLLOUT_STUCK, K8S_SCALE_FAILED,
)
from ops_pilot.diagnostics.conclusion import Diagnosis, fail, ok
from ops_pilot.tools._base import JsonObservation, SshReadOnlyExecutor
from ops_pilot.tools.sshcmd import run_lenient

# 防注入：K8s 资源名 / 命名空间 / 副本数
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,62}$")
NS_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _audit(kind: str, target: str, detail: dict[str, Any]) -> None:
    """写审计；审计失败不能阻断主流程，但要留下痕迹。"""
    try:
        from ops_pilot.server import audit, db
        conn = db.connect(os.environ.get("OPSPILOT_DB", "opspilot.db"))
        audit.record(conn, kind=audit.KIND_TOOL, target_type="change",
                     target_id=target, tier="L3", detail=detail)
    except Exception:
        pass


def _guard_names(**pairs: str) -> None:
    for key, val in pairs.items():
        pat = NS_RE if key == "namespace" else NAME_RE
        if not val or not pat.match(val):
            raise ValueError(f"{key} 不合法：{val!r}（只允许小写字母数字 . - ）")


# ============================================================ 1. 滚动更新诊断（只读）
class RolloutStatusAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    namespace: str = Field(default="default", description="命名空间")
    name: str = Field(description="Deployment 名称")
    timeout: str = Field(default="60s", description="等待超时时间，如 60s / 2m")


class RolloutStatusObservation(JsonObservation):
    server_id: str
    namespace: str
    name: str
    command: str
    exit_code: int
    output: str
    desired: int | None
    updated: int | None
    ready: int | None
    available: int | None
    diagnosis: dict[str, Any]


class RolloutStatusExecutor(SshReadOnlyExecutor[RolloutStatusAction, RolloutStatusObservation]):
    def collect(self, runner: Any, action: RolloutStatusAction) -> dict[str, Any]:
        _guard_names(namespace=action.namespace, name=action.name)
        ns = f"-n {action.namespace}"

        cmd_status = f"kubectl rollout status deploy/{action.name} {ns} --timeout={action.timeout} 2>&1"
        code, out, err = run_lenient(runner, cmd_status, self._command_timeout + 60)
        status_out = (out or "").strip() or (err or "").strip()

        # 读副本分布：desired/updated/ready/available
        cmd_get = (f"kubectl get deploy/{action.name} {ns} -o jsonpath="
                   "'{.spec.replicas} {.status.updatedReplicas} {.status.readyReplicas} {.status.availableReplicas}'")
        _, out2, _ = run_lenient(runner, cmd_get, self._command_timeout)
        parts = (out2 or "").strip().split()
        nums = []
        for p in parts[:4]:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(None)
        nums += [None] * (4 - len(nums))
        desired, updated, ready, available = nums[:4]

        evidence = [
            {"cmd": cmd_status, "exit_code": code, "output": status_out[:800]},
            {"cmd": cmd_get, "output": (out2 or "").strip()[:200]},
        ]

        if code != 0 or "ProgressDeadlineExceeded" in status_out or "timed out" in status_out.lower():
            d = fail(K8S_ROLLOUT_STUCK,
                     summary=f"Deployment {action.namespace}/{action.name} 滚动更新未进入完成状态",
                     evidence=evidence,
                     impact=f"期望 {desired} 副本，已更新 {updated}，就绪 {ready}",
                     extra_fix_steps=(
                         f"确认新副本卡在哪：kubectl describe deploy/{action.name} -n {action.namespace}",
                         f"看新 Pod 为何不就绪：kubectl get pods -n {action.namespace} -l app={action.name}",
                         f"必要时回滚：kubectl rollout undo deploy/{action.name} -n {action.namespace}",
                     ))
        else:
            d = ok("k8s", f"Deployment {action.namespace}/{action.name} 滚动更新状态正常",
                   evidence=evidence)

        return {
            "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
            "command": cmd_status, "exit_code": code, "output": status_out[:2000],
            "desired": desired, "updated": updated, "ready": ready, "available": available,
            "diagnosis": d.to_dict(),
        }

    def build(self, action: RolloutStatusAction, data: dict[str, Any]) -> RolloutStatusObservation:
        return RolloutStatusObservation(**data)


class RolloutStatusTool(ToolDefinition[RolloutStatusAction, RolloutStatusObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[RolloutStatusTool]:
        return [cls(
            action_type=RolloutStatusAction,
            observation_type=RolloutStatusObservation,
            description="诊断 Deployment 滚动更新是否卡住（只读）。返回期望/已更新/就绪副本数与卡住原因。",
            annotations=ToolAnnotations(title="rollout_status", readOnlyHint=True),
            executor=RolloutStatusExecutor(),
        )]


# ============================================================ 2. 扩缩容（写，dry-run 优先）
class ScaleWorkloadAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    namespace: str = Field(default="default", description="命名空间")
    name: str = Field(description="Deployment 名称")
    replicas: int = Field(description="目标副本数", ge=0, le=500)
    dry_run: bool = Field(default=True, description="true=只预演与校验，不真正扩缩容（默认 true）")
    rollback_command: str = Field(
        default="",
        description="回滚命令；留空时系统按当前副本数自动生成（kubectl scale --replicas=<当前值>）",
    )


class ScaleWorkloadObservation(JsonObservation):
    server_id: str
    namespace: str
    name: str
    dry_run: bool
    from_replicas: int | None
    to_replicas: int
    command: str
    exit_code: int
    output: str
    rollback_command: str
    diagnosis: dict[str, Any]


class ScaleWorkloadExecutor(SshReadOnlyExecutor[ScaleWorkloadAction, ScaleWorkloadObservation]):
    def collect(self, runner: Any, action: ScaleWorkloadAction) -> dict[str, Any]:
        _guard_names(namespace=action.namespace, name=action.name)
        ns = f"-n {action.namespace}"

        # 1) 记录回滚点：当前副本数
        _, out0, _ = run_lenient(
            runner, f"kubectl get deploy/{action.name} {ns} -o jsonpath='{{.spec.replicas}}'",
            self._command_timeout)
        try:
            current = int((out0 or "").strip())
        except ValueError:
            current = None

        rollback_cmd = action.rollback_command.strip()
        if not rollback_cmd:
            if current is None:
                # 连当前副本数都拿不到 → 无法构造回滚方案 → 拒绝
                d = fail(CHANGE_NO_ROLLBACK_PLAN,
                         summary="无法获取当前副本数，也就无法生成回滚方案，已拒绝执行",
                         evidence=[{"cmd": "kubectl get deploy ... .spec.replicas", "output": (out0 or "")[:200]}])
                return {
                    "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
                    "dry_run": action.dry_run, "from_replicas": None, "to_replicas": action.replicas,
                    "command": "", "exit_code": -1, "output": "",
                    "rollback_command": "", "diagnosis": d.to_dict(),
                }
            rollback_cmd = f"kubectl scale deploy/{action.name} {ns} --replicas={current}"

        # 2) 预演：dry-run 先跑一遍
        dry_cmd = f"kubectl scale deploy/{action.name} {ns} --replicas={action.replicas} --dry-run=client 2>&1"
        dcode, dout, derr = run_lenient(runner, dry_cmd, self._command_timeout)
        dry_out = (dout or "").strip() or (derr or "").strip()
        if dcode != 0:
            d = fail(CHANGE_DRYRUN_FAILED,
                     summary=f"扩缩容预演失败：{dry_out[:200]}",
                     evidence=[{"cmd": dry_cmd, "exit_code": dcode, "output": dry_out[:500]}])
            return {
                "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
                "dry_run": True, "from_replicas": current, "to_replicas": action.replicas,
                "command": dry_cmd, "exit_code": dcode, "output": dry_out[:2000],
                "rollback_command": rollback_cmd, "diagnosis": d.to_dict(),
            }

        if action.dry_run:
            d = ok("change",
                   f"预演通过：{action.namespace}/{action.name} 可从 {current} 扩缩到 {action.replicas}（未实际执行）",
                   evidence=[{"cmd": dry_cmd, "output": dry_out[:300]},
                             {"rollback_command": rollback_cmd}])
            return {
                "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
                "dry_run": True, "from_replicas": current, "to_replicas": action.replicas,
                "command": dry_cmd, "exit_code": dcode, "output": dry_out[:2000],
                "rollback_command": rollback_cmd, "diagnosis": d.to_dict(),
            }

        # 3) 真执行（到这里说明预演已通过 + 回滚方案已就绪 + 已过 L3 审批）
        _audit("scale_workload", f"{action.namespace}/{action.name}", {
            "from": current, "to": action.replicas, "rollback": rollback_cmd,
            "server_id": action.server_id,
        })
        real_cmd = f"kubectl scale deploy/{action.name} {ns} --replicas={action.replicas} 2>&1"
        code, out, err = run_lenient(runner, real_cmd, self._command_timeout + 30)
        output = (out or "").strip() or (err or "").strip()

        if code != 0:
            d = fail(CHANGE_EXEC_FAILED, summary=f"扩缩容执行失败：{output[:200]}",
                     evidence=[{"cmd": real_cmd, "exit_code": code, "output": output[:500]}],
                     impact=f"{action.namespace}/{action.name} 副本数可能未变更",
                     rollback=rollback_cmd,
                     extra_fix_steps=(f"立即回滚：{rollback_cmd}", "确认当前副本数后再重试"))
        else:
            d = ok("change",
                   f"已扩缩容：{action.namespace}/{action.name} {current} → {action.replicas}",
                   evidence=[{"cmd": real_cmd, "output": output[:300]}],
                   impact=f"副本数 {current} → {action.replicas}")
            d.rollback = rollback_cmd

        return {
            "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
            "dry_run": False, "from_replicas": current, "to_replicas": action.replicas,
            "command": real_cmd, "exit_code": code, "output": output[:2000],
            "rollback_command": rollback_cmd, "diagnosis": d.to_dict(),
        }

    def build(self, action: ScaleWorkloadAction, data: dict[str, Any]) -> ScaleWorkloadObservation:
        return ScaleWorkloadObservation(**data)


class ScaleWorkloadTool(ToolDefinition[ScaleWorkloadAction, ScaleWorkloadObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ScaleWorkloadTool]:
        return [cls(
            action_type=ScaleWorkloadAction,
            observation_type=ScaleWorkloadObservation,
            description=(
                "扩缩容 Deployment（中高风险，会改变服务能力）。"
                "默认 dry_run=true 只预演；正式执行前会先跑 --dry-run=client 校验，"
                "并自动记录回滚命令（按变更前的副本数）。执行前必须说明影响与回滚方案。"
            ),
            annotations=ToolAnnotations(
                title="scale_workload",
                readOnlyHint=False, destructiveHint=True, idempotentHint=True,
            ),
            executor=ScaleWorkloadExecutor(),
        )]


# ============================================================ 3. 回滚（写）
class RollbackDeployAction(Action):
    server_id: str = Field(description="装有 kubectl 的目标主机标识（非 IP）")
    namespace: str = Field(default="default", description="命名空间")
    name: str = Field(description="Deployment 名称")
    to_revision: int = Field(default=0, description="回滚到指定 revision；0 表示上一个版本")
    dry_run: bool = Field(default=True, description="true=只查看可回滚版本，不执行（默认 true）")


class RollbackDeployObservation(JsonObservation):
    server_id: str
    namespace: str
    name: str
    dry_run: bool
    command: str
    exit_code: int
    output: str
    history: list[dict[str, Any]]
    diagnosis: dict[str, Any]


class RollbackDeployExecutor(SshReadOnlyExecutor[RollbackDeployAction, RollbackDeployObservation]):
    def collect(self, runner: Any, action: RollbackDeployAction) -> dict[str, Any]:
        _guard_names(namespace=action.namespace, name=action.name)
        ns = f"-n {action.namespace}"

        # 历史版本（回滚的"回滚方案"就是往另一个 revision 再回滚）
        cmd_hist = f"kubectl rollout history deploy/{action.name} {ns} 2>&1"
        _, out_h, _ = run_lenient(runner, cmd_hist, self._command_timeout)
        history: list[dict[str, Any]] = []
        for ln in (out_h or "").splitlines()[2:]:
            m = re.match(r"^(\d+)\s+(.*)$", ln.strip())
            if m:
                history.append({"revision": int(m.group(1)), "description": m.group(2)[:160]})

        if action.dry_run:
            d = ok("change",
                   f"可回滚版本 {len(history)} 个（未执行回滚）",
                   evidence=[{"cmd": cmd_hist, "output": (out_h or "")[:400]}])
            return {
                "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
                "dry_run": True, "command": cmd_hist, "exit_code": 0,
                "output": (out_h or "")[:2000], "history": history, "diagnosis": d.to_dict(),
            }

        if not history:
            d = fail(K8S_ROLLBACK_FAILED,
                     summary="没有可回滚的历史版本（可能刚创建或历史被清理）",
                     evidence=[{"cmd": cmd_hist, "output": (out_h or "")[:300]}],
                     extra_fix_steps=("用上一版镜像 tag 重新 apply 作为兜底回滚",))
            return {
                "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
                "dry_run": False, "command": cmd_hist, "exit_code": -1,
                "output": (out_h or "")[:2000], "history": [], "diagnosis": d.to_dict(),
            }

        target = f"--to-revision={action.to_revision}" if action.to_revision else ""
        real = f"kubectl rollout undo deploy/{action.name} {ns} {target} 2>&1".replace("  ", " ")
        _audit("rollback_deploy", f"{action.namespace}/{action.name}",
               {"to_revision": action.to_revision or "previous", "command": real,
                "server_id": action.server_id})
        code, out, err = run_lenient(runner, real, self._command_timeout + 30)
        output = (out or "").strip() or (err or "").strip()

        if code != 0:
            d = fail(K8S_ROLLBACK_FAILED, summary=f"回滚失败：{output[:200]}",
                     evidence=[{"cmd": real, "exit_code": code, "output": output[:500]}],
                     impact=f"{action.namespace}/{action.name} 仍停留在当前（可能有问题的）版本",
                     extra_fix_steps=("立即人工介入，必要时用镜像 tag 重新 apply",))
        else:
            d = ok("change", f"已回滚 {action.namespace}/{action.name}",
                   evidence=[{"cmd": real, "output": output[:300]}])

        return {
            "server_id": action.server_id, "namespace": action.namespace, "name": action.name,
            "dry_run": False, "command": real, "exit_code": code,
            "output": output[:2000], "history": history, "diagnosis": d.to_dict(),
        }

    def build(self, action: RollbackDeployAction, data: dict[str, Any]) -> RollbackDeployObservation:
        return RollbackDeployObservation(**data)


class RollbackDeployTool(ToolDefinition[RollbackDeployAction, RollbackDeployObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[RollbackDeployTool]:
        return [cls(
            action_type=RollbackDeployAction,
            observation_type=RollbackDeployObservation,
            description=(
                "回滚 Deployment 到上一个或指定版本（高风险）。默认 dry_run=true 只列可回滚版本；"
                "执行前需确认回滚目标版本与回滚后状态。"
            ),
            annotations=ToolAnnotations(
                title="rollback_deploy",
                readOnlyHint=False, destructiveHint=True, idempotentHint=False,
            ),
            executor=RollbackDeployExecutor(),
        )]


# ============================================================ 4. 通用变更（脚本，回滚命令必填）
class RunChangeScriptAction(Action):
    server_id: str = Field(description="执行变更的目标主机标识（非 IP）")
    change_command: str = Field(description="要执行的变更命令（由你或你的部署脚本提供）")
    rollback_command: str = Field(description="对应的回滚命令（必填；填不出回滚方式就不要执行）")
    dry_run: bool = Field(default=True, description="true=只做存在性与权限校验，不执行（默认 true）")
    working_dir: str = Field(default="", description="可选的工作目录")


class RunChangeScriptObservation(JsonObservation):
    server_id: str
    dry_run: bool
    change_command: str
    rollback_command: str
    exit_code: int
    output: str
    diagnosis: dict[str, Any]


class RunChangeScriptExecutor(SshReadOnlyExecutor[RunChangeScriptAction, RunChangeScriptObservation]):
    def collect(self, runner: Any, action: RunChangeScriptAction) -> dict[str, Any]:
        change = (action.change_command or "").strip()
        rollback = (action.rollback_command or "").strip()

        # 红线 1：必须有回滚方案
        if not change:
            d = fail(CHANGE_NO_ROLLBACK_PLAN, summary="变更命令为空，无法执行")
            return {"server_id": action.server_id, "dry_run": action.dry_run,
                    "change_command": change, "rollback_command": rollback,
                    "exit_code": -1, "output": "", "diagnosis": d.to_dict()}
        if not rollback:
            d = fail(CHANGE_NO_ROLLBACK_PLAN,
                     summary="缺少回滚命令，已拒绝执行（没有回滚方案的变更不允许落地）",
                     evidence=[{"change_command": change}])
            return {"server_id": action.server_id, "dry_run": action.dry_run,
                    "change_command": change, "rollback_command": "",
                    "exit_code": -1, "output": "", "diagnosis": d.to_dict()}

        cd = f"cd {action.working_dir} && " if action.working_dir else ""

        if action.dry_run:
            # 预演：只验证目录/命令可解析与权限，不做状态改变（用 command -v 与目录检查）
            probe = f"{cd}command -v $(echo {change.split()[0]}) >/dev/null 2>&1 && echo ok || echo missing"
            code, out, err = run_lenient(runner, probe, self._command_timeout)
            output = (out or "").strip() or (err or "").strip()
            d = ok("change",
                   "预演通过：变更命令与回滚命令均已提供，可执行（未实际执行）" if output == "ok"
                   else f"预演提示：未在目标主机找到命令 {change.split()[0]}，请确认命令存在",
                   evidence=[{"change_command": change, "rollback_command": rollback,
                              "probe": output}])
            return {"server_id": action.server_id, "dry_run": True,
                    "change_command": change, "rollback_command": rollback,
                    "exit_code": code, "output": output[:1000], "diagnosis": d.to_dict()}

        _audit("run_change_script", action.server_id, {
            "change_command": change, "rollback_command": rollback,
            "working_dir": action.working_dir,
        })
        full = f"{cd}{change} 2>&1"
        code, out, err = run_lenient(runner, full, self._command_timeout + 120)
        output = (out or "").strip() or (err or "").strip()

        if code != 0:
            d = fail(CHANGE_EXEC_FAILED, summary=f"变更执行失败：{output[:200]}",
                     evidence=[{"cmd": full, "exit_code": code, "output": output[:600]}],
                     rollback=rollback,
                     extra_fix_steps=(f"立即回滚：{rollback}", "保留现场输出用于复盘"))
        else:
            d = ok("change", "变更执行成功", evidence=[{"cmd": full, "output": output[:600]}])
            d.rollback = rollback

        return {"server_id": action.server_id, "dry_run": False,
                "change_command": change, "rollback_command": rollback,
                "exit_code": code, "output": output[:2000], "diagnosis": d.to_dict()}

    def build(self, action: RunChangeScriptAction, data: dict[str, Any]) -> RunChangeScriptObservation:
        return RunChangeScriptObservation(**data)


class RunChangeScriptTool(ToolDefinition[RunChangeScriptAction, RunChangeScriptObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[RunChangeScriptTool]:
        return [cls(
            action_type=RunChangeScriptAction,
            observation_type=RunChangeScriptObservation,
            description=(
                "在目标主机执行变更命令（部署脚本/ansible/自定义操作），高风险。"
                "红线：① 必须提供 rollback_command，否则直接拒绝；"
                "② 默认 dry_run=true 只预演；③ 需人工审批后才可执行。"
            ),
            annotations=ToolAnnotations(
                title="run_change_script",
                readOnlyHint=False, destructiveHint=True, idempotentHint=False,
            ),
            executor=RunChangeScriptExecutor(),
        )]


register_tool(RolloutStatusTool.name, RolloutStatusTool)
register_tool(ScaleWorkloadTool.name, ScaleWorkloadTool)
register_tool(RollbackDeployTool.name, RollbackDeployTool)
register_tool(RunChangeScriptTool.name, RunChangeScriptTool)
