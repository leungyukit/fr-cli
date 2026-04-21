"""
@db 内置 Agent —— 数据库智能助手
支持 MySQL / PostgreSQL / SQL Server / Oracle 的 Schema 分析和 SQL 生成。
"""
from pathlib import Path

DB_CFG_PATH = Path.home() / ".fr_cli_databases.json"

DB_SYS_PROMPT = """你是一个数据库专家。请根据以下数据库 Schema 信息和用户需求，生成最合适的 SQL 语句。

规则：
1. 只输出 SQL 语句本身，不要任何解释、不要 markdown 代码块
2. 如果涉及 DELETE / DROP / TRUNCATE 等危险操作，输出 COMMENT: 警告
3. 优先使用标准 SQL，必要时针对特定数据库方言优化
4. 如果需求不明确，输出 COMMENT: 提示需要更多信息
5. 对于查询类需求，尽量给出列名明确的 SELECT 语句

数据库类型: {db_type}
数据库名: {database}

Schema 信息:
{schema_info}
"""


def _load_dbs():
    from fr_cli.agent.builtins._utils import load_json_config
    return load_json_config(DB_CFG_PATH)


def _save_dbs(dbs):
    from fr_cli.agent.builtins._utils import save_json_config
    save_json_config(DB_CFG_PATH, dbs)


def _connect(db_cfg):
    """根据配置建立数据库连接"""
    db_type = db_cfg["type"]
    host = db_cfg["host"]
    port = db_cfg.get("port")
    user = db_cfg["user"]
    password = db_cfg["password"]
    database = db_cfg.get("database", "")

    if db_type == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=host, port=int(port) if port else 3306,
            user=user, password=password, database=database,
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    elif db_type == "postgresql":
        import psycopg2
        conn = psycopg2.connect(
            host=host, port=port or "5432",
            user=user, password=password, dbname=database
        )
        return conn
    elif db_type == "sqlserver":
        import pyodbc
        port_str = f",{port}" if port else ""
        conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host}{port_str};DATABASE={database};UID={user};PWD={password}"
        conn = pyodbc.connect(conn_str)
        return conn
    elif db_type == "oracle":
        import oracledb
        dsn = oracledb.makedsn(host, int(port) if port else 1521, service_name=database)
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        return conn
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


def _get_schema_info(conn, db_type):
    """获取数据库 Schema 信息（表、列、主键、外键）"""
    info = []
    cursor = conn.cursor()

    if db_type == "mysql":
        cursor.execute("SHOW TABLES")
        tables = [list(row.values())[0] for row in cursor.fetchall()]
        for table in tables:
            info.append(f"\n表: {table}")
            cursor.execute(f"DESCRIBE `{table}`")
            for col in cursor.fetchall():
                info.append(f"  {col['Field']} {col['Type']} {'PK' if col['Key'] == 'PRI' else ''}")
    elif db_type == "postgresql":
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            info.append(f"\n表: {table}")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s ORDER BY ordinal_position
            """, (table,))
            for col in cursor.fetchall():
                info.append(f"  {col[0]} {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
    elif db_type == "sqlserver":
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE'")
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            info.append(f"\n表: {table}")
            cursor.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'")
            for col in cursor.fetchall():
                info.append(f"  {col[0]} {col[1]}")
    elif db_type == "oracle":
        cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            info.append(f"\n表: {table}")
            cursor.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
            for col in cursor.fetchall():
                info.append(f"  {col[0]} {col[1]}")

    return "\n".join(info)


def _exec_sql(conn, sql, db_type):
    """执行 SQL 并返回结果"""
    cursor = conn.cursor()
    try:
        # 限制只执行单条语句，防止注入
        sql = sql.strip().rstrip(";")
        cursor.execute(sql)

        # 如果是 SELECT，返回结果集
        if sql.lower().startswith("select") or sql.lower().startswith("show") or sql.lower().startswith("desc"):
            rows = cursor.fetchall()
            if db_type == "mysql":
                return rows, None
            else:
                # 将 pyodbc/psycopg2 的行转为字典列表
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                return [{cols[i]: row[i] for i in range(len(cols))} for row in rows], None
        else:
            conn.commit()
            return f"受影响行数: {cursor.rowcount}", None
    except Exception as e:
        return None, str(e)


def handle_db(user_input, state):
    """处理 @db 前缀的请求"""
    from fr_cli.core.stream import stream_cnt
    from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET

    dbs = _load_dbs()
    if not dbs:
        print(f"{YELLOW}未配置数据库。正在启动配置向导...{RESET}")
        _setup_wizard(state.lang)
        dbs = _load_dbs()
        if not dbs:
            print(f"{RED}配置取消。{RESET}")
            return

    # 解析: @db [别名] 需求
    text = user_input[len("@db"):].strip()
    parts = text.split(None, 1)

    if len(dbs) == 1:
        alias = list(dbs.keys())[0]
        query = text
    else:
        if len(parts) < 2:
            print(f"{YELLOW}用法: @db <别名> <需求>{RESET}")
            print(f"{DIM}已配置数据库: {', '.join(dbs.keys())}{RESET}")
            return
        alias = parts[0]
        query = parts[1]

    db_cfg = dbs.get(alias)
    if not db_cfg:
        print(f"{RED}未找到数据库 [{alias}]。已配置: {', '.join(dbs.keys())}{RESET}")
        return

    try:
        conn = _connect(db_cfg)
    except Exception as e:
        print(f"{RED}数据库连接失败: {e}{RESET}")
        return

    try:
        print(f"{CYAN}📊 正在分析 {db_cfg['type'].upper()} [{alias}]({db_cfg.get('database','')}) 的 Schema...{RESET}")
        schema = _get_schema_info(conn, db_cfg["type"])

        prompt = DB_SYS_PROMPT.format(
            db_type=db_cfg["type"].upper(),
            database=db_cfg.get("database", ""),
            schema_info=schema[:3000]
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]

        print(f"{CYAN}🧙 正在生成 SQL...{RESET}")
        sql_text, _, _ = stream_cnt(state.client, state.model_name, messages, state.lang, custom_prefix="", max_tokens=1024)
        sql_text = sql_text.strip()

        from fr_cli.agent.builtins._utils import strip_code_blocks
        sql_text = strip_code_blocks(sql_text)

        if sql_text.startswith("COMMENT:"):
            print(f"{YELLOW}{sql_text}{RESET}")
            return

        print(f"\n{DIM}生成 SQL:{RESET}\n{CYAN}{sql_text}{RESET}")
        from fr_cli.agent.builtins._utils import confirm_execute
        if not confirm_execute():
            print(f"{DIM}已取消。{RESET}")
            return

        result, err = _exec_sql(conn, sql_text, db_cfg["type"])
        if err:
            print(f"{RED}❌ 执行失败: {err}{RESET}")
        else:
            if isinstance(result, list):
                print(f"\n{GREEN}返回 {len(result)} 行:{RESET}")
                for i, row in enumerate(result[:20]):
                    print(f"  {row}")
                if len(result) > 20:
                    print(f"  {DIM}... 还有 {len(result)-20} 行{RESET}")
            else:
                print(f"{GREEN}{result}{RESET}")
    finally:
        conn.close()


def _setup_wizard(lang="zh"):
    """数据库配置向导"""
    from fr_cli.ui.ui import CYAN, GREEN, YELLOW, DIM, RESET

    print(f"{CYAN}═══ 数据库配置向导 ═══{RESET}")
    alias = input(f"{DIM}别名 (如: mydb): {RESET}").strip()
    if not alias:
        print(f"{YELLOW}别名不能为空。{RESET}")
        return

    db_type = input(f"{DIM}数据库类型 (mysql/postgresql/sqlserver/oracle) [mysql]: {RESET}").strip() or "mysql"
    if db_type not in ("mysql", "postgresql", "sqlserver", "oracle"):
        print(f"{YELLOW}不支持的数据库类型。{RESET}")
        return

    host = input(f"{DIM}主机地址 [localhost]: {RESET}").strip() or "localhost"
    port_default = {"mysql": "3306", "postgresql": "5432", "sqlserver": "1433", "oracle": "1521"}[db_type]
    port = input(f"{DIM}端口 [{port_default}]: {RESET}").strip() or port_default
    user = input(f"{DIM}用户名: {RESET}").strip()
    if not user:
        print(f"{YELLOW}用户名不能为空。{RESET}")
        return
    password = input(f"{DIM}密码: {RESET}").strip()
    database = input(f"{DIM}数据库名: {RESET}").strip()

    dbs = _load_dbs()
    dbs[alias] = {
        "type": db_type,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }
    _save_dbs(dbs)
    print(f"{GREEN}✅ 数据库 [{alias}] ({db_type}) 已保存。{RESET}")
