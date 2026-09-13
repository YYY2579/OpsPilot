"""数据库只读工具：list_databases / list_tables / describe_table / query_readonly / explain_sql

规格 §A5.2 数据库类。全部 readOnlyHint=True（L1 只读，免确认）。
分层：Executor 只依赖 DbRunner 协议；pymysql 只在 db/client.py 延迟导入。
凭据纪律（§A6.4）：Action 只有 database_id，凭据解析只发生在 Executor 内。
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar

from openhands.sdk.tool import (
    Action,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)
from pydantic import Field

from ops_pilot.credentials import CredentialError
from ops_pilot.db.client import DbRunner, PymysqlRunner
from ops_pilot.db.credentials import DbCredential, DbCredentialResolver, DbError
from ops_pilot.tools._base import JsonObservation
from ops_pilot.tools.sshcmd import clamp

ActionT = TypeVar("ActionT")
ObservationT = TypeVar("ObservationT")

#: 元数据查询是内部 SQL，不受用户 limit 约束，但要有个兜底上限防止失控
_METADATA_LIMIT = 5000
#: information_schema 里表数量的合理上限：超过即提示分表/设计问题
TABLES_WARN = 500
#: 单库体积阈值（MB）：> 50 GB warning，> 200 GB critical
DB_SIZE_WARN_MB, DB_SIZE_CRIT_MB = 50 * 1024, 200 * 1024
#: query_readonly 慢查询阈值（秒）
QUERY_SLOW_S = 3.0
#: EXPLAIN 全表扫描的行数阈值
EXPLAIN_FULL_SCAN_ROWS = 10000


# ============================ 公共执行层 ============================

class DbReadOnlyExecutor(ToolExecutor[ActionT, ObservationT], Generic[ActionT, ObservationT]):
    """只读 DB 工具的统一执行层。子类只需实现 collect() 与 build()。

    runner_factory 仅供测试注入假 Runner；生产路径统一走 PymysqlRunner。
    """

    def __init__(
        self,
        resolver: DbCredentialResolver | None = None,
        runner_factory: Callable[[DbCredential], DbRunner] | None = None,
        connect_timeout: float = 8.0,
    ) -> None:
        self._resolver = resolver or DbCredentialResolver()
        self._runner_factory = runner_factory
        self._connect_timeout = connect_timeout

    def collect(self, runner: Any, action: ActionT) -> dict[str, Any]:
        raise NotImplementedError

    def build(self, action: ActionT, data: dict[str, Any]) -> ObservationT:
        raise NotImplementedError

    def __call__(self, action: ActionT, conversation: Any = None) -> ObservationT:
        runner = None
        try:
            credential = self._resolver.resolve(getattr(action, "database_id"))
            runner = (
                self._runner_factory(credential)
                if self._runner_factory is not None
                else PymysqlRunner(credential, connect_timeout=self._connect_timeout)
            )
            data = self.collect(runner, action)
        except (DbError, CredentialError) as exc:
            # 明确区分：认证失败 / 网络不通 / SQL 失败 / 凭据缺失（规格 §A12 同一套口径）
            raise ValueError(f"DB {exc.kind}: {exc.detail}") from exc
        finally:
            if runner is not None:
                runner.close()
        return self.build(action, data)


# ============================ SQL 白名单 ============================

_READONLY_PREFIXES = ("select", "show", "explain", "describe", "desc")

# 显式拒绝清单按词边界匹配：只拦"关键字当关键字用"的语句，
# 避免 created_at / offset / grants 这类标识符被误杀。白名单宁可误杀字符串
# 字面量里的关键字（如 WHERE note='delete it'），也不放过任何放行风险。
_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "replace", "grant", "revoke", "rename", "load data", "into outfile",
    "into dumpfile", "lock tables", "unlock tables", "call", "set",
)
_FORBIDDEN_RE = re.compile(
    "|".join(
        r"\b" + r"\s+".join(re.escape(word) for word in kw.split()) + r"\b"
        for kw in _FORBIDDEN_KEYWORDS
    )
)
_LIMIT_RE = re.compile(r"\blimit\b")


def sanitize_readonly_sql(sql: str, limit: int | None = 200) -> str:
    """规范化 + 白名单校验 + 自动追加 LIMIT。拒绝时抛 ValueError。

    limit=None 时不追加（EXPLAIN 场景：LIMIT 会改变执行计划）。
    """
    text = " ".join(sql.strip().rstrip(";").split())   # 去首尾空白/结尾分号，压缩连续空白
    if not text:
        raise ValueError("只读模式不允许该语句：空语句")
    lowered = text.lower()
    if not lowered.startswith(_READONLY_PREFIXES):
        raise ValueError(
            "只读模式不允许该语句：仅支持以 SELECT / SHOW / EXPLAIN / DESCRIBE / DESC 开头"
        )
    hit = _FORBIDDEN_RE.search(lowered)
    if hit:
        raise ValueError(f"只读模式不允许该语句：包含禁止关键字 {hit.group(0)}")
    if ";" in text:
        # 前面的 rstrip 只去掉结尾分号，这里还剩分号说明是多条语句
        raise ValueError("只读模式不允许该语句：不支持多条语句")
    if limit is not None and lowered.startswith("select") and not _LIMIT_RE.search(lowered):
        # 只对 SELECT 追加：DESCRIBE / SHOW 子句语法各异，盲加 LIMIT 会产生非法 SQL；
        # 非 SELECT 语句的行数由 DbRunner 的 fetchmany 兜底截断
        text = f"{text} LIMIT {limit}"
    return text


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ============================ list_databases ============================

class ListDatabasesAction(Action):
    database_id: str = Field(description="目标数据库实例标识，如 mysql-prod（非 IP）")


class ListDatabasesObservation(JsonObservation):
    database_id: str
    databases: list[dict[str, Any]]
    anomalies: list[dict[str, str]]


_DB_SIZE_SQL = (
    "SELECT table_schema AS database_name, "
    "ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb "
    "FROM information_schema.tables GROUP BY table_schema ORDER BY size_mb DESC"
)


def analyze_database_sizes(databases: list[dict[str, Any]]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    for db in databases:
        size = db["size_mb"]
        if size is None:
            continue
        if size > DB_SIZE_CRIT_MB:
            anomalies.append({"item": f"database:{db['name']}", "level": "critical",
                              "hint": f"库大小 {size / 1024:.1f} GB > 200 GB"})
        elif size > DB_SIZE_WARN_MB:
            anomalies.append({"item": f"database:{db['name']}", "level": "warning",
                              "hint": f"库大小 {size / 1024:.1f} GB > 50 GB"})
    return anomalies


class ListDatabasesExecutor(DbReadOnlyExecutor[ListDatabasesAction, ListDatabasesObservation]):
    def collect(self, runner: Any, action: ListDatabasesAction) -> dict[str, Any]:
        columns, rows = runner.query(_DB_SIZE_SQL, (), limit=_METADATA_LIMIT)
        databases = [{"name": row[0], "size_mb": _to_float(row[1])} for row in rows]
        return {
            "database_id": action.database_id,
            "databases": databases,
            "anomalies": analyze_database_sizes(databases),
        }

    def build(self, action: ListDatabasesAction, data: dict[str, Any]) -> ListDatabasesObservation:
        return ListDatabasesObservation(**data)


class ListDatabasesTool(ToolDefinition[ListDatabasesAction, ListDatabasesObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ListDatabasesTool]:
        return [cls(
            action_type=ListDatabasesAction,
            observation_type=ListDatabasesObservation,
            description="只读列出 MySQL 实例上的所有数据库及各自体积（information_schema 汇总），"
                        "按体积降序，并对超大库给出 anomalies。",
            annotations=ToolAnnotations(title="list_databases", readOnlyHint=True),
            executor=ListDatabasesExecutor(),
        )]


# ============================ list_tables ============================

class ListTablesAction(Action):
    database_id: str = Field(description="目标数据库实例标识，如 mysql-prod（非 IP）")
    database: str = Field(description="要查看的库名，如 ops_db")


class ListTablesObservation(JsonObservation):
    database_id: str
    database: str
    tables: list[dict[str, Any]]
    table_total: int
    anomalies: list[dict[str, str]]


_TABLES_SQL = (
    "SELECT table_name, table_rows, engine FROM information_schema.tables "
    "WHERE table_schema = %s ORDER BY table_name"
)


class ListTablesExecutor(DbReadOnlyExecutor[ListTablesAction, ListTablesObservation]):
    def collect(self, runner: Any, action: ListTablesAction) -> dict[str, Any]:
        _cols, rows = runner.query(_TABLES_SQL, (action.database,), limit=_METADATA_LIMIT)
        # InnoDB 的 table_rows 是估算值，供量级判断用，不承诺精确
        tables = [
            {"name": row[0], "rows": _to_int(row[1]), "engine": row[2]}
            for row in rows
        ]
        anomalies: list[dict[str, str]] = []
        if len(tables) > TABLES_WARN:
            anomalies.append({
                "item": f"database:{action.database}",
                "level": "warning",
                "hint": f"表数量 {len(tables)} > {TABLES_WARN}，可能是分表策略或设计问题",
            })
        return {
            "database_id": action.database_id,
            "database": action.database,
            "tables": tables,
            "table_total": len(tables),
            "anomalies": anomalies,
        }

    def build(self, action: ListTablesAction, data: dict[str, Any]) -> ListTablesObservation:
        return ListTablesObservation(**data)


class ListTablesTool(ToolDefinition[ListTablesAction, ListTablesObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ListTablesTool]:
        return [cls(
            action_type=ListTablesAction,
            observation_type=ListTablesObservation,
            description="只读列出指定库的全部表（表名/行数/引擎），行数为 InnoDB 估算值；"
                        "表数量过多时给出 anomalies 提示。",
            annotations=ToolAnnotations(title="list_tables", readOnlyHint=True),
            executor=ListTablesExecutor(),
        )]


# ============================ describe_table ============================

class DescribeTableAction(Action):
    database_id: str = Field(description="目标数据库实例标识，如 mysql-prod（非 IP）")
    database: str = Field(description="库名，如 ops_db")
    table: str = Field(description="表名，如 orders")


class DescribeTableObservation(JsonObservation):
    database_id: str
    database: str
    table: str
    columns: list[dict[str, Any]]
    has_primary_key: bool
    anomalies: list[dict[str, str]]


_COLUMNS_SQL = (
    "SELECT column_name, column_type, is_nullable, column_key, column_default, extra "
    "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
    "ORDER BY ordinal_position"
)


class DescribeTableExecutor(DbReadOnlyExecutor[DescribeTableAction, DescribeTableObservation]):
    def collect(self, runner: Any, action: DescribeTableAction) -> dict[str, Any]:
        _cols, rows = runner.query(_COLUMNS_SQL, (action.database, action.table), limit=_METADATA_LIMIT)
        if not rows:
            # 列信息为空：表不存在或账号没有该库的元数据权限，不能静默返回空表结构
            raise ValueError(f"表 {action.database}.{action.table} 不存在或无元数据权限")
        columns = [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "key": row[3] or "",
                "default": row[4],
                "extra": row[5] or "",
            }
            for row in rows
        ]
        has_pk = any(col["key"] == "PRI" for col in columns)
        anomalies: list[dict[str, str]] = []
        if not has_pk:
            anomalies.append({
                "item": f"table:{action.database}.{action.table}",
                "level": "warning",
                "hint": "无主键，写操作风险高",
            })
        return {
            "database_id": action.database_id,
            "database": action.database,
            "table": action.table,
            "columns": columns,
            "has_primary_key": has_pk,
            "anomalies": anomalies,
        }

    def build(self, action: DescribeTableAction, data: dict[str, Any]) -> DescribeTableObservation:
        return DescribeTableObservation(**data)


class DescribeTableTool(ToolDefinition[DescribeTableAction, DescribeTableObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[DescribeTableTool]:
        return [cls(
            action_type=DescribeTableAction,
            observation_type=DescribeTableObservation,
            description="只读查看表结构（列名/类型/可空/键/默认值/extra），并检查无主键风险。",
            annotations=ToolAnnotations(title="describe_table", readOnlyHint=True),
            executor=DescribeTableExecutor(),
        )]


# ============================ query_readonly ============================

class QueryReadonlyAction(Action):
    database_id: str = Field(description="目标数据库实例标识，如 mysql-prod（非 IP）")
    sql: str = Field(description="只读 SQL，仅允许 SELECT / SHOW / EXPLAIN / DESCRIBE / DESC 开头")
    limit: int = Field(default=200, description="自动追加 LIMIT 的行数上限（1–1000）")


class QueryReadonlyObservation(JsonObservation):
    database_id: str
    sql: str                  # 实际执行的 SQL（含自动追加的 LIMIT）
    columns: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool
    elapsed_s: float
    anomalies: list[dict[str, str]]


class QueryReadonlyExecutor(DbReadOnlyExecutor[QueryReadonlyAction, QueryReadonlyObservation]):
    def collect(self, runner: Any, action: QueryReadonlyAction) -> dict[str, Any]:
        limit = clamp(action.limit, 1, 1000)
        final_sql = sanitize_readonly_sql(action.sql, limit=limit)
        started = time.perf_counter()
        columns, rows = runner.query(final_sql, (), limit=limit)
        elapsed = time.perf_counter() - started
        # 行数打到 limit 即视为被截断：精确等于的场景极少，宁可多提示一次
        truncated = len(rows) >= limit
        anomalies: list[dict[str, str]] = []
        if truncated:
            anomalies.append({
                "item": "query:result",
                "level": "warning",
                "hint": f"结果达到 LIMIT {limit} 被截断，建议加 WHERE 收窄或调高 limit（上限 1000）",
            })
        if elapsed > QUERY_SLOW_S:
            anomalies.append({
                "item": "query:elapsed",
                "level": "warning",
                "hint": f"执行耗时 {elapsed:.2f}s > {QUERY_SLOW_S}s，可能是慢查询",
            })
        return {
            "database_id": action.database_id,
            "sql": final_sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_s": round(elapsed, 3),
            "anomalies": anomalies,
        }

    def build(self, action: QueryReadonlyAction, data: dict[str, Any]) -> QueryReadonlyObservation:
        return QueryReadonlyObservation(**data)


class QueryReadonlyTool(ToolDefinition[QueryReadonlyAction, QueryReadonlyObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[QueryReadonlyTool]:
        return [cls(
            action_type=QueryReadonlyAction,
            observation_type=QueryReadonlyObservation,
            description="只读执行 SQL：仅允许 SELECT / SHOW / EXPLAIN / DESCRIBE / DESC 开头的单条语句，"
                        "显式拒绝写关键字（INSERT/UPDATE/DELETE/DDL 等），无 LIMIT 时自动追加。"
                        "结果被截断或执行过慢时给出 anomalies。",
            annotations=ToolAnnotations(title="query_readonly", readOnlyHint=True),
            executor=QueryReadonlyExecutor(),
        )]


# ============================ explain_sql ============================

class ExplainSqlAction(Action):
    database_id: str = Field(description="目标数据库实例标识，如 mysql-prod（非 IP）")
    sql: str = Field(description="要分析的 SELECT 语句（不含 EXPLAIN 关键字）")


class ExplainSqlObservation(JsonObservation):
    database_id: str
    sql: str                  # 实际执行的 EXPLAIN 语句
    plan: list[dict[str, Any]]
    anomalies: list[dict[str, str]]


class ExplainSqlExecutor(DbReadOnlyExecutor[ExplainSqlAction, ExplainSqlObservation]):
    def collect(self, runner: Any, action: ExplainSqlAction) -> dict[str, Any]:
        # 白名单照走（EXPLAIN 套写语句必须拦），但不追加 LIMIT —— LIMIT 会改变执行计划
        inner = sanitize_readonly_sql(action.sql, limit=None)
        if not inner.lower().startswith("select"):
            raise ValueError("explain_sql 仅支持对 SELECT 语句执行 EXPLAIN")
        final_sql = f"EXPLAIN {inner}"
        columns, rows = runner.query(final_sql, (), limit=200)
        plan = [dict(zip(columns, row)) for row in rows]
        anomalies: list[dict[str, str]] = []
        for node in plan:
            if str(node.get("type", "")).lower() == "all":
                scanned = _to_int(node.get("rows")) or 0
                if scanned > EXPLAIN_FULL_SCAN_ROWS:
                    anomalies.append({
                        "item": f"explain:{node.get('table') or '?'}",
                        "level": "warning",
                        "hint": f"全表扫描（type=ALL），预估扫描 {scanned} 行 > "
                                f"{EXPLAIN_FULL_SCAN_ROWS}，建议加索引或收窄 WHERE 条件",
                    })
        return {
            "database_id": action.database_id,
            "sql": final_sql,
            "plan": plan,
            "anomalies": anomalies,
        }

    def build(self, action: ExplainSqlAction, data: dict[str, Any]) -> ExplainSqlObservation:
        return ExplainSqlObservation(**data)


class ExplainSqlTool(ToolDefinition[ExplainSqlAction, ExplainSqlObservation]):
    @classmethod
    def create(cls, conv_state: Any = None, **params: Any) -> Sequence[ExplainSqlTool]:
        return [cls(
            action_type=ExplainSqlAction,
            observation_type=ExplainSqlObservation,
            description="只读对 SELECT 语句执行 EXPLAIN 并返回执行计划，"
                        "出现全表扫描（type=ALL 且预估行数大）时给出 anomalies。",
            annotations=ToolAnnotations(title="explain_sql", readOnlyHint=True),
            executor=ExplainSqlExecutor(),
        )]


register_tool(ListDatabasesTool.name, ListDatabasesTool)
register_tool(ListTablesTool.name, ListTablesTool)
register_tool(DescribeTableTool.name, DescribeTableTool)
register_tool(QueryReadonlyTool.name, QueryReadonlyTool)
register_tool(ExplainSqlTool.name, ExplainSqlTool)
