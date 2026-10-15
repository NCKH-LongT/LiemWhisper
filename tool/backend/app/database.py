"""Database adapter supporting both SQLite and PostgreSQL (via psycopg).
Preserves the sqlite3 qmark '?' API, provides dict-like and index-based Row access,
and handles schema initialization and migrations portably.
"""
import os
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_ROOT = PROJECT_ROOT / "private-data"


def get_data_root() -> Path:
    root = Path(os.getenv("DATA_ROOT", str(DEFAULT_DATA_ROOT))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def is_postgres() -> bool:
    url = get_database_url()
    return bool(url and (url.startswith("postgres://") or url.startswith("postgresql://")))


_PARAM_REGEX = re.compile(r"('(?:''|[^'])*'|--[^\n]*|/\*.*?\*/|\?)", re.DOTALL)


def qmark_to_pyformat(sql: str) -> str:
    """Replace '?' with '%s' outside of string literals and comments."""
    def replacer(match: re.Match) -> str:
        text = match.group(0)
        if text == "?":
            return "%s"
        return text
    return _PARAM_REGEX.sub(replacer, sql)


class Row(Mapping):
    """Row wrapper that provides both mapping access (row['col']) and integer indexing (row[0])."""
    __slots__ = ("_values", "_mapping")

    def __init__(self, description: Any, values: tuple | list):
        self._values = tuple(values)
        if description:
            # Handle both sqlite tuple description and psycopg Column objects
            self._mapping = {
                desc[0]: val for desc, val in zip(description, values)
            }
        else:
            self._mapping = {}

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def __contains__(self, key: Any) -> bool:
        return key in self._mapping

    def get(self, key: str, default: Any = None) -> Any:
        return self._mapping.get(key, default)

    def keys(self):
        return self._mapping.keys()

    def values(self):
        return self._mapping.values()

    def items(self):
        return self._mapping.items()

    def __repr__(self) -> str:
        return f"Row({self._mapping})"


class PgCursorWrapper:
    """Wraps a psycopg cursor to convert qmark queries and wrap returned rows."""

    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self) -> Any:
        return self._cursor.description

    def fetchone(self) -> Row | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return row if isinstance(row, Row) else Row(self._cursor.description, row)

    def fetchall(self) -> list[Row]:
        rows = self._cursor.fetchall()
        return [r if isinstance(r, Row) else Row(self._cursor.description, r) for r in rows]

    def execute(self, sql: str, params: Any = None) -> "PgCursorWrapper":
        pg_sql = qmark_to_pyformat(sql)
        if params is not None:
            self._cursor.execute(pg_sql, tuple(params))
        else:
            self._cursor.execute(pg_sql)
        return self


class PgConnectionWrapper:
    """Wraps a psycopg connection with qmark execute and row mapping."""

    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> PgCursorWrapper:
        cur = self._conn.cursor()
        wrapper = PgCursorWrapper(cur)
        wrapper.execute(sql, params)
        return wrapper

    def executemany(self, sql: str, params_seq: Any) -> PgCursorWrapper:
        cur = self._conn.cursor()
        pg_sql = qmark_to_pyformat(sql)
        cur.executemany(pg_sql, params_seq)
        return PgCursorWrapper(cur)

    def executescript(self, script: str) -> None:
        self._conn.execute(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class SqliteCursorWrapper:
    """Wraps sqlite3 cursor to ensure Row returned has .get and dict-like behavior."""

    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def description(self) -> Any:
        return self._cursor.description

    def fetchone(self) -> Row | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        return row if isinstance(row, Row) else Row(self._cursor.description, row)

    def fetchall(self) -> list[Row]:
        rows = self._cursor.fetchall()
        return [r if isinstance(r, Row) else Row(self._cursor.description, r) for r in rows]

    def execute(self, sql: str, params: Any = None) -> "SqliteCursorWrapper":
        if params is not None:
            self._cursor.execute(sql, tuple(params))
        else:
            self._cursor.execute(sql)
        return self


class SqliteConnectionWrapper:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> SqliteCursorWrapper:
        cur = self._conn.cursor()
        wrapper = SqliteCursorWrapper(cur)
        wrapper.execute(sql, params)
        return wrapper

    def executemany(self, sql: str, params_seq: Any) -> SqliteCursorWrapper:
        cur = self._conn.cursor()
        cur.executemany(sql, params_seq)
        return SqliteCursorWrapper(cur)

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def db():
    if is_postgres():
        import psycopg
        url = get_database_url()
        assert url is not None
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]

        def row_factory(cursor: Any):
            desc = cursor.description
            return lambda values: Row(desc, values)

        conn = psycopg.connect(url, row_factory=row_factory, autocommit=False)
        wrapped = PgConnectionWrapper(conn)
        try:
            yield wrapped
            wrapped.commit()
        except Exception:
            wrapped.rollback()
            raise
        finally:
            wrapped.close()
    else:
        root = get_data_root()
        db_path = root / "collection.sqlite3"
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = lambda cur, row: Row(cur.description, row)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        wrapped = SqliteConnectionWrapper(conn)
        try:
            yield wrapped
            wrapped.commit()
        except Exception:
            wrapped.rollback()
            raise
        finally:
            wrapped.close()


def init_db() -> None:
    blob_type = "BYTEA" if is_postgres() else "BLOB"

    with db() as c:
        if is_postgres():
            c.executescript(f"""
            CREATE TABLE IF NOT EXISTS courses(
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS prompts(
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'vi-en',
                target_terms TEXT DEFAULT '[]',
                difficulty TEXT DEFAULT 'normal',
                category TEXT DEFAULT '',
                published INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS participants(
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                participant_code TEXT DEFAULT '',
                consent_version TEXT NOT NULL,
                consent_at INTEGER NOT NULL,
                survey TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recordings(
                id TEXT PRIMARY KEY,
                participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
                storage_key TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                mime TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                duration_seconds REAL DEFAULT 0.0,
                format TEXT DEFAULT 'webm',
                status TEXT NOT NULL DEFAULT 'pending_review',
                transcript TEXT,
                reviewer_notes TEXT DEFAULT '',
                reviewed_at INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                drive_sync_status TEXT DEFAULT 'pending',
                drive_file_id TEXT,
                UNIQUE(participant_id, prompt_id)
            );
            CREATE TABLE IF NOT EXISTS recording_audio(
                recording_id TEXT PRIMARY KEY,
                body {blob_type} NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drive_sync_jobs(
                id TEXT PRIMARY KEY,
                recording_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                drive_file_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            ALTER TABLE prompts ADD COLUMN IF NOT EXISTS target_terms TEXT DEFAULT '[]';
            ALTER TABLE prompts ADD COLUMN IF NOT EXISTS difficulty TEXT DEFAULT 'normal';
            ALTER TABLE prompts ADD COLUMN IF NOT EXISTS category TEXT DEFAULT '';
            ALTER TABLE prompts ADD COLUMN IF NOT EXISTS created_at INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE participants ADD COLUMN IF NOT EXISTS participant_code TEXT DEFAULT '';
            ALTER TABLE participants ADD COLUMN IF NOT EXISTS email TEXT DEFAULT '';
            ALTER TABLE participants ADD COLUMN IF NOT EXISTS google_id TEXT DEFAULT '';
            ALTER TABLE participants ADD COLUMN IF NOT EXISTS name TEXT DEFAULT '';
            ALTER TABLE participants ADD COLUMN IF NOT EXISTS onboarded INTEGER DEFAULT 0;
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS duration_seconds REAL DEFAULT 0.0;
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS format TEXT DEFAULT 'webm';
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS reviewer_notes TEXT DEFAULT '';
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS reviewed_at INTEGER DEFAULT 0;
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS drive_sync_status TEXT DEFAULT 'pending';
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS drive_file_id TEXT;
            ALTER TABLE recordings ADD COLUMN IF NOT EXISTS client_ip TEXT DEFAULT '';
            """)
        else:

            c.executescript(f"""
            CREATE TABLE IF NOT EXISTS courses(
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS prompts(
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'vi-en',
                target_terms TEXT DEFAULT '[]',
                difficulty TEXT DEFAULT 'normal',
                category TEXT DEFAULT '',
                published INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS participants(
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                participant_code TEXT DEFAULT '',
                consent_version TEXT NOT NULL,
                consent_at INTEGER NOT NULL,
                survey TEXT NOT NULL,
                email TEXT DEFAULT '',
                google_id TEXT DEFAULT '',
                name TEXT DEFAULT '',
                onboarded INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS recordings(
                id TEXT PRIMARY KEY,
                participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
                prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
                storage_key TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                mime TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                duration_seconds REAL DEFAULT 0.0,
                format TEXT DEFAULT 'webm',
                status TEXT NOT NULL DEFAULT 'pending_review',
                transcript TEXT,
                reviewer_notes TEXT DEFAULT '',
                reviewed_at INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                drive_sync_status TEXT DEFAULT 'pending',
                drive_file_id TEXT,
                UNIQUE(participant_id, prompt_id)
            );
            CREATE TABLE IF NOT EXISTS recording_audio(
                recording_id TEXT PRIMARY KEY,
                body {blob_type} NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drive_sync_jobs(
                id TEXT PRIMARY KEY,
                recording_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                drive_file_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """)

            # Safe migrations for SQLite
            prompts_cols = [r[1] for r in c.execute("PRAGMA table_info(prompts)").fetchall()]
            if "target_terms" not in prompts_cols:
                c.execute("ALTER TABLE prompts ADD COLUMN target_terms TEXT DEFAULT '[]'")
            if "difficulty" not in prompts_cols:
                c.execute("ALTER TABLE prompts ADD COLUMN difficulty TEXT DEFAULT 'normal'")
            if "category" not in prompts_cols:
                c.execute("ALTER TABLE prompts ADD COLUMN category TEXT DEFAULT ''")
            if "created_at" not in prompts_cols:
                c.execute("ALTER TABLE prompts ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")

            part_cols = [r[1] for r in c.execute("PRAGMA table_info(participants)").fetchall()]
            if "participant_code" not in part_cols:
                c.execute("ALTER TABLE participants ADD COLUMN participant_code TEXT DEFAULT ''")
            if "email" not in part_cols:
                c.execute("ALTER TABLE participants ADD COLUMN email TEXT DEFAULT ''")
            if "google_id" not in part_cols:
                c.execute("ALTER TABLE participants ADD COLUMN google_id TEXT DEFAULT ''")
            if "name" not in part_cols:
                c.execute("ALTER TABLE participants ADD COLUMN name TEXT DEFAULT ''")
            if "onboarded" not in part_cols:
                c.execute("ALTER TABLE participants ADD COLUMN onboarded INTEGER DEFAULT 0")

            rec_cols = [r[1] for r in c.execute("PRAGMA table_info(recordings)").fetchall()]
            if "duration_seconds" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN duration_seconds REAL DEFAULT 0.0")
            if "format" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN format TEXT DEFAULT 'webm'")
            if "reviewer_notes" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN reviewer_notes TEXT DEFAULT ''")
            if "reviewed_at" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN reviewed_at INTEGER DEFAULT 0")
            if "drive_sync_status" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN drive_sync_status TEXT DEFAULT 'pending'")
            if "drive_file_id" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN drive_file_id TEXT")
            if "client_ip" not in rec_cols:
                c.execute("ALTER TABLE recordings ADD COLUMN client_ip TEXT DEFAULT ''")


if __name__ == "__main__":
    init_db()
    print("Database initialization and migrations completed successfully.")
