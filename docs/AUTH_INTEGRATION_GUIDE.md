# Authentication & Authorization Integration Guide

## 1. Overview & Security Rationale

The previous authentication design had two primary security weaknesses:
1. **Raw Admin API Key Exposure**: The long-lived admin secret (`ADMIN_API_KEY`) was sent as a plaintext header (`x-admin-key`) on every administrative HTTP request, vulnerable to logging, caching, and network inspection. Furthermore, there was no brute-force protection or session revocation mechanism.
2. **Student-ID-Only Participant Impersonation**: Participants could authenticate using either their secret token or their public student code (`participant_code`, e.g. `SV_TEST_01`) via `WHERE token_hash=? OR (participant_code != '' AND LOWER(participant_code)=LOWER(?))`. This allowed anyone knowing a student's ID to impersonate them, view tasks, and upload recordings on their behalf without the secret token.

The standalone module `app.auth` (`tool/backend/app/auth.py`) resolves both vulnerabilities:
- **Session-Based Admin Auth**: Admin logs in via `/api/v1/auth/admin-login`. The server verifies credentials against configured strong secret with `secrets.compare_digest`, enforces database-backed brute-force rate-limiting (5 failed attempts triggers a 300-second cooldown), and issues an opaque random session token stored as a SHA-256 hash in `admin_sessions` with an 8-hour TTL.
- **Strict Session Enforcement**: Ordinary admin endpoints require valid session tokens via `require_admin(db, token)`. Raw admin API keys are strictly rejected with HTTP 403.
- **Admin Session Revocation**: Sessions can be revoked instantly via `revoke_admin(db, token)`.
- **Secret-Only Participant Auth**: Participant login and request authorization are restricted to SHA-256 token hash lookup via `participant_login(db, identifier)`. Student IDs (`participant_code`) are rejected with generic HTTP 401.

---

## 2. Module API & Signatures (`app.auth`)

```python
def setup_auth(db: Any) -> None:
    """Creates admin_sessions and auth_rate_limit tables if they do not exist."""

def admin_login(db: Any, supplied: str, expected: str, ttl_seconds: int = 28800) -> str:
    """Authenticates admin credentials, checks rate limits, and issues an 8-hour opaque session token."""

def require_admin(db: Any, token: str | None) -> None:
    """Validates session token. Raises HTTP 403 on invalid, expired, revoked, or raw keys; returns None on success."""

def revoke_admin(db: Any, token: str | None) -> bool:
    """Revokes an active session. Returns True if revoked, False otherwise."""

def participant_login(db: Any, identifier: str | None) -> dict[str, Any]:
    """Authenticates participant by secret token hash only. Rejects student code. No DB mutation."""
```

---

## 3. Main Integration Steps (`tool/backend/app/main.py`)

### Step 1: Import the auth module
```python
from app.auth import setup_auth, admin_login, require_admin, revoke_admin, participant_login
```

### Step 2: Initialize auth tables in `init_db()`
Add `setup_auth(db)` inside `init_db()`:
```python
def init_db():
    with db() as c:
        # existing table definitions...
    setup_auth(db)
```

### Step 3: Update `admin()` dependency
Replace raw key comparison with session validation:
```python
def admin(
    x_admin_session: str | None = Header(None),
    x_admin_key: str | None = Header(None),
    authorization: str | None = Header(None),
    key: str | None = Query(None)
):
    # Extract session token from x-admin-session or Authorization: Bearer <token>
    token = x_admin_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if not token:
        # Fallback to legacy headers for transitional compatibility checking,
        # but require_admin will strictly reject raw keys.
        token = x_admin_key or key
    
    require_admin(db, token)
```

### Step 4: Update `/api/v1/auth/admin-login` & add `/api/v1/auth/admin-logout`
```python
@app.post("/api/v1/auth/admin-login")
def auth_admin_login(data: AdminLoginInput):
    session_token = admin_login(db, data.key, ADMIN_KEY)
    return {
        "success": True,
        "role": "admin",
        "token": session_token,
        "message": "Đăng nhập quản trị thành công."
    }

@app.post("/api/v1/auth/admin-logout")
def auth_admin_logout(
    x_admin_session: str | None = Header(None),
    authorization: str | None = Header(None)
):
    token = x_admin_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    revoke_admin(db, token)
    return {"success": True, "message": "Đã đăng xuất thành công."}
```

### Step 5: Update `participant()` dependency & `/api/v1/auth/student-login`
Remove student-code fallback lookup:
```python
def participant(x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    supplied = x_participant_token or token
    row = participant_login(db, supplied)
    return row["id"]

@app.post("/api/v1/auth/student-login")
def auth_student_login(data: StudentLoginInput):
    row = participant_login(db, data.identifier)
    survey = json.loads(row["survey"]) if row.get("survey") else {}
    return {
        "success": True,
        "role": "student",
        "participant_id": row["id"],
        "participant_code": row["participant_code"],
        "token": data.identifier.strip(),
        "survey": survey
    }
```

---

## 4. Frontend & Client Integration

1. **Admin Console**:
   - Send `POST /api/v1/auth/admin-login` with `{ key: password }`.
   - Store the returned `token` in memory or session storage.
   - For all subsequent admin API requests, send header `Authorization: Bearer <token>` or `x-admin-session: <token>`.
   - On logout, call `POST /api/v1/auth/admin-logout` with the session header.

2. **Participant Portal**:
   - Students register once at `/api/v1/participants`, receiving a private `participant_token`.
   - On return visits, students log in using their private `participant_token`.
   - The public student code `participant_code` is displayed for UI greeting only and cannot be used to log in.
