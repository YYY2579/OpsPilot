"""database_id → MySQL 连接信息（§A6.4 凭据边界在数据库侧的实现）。

来源 = 环境变量（与 ops_pilot/credentials.py 的 SSH 侧同一套前缀约定）：
    OPSPILOT_DB_{DATABASE_ID}_HOST      必需
    OPSPILOT_DB_{DATABASE_ID}_PORT      可选，默认 3306
    OPSPILOT_DB_{DATABASE_ID}_USERNAME  必需
    OPSPILOT_DB_{DATABASE_ID}_PASSWORD  必需
    OPSPILOT_DB_{DATABASE_ID}_DATABASE  可选（默认连接库；工具都显式指定库，一般用不到）

DATABASE_ID 规范化：大写，`-` 与 `.` 转 `_`（mysql-prod → MYSQL_PROD）。

密钥纪律：解析结果（DbCredential）只允许在 Executor 内部使用，禁止进入
Action / Observation / 日志；错误信息里只出现环境变量名，绝不出现值。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ops_pilot.credentials import CredentialError


class DbError(RuntimeError):
    """数据库连接/查询失败。kind: auth（认证失败）/ network（连不上）/ sql（SQL 执行错误）。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail   # 与 SshError/CollectionError/CredentialError 对齐：统一 .kind/.detail 协议


def normalize_database_id(database_id: str) -> str:
    """mysql-prod → MYSQL_PROD（与 SSH 侧 normalize_env_prefix 同一规则）。"""
    return database_id.upper().replace("-", "_").replace(".", "_")


@dataclass(frozen=True)
class DbCredential:
    """MySQL 连接信息。**敏感对象**：只允许在 Executor 内部使用。"""

    database_id: str
    host: str
    port: int
    username: str
    password: str
    database: str | None = None

    def redacted(self) -> dict:
        """可安全打印/入库的视图（用于审计与调试，与 SshCredential.redacted 对齐）。"""
        return {
            "database_id": self.database_id,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "database": self.database,
        }


class DbCredentialResolver:
    """从环境变量解析 database_id 的连接信息。接口与 SSH 侧 CredentialResolver 对齐，
    后续接密钥环时只需替换本实现。"""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._env = os.environ if environ is None else environ

    def resolve(self, database_id: str) -> DbCredential:
        prefix = "OPSPILOT_DB_" + normalize_database_id(database_id)
        host = self._env.get(f"{prefix}_HOST")
        if not host:
            # HOST 是第一个必填项：它缺失视为整条凭据未配置（与 SSH 侧口径一致）
            raise CredentialError(
                "missing", f"未配置 {prefix}_HOST，无法解析 database_id={database_id}"
            )
        username = self._env.get(f"{prefix}_USERNAME")
        password = self._env.get(f"{prefix}_PASSWORD")
        missing = [name for name, value in (
            (f"{prefix}_USERNAME", username),
            (f"{prefix}_PASSWORD", password),
        ) if not value]
        if missing:
            raise CredentialError("incomplete", "已配置主机但缺少 " + "、".join(missing))
        try:
            port = int(self._env.get(f"{prefix}_PORT") or "3306")
        except ValueError as exc:  # pragma: no cover - 防御式
            raise CredentialError("incomplete", f"{prefix}_PORT 不是整数") from exc
        return DbCredential(
            database_id=database_id,
            host=host,
            port=port,
            username=username,
            password=password,
            database=self._env.get(f"{prefix}_DATABASE") or None,
        )
