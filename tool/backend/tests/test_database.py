"""Tests for database adapter: qmark translation, dual mapping/index Row, SQLite and PostgreSQL support."""
import os
import pytest

from app.database import db, init_db, qmark_to_pyformat, Row


def test_qmark_to_pyformat():
    sql = "SELECT id, 'hello? world' as greeting FROM users WHERE name = ? AND age > ? AND note = '??'"
    converted = qmark_to_pyformat(sql)
    assert converted == "SELECT id, 'hello? world' as greeting FROM users WHERE name = %s AND age > %s AND note = '??'"


def test_row_mapping_and_index():
    desc = [("id",), ("name",), ("score",)]
    values = ("u1", "Alice", 98.5)
    row = Row(desc, values)

    # Key / mapping access
    assert row["id"] == "u1"
    assert row["name"] == "Alice"
    assert row["score"] == 98.5
    assert row.get("missing", "default") == "default"
    assert "name" in row

    # Integer indexing access
    assert row[0] == "u1"
    assert row[1] == "Alice"
    assert row[2] == 98.5

    # Conversion to dict
    d = dict(row)
    assert d == {"id": "u1", "name": "Alice", "score": 98.5}


def test_sqlite_db_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    init_db()

    with db() as c:
        c.execute("INSERT INTO courses(id, title, created_at) VALUES (?, ?, ?)", ("c1", "Course 1", 100))
        row = c.execute("SELECT id, title, created_at FROM courses WHERE id = ?", ("c1",)).fetchone()

        assert row is not None
        assert row["title"] == "Course 1"
        assert row[0] == "c1"
        assert row[1] == "Course 1"
        assert row[2] == 100
        assert dict(row) == {"id": "c1", "title": "Course 1", "created_at": 100}

        count = c.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        assert count == 1
