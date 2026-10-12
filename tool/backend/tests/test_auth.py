"""Isolated unit tests for standalone secure auth module (app.auth)."""
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

# Ensure tool/backend is on python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.auth import setup_auth


@contextmanager
def in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def test_setup_auth_creates_required_tables():
    @contextmanager
    def db():
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Before setup, tables should not exist
    with db() as c:
        setup_auth(c)
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "admin_sessions" in tables
        assert "auth_rate_limit" in tables


def test_setup_auth_accepts_factory_callable():
    @contextmanager
    def db_factory():
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Pass the callable directly
    setup_auth(db_factory)


def test_admin_login_rejects_weak_or_default_expected_secret():
    from app.auth import admin_login

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    # Disallowed defaults
    with pytest.raises(ValueError, match="strong non-default"):
        admin_login(conn, "any_attempt", "liemwhisper-admin-secret-2026")

    with pytest.raises(ValueError, match="strong non-default"):
        admin_login(conn, "any_attempt", "admin")

    with pytest.raises(ValueError, match="strong non-default"):
        admin_login(conn, "any_attempt", "password")

    with pytest.raises(ValueError, match="strong non-default"):
        admin_login(conn, "any_attempt", "short-secret")


def test_admin_login_success_creates_hashed_session_with_8h_ttl():
    import hashlib
    import time
    from app.auth import admin_login

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    token = admin_login(conn, strong_secret, strong_secret)

    assert isinstance(token, str)
    assert len(token) >= 32
    # Verify token is opaque and not equal to the admin secret
    assert token != strong_secret

    # Check database storage
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = conn.execute("SELECT * FROM admin_sessions WHERE token_hash=?", (token_hash,)).fetchone()
    assert row is not None
    assert row["token_hash"] == token_hash
    assert row["revoked_at"] is None

    now = int(time.time())
    # Created around now
    assert abs(row["created_at"] - now) <= 5
    # TTL 8 hours = 28800 seconds
    assert abs(row["expires_at"] - (row["created_at"] + 8 * 3600)) <= 2

    # Verify raw token is NOT stored anywhere in the table
    all_rows = conn.execute("SELECT * FROM admin_sessions").fetchall()
    for r in all_rows:
        assert token != r["token_hash"]
        assert strong_secret != r["token_hash"]


def test_admin_login_rejects_oversized_input():
    from app.auth import admin_login
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    with pytest.raises(HTTPException) as exc_info:
        admin_login(conn, "A" * 2048, strong_secret)

    assert exc_info.value.status_code == 400
    assert "exceeds maximum" in exc_info.value.detail.lower()


def test_admin_login_rate_limiting_and_cooldown():
    from app.auth import admin_login
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    wrong_secret = "synthetic-wrong-admin-pass-xyz-99999"

    # First 5 failed attempts should return HTTP 401
    for i in range(5):
        with pytest.raises(HTTPException) as exc_info:
            admin_login(conn, wrong_secret, strong_secret)
        assert exc_info.value.status_code == 401

        # Check DB recorded failed count
        row = conn.execute("SELECT * FROM auth_rate_limit WHERE rate_key='admin_login'").fetchone()
        assert row is not None
        assert row["failed_count"] == i + 1

    # 6th attempt should be blocked with HTTP 429 Cooldown
    with pytest.raises(HTTPException) as exc_info:
        admin_login(conn, wrong_secret, strong_secret)
    assert exc_info.value.status_code == 429
    assert "cooldown" in exc_info.value.detail.lower() or "too many" in exc_info.value.detail.lower()

    # Even right password should be blocked during cooldown
    with pytest.raises(HTTPException) as exc_info:
        admin_login(conn, strong_secret, strong_secret)
    assert exc_info.value.status_code == 429


def test_admin_login_success_resets_failed_counter():
    from app.auth import admin_login
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    wrong_secret = "synthetic-wrong-admin-pass-xyz-99999"

    # Make 3 failed attempts
    for _ in range(3):
        with pytest.raises(HTTPException):
            admin_login(conn, wrong_secret, strong_secret)

    row = conn.execute("SELECT failed_count FROM auth_rate_limit WHERE rate_key='admin_login'").fetchone()
    assert row["failed_count"] == 3

    # Now succeed
    token = admin_login(conn, strong_secret, strong_secret)
    assert token

    # Check that failed_count was reset to 0
    row_after = conn.execute("SELECT failed_count, locked_until FROM auth_rate_limit WHERE rate_key='admin_login'").fetchone()
    assert row_after["failed_count"] == 0
    assert row_after["locked_until"] == 0


def test_require_admin_accepts_valid_session():
    from app.auth import admin_login, require_admin

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    token = admin_login(conn, strong_secret, strong_secret)

    # Should succeed without raising exception and return None
    result = require_admin(conn, token)
    assert result is None


def test_require_admin_rejects_missing_or_invalid_session():
    from app.auth import require_admin
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    # Missing / None
    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, None)
    assert exc_info.value.status_code == 403

    # Empty string
    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, "")
    assert exc_info.value.status_code == 403

    # Fake / invalid session token
    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, "totally-fabricated-invalid-session-token-xyz")
    assert exc_info.value.status_code == 403


def test_require_admin_rejects_raw_admin_key():
    from app.auth import admin_login, require_admin
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    admin_login(conn, strong_secret, strong_secret)

    # Passing the raw admin key directly MUST be rejected with HTTP 403
    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, strong_secret)
    assert exc_info.value.status_code == 403


def test_require_admin_rejects_expired_session():
    import time
    from app.auth import admin_login, require_admin
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    # Create session with negative or past TTL (-10 seconds)
    token = admin_login(conn, strong_secret, strong_secret, ttl_seconds=-10)

    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, token)
    assert exc_info.value.status_code == 403
    assert "expired" in exc_info.value.detail.lower()


def test_require_admin_rejects_revoked_session_manually_revoked():
    import hashlib
    import time
    from app.auth import admin_login, require_admin
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    token = admin_login(conn, strong_secret, strong_secret)

    # Manually mark revoked in DB
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn.execute("UPDATE admin_sessions SET revoked_at = ? WHERE token_hash = ?", (int(time.time()), token_hash))

    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, token)
    assert exc_info.value.status_code == 403
    assert "revoked" in exc_info.value.detail.lower()


def test_revoke_admin_invalidates_session():
    from app.auth import admin_login, require_admin, revoke_admin
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    setup_auth(conn)

    strong_secret = "synthetic-strong-admin-pass-xyz-12345"
    token = admin_login(conn, strong_secret, strong_secret)

    # Valid before revocation
    assert require_admin(conn, token) is None

    # Revoke session
    revoked = revoke_admin(conn, token)
    assert revoked is True

    # Revoking again returns False (idempotent / already revoked)
    assert revoke_admin(conn, token) is False

    # Now require_admin must raise HTTP 403
    with pytest.raises(HTTPException) as exc_info:
        require_admin(conn, token)
    assert exc_info.value.status_code == 403
    assert "revoked" in exc_info.value.detail.lower()

    # Revoking invalid or None token returns False
    assert revoke_admin(conn, "non-existent-token") is False
    assert revoke_admin(conn, None) is False


def test_participant_login_with_valid_secret_token():
    import hashlib
    from app.auth import participant_login

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE participants(
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            participant_code TEXT DEFAULT '',
            consent_version TEXT NOT NULL,
            consent_at INTEGER NOT NULL,
            survey TEXT NOT NULL
        )
    """)

    raw_token = "synthetic-participant-secret-token-xyz"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO participants VALUES (?, ?, ?, ?, ?, ?)",
        ("p_123", token_hash, "SV_2026_01", "v1.0", 1700000000, '{"familiarity":"intermediate"}')
    )

    data = participant_login(conn, raw_token)
    assert data["id"] == "p_123"
    assert data["participant_code"] == "SV_2026_01"
    assert data["consent_version"] == "v1.0"
    assert data["consent_at"] == 1700000000


def test_participant_login_rejects_student_code_only():
    import hashlib
    from app.auth import participant_login
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE participants(
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            participant_code TEXT DEFAULT '',
            consent_version TEXT NOT NULL,
            consent_at INTEGER NOT NULL,
            survey TEXT NOT NULL
        )
    """)

    raw_token = "synthetic-participant-secret-token-xyz"
    student_id = "SV_2026_01"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO participants VALUES (?, ?, ?, ?, ?, ?)",
        ("p_123", token_hash, student_id, "v1.0", 1700000000, "{}")
    )

    # Attempting to authenticate using student ID alone MUST FAIL with generic HTTP 401
    with pytest.raises(HTTPException) as exc_info:
        participant_login(conn, student_id)
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


def test_participant_login_no_mutation_and_generic_401():
    from app.auth import participant_login
    from fastapi import HTTPException

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE participants(
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            participant_code TEXT DEFAULT '',
            consent_version TEXT NOT NULL,
            consent_at INTEGER NOT NULL,
            survey TEXT NOT NULL
        )
    """)

    # Non-existent token raises generic 401
    with pytest.raises(HTTPException) as exc_info:
        participant_login(conn, "synthetic-non-existent-token")
    assert exc_info.value.status_code == 401

    # Verify no records created or altered
    count = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
    assert count == 0
