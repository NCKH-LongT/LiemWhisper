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


def is_drive_connected(db_conn_or_factory: Any) -> bool:
    try:
        if callable(db_conn_or_factory):
            with db_conn_or_factory() as c:
                row = c.execute("SELECT folder_id, refresh_token_enc FROM drive_connection WHERE id='default'").fetchone()
        else:
            row = db_conn_or_factory.execute("SELECT folder_id, refresh_token_enc FROM drive_connection WHERE id='default'").fetchone()
        return bool(row and row["folder_id"] and row["refresh_token_enc"])
    except Exception:
        return False


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

        total_recordings = 0
        synced_count = 0
        pending_count = 0
        failed_count = 0

        include_counts = request.query_params.get("counts") == "1" or request.query_params.get("include_counts") == "1"

        with db() as c:
            row = c.execute("SELECT folder_id FROM drive_connection WHERE id='default'").fetchone()
            if include_counts:
                try:
                    counts = c.execute("""
                        SELECT
                            COUNT(*) AS total,
                            COUNT(CASE WHEN drive_sync_status = 'synced' THEN 1 END) AS synced,
                            COUNT(CASE WHEN drive_sync_status = 'pending' THEN 1 END) AS pending,
                            COUNT(CASE WHEN drive_sync_status = 'failed' THEN 1 END) AS failed
                        FROM recordings
                    """).fetchone()
                    if counts:
                        total_recordings = counts["total"]
                        synced_count = counts["synced"]
                        pending_count = counts["pending"]
                        failed_count = counts["failed"]
                except Exception:
                    pass

        res = {
            "connected": bool(row),
            "configured": configured,
            "folder_id": row["folder_id"] if row and row["folder_id"] else None,
        }
        if include_counts:
            res.update({
                "total_recordings": total_recordings,
                "synced_count": synced_count,
                "pending_count": pending_count,
                "failed_count": failed_count,
            })
        return res

    @app.post("/api/v1/admin/drive/sync")
    def trigger_drive_sync(
        request: Request,
        x_admin_key: str | None = Header(None, alias="x-admin-key"),
    ):
        if request.query_params.get("key") or request.query_params.get("x_admin_key"):
            raise HTTPException(403, "Admin credential must be in header")
        admin(x_admin_key)

        from app.worker import backfill_unsynced_drive_jobs, process_all_outbox
        enqueued = backfill_unsynced_drive_jobs(db)
        processed = process_all_outbox(db, max_total=50)

        with db() as c:
            counts = c.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN drive_sync_status = 'synced' THEN 1 END) AS synced,
                    COUNT(CASE WHEN drive_sync_status = 'pending' THEN 1 END) AS pending,
                    COUNT(CASE WHEN drive_sync_status = 'failed' THEN 1 END) AS failed
                FROM recordings
            """).fetchone()

        return {
            "status": "ok",
            "enqueued": enqueued,
            "processed": processed,
            "total_recordings": counts["total"] if counts else 0,
            "synced_count": counts["synced"] if counts else 0,
            "pending_count": counts["pending"] if counts else 0,
            "failed_count": counts["failed"] if counts else 0,
            "message": f"Đã đồng bộ {processed} bản ghi lên Google Drive thành công"
        }

    @app.post("/api/v1/admin/drive/cleanup-duplicates")
    def trigger_drive_cleanup_duplicates(
        request: Request,
        x_admin_key: str | None = Header(None, alias="x-admin-key"),
    ):
        if request.query_params.get("key") or request.query_params.get("x_admin_key"):
            raise HTTPException(403, "Admin credential must be in header")
        admin(x_admin_key)
        from app.drive_cleanup_job import start_cleanup
        try:
            return JSONResponse(start_cleanup(db), status_code=202)
        except Exception as exc:
            logging.getLogger(__name__).exception("Drive cleanup failed")
            raise HTTPException(502, "Không thể hoàn tất sắp xếp Drive. Dữ liệu chưa xác minh được giữ lại.") from exc

    @app.get("/api/v1/admin/drive/cleanup-status")
    def get_cleanup_status(x_admin_key: str | None = Header(None, alias="x-admin-key")):
        admin(x_admin_key)
        from app.drive_cleanup_job import cleanup_status
        return cleanup_status(db)

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

        # Trigger immediate background sync for any existing recordings
        if os.getenv("TESTING") != "true":
            def _bg_sync():
                try:
                    from app.worker import backfill_unsynced_drive_jobs, process_all_outbox
                    backfill_unsynced_drive_jobs(db)
                    process_all_outbox(db)
                except Exception as e:
                    logging.getLogger(__name__).warning("Initial drive sync failed: %s", e)
            import threading
            threading.Thread(target=_bg_sync, daemon=True).start()

        web_public_url = (os.getenv("WEB_PUBLIC_URL") or "").strip().rstrip("/")
        target_url = web_public_url if web_public_url.startswith(("http://", "https://")) else ""
        nonce = secrets.token_urlsafe(24)
        target_json = json.dumps(target_url)
        refresh_meta = f'<meta http-equiv="refresh" content="2;url={target_url}">' if target_url else ""
        action_btn = (
            f'<a href="{target_url}" class="btn">Quay về trang quản trị</a>'
            if target_url
            else '<button onclick="window.close()" class="btn">Đóng cửa sổ</button>'
        )

        html_content = (
            "<!DOCTYPE html>"
            '<html lang="vi">'
            "<head>"
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "<title>Google Drive đã kết nối</title>"
            f"{refresh_meta}"
            "<style>"
            "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#fafafa;color:#09090b;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px;box-sizing:border-box}"
            ".card{background:#ffffff;border:1px solid #e4e4e7;border-radius:12px;padding:32px;max-width:440px;width:100%;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.05)}"
            ".badge{display:inline-block;background:#dcfce7;color:#166534;padding:4px 12px;border-radius:9999px;font-size:12px;font-weight:600;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.04em}"
            "h2{margin:0 0 8px;font-size:18px;font-weight:700}"
            "p{color:#52525b;font-size:14px;line-height:1.5;margin:0 0 20px}"
            ".btn{display:inline-block;padding:10px 18px;background:#09090b;color:#ffffff;text-decoration:none;border-radius:8px;font-size:13px;font-weight:500;border:none;cursor:pointer}"
            "</style>"
            "</head>"
            "<body>"
            '<div class="card">'
            '<div class="badge">Đã kết nối</div>'
            "<h2>Google Drive đã liên kết thành công</h2>"
            "<p>Thư mục lưu trữ LiemWhisper đã sẵn sàng. Cửa sổ này sẽ tự động đóng.</p>"
            f"{action_btn}"
            "</div>"
            f'<script nonce="{nonce}">'
            "(() => {"
            f"  const targetUrl = {target_json};"
            "  try {"
            "    if (window.opener) {"
            '      window.opener.postMessage({ type: "DRIVE_CONNECTED" }, "*");'
            "    }"
            "  } catch (e) {}"
            "  setTimeout(() => {"
            "    try { window.close(); } catch (e) {}"
            "    if (!window.opener && targetUrl) {"
            "      window.location.replace(targetUrl);"
            "    }"
            "  }, 1200);"
            "})();"
            "</script>"
            "</body>"
            "</html>"
        )
        res = HTMLResponse(
            content=html_content,
            status_code=200,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; "
                    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
                ),
            },
        )
        res.delete_cookie(COOKIE_NAME, path="/api/v1/admin/drive")
        return res


class GoogleDriveClient:
    def __init__(self, db: Callable[[], Any], folder_id: str, refresh_token_enc: str):
        self.db = db
        self.folder_id = folder_id
        self._refresh_token_enc = refresh_token_enc
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._subfolder_cache: dict[str, str] = {}

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

    def put(self, file_id: str, name: str, body: bytes, mime: str, parent_id: str | None = None) -> str:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        target_folder = parent_id or self.folder_id

        # 1. Idempotent check: see if file with file_id already exists in Drive
        existing_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,parents,trashed"
        try:
            check_res = requests.request("GET", existing_url, headers=headers, timeout=15.0)
            if check_res.status_code == 200:
                item = check_res.json()
                if item.get("trashed"):
                    raise RuntimeError("Recording file is in the Drive trash; restore it before retrying")
                patch_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
                upload_res = requests.request(
                    "PATCH",
                    patch_url,
                    headers={**headers, "Content-Type": mime},
                    data=body,
                    timeout=15.0,
                )
                upload_res.raise_for_status()

                # Update metadata (name & parents) if needed
                patch_meta = {}
                if item.get("name") != name:
                    patch_meta["name"] = name
                parents = item.get("parents", [])
                move_params = {}
                if target_folder not in parents:
                    move_params["addParents"] = target_folder
                    if parents:
                        move_params["removeParents"] = ",".join(parents)
                if patch_meta or move_params:
                    meta_res = requests.request(
                        "PATCH",
                        f"https://www.googleapis.com/drive/v3/files/{file_id}",
                        headers={**headers, "Content-Type": "application/json"},
                        params=move_params,
                        json=patch_meta,
                        timeout=15.0
                    )
                    meta_res.raise_for_status()
                return file_id
            elif check_res.status_code != 404:
                check_res.raise_for_status()
        except Exception:
            # A timeout/403/5xx is not evidence that the object is absent.
            # Retry the same persisted ID instead of searching/deleting by name.
            raise

        boundary = f"=====boundary_{secrets.token_hex(16)}====="
        metadata = json.dumps({
            "id": file_id,
            "name": name,
            "parents": [target_folder],
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
        return file_id

    def ensure_folder(self, folder_id: str, name: str) -> None:
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}
        url = f"https://www.googleapis.com/drive/v3/files/{folder_id}"
        res = requests.request("GET", url, headers=headers, params={"fields": "id,name,mimeType,trashed,parents"}, timeout=15)
        if res.status_code == 404:
            created = requests.request(
                "POST", "https://www.googleapis.com/drive/v3/files",
                headers=headers, json={"id": folder_id, "name": name,
                    "parents": [self.folder_id], "mimeType": "application/vnd.google-apps.folder"},
                timeout=15,
            )
            created.raise_for_status()
            return
        res.raise_for_status()
        item = res.json()
        if item.get("trashed") or item.get("mimeType") != "application/vnd.google-apps.folder":
            raise RuntimeError("Configured participant folder is unavailable")
        if self.folder_id not in item.get("parents", []):
            raise RuntimeError("Participant folder is outside the configured Drive root")
        if item.get("name") != name:
            renamed = requests.request("PATCH", url, headers=headers, json={"name": name}, timeout=15)
            renamed.raise_for_status()

    def trash(self, file_id: str) -> None:
        res = requests.request(
            "PATCH", f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers={"Authorization": f"Bearer {self._get_access_token()}"},
            json={"trashed": True}, timeout=15,
        )
        res.raise_for_status()

    def get_or_create_subfolder(self, folder_name: str, parent_id: str | None = None) -> str:
        target_parent = parent_id or self.folder_id
        cache_key = f"{target_parent}:{folder_name}"
        if cache_key in self._subfolder_cache:
            return self._subfolder_cache[cache_key]

        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        escaped_name = folder_name.replace("'", "\\'")
        q = f"'{target_parent}' in parents and name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = requests.request("GET", "https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": q, "fields": "files(id, name)"}, timeout=15.0)
        res.raise_for_status()
        files = res.json().get("files", [])
        if files:
            found_id = files[0]["id"]
            self._subfolder_cache[cache_key] = found_id
            return found_id

        create_res = requests.request(
            "POST",
            "https://www.googleapis.com/drive/v3/files",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "name": folder_name,
                "parents": [target_parent],
                "mimeType": "application/vnd.google-apps.folder",
            },
            timeout=15.0,
        )
        create_res.raise_for_status()
        created_id = create_res.json()["id"]
        self._subfolder_cache[cache_key] = created_id
        return created_id

    def upload_or_update_file(self, filename: str, body: bytes, mime: str = "text/csv; charset=utf-8", parent_id: str | None = None) -> str:
        from app.drive_lock import drive_lock
        target_parent = parent_id or self.folder_id
        with drive_lock(self.db):
            with self.db() as c:
                c.execute("CREATE TABLE IF NOT EXISTS drive_managed_files (parent_id TEXT NOT NULL, name TEXT NOT NULL, file_id TEXT NOT NULL, PRIMARY KEY(parent_id, name))")
                row = c.execute("SELECT file_id FROM drive_managed_files WHERE parent_id=? AND name=?", (target_parent, filename)).fetchone()
                if row:
                    file_id = row["file_id"]
                else:
                    matches = [f for f in self.list_children(target_parent) if f["name"] == filename]
                    file_id = matches[0]["id"] if matches else self.allocate_id()
                    c.execute("INSERT INTO drive_managed_files(parent_id, name, file_id) VALUES (?, ?, ?)", (target_parent, filename, file_id))
            return self.put(file_id, filename, body, mime, target_parent)

    def move_and_rename_file(self, file_id: str, new_name: str, target_parent_id: str, old_parent_id: str | None = None) -> bool:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            params = {}
            get_res = requests.request(
                "GET",
                f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=id,name,parents",
                headers=headers,
                timeout=15.0
            )
            if get_res.status_code == 200:
                meta = get_res.json()
                current_parents = meta.get("parents", [])
                current_name = meta.get("name", "")
                if target_parent_id not in current_parents:
                    params["addParents"] = target_parent_id
                removable = [p for p in current_parents if p != target_parent_id]
                if removable:
                    params["removeParents"] = ",".join(removable)
                if current_name == new_name and not params:
                    return True
            else:
                params["addParents"] = target_parent_id
                if old_parent_id or self.folder_id:
                    params["removeParents"] = old_parent_id or self.folder_id

            res = requests.request(
                "PATCH",
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers={**headers, "Content-Type": "application/json"},
                params=params,
                json={"name": new_name},
                timeout=15.0
            )
            return res.status_code == 200
        except Exception:
            return False

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

    def list_children(self, parent_id: str | None = None, mime_type: str | None = None) -> list[dict]:
        """Lists active (non-trashed) files/folders inside a parent folder."""
        target_parent = parent_id or self.folder_id
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        q_parts = [f"'{target_parent}' in parents", "trashed = false"]
        if mime_type:
            q_parts.append(f"mimeType = '{mime_type}'")
        q = " and ".join(q_parts)

        items = []
        page_token = None
        while True:
            params = {
                "q": q,
                "fields": "nextPageToken, files(id, name, mimeType, parents, createdTime, size)",
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                res = requests.request(
                    "GET",
                    "https://www.googleapis.com/drive/v3/files",
                    headers=headers,
                    params=params,
                    timeout=20.0,
                )
                res.raise_for_status()
                data = res.json()
                items.extend(data.get("files", []))
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Error querying files from Google Drive: %s", exc)
                raise
        return items


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
