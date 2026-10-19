"""Standalone secure authentication module for LiemWhisper.

Provides session-based admin auth, brute-force rate-limiting cooldown,
and secret-only participant authentication. Portable across SQLite & PostgreSQL.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator

try:
    from fastapi import HTTPException
except ImportError:
    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")


@contextmanager
def _get_db(db: Any) -> Generator[Any, None, None]:
    """Normalize db input whether passed as contextmanager callable, contextmanager instance, or connection."""
    if hasattr(db, "execute"):
        # db is already an active connection or cursor
        yield db
    elif callable(db):
        cm = db()
        if hasattr(cm, "__enter__"):
            with cm as c:
                yield c
        else:
            yield cm
    elif hasattr(db, "__enter__"):
        with db as c:
            yield c
    else:
        yield db


def setup_auth(db: Any) -> None:
    """Create authentication and rate-limiting tables if they do not exist."""
    with _get_db(db) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER DEFAULT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS auth_rate_limit (
                rate_key TEXT PRIMARY KEY,
                failed_count INTEGER NOT NULL DEFAULT 0,
                last_failed_at INTEGER NOT NULL DEFAULT 0,
                locked_until INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_emails (
                email TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                created_by TEXT DEFAULT 'system'
            )
        """)
        if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
            c.commit()


MIN_SECRET_LENGTH = 16
DISALLOWED_DEFAULTS = frozenset({
    "liemwhisper-admin-secret-2026",
    "admin",
    "password",
    "secret",
    "changeme",
    "12345678",
    "1234567890",
    "admin123",
    "root",
    "default",
})


def _validate_expected_admin_key(expected: str) -> None:
    if not expected or not isinstance(expected, str):
        raise ValueError("Admin expected secret must be configured with a strong non-default string.")
    if len(expected.strip()) < MIN_SECRET_LENGTH:
        raise ValueError(f"Admin expected secret must be configured with a strong non-default secret (at least {MIN_SECRET_LENGTH} characters).")
    if expected.strip().lower() in DISALLOWED_DEFAULTS:
        raise ValueError("Admin expected secret must be configured with a strong non-default secret.")


DEFAULT_SESSION_TTL_SECONDS = 8 * 3600  # 8 hours
MAX_INPUT_LENGTH = 1024
MAX_FAILED_ATTEMPTS = 5
COOLDOWN_SECONDS = 300  # 5 minutes cooldown after max failed attempts


def _check_rate_limit_pre_login(c: Any, key: str = "admin_login") -> None:
    now = int(time.time())
    row = c.execute(
        "SELECT failed_count, last_failed_at, locked_until FROM auth_rate_limit WHERE rate_key = ?",
        (key,)
    ).fetchone()

    if not row:
        c.execute(
            "INSERT INTO auth_rate_limit (rate_key, failed_count, last_failed_at, locked_until) VALUES (?, ?, ?, ?)",
            (key, 0, 0, 0)
        )
        return

    locked_until = int(row["locked_until"])
    if locked_until > now:
        remaining = locked_until - now
        raise HTTPException(429, f"Too many failed login attempts. Cooldown active for {remaining} seconds.")

    failed_count = int(row["failed_count"])
    last_failed_at = int(row["last_failed_at"])
    # If cooldown window passed since last failure, auto-reset counter
    if failed_count > 0 and (now - last_failed_at) > COOLDOWN_SECONDS:
        c.execute("UPDATE auth_rate_limit SET failed_count = 0, locked_until = 0 WHERE rate_key = ?", (key,))


def _record_failed_attempt(c: Any, key: str = "admin_login") -> None:
    now = int(time.time())
    row = c.execute(
        "SELECT failed_count FROM auth_rate_limit WHERE rate_key = ?",
        (key,)
    ).fetchone()

    current_count = int(row["failed_count"]) if row else 0
    new_count = current_count + 1
    new_locked = (now + COOLDOWN_SECONDS) if new_count >= MAX_FAILED_ATTEMPTS else 0

    if row:
        c.execute(
            "UPDATE auth_rate_limit SET failed_count = ?, last_failed_at = ?, locked_until = ? WHERE rate_key = ?",
            (new_count, now, new_locked, key)
        )
    else:
        c.execute(
            "INSERT INTO auth_rate_limit (rate_key, failed_count, last_failed_at, locked_until) VALUES (?, ?, ?, ?)",
            (key, new_count, now, new_locked)
        )


def _reset_rate_limit(c: Any, key: str = "admin_login") -> None:
    c.execute(
        "UPDATE auth_rate_limit SET failed_count = 0, locked_until = 0 WHERE rate_key = ?",
        (key,)
    )


def admin_login(db: Any, supplied: str, expected: str, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> str:
    _validate_expected_admin_key(expected)
    if not supplied or not isinstance(supplied, str):
        raise HTTPException(401, "Invalid admin credentials")
    if len(supplied) > MAX_INPUT_LENGTH:
        raise HTTPException(400, "Supplied credential exceeds maximum allowed length")

    with _get_db(db) as c:
        _check_rate_limit_pre_login(c, "admin_login")

        if not secrets.compare_digest(supplied, expected):
            _record_failed_attempt(c, "admin_login")
            if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
                c.commit()
            raise HTTPException(401, "Invalid admin credentials")

        # Credentials valid: reset rate limit and create session
        _reset_rate_limit(c, "admin_login")
        return create_admin_session(c, ttl_seconds)


def create_admin_session(db: Any, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> str:
    """Create a new admin session token with SHA-256 hash in database."""
    now = int(time.time())
    expires_at = now + ttl_seconds
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    with _get_db(db) as c:
        c.execute(
            "INSERT INTO admin_sessions (token_hash, created_at, expires_at, revoked_at) VALUES (?, ?, ?, NULL)",
            (token_hash, now, expires_at)
        )
        if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
            c.commit()

    return raw_token


def require_admin(db: Any, token: str | None) -> None:
    """Validate admin session token. Raises HTTPException(403) on failure; returns None on success.
    
    Session-only: raw admin API key is strictly rejected.
    """
    if not token or not isinstance(token, str):
        raise HTTPException(403, "Admin session token required")

    clean_token = token.strip()
    if not clean_token or len(clean_token) > MAX_INPUT_LENGTH:
        raise HTTPException(403, "Invalid admin session")

    token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
    now = int(time.time())

    with _get_db(db) as c:
        row = c.execute(
            "SELECT token_hash, created_at, expires_at, revoked_at FROM admin_sessions WHERE token_hash = ?",
            (token_hash,)
        ).fetchone()

        if not row:
            raise HTTPException(403, "Invalid admin session")

        if row["revoked_at"] is not None:
            raise HTTPException(403, "Admin session has been revoked")

        if int(row["expires_at"]) <= now:
            raise HTTPException(403, "Admin session has expired")

    return None


def revoke_admin(db: Any, token: str | None) -> bool:
    """Revoke an active admin session. Returns True if revoked, False otherwise."""
    if not token or not isinstance(token, str):
        return False

    clean_token = token.strip()
    if not clean_token or len(clean_token) > MAX_INPUT_LENGTH:
        return False

    token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
    now = int(time.time())

    with _get_db(db) as c:
        cursor = c.execute(
            "UPDATE admin_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now, token_hash)
        )
        rowcount = getattr(cursor, "rowcount", 0)
        if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
            c.commit()
        return bool(rowcount and rowcount > 0)


def participant_login(db: Any, identifier: str | None) -> dict[str, Any]:
    """Authenticate participant using secret token hash only.
    
    Student ID / participant_code lookup is strictly rejected to prevent unauthorized access.
    Returns existing participant row fields without database mutation.
    """
    if not identifier or not isinstance(identifier, str):
        raise HTTPException(401, "Invalid participant credentials")

    clean_identifier = identifier.strip()
    if not clean_identifier or len(clean_identifier) > MAX_INPUT_LENGTH:
        raise HTTPException(401, "Invalid participant credentials")

    token_hash = hashlib.sha256(clean_identifier.encode("utf-8")).hexdigest()

    with _get_db(db) as c:
        row = c.execute(
            """SELECT id, participant_code, consent_version, consent_at, survey
               FROM participants
               WHERE token_hash = ?""",
            (token_hash,)
        ).fetchone()

        if not row:
            raise HTTPException(401, "Invalid participant credentials")

        return dict(row)


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def is_admin_email(db: Any, email: str | None) -> bool:
    """Check if an email address has admin privileges via env or database."""
    if not email or not isinstance(email, str):
        return False
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        return False

    env_emails = os.getenv("ADMIN_EMAILS", "")
    if env_emails:
        allowed = {e.strip().lower() for e in env_emails.split(",") if e.strip()}
        if clean_email in allowed:
            return True

    with _get_db(db) as c:
        row = c.execute(
            "SELECT 1 FROM admin_emails WHERE LOWER(email) = ?",
            (clean_email,)
        ).fetchone()
        if row:
            return True

    return False


def add_admin_email(db: Any, email: str, created_by: str = "admin") -> dict[str, Any]:
    """Grant admin role to an email address (e.g. Gmail)."""
    if not email or not isinstance(email, str):
        raise HTTPException(400, "Vui lòng nhập địa chỉ email hợp lệ.")

    clean_email = email.strip().lower()
    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(400, "Định dạng email không hợp lệ (ví dụ: nguyenvanan@gmail.com).")

    now = int(time.time())
    with _get_db(db) as c:
        row = c.execute(
            "SELECT email FROM admin_emails WHERE LOWER(email) = ?",
            (clean_email,)
        ).fetchone()
        if row:
            raise HTTPException(400, f"Email '{clean_email}' đã có quyền Quản trị viên.")

        c.execute(
            "INSERT INTO admin_emails (email, created_at, created_by) VALUES (?, ?, ?)",
            (clean_email, now, created_by)
        )
        try:
            c.execute("UPDATE participants SET is_admin = 1 WHERE LOWER(email) = ?", (clean_email,))
        except Exception:
            pass

        if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
            c.commit()

    return {"email": clean_email, "created_at": now, "created_by": created_by}


def remove_admin_email(db: Any, email: str) -> bool:
    """Revoke admin role from an email address."""
    if not email or not isinstance(email, str):
        return False

    clean_email = email.strip().lower()
    env_emails = os.getenv("ADMIN_EMAILS", "")
    if env_emails:
        allowed = {e.strip().lower() for e in env_emails.split(",") if e.strip()}
        if clean_email in allowed:
            raise HTTPException(400, f"Email '{clean_email}' được cấu hình cố định trong biến môi trường ADMIN_EMAILS, không thể xóa.")

    with _get_db(db) as c:
        cursor = c.execute(
            "DELETE FROM admin_emails WHERE LOWER(email) = ?",
            (clean_email,)
        )
        try:
            c.execute("UPDATE participants SET is_admin = 0 WHERE LOWER(email) = ?", (clean_email,))
        except Exception:
            pass

        rowcount = getattr(cursor, "rowcount", 0)
        if hasattr(c, "commit") and not hasattr(db, "__enter__") and not callable(db):
            c.commit()

    return bool(rowcount and rowcount > 0)


def list_admin_emails(db: Any) -> list[dict[str, Any]]:
    """Return all granted admin emails merged with environment configured admins."""
    admins_map: dict[str, dict[str, Any]] = {}

    with _get_db(db) as c:
        rows = c.execute(
            "SELECT email, created_at, created_by FROM admin_emails ORDER BY created_at ASC"
        ).fetchall()
        for r in rows:
            em = r["email"].strip().lower()
            part = c.execute(
                "SELECT id, participant_code, name, onboarded FROM participants WHERE LOWER(email) = ?",
                (em,)
            ).fetchone()
            admins_map[em] = {
                "email": em,
                "created_at": int(r["created_at"]),
                "created_by": r["created_by"] or "admin",
                "linked": bool(part),
                "name": (part["name"] if part and part["name"] else "") or (part["participant_code"] if part else ""),
                "is_env": False,
            }

    env_emails = os.getenv("ADMIN_EMAILS", "")
    if env_emails:
        for e in env_emails.split(","):
            em = e.strip().lower()
            if em and em not in admins_map:
                with _get_db(db) as c:
                    part = c.execute(
                        "SELECT id, participant_code, name FROM participants WHERE LOWER(email) = ?",
                        (em,)
                    ).fetchone()
                admins_map[em] = {
                    "email": em,
                    "created_at": 0,
                    "created_by": "env (ADMIN_EMAILS)",
                    "linked": bool(part),
                    "name": (part["name"] if part and part["name"] else "") or (part["participant_code"] if part else ""),
                    "is_env": True,
                }

    return list(admins_map.values())
