"""credential_ref → 连接信息（需求开发文档 §A6.4）。

M1 阶段来源 = 环境变量（后续接系统密钥环 / SecretRegistry，只需替换 Resolver 实现）：
    OPSPILOT_{SERVER_ID}_HOST      必需
    OPSPILOT_{SERVER_ID}_PORT      可选，默认 22
    OPSPILOT_{SERVER_ID}_USERNAME  必需
    OPSPILOT_{SERVER_ID}_PASSWORD  可选（与 _KEY_PATH 二选一）
    OPSPILOT_{SERVER_ID}_KEY_PATH  可选（私钥文件路径）

SERVER_ID 规范化：大写，`-` 与 `.` 转 `_`（hk-ubuntu → HK_UBUNTU）。

密钥纪律：
- 解析结果（SshCredential）只允许在 Executor 内部使用，禁止进入 prompt /
  Observation / 日志（§A6.4 第 1-3 条）。
- mask() / assert_no_secrets() 供测试与审计复用；占位符与 OpenHands
  SecretRegistry 一致：<secret-hidden>（源码索引 §1.6）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# 与 OpenHands SecretRegistry 的占位符保持一致（源码索引 §1.6 / §0.3）
SECRET_PLACEHOLDER = "<secret-hidden>"


class CredentialError(RuntimeError):
    """凭据缺失或配置不完整。kind: missing（整条缺失）/ incomplete（字段不齐）。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail   # 与 SshError/CollectionError 对齐：统一 .kind/.detail 协议


@dataclass(frozen=True)
class SshCredential:
    """SSH 连接信息。**敏感对象**：只允许在 Executor 内部使用。"""

    server_id: str
    host: str
    port: int
    username: str
    password: str | None = None
    key_path: str | None = None

    def secrets(self) -> tuple[str, ...]:
        """返回该凭据包含的所有敏感串（用于泄密检查）。"""
        values: list[str] = []
        if self.password:
            values.append(self.password)
        if self.key_path and os.path.isfile(self.key_path):
            with open(self.key_path, encoding="utf-8") as fh:
                values.append(fh.read())
        return tuple(values)

    def redacted(self) -> dict:
        """可安全打印/入库的视图（用于审计与调试）。"""
        return {
            "server_id": self.server_id,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth": "key" if self.key_path else ("password" if self.password else "none"),
        }


def normalize_env_prefix(server_id: str) -> str:
    """hk-ubuntu → HK_UBUNTU 之类的前缀（hk-ubuntu → HK_UBUNTU）。"""
    return server_id.upper().replace("-", "_").replace(".", "_")


#: server_id 别名 → 真正的 credential_ref。
#:
#: **为什么需要它**：Agent 的 Action 里只有 `server_id`（架构约束：schema 不带
#: 主机/账号/口令），而它拿到的是 serverconnection 的**主键**（如 `4d6cc8bd599d`）。
#: 但环境变量是按 `credential_ref`（如 `JZZ_18`）配置的，于是工具层会去查
#: `OPSPILOT_4D6CC8BD599D_HOST` —— 必然找不到，报 `SSH missing`。
#: **真实踩过**：/api/servers/{id}/health 一直是通的（它先 resolve_server 取
#: credential_ref 再解析），唯独 Agent 调用工具时全挂，看起来像"工具坏了"。
#:
#: 由服务启动时从 serverconnection 表填充（见 app._load_credential_aliases）。
_ALIASES: dict[str, str] = {}


def set_credential_aliases(mapping: dict[str, str]) -> None:
    """整体替换别名表（启动时加载；key 会被规范化成小写）。"""
    _ALIASES.clear()
    for k, v in mapping.items():
        if k and v:
            _ALIASES[str(k).lower()] = str(v)


def clear_credential_aliases() -> None:
    _ALIASES.clear()


def credential_aliases() -> dict[str, str]:
    return dict(_ALIASES)


def mask(text: str, secrets: tuple[str, ...] | list[str]) -> str:
    """把文本中的敏感串替换为 <secret-hidden>（与 SecretRegistry 行为一致）。"""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, SECRET_PLACEHOLDER)
    return out


def assert_no_secrets(text: str, secrets: tuple[str, ...] | list[str]) -> None:
    """泄密断言：文本中出现任何敏感串即抛 AssertionError（§A6.4 第 6 条）。"""
    leaked = [f"<第{i}个敏感串>" for i, s in enumerate(secrets, 1) if s and s in text]
    if leaked:
        raise AssertionError(f"泄密！prompt/输出中包含：{', '.join(leaked)}")


class CredentialResolver:
    """从环境变量解析凭据。真实部署时替换为密钥环实现，接口不变。

    on_resolve: 可选的解析回调（§A6.4 要求每次解析留痕）。
    回调只会收到 **redacted() 后的脱敏视图**，绝不含密码或私钥内容。
    """

    def __init__(self, environ: dict[str, str] | None = None, on_resolve=None) -> None:
        self._env = os.environ if environ is None else environ
        self._on_resolve = on_resolve

    def _lookup(self, server_id: str) -> SshCredential:
        """按某个标识实际查环境变量（调用方已决定用哪个标识）。"""
        prefix = "OPSPILOT_" + normalize_env_prefix(server_id)
        host = self._env.get(f"{prefix}_HOST")
        if not host:
            raise CredentialError(
                "missing", f"未配置 {prefix}_HOST，无法解析 server_id={server_id}"
            )
        username = self._env.get(f"{prefix}_USERNAME")
        if not username:
            raise CredentialError(
                "incomplete", f"已配置主机但缺少 {prefix}_USERNAME"
            )
        password = self._env.get(f"{prefix}_PASSWORD") or None
        key_path = self._env.get(f"{prefix}_KEY_PATH") or None
        if not password and not key_path:
            raise CredentialError(
                "incomplete",
                f"{prefix}_PASSWORD 与 {prefix}_KEY_PATH 至少配置一个",
            )
        try:
            port = int(self._env.get(f"{prefix}_PORT") or "22")
        except ValueError as exc:  # pragma: no cover - 防御式
            raise CredentialError("incomplete", f"{prefix}_PORT 不是整数") from exc
        return SshCredential(
            server_id=server_id,
            host=host,
            port=port,
            username=username,
            password=password,
            key_path=key_path,
        )

    def resolve(self, server_id: str) -> SshCredential:
        """解析凭据：先按原样查，查不到再走别名表（主键/名称 → credential_ref）。"""
        try:
            credential = self._lookup(server_id)
        except CredentialError as first:
            alias = _ALIASES.get(str(server_id).lower())
            if not alias or alias.lower() == str(server_id).lower():
                raise
            try:
                credential = self._lookup(alias)
            except CredentialError:
                # 别名单也找不到时，报**最初**那个标识，避免日志里冒出陌生的 ref
                raise first from None
        if self._on_resolve is not None:
            self._on_resolve(credential.redacted())
        return credential
