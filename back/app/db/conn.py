"""Database access.

psycopg 3, raw SQL, dict rows.  No ORM: the engine is read-heavy and its hot
path is one query over one view, so an object mapper would add a layer with no
query it needs to express.  The schema lives in `schema.sql` where it can be
read as a document during a design walkthrough.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row

from app.core.settings import settings

SQL_DIR = Path(__file__).resolve().parent


@contextmanager
def connect(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """A connection with dict rows.  Commits on clean exit, rolls back on error."""
    conn = psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=autocommit)
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


def query(conn: psycopg.Connection, sql: str, params: Sequence[Any] | dict | None = None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(conn: psycopg.Connection, sql: str, params: Sequence[Any] | dict | None = None) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(conn: psycopg.Connection, sql: str, params: Sequence[Any] | dict | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_many(conn: psycopg.Connection, sql: str, rows: Sequence[Sequence[Any]]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        return cur.rowcount


def run_sql_file(conn: psycopg.Connection, filename: str) -> None:
    """Apply a .sql file from app/db/ as a single statement batch."""
    path = SQL_DIR / filename
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)


def init_schema() -> None:
    """Create the schema from scratch and seed the rules.

    `schema.sql` drops before it creates, so this is idempotent and is the
    normal way to reset during development.
    """
    with connect() as conn:
        run_sql_file(conn, "schema.sql")
        run_sql_file(conn, "seed_rules.sql")


def check_connection() -> str:
    with connect(autocommit=True) as conn:
        row = query_one(conn, "SELECT version() AS v")
        return row["v"] if row else "unknown"
