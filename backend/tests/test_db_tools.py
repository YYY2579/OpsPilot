"""M7-1 数据库只读工具测试（对应真实 SDK，FakeRunner 注入，不连真实数据库）。

覆盖：解析正确性 + 异常判断阈值 + SQL 白名单 + LIMIT 追加 + 凭据解析 + 注册完整性。
风格与 test_tools_readonly.py 对齐：Executor 用 __new__ 绕开 __init__，直接调 collect/build。
"""
from __future__ import annotations

import pytest

from ops_pilot.credentials import CredentialError
from ops_pilot.db.credentials import DbError
from ops_pilot.tools import database as db_mod


class FakeRunner:
    """SQL（前缀匹配，空串命中一切）→ (columns, rows)。记录调用便于断言最终执行的 SQL。"""

    def __init__(self, mapping: dict[str, tuple[list[str], list[tuple]]], error: Exception | None = None):
        self._m = mapping
        self.calls: list[str] = []
        self._error = error

    def query(self, sql: str, params: tuple = (), limit: int = 200):
        self.calls.append(sql)
        if self._error is not None:
            raise self._error
        for key, value in self._m.items():
            if sql == key or sql.startswith(key):
                return value
        return [], []

    def close(self):
        pass


def run_with(cls, action, mapping, error=None):
    """绕开 __init__（不解析凭据），直接 collect + build。返回 (Observation, runner)。"""
    ex = cls.__new__(cls)
    runner = FakeRunner(mapping, error)
    data = ex.collect(runner, action)
    return ex.build(action, data), runner


# ---------------- list_databases ----------------

DB_SIZE_SQL = "SELECT table_schema AS database_name"


def test_list_databases_parses():
    obs, _ = run_with(
        db_mod.ListDatabasesExecutor,
        db_mod.ListDatabasesAction(database_id="mysql-prod"),
        {DB_SIZE_SQL: (["database_name", "size_mb"],
                       [("ops_db", 120.5), ("blog", 30.0), ("no_perm", None)])},
    )
    assert obs.database_id == "mysql-prod"
    assert obs.databases[0] == {"name": "ops_db", "size_mb": 120.5}
    assert obs.databases[2]["size_mb"] is None
    assert obs.anomalies == []                        # 字段齐全且无异常


def test_list_databases_size_thresholds():
    obs, _ = run_with(
        db_mod.ListDatabasesExecutor,
        db_mod.ListDatabasesAction(database_id="mysql-prod"),
        # 51200MB=50GB 边界不触发；51201MB warning；204801MB(≈200GB) critical
        {DB_SIZE_SQL: (["database_name", "size_mb"],
                       [("edge", 51200.0), ("big", 51201.0), ("huge", 204801.0)])},
    )
    levels = {a["item"]: a["level"] for a in obs.anomalies}
    assert "database:edge" not in levels
    assert levels["database:big"] == "warning"
    assert levels["database:huge"] == "critical"


# ---------------- list_tables ----------------

TABLES_SQL = "SELECT table_name, table_rows, engine"


def test_list_tables_parses():
    obs, _ = run_with(
        db_mod.ListTablesExecutor,
        db_mod.ListTablesAction(database_id="mysql-prod", database="ops_db"),
        {TABLES_SQL: (["table_name", "table_rows", "engine"],
                      [("orders", 1234, "InnoDB"), ("users", 99, "InnoDB"), ("logs", None, "MyISAM")])},
    )
    assert obs.database == "ops_db"
    assert obs.tables[0] == {"name": "orders", "rows": 1234, "engine": "InnoDB"}
    assert obs.tables[2]["rows"] is None
    assert obs.table_total == 3
    assert obs.anomalies == []


def test_list_tables_too_many_tables():
    rows = [(f"t{i:03d}", 10, "InnoDB") for i in range(501)]   # 501 > 500 触发
    obs, _ = run_with(
        db_mod.ListTablesExecutor,
        db_mod.ListTablesAction(database_id="mysql-prod", database="ops_db"),
        {TABLES_SQL: (["table_name", "table_rows", "engine"], rows)},
    )
    assert obs.table_total == 501
    assert obs.anomalies[0]["level"] == "warning"
    assert "分表" in obs.anomalies[0]["hint"]


# ---------------- describe_table ----------------

COLUMNS_SQL = "SELECT column_name, column_type, is_nullable, column_key, column_default, extra"


def test_describe_table_parses():
    obs, _ = run_with(
        db_mod.DescribeTableExecutor,
        db_mod.DescribeTableAction(database_id="mysql-prod", database="ops_db", table="orders"),
        {COLUMNS_SQL: (["column_name", "column_type", "is_nullable", "column_key",
                        "column_default", "extra"],
                       [("id", "bigint", "NO", "PRI", None, "auto_increment"),
                        ("note", "varchar(200)", "YES", "", None, "")])},
    )
    assert obs.columns[0] == {"name": "id", "type": "bigint", "nullable": False,
                              "key": "PRI", "default": None, "extra": "auto_increment"}
    assert obs.has_primary_key is True
    assert obs.anomalies == []


def test_describe_table_no_primary_key():
    obs, _ = run_with(
        db_mod.DescribeTableExecutor,
        db_mod.DescribeTableAction(database_id="mysql-prod", database="ops_db", table="logs"),
        {COLUMNS_SQL: (["column_name", "column_type", "is_nullable", "column_key",
                        "column_default", "extra"],
                       [("msg", "text", "YES", "", None, "")])},
    )
    assert obs.has_primary_key is False
    assert obs.anomalies[0]["level"] == "warning"
    assert "无主键，写操作风险高" in obs.anomalies[0]["hint"]


def test_describe_table_missing_table_is_clear():
    with pytest.raises(ValueError) as exc:
        run_with(
            db_mod.DescribeTableExecutor,
            db_mod.DescribeTableAction(database_id="mysql-prod", database="ops_db", table="ghost"),
            {COLUMNS_SQL: ([], [])},
        )
    assert "ghost" in str(exc.value)


# ---------------- query_readonly：主用例 + 白名单 + LIMIT ----------------

QUERY_SQL_PREFIX = "select id, name from users"


def test_query_readonly_parses_and_keeps_existing_limit():
    obs, runner = run_with(
        db_mod.QueryReadonlyExecutor,
        db_mod.QueryReadonlyAction(database_id="mysql-prod", sql="SELECT id, name FROM users LIMIT 10"),
        {"": (["id", "name"], [(1, "a"), (2, "b")])},
    )
    assert runner.calls[0] == "SELECT id, name FROM users LIMIT 10"   # 已有 LIMIT 不追加
    assert obs.columns == ["id", "name"]
    assert obs.rows == [(1, "a"), (2, "b")]
    assert obs.row_count == 2
    assert obs.truncated is False
    assert obs.elapsed_s >= 0
    assert obs.anomalies == []


@pytest.mark.parametrize("sql", [
    "DELETE FROM users WHERE id = 1",
    "UPDATE users SET name = 'x' WHERE id = 1",
    "INSERT INTO users VALUES (1)",
    "REPLACE INTO users VALUES (1)",
    "DROP TABLE users",
    "TRUNCATE TABLE users",
    "ALTER TABLE users ADD COLUMN c INT",
    "CREATE TABLE t (id INT)",
    "GRANT ALL PRIVILEGES ON *.* TO 'u'@'%'",
    "REVOKE ALL ON *.* FROM u",
    "RENAME TABLE a TO b",
    "LOAD DATA INFILE '/tmp/x' INTO TABLE t",
    "CALL do_something()",
    "SET GLOBAL max_connections = 100",
    "LOCK TABLES users READ",
    "UNLOCK TABLES",
    "SELECT * FROM users INTO OUTFILE '/tmp/x'",
    "SELECT * FROM users INTO DUMPFILE '/tmp/x'",
    "SELECT * FROM users; DROP TABLE users",           # 多条语句
    "SELECT 1; DELETE FROM users;",                    # 结尾分号掩盖的写语句
    "explain delete from users",                        # EXPLAIN 套写语句也要拦
    "",                                                  # 空语句
])
def test_query_readonly_whitelist_rejects(sql):
    with pytest.raises(ValueError, match="只读模式不允许该语句"):
        db_mod.sanitize_readonly_sql(sql)


@pytest.mark.parametrize("sql,expected", [
    # 前后空白/结尾分号规范化 + 自动追加 LIMIT
    ("  SELECT * FROM users ;  ", "SELECT * FROM users LIMIT 200"),
    ("select id from t", "select id from t LIMIT 200"),
    ("SHOW TABLES", "SHOW TABLES"),
    ("DESCRIBE users", "DESCRIBE users"),
    ("desc users", "desc users"),
    ("EXPLAIN SELECT * FROM users", "EXPLAIN SELECT * FROM users"),
    # 已有 LIMIT 不追加
    ("SELECT * FROM users LIMIT 10", "SELECT * FROM users LIMIT 10"),
    # 词边界：标识符不误杀（created_at / grants / offset）
    ("select id, created_at from t where status = 'ok'", None),
    ("SHOW GRANTS FOR CURRENT_USER", None),
])
def test_query_readonly_whitelist_allows(sql, expected):
    result = db_mod.sanitize_readonly_sql(sql)
    if expected is not None:
        assert result == expected


def test_query_readonly_appends_and_clamps_limit():
    # 无 limit → 追加默认 200
    _, r1 = run_with(
        db_mod.QueryReadonlyExecutor,
        db_mod.QueryReadonlyAction(database_id="mysql-prod", sql="select * from users"),
        {"": ([], [])},
    )
    assert r1.calls[0] == "select * from users LIMIT 200"
    # 超过上限 1000 → 收敛到 1000
    _, r2 = run_with(
        db_mod.QueryReadonlyExecutor,
        db_mod.QueryReadonlyAction(database_id="mysql-prod", sql="select * from users", limit=9999),
        {"": ([], [])},
    )
    assert r2.calls[0] == "select * from users LIMIT 1000"


def test_query_readonly_truncated_warning():
    rows = [(i, f"u{i}") for i in range(5)]
    obs, _ = run_with(
        db_mod.QueryReadonlyExecutor,
        db_mod.QueryReadonlyAction(database_id="mysql-prod", sql="SELECT * FROM users LIMIT 5", limit=5),
        {"": (["id", "name"], rows)},
    )
    assert obs.truncated is True
    assert any(a["item"] == "query:result" and a["level"] == "warning" for a in obs.anomalies)


def test_query_readonly_slow_warning(monkeypatch):
    # 真实 3s 阈值不进测试：把阈值改成 -1，任何耗时都会命中同一条代码路径
    monkeypatch.setattr(db_mod, "QUERY_SLOW_S", -1.0)
    obs, _ = run_with(
        db_mod.QueryReadonlyExecutor,
        db_mod.QueryReadonlyAction(database_id="mysql-prod", sql="SELECT SLEEP(0)"),
        {"": ([], [])},
    )
    assert any(a["item"] == "query:elapsed" and a["level"] == "warning" for a in obs.anomalies)


# ---------------- explain_sql ----------------

EXPLAIN_PREFIX = "EXPLAIN "


def test_explain_sql_parses_and_keeps_no_limit():
    obs, runner = run_with(
        db_mod.ExplainSqlExecutor,
        db_mod.ExplainSqlAction(database_id="mysql-prod", sql="SELECT * FROM orders WHERE user_id = 1"),
        {EXPLAIN_PREFIX: (["id", "select_type", "table", "type", "rows", "Extra"],
                          [(1, "SIMPLE", "orders", "ref", "12", "Using where")])},
    )
    assert runner.calls[0] == "EXPLAIN SELECT * FROM orders WHERE user_id = 1"  # 不追加 LIMIT
    assert obs.sql.startswith("EXPLAIN ")
    assert obs.plan[0]["type"] == "ref"
    assert obs.anomalies == []


def test_explain_sql_full_scan_warning():
    cols = ["id", "select_type", "table", "type", "rows", "Extra"]
    # 25000 > 10000 触发；10000 是边界不触发
    obs, _ = run_with(
        db_mod.ExplainSqlExecutor,
        db_mod.ExplainSqlAction(database_id="mysql-prod", sql="SELECT * FROM big_log"),
        {EXPLAIN_PREFIX: (cols, [(1, "SIMPLE", "big_log", "ALL", "25000", "Using where")])},
    )
    assert obs.anomalies[0]["level"] == "warning"
    assert "全表扫描" in obs.anomalies[0]["hint"]
    assert obs.anomalies[0]["item"] == "explain:big_log"

    obs2, _ = run_with(
        db_mod.ExplainSqlExecutor,
        db_mod.ExplainSqlAction(database_id="mysql-prod", sql="SELECT * FROM small_log"),
        {EXPLAIN_PREFIX: (cols, [(1, "SIMPLE", "small_log", "ALL", "10000", "")])},
    )
    assert obs2.anomalies == []


def test_explain_sql_rejects_non_select():
    with pytest.raises(ValueError, match="仅支持对 SELECT"):
        run_with(
            db_mod.ExplainSqlExecutor,
            db_mod.ExplainSqlAction(database_id="mysql-prod", sql="SHOW TABLES"),
            {},
        )


# ---------------- 错误转换（Executor 统一出口） ----------------

def test_executor_converts_dberror_to_valueerror():
    ex = db_mod.ListDatabasesExecutor(
        resolver=db_mod.DbCredentialResolver(environ=FULL_ENV),
        runner_factory=lambda c: FakeRunner({}, error=DbError("auth", "认证失败")),
    )
    with pytest.raises(ValueError) as exc:
        ex(db_mod.ListDatabasesAction(database_id="mysql-prod"))
    assert "DB auth" in str(exc.value)


def test_executor_converts_credentialerror_to_valueerror():
    ex = db_mod.ListDatabasesExecutor(resolver=db_mod.DbCredentialResolver(environ={}))
    with pytest.raises(ValueError) as exc:
        ex(db_mod.ListDatabasesAction(database_id="mysql-prod"))
    assert "DB missing" in str(exc.value)


# ---------------- 凭据解析（DbCredentialResolver） ----------------

FULL_ENV = {
    "OPSPILOT_DB_MYSQL_PROD_HOST": "10.0.0.5",
    "OPSPILOT_DB_MYSQL_PROD_PORT": "3307",
    "OPSPILOT_DB_MYSQL_PROD_USERNAME": "readonly",
    "OPSPILOT_DB_MYSQL_PROD_PASSWORD": "pw-123",
    "OPSPILOT_DB_MYSQL_PROD_DATABASE": "ops_db",
}


def test_resolver_missing_when_no_env():
    with pytest.raises(CredentialError) as exc:
        db_mod.DbCredentialResolver(environ={}).resolve("mysql-prod")
    assert exc.value.kind == "missing"


@pytest.mark.parametrize("drop", ["OPSPILOT_DB_MYSQL_PROD_USERNAME", "OPSPILOT_DB_MYSQL_PROD_PASSWORD"])
def test_resolver_incomplete_when_field_missing(drop):
    env = {k: v for k, v in FULL_ENV.items() if k != drop}
    with pytest.raises(CredentialError) as exc:
        db_mod.DbCredentialResolver(environ=env).resolve("mysql-prod")
    assert exc.value.kind == "incomplete"


def test_resolver_normalizes_database_id():
    # mysql-prod 与 MYSQL.PROD 命中同一组环境变量
    resolver = db_mod.DbCredentialResolver(environ=FULL_ENV)
    c1 = resolver.resolve("mysql-prod")
    c2 = resolver.resolve("MYSQL.PROD")
    # database_id 保留调用方原始写法，连接字段必须完全一致
    assert (c1.host, c1.port, c1.username, c1.password, c1.database) == \
           (c2.host, c2.port, c2.username, c2.password, c2.database)
    assert c1.host == "10.0.0.5" and c1.port == 3307
    assert c1.username == "readonly" and c1.password == "pw-123"
    assert c1.database == "ops_db"


def test_resolver_defaults_port_and_database():
    env = {k: v for k, v in FULL_ENV.items() if k not in ("OPSPILOT_DB_MYSQL_PROD_PORT", "OPSPILOT_DB_MYSQL_PROD_DATABASE")}
    c = db_mod.DbCredentialResolver(environ=env).resolve("mysql-prod")
    assert c.port == 3306 and c.database is None


# ---------------- 注册完整性 + 风险等级 + readOnlyHint ----------------

DB_TOOL_NAMES = ("list_databases", "list_tables", "describe_table", "query_readonly", "explain_sql")


def test_db_tools_registered_l1_readonly():
    import ops_pilot.tools.register_all as reg
    from openhands.sdk.tool import Tool, resolve_tool
    from openhands.sdk.tool.registry import list_registered_tools

    from ops_pilot.security.guard import TOOL_LEVELS, level_of
    from ops_pilot.security.levels import RiskLevel

    registered = set(list_registered_tools())
    for name in DB_TOOL_NAMES:
        assert name in registered, f"{name} 未注册"
        assert name in reg.READONLY_TOOL_NAMES
        assert TOOL_LEVELS[name] is RiskLevel.L1
        assert level_of(name) is RiskLevel.L1

        class _StubState:      # create(conv_state=...) 里我们的工具不使用 workspace
            pass

        tools = resolve_tool(Tool(name=name), _StubState())
        for t in tools:
            assert t.annotations is not None
            assert t.annotations.readOnlyHint is True, f"{t.name} 未声明 readOnlyHint=True"
