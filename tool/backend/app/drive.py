"""Google Drive OAuth integration and storage client for LiemWhisper."""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

from cryptography.fernet import Fernet
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import requests

STATE_TTL_SECONDS = 600  # 10 minutes
COOKIE_NAME = "drive_oauth_verifier"


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _init_tables(db: Callable[[], Any]) -> None:
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS drive_oauth_state(
            state_hash TEXT PRIMARY KEY,
            cookie_hash TEXT NOT NULL,
            pkce_verifier TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS drive_oauth_handoff(
            ticket_hash TEXT PRIMARY KEY,
            expires_at INTEGER NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS drive_connection(
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            account_email TEXT,
            refresh_token_enc TEXT NOT NULL,
            folder_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)


def register_drive_routes(app: FastAPI, db: Callable[[], Any], admin: Callable[[str | None], None]) -> None:
    _init_tables(db)

    @app.get("/api/v1/admin/drive/status")
    def get_status(request: Request, x_admin_key: str | None = Header(None, alias="x-admin-key")):
        if request.query_params.get("key") or request.query_params.get("x_admin_key"):
            raise HTTPException(403, "Admin credential must be in header")
        admin(x_admin_key)

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        enc_key = os.getenv("TOKEN_ENCRYPTION_KEY")
        configured = bool(client_id and client_secret and redirect_uri and enc_key)

        with db() as c:
            row = c.execute("SELECT folder_id FROM drive_connection WHERE id='default'").fetchone()

        if row:
            return {
                "connected": True,
                "configured": configured,
                "folder_id": row["folder_id"] if row["folder_id"] else None,
            }
        return {
            "connected": False,
            "configured": configured,
            "folder_id": None,
        }

    @app.post("/api/v1/admin/drive/connect")
    def connect_drive(
        request: Request,
        response: Response,
        x_admin_key: str | None = Header(None, alias="x-admin-key"),
    ):
        if request.query_params.get("key") or request.query_params.get("x_admin_key"):
            raise HTTPException(403, "Admin credential must be in header")
        admin(x_admin_key)

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not client_id or not redirect_uri:
            raise HTTPException(500, "Google OAuth environment variables not configured")

        # The cross-site frontend fetch must not set the OAuth cookie. Hand off
        # via a short-lived, single-use capability, never an admin credential.
        ticket = secrets.token_urlsafe(32)
        now = int(time.time())
        with db() as c:
            c.execute("DELETE FROM drive_oauth_handoff WHERE expires_at <= ?", (now,))
            c.execute(
                "INSERT INTO drive_oauth_handoff (ticket_hash, expires_at) VALUES (?, ?)",
                (hashlib.sha256(ticket.encode()).hexdigest(), now + 120),
            )
        callback = urlsplit(redirect_uri)
        start_url = urlunsplit((callback.scheme, callback.netloc, "/api/v1/admin/drive/start", "", ticket))
        response.headers["Cache-Control"] = "no-store"
        return {"authorization_url": start_url}

    @app.get("/api/v1/admin/drive/start", response_class=HTMLResponse)
    def start_page():
        # Fragment stays out of HTTP logs and Referer; erase it before any I/O.
        nonce = secrets.token_urlsafe(24)
        content = """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<title>Liên kết Google Drive</title></head><body>
<p id="status">Đang chuẩn bị liên kết Google Drive…</p>
<noscript>Vui lòng bật JavaScript rồi kết nối lại từ trang quản trị.</noscript>
<script nonce="NONCE">
(async () => {
  const ticket = location.hash.slice(1);
  history.replaceState(null, '', location.pathname);
  try {
    if (!ticket) throw new Error('Phiên kết nối không hợp lệ. Hãy kết nối lại từ trang quản trị.');
    const response = await fetch(location.pathname, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticket})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Không thể tạo phiên kết nối.');
    location.replace(data.authorization_url);
  } catch (error) {
    document.getElementById('status').textContent = error.message;
  }
})();
</script></body></html>""".replace("NONCE", nonce)
        return HTMLResponse(content, headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                f"default-src 'none'; script-src 'nonce-{nonce}'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            ),
        })

    @app.post("/api/v1/admin/drive/start")
    def start_drive(request: Request, response: Response, ticket: str = Body(embed=True)):
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not client_id or not redirect_uri:
            raise HTTPException(500, "Google OAuth environment variables not configured")
        callback = urlsplit(redirect_uri)
        expected_origin = f"{callback.scheme}://{callback.netloc}"
        if request.headers.get("origin") not in (None, expected_origin):
            raise HTTPException(403, "OAuth start must be same-origin")
        if not ticket or len(ticket) > 128:
            raise HTTPException(400, "Invalid or expired OAuth handoff")
        now = int(time.time())
        with db() as c:
            # Atomic consume works across processes on both PostgreSQL and SQLite.
            handoff = c.execute(
                "DELETE FROM drive_oauth_handoff WHERE ticket_hash = ? RETURNING expires_at",
                (hashlib.sha256(ticket.encode()).hexdigest(),),
            ).fetchone()
        if not handoff or handoff["expires_at"] <= now:
            raise HTTPException(400, "Invalid or expired OAuth handoff; reconnect from admin")
        response.headers["Cache-Control"] = "no-store"
        raw_state = secrets.token_urlsafe(32)
        state_hash = hashlib.sha256(raw_state.encode("utf-8")).hexdigest()

        cookie_verifier = secrets.token_urlsafe(32)
        cookie_hash = hashlib.sha256(cookie_verifier.encode("utf-8")).hexdigest()

        pkce_verifier = secrets.token_urlsafe(48)
        pkce_challenge = _b64url_no_pad(hashlib.sha256(pkce_verifier.encode("utf-8")).digest())

        now = int(time.time())
        expires_at = now + STATE_TTL_SECONDS

        with db() as c:
            c.execute(
                "INSERT INTO drive_oauth_state (state_hash, cookie_hash, pkce_verifier, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(state_hash) DO UPDATE SET "
                "cookie_hash=excluded.cookie_hash, pkce_verifier=excluded.pkce_verifier, "
                "created_at=excluded.created_at, expires_at=excluded.expires_at",
                (state_hash, cookie_hash, pkce_verifier, now, expires_at),
            )

        response.set_cookie(
            key=COOKIE_NAME,
            value=cookie_verifier,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=STATE_TTL_SECONDS,
            path="/api/v1/admin/drive",
        )



        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "https://www.googleapis.com/auth/drive.file",
            "access_type": "offline",
            "prompt": "consent",
            "state": raw_state,
            "code_challenge": pkce_challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return {"authorization_url": auth_url}

    @app.get("/api/v1/admin/drive/callback")
    def oauth_callback(
        request: Request,
        response: Response,
        code: str | None = Query(None),
        state: str | None = Query(None),
        error: str | None = Query(None),
    ):
        if error:
            return HTMLResponse(
                "<!DOCTYPE html><html><body><h1>Authorization Failed</h1>"
                "<p>Google OAuth authorization was not granted.</p></body></html>",
                status_code=400,
            )

        if not code or not state:
            raise HTTPException(400, "Missing code or state parameter")

        cookie_verifier = request.cookies.get(COOKIE_NAME)
        if not cookie_verifier:
            raise HTTPException(400, "Missing CSRF verification cookie")

        state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        cookie_hash = hashlib.sha256(cookie_verifier.encode("utf-8")).hexdigest()
        now = int(time.time())

        with db() as c:
            row = c.execute(
                "SELECT state_hash, cookie_hash, pkce_verifier, expires_at FROM drive_oauth_state WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            c.execute("DELETE FROM drive_oauth_state WHERE state_hash = ?", (state_hash,))

        if not row:
            raise HTTPException(400, "Invalid or expired OAuth state")

        if now > row["expires_at"]:
            raise HTTPException(400, "OAuth state expired")

        if not secrets.compare_digest(row["cookie_hash"], cookie_hash):
            raise HTTPException(400, "CSRF cookie verification mismatch")

        pkce_verifier = row["pkce_verifier"]

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        enc_key = os.getenv("TOKEN_ENCRYPTION_KEY")
        if not client_id or not client_secret or not redirect_uri or not enc_key:
            raise HTTPException(500, "OAuth environment variables not configured")

        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": pkce_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        try:
            token_res = requests.request(
                "POST",
                "https://oauth2.googleapis.com/token",
                data=token_data,
                timeout=15.0,
            )
            token_res.raise_for_status()
            token_json = token_res.json()
        except Exception:
            raise HTTPException(502, "Failed to exchange authorization code with Google")

        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")
        if not access_token:
            raise HTTPException(502, "Missing access token in token exchange response")

        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            about_res = requests.request(
                "GET",
                "https://www.googleapis.com/drive/v3/about?fields=user(permissionId,emailAddress)",
                headers=headers,
                timeout=15.0,
            )
            about_res.raise_for_status()
            about_json = about_res.json()
            user_info = about_json.get("user", {})
            account_id = user_info.get("permissionId")
            account_email = user_info.get("emailAddress", "")
        except Exception:
            raise HTTPException(502, "Failed to query Google Drive account identity")

        if not account_id:
            raise HTTPException(502, "Unable to determine Drive account identifier")

        with db() as c:
            existing = c.execute(
                "SELECT account_id, folder_id, refresh_token_enc FROM drive_connection WHERE id = 'default'"
            ).fetchone()

        if existing and existing["account_id"] and existing["account_id"] != account_id:
            raise HTTPException(400, "Drive account mismatch with existing connected account")

        folder_id = existing["folder_id"] if existing and existing["folder_id"] else None
        if not folder_id:
            try:
                gen_res = requests.request(
                    "GET",
                    "https://www.googleapis.com/drive/v3/files/generateIds?count=1&space=drive",
                    headers=headers,
                    timeout=15.0,
                )
                gen_res.raise_for_status()
                folder_id = gen_res.json()["ids"][0]
            except Exception:
                raise HTTPException(502, "Failed to generate Drive folder ID")

            try:
                folder_body = {
                    "id": folder_id,
                    "name": "LiemWhisper Recordings",
                    "mimeType": "application/vnd.google-apps.folder",
                }
                create_res = requests.request(
                    "POST",
                    "https://www.googleapis.com/drive/v3/files",
                    headers={**headers, "Content-Type": "application/json"},
                    json=folder_body,
                    timeout=15.0,
                )
                create_res.raise_for_status()
            except Exception:
                raise HTTPException(502, "Failed to create Google Drive folder")

        if not refresh_token and existing:
            refresh_token_enc = existing["refresh_token_enc"]
        elif refresh_token:
            fernet = Fernet(enc_key.encode("utf-8"))
            refresh_token_enc = fernet.encrypt(refresh_token.encode("utf-8")).decode("utf-8")
        else:
            raise HTTPException(400, "No refresh token provided by Google. Re-consent required.")

        with db() as c:
            c.execute(
                "INSERT INTO drive_connection (id, account_id, account_email, refresh_token_enc, folder_id, created_at, updated_at) "
                "VALUES ('default', ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "account_id=excluded.account_id, account_email=excluded.account_email, "
                "refresh_token_enc=excluded.refresh_token_enc, folder_id=excluded.folder_id, "
                "updated_at=excluded.updated_at",
                (account_id, account_email, refresh_token_enc, folder_id, now, now),
            )

        html_content = (
            "<!DOCTYPE html>"
            "<html>"
            "<head><title>Google Drive Connected</title></head>"
            "<body>"
            "<h2>Google Drive Connected Successfully</h2>"
            "<p>Your personal Google Drive storage has been connected. You can now close this tab.</p>"
            "</body>"
            "</html>"
        )
        res = HTMLResponse(content=html_content, status_code=200)
        res.delete_cookie(COOKIE_NAME, path="/api/v1/admin/drive")
        return res


class GoogleDriveClient:
    def __init__(self, db: Callable[[], Any], folder_id: str, refresh_token_enc: str):
        self.db = db
        self.folder_id = folder_id
        self._refresh_token_enc = refresh_token_enc
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        enc_key = os.getenv("TOKEN_ENCRYPTION_KEY")
        if not client_id or not client_secret or not enc_key:
            raise RuntimeError("OAuth environment variables not configured")

        try:
            fernet = Fernet(enc_key.encode("utf-8"))
            refresh_token = fernet.decrypt(self._refresh_token_enc.encode("utf-8")).decode("utf-8")
        except Exception:
            raise RuntimeError("Failed to decrypt Google Drive refresh token")

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            res = requests.request("POST", "https://oauth2.googleapis.com/token", data=data, timeout=15.0)
            res.raise_for_status()
            token_json = res.json()
        except Exception:
            raise RuntimeError("Failed to refresh Google Drive access token")

        token = token_json.get("access_token")
        if not token:
            raise RuntimeError("Missing access token in token refresh response")

        expires_in = token_json.get("expires_in", 3600)
        self._access_token = token
        self._token_expires_at = now + expires_in
        return token

    def allocate_id(self) -> str:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = requests.request(
                "GET",
                "https://www.googleapis.com/drive/v3/files/generateIds?count=1&space=drive",
                headers=headers,
                timeout=15.0,
            )
            res.raise_for_status()
            return res.json()["ids"][0]
        except Exception:
            raise RuntimeError("Failed to allocate Google Drive file ID")

    def put(self, file_id: str, name: str, body: bytes, mime: str) -> None:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        # Idempotent check: see if file already exists
        existing_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,parents,trashed"
        try:
            check_res = requests.request("GET", existing_url, headers=headers, timeout=15.0)
            if check_res.status_code == 200:
                item = check_res.json()
                parents = item.get("parents", [])
                if parents and self.folder_id not in parents:
                    raise ValueError(f"File ID {file_id} belongs to an unrelated folder/location")
                patch_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
                upload_res = requests.request(
                    "PATCH",
                    patch_url,
                    headers={**headers, "Content-Type": mime},
                    data=body,
                    timeout=15.0,
                )
                upload_res.raise_for_status()
                return
            elif check_res.status_code != 404:
                check_res.raise_for_status()
        except ValueError:
            raise
        except Exception:
            pass

        boundary = f"=====boundary_{secrets.token_hex(16)}====="
        metadata = json.dumps({
            "id": file_id,
            "name": name,
            "parents": [self.folder_id],
            "mimeType": mime,
        }).encode("utf-8")

        payload = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode("utf-8") + metadata + (
            f"\r\n--{boundary}\r\n"
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + body + (
            f"\r\n--{boundary}--\r\n"
        ).encode("utf-8")

        upload_headers = {
            **headers,
            "Content-Type": f"multipart/related; boundary={boundary}",
        }
        upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
        res = requests.request("POST", upload_url, headers=upload_headers, data=payload, timeout=15.0)
        res.raise_for_status()

    def download(self, file_id: str) -> bytes:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        res = requests.request("GET", url, headers=headers, timeout=15.0)
        res.raise_for_status()
        return res.content

    def delete(self, file_id: str) -> None:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        res = requests.request("DELETE", url, headers=headers, timeout=15.0)
        if res.status_code == 404 or res.status_code in (200, 204):
            return
        res.raise_for_status()


def get_drive_client(db: Callable[[], Any]) -> GoogleDriveClient:
    with db() as c:
        row = c.execute(
            "SELECT folder_id, refresh_token_enc FROM drive_connection WHERE id = 'default'"
        ).fetchone()

    if not row or not row["folder_id"] or not row["refresh_token_enc"]:
        raise RuntimeError("Google Drive is not connected or folder_id is missing")

    return GoogleDriveClient(
        db=db,
        folder_id=row["folder_id"],
        refresh_token_enc=row["refresh_token_enc"],
    )
