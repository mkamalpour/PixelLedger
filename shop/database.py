"""SQLite transactions and bounded, genuinely read-only query exploration."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DEFAULT_PATH = Path(os.getenv("PIXELLEDGER_DB", str(ROOT / "data" / "shop.db")))


class Database:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path).resolve()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                (ROOT / "shop/schema.sql").read_text(encoding="utf-8")
            )

    def schema(self):
        with closing(self.connect()) as connection:
            names = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' AND name!='requests' ORDER BY name"
                )
            ]
            return {
                "tables": [
                    {
                        "name": name,
                        "columns": [
                            {"name": row[1], "type": row[2]}
                            for row in connection.execute(
                                f'PRAGMA table_info("{name}")'
                            )
                        ],
                    }
                    for name in names
                ]
            }

    def query(self, sql):
        if not sql.strip() or len(sql) > 10000:
            raise ValueError("Enter a read-only query under 10,000 characters")
        allowed_functions = {
            "count",
            "sum",
            "avg",
            "min",
            "max",
            "round",
            "coalesce",
            "nullif",
            "ifnull",
            "iif",
            "length",
            "lower",
            "upper",
            "substr",
            "substring",
            "abs",
            "printf",
            "format",
            "instr",
            "date",
            "datetime",
            "strftime",
            "julianday",
            "unixepoch",
            "trim",
            "ltrim",
            "rtrim",
            "replace",
            "group_concat",
            "typeof",
            "like",
            "glob",
            "total",
        }

        def authorize(action, first, second, database, trigger):
            if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and first != "requests":
                return sqlite3.SQLITE_OK
            if (
                action == sqlite3.SQLITE_FUNCTION
                and (second or "").lower() in allowed_functions
            ):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        uri = self.path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
            connection.set_authorizer(authorize)
            deadline = time.monotonic() + 2
            connection.set_progress_handler(
                lambda: int(time.monotonic() > deadline), 1000
            )
            cursor = connection.execute(sql)
            if not cursor.description:
                raise ValueError("Only read-only SELECT queries are permitted")
            rows = cursor.fetchmany(201)
            return {
                "columns": [column[0] for column in cursor.description],
                "rows": [list(row) for row in rows[:200]],
                "truncated": len(rows) > 200,
            }
