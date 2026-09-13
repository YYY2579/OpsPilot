"""数据库查询执行适配器。

设计：tools/database.py 的 Executor 只依赖 DbRunner 协议（纯逻辑、可注入假实现测试），
pymysql 只在本文件内延迟导入 —— 真正连接时才需要安装，与 ssh/client.py
延迟导入 paramiko 是同一套约定。
"""
from __future__ import annotations

from typing import Protocol

from ops_pilot.db.credentials import DbCredential, DbError


class DbRunner(Protocol):
    """数据库工具只依赖这个协议，便于单测注入假输出。"""

    def query(self, sql: str, params: tuple = (), limit: int = 200) -> tuple[list[str], list[tuple]]:
        """执行一条（已由上层保证只读的）SQL，返回 (列名, 行)，行数最多 limit。失败抛 DbError。"""

    def close(self) -> None:
        """释放连接。"""


# 连接阶段的认证类错误码；其余连接错误一律归为 network（宁把网络问题报松不报紧）
_AUTH_ERRNOS = frozenset({1044, 1045, 1698})


class PymysqlRunner:
    """基于 pymysql 的 DbRunner。只读保证不在这里：SQL 白名单在 tools/database.py。"""

    def __init__(self, credential: DbCredential, connect_timeout: float = 8.0) -> None:
        import pymysql
        from pymysql.err import MySQLError  # 延迟导入：单测不需要装

        self._mysql_error = MySQLError
        try:
            self._conn = pymysql.connect(
                host=credential.host,
                port=credential.port,
                user=credential.username,
                password=credential.password,
                database=credential.database,
                charset="utf8mb4",
                connect_timeout=int(connect_timeout),
                # 采集类查询都很轻，读超时给个比连接超时更宽的上限即可
                read_timeout=max(int(connect_timeout), 30),
            )
        except MySQLError as exc:
            errno = exc.args[0] if exc.args else None
            if errno in _AUTH_ERRNOS:
                raise DbError("auth", f"认证失败：{credential.username}@{credential.host}") from exc
            raise DbError("network", f"无法连接 {credential.host}:{credential.port}（{exc}）") from exc
        except (TimeoutError, OSError) as exc:
            raise DbError("network", f"无法连接 {credential.host}:{credential.port}（{exc}）") from exc

    def query(self, sql: str, params: tuple = (), limit: int = 200) -> tuple[list[str], list[tuple]]:
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(sql, params or None)
                if cursor.description is None:
                    # 只读白名单下不该出现无结果集的语句，防御式返回空
                    return [], []
                columns = [col[0] for col in cursor.description]
                rows = [tuple(row) for row in cursor.fetchmany(limit)]
            return columns, rows
        except self._mysql_error as exc:
            # 查询阶段的错误统一归 sql（断连等边界情况带原始 errno，可读性够用）
            raise DbError("sql", f"SQL 执行失败：{exc}") from exc

    def close(self) -> None:
        self._conn.close()
