"""Drive tests use a real SQLite DB and explicit fake Google HTTP; no live Google."""
import base64
import hashlib
import importlib
import importlib.util
import sqlite3
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BASE = "/api/v1/admin/drive"
HEADERS = {"x-admin-key": "test-admin"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, value in {
        "GOOGLE_CLIENT_ID": "test-client",
        "GOOGLE_CLIENT_SECRET": "test-secret",
        "GOOGLE_REDIRECT_URI": "https://app.test" + BASE + "/callback",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }.items():
        monkeypatch.setenv(key, value)

    @contextmanager
    def db():
        conn = sqlite3.connect(tmp_path / "drive.sqlite", timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def admin(key):
        if key != "test-admin":
            raise HTTPException(403, "Admin credential required")

    assert importlib.util.find_spec("app.drive") is not None, "Drive OAuth module is missing"
    drive = importlib.import_module("app.drive")
    app = FastAPI()
    drive.register_drive_routes(app, db, admin)
    return drive, db, TestClient(app, base_url="https://app.test")


def first_party_start(client, response):
    assert response.status_code == 200, response.text
    url = urlparse(response.json()["authorization_url"])
    assert url.netloc == "app.test"
    assert url.path == BASE + "/start"
    assert not url.query
    assert "set-cookie" not in response.headers
    # Model the cross-site browser dropping ALL cookies from the initial fetch.
    client.cookies.clear()
    landing = client.get(url.path)
    assert landing.status_code == 200
    assert "history.replaceState" in landing.text
    return client.post(BASE + "/start", json={"ticket": url.fragment})


def start(client):
    response = first_party_start(client, client.post(BASE + "/connect", headers=HEADERS))
    assert response.status_code == 200, response.text
    return parse_qs(urlparse(response.json()["authorization_url"]).query)


def test_connect_requires_header_and_binds_short_lived_pkce_state(env):
    drive, db, client = env
    assert client.get(BASE + "/status?key=test-admin").status_code == 403
    assert client.post(BASE + "/connect?key=test-admin").status_code == 403
    assert client.get(BASE + "/status", headers=HEADERS).json() == {
        "connected": False, "configured": True, "folder_id": None,
    }
    response = first_party_start(client, client.post(BASE + "/connect", headers=HEADERS))
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["https://app.test" + BASE + "/callback"]
    assert query["code_challenge_method"] == ["S256"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" in cookie
    with db() as conn:
        row = conn.execute("SELECT * FROM drive_oauth_state").fetchone()
    assert row["state_hash"] == hashlib.sha256(query["state"][0].encode()).hexdigest()
    assert row["expires_at"] > 0
    assert query["code_challenge"] == [base64.urlsafe_b64encode(
        hashlib.sha256(row["pkce_verifier"].encode()).digest()).rstrip(b"=").decode()]


def test_oauth_callback_success(env, monkeypatch):
    drive, db, client = env

    # 1. Start connect to get state & cookie
    connect_res = first_party_start(client, client.post(BASE + "/connect", headers=HEADERS))
    assert connect_res.status_code == 200
    state = parse_qs(urlparse(connect_res.json()["authorization_url"]).query)["state"][0]

    # Mock Google HTTP responses
    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = str(json_data)
            self.content = b""

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP error {self.status_code}")

    recorded_requests = []

    def fake_request(method, url, **kwargs):
        recorded_requests.append((method, url, kwargs))
        if "oauth2.googleapis.com/token" in url:
            # Check PKCE code_verifier is passed
            assert kwargs.get("data", {}).get("code_verifier") is not None
            assert kwargs.get("data", {}).get("code") == "fake-auth-code"
            return FakeResponse(200, {
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token-secret-123",
                "expires_in": 3600,
                "token_type": "Bearer",
            })
        if "drive/v3/about" in url:
            return FakeResponse(200, {
                "user": {
                    "permissionId": "user-perm-id-001",
                    "emailAddress": "owner@example.com",
                }
            })
        if "drive/v3/files/generateIds" in url:
            return FakeResponse(200, {"ids": ["generated-folder-id-123"]})
        if "drive/v3/files" in url and method == "POST":
            return FakeResponse(200, {
                "id": "generated-folder-id-123",
                "name": "LiemWhisper Recordings",
                "mimeType": "application/vnd.google-apps.folder",
            })
        raise ValueError(f"Unexpected URL: {url}")

    monkeypatch.setattr("requests.request", fake_request)

    # 2. Invoke callback
    callback_res = client.get(f"{BASE}/callback?code=fake-auth-code&state={state}")
    assert callback_res.status_code == 200
    assert "text/html" in callback_res.headers.get("content-type", "")
    assert "fake-refresh-token-secret-123" not in callback_res.text
    assert "fake-auth-code" not in callback_res.text

    # 3. Verify single-use state is consumed from DB
    with db() as conn:
        state_rows = conn.execute("SELECT * FROM drive_oauth_state").fetchall()
        assert len(state_rows) == 0

        # Verify drive_connection record
        conn_row = conn.execute("SELECT * FROM drive_connection WHERE id='default'").fetchone()
        assert conn_row is not None
        assert conn_row["account_id"] == "user-perm-id-001"
        assert conn_row["account_email"] == "owner@example.com"
        assert conn_row["folder_id"] == "generated-folder-id-123"
        # Refresh token must be Fernet-encrypted TEXT, not raw plaintext
        assert conn_row["refresh_token_enc"] != "fake-refresh-token-secret-123"
        fernet = Fernet(env[0].os.getenv("TOKEN_ENCRYPTION_KEY"))
        decrypted = fernet.decrypt(conn_row["refresh_token_enc"].encode("utf-8")).decode("utf-8")
        assert decrypted == "fake-refresh-token-secret-123"

    # 4. Status route now reports connected and folder_id
    status_res = client.get(BASE + "/status", headers=HEADERS)
    assert status_res.status_code == 200
    assert status_res.json() == {
        "connected": True,
        "configured": True,
        "folder_id": "generated-folder-id-123",
    }


def test_oauth_callback_rejects_account_mismatch(env, monkeypatch):
    drive, db, client = env

    # Seed an existing drive_connection for user-alpha
    fernet = Fernet(env[0].os.getenv("TOKEN_ENCRYPTION_KEY"))
    with db() as conn:
        conn.execute(
            "INSERT INTO drive_connection (id, account_id, account_email, refresh_token_enc, folder_id, created_at, updated_at) "
            "VALUES ('default', 'user-alpha', 'alpha@example.com', ?, 'existing-folder', 1000, 1000)",
            (fernet.encrypt(b"alpha-refresh").decode("utf-8"),),
        )

    # Start connect
    connect_res = first_party_start(client, client.post(BASE + "/connect", headers=HEADERS))
    state = parse_qs(urlparse(connect_res.json()["authorization_url"]).query)["state"][0]

    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = str(json_data)
        def json(self):
            return self._json
        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("HTTP error")

    def fake_request(method, url, **kwargs):
        if "oauth2.googleapis.com/token" in url:
            return FakeResponse(200, {
                "access_token": "token-beta",
                "refresh_token": "refresh-beta",
                "expires_in": 3600,
            })
        if "drive/v3/about" in url:
            # Different permissionId! (user-beta instead of user-alpha)
            return FakeResponse(200, {
                "user": {
                    "permissionId": "user-beta",
                    "emailAddress": "beta@example.com",
                }
            })
        raise ValueError(f"Unexpected: {url}")

    monkeypatch.setattr("requests.request", fake_request)

    res = client.get(f"{BASE}/callback?code=code-beta&state={state}")
    assert res.status_code == 400
    assert "mismatch" in res.text.lower()

    # Verify original connection was not overwritten
    with db() as conn:
        row = conn.execute("SELECT * FROM drive_connection WHERE id='default'").fetchone()
        assert row["account_id"] == "user-alpha"
        assert row["folder_id"] == "existing-folder"


def test_oauth_callback_invalid_csrf_and_single_use(env):
    drive, db, client = env

    connect_res = first_party_start(client, client.post(BASE + "/connect", headers=HEADERS))
    state = parse_qs(urlparse(connect_res.json()["authorization_url"]).query)["state"][0]

    # 1. Missing cookie -> 400
    no_cookie_client = TestClient(client.app, base_url="https://app.test")
    res = no_cookie_client.get(f"{BASE}/callback?code=code1&state={state}")
    assert res.status_code == 400

    # 2. Tampered cookie -> 400
    tampered_client = TestClient(client.app, base_url="https://app.test", cookies={drive.COOKIE_NAME: "wrong-verifier"})
    res2 = tampered_client.get(f"{BASE}/callback?code=code1&state={state}")
    assert res2.status_code == 400

    # 3. State is single use: after attempt, state row was consumed / deleted
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) as c FROM drive_oauth_state").fetchone()["c"] == 0


def test_handoff_requires_auth_is_hashed_single_use_and_expires(env, monkeypatch):
    drive, db, client = env
    assert client.post(BASE + "/connect").status_code == 403
    assert client.post(BASE + "/start", json={"ticket": "forged"}).status_code == 400
    response = client.post(BASE + "/connect", headers=HEADERS)
    ticket = urlparse(response.json()["authorization_url"]).fragment
    with db() as conn:
        row = conn.execute("SELECT * FROM drive_oauth_handoff").fetchone()
    assert row["ticket_hash"] == hashlib.sha256(ticket.encode()).hexdigest()
    assert ticket not in str(dict(row))
    assert response.headers["cache-control"] == "no-store"
    assert client.post(BASE + "/start", json={"ticket": ticket},
                       headers={"Origin": "https://foreign.test"}).status_code == 403
    assert client.post(BASE + "/start", json={"ticket": ticket},
                       headers={"Origin": "https://app.test"}).status_code == 200
    assert client.post(BASE + "/start", json={"ticket": ticket}).status_code == 400
    response = client.post(BASE + "/connect", headers=HEADERS)
    ticket = urlparse(response.json()["authorization_url"]).fragment
    now = drive.time.time()
    monkeypatch.setattr(drive.time, "time", lambda: now + 121)
    assert client.post(BASE + "/start", json={"ticket": ticket}).status_code == 400


def test_start_page_does_not_consume_ticket_or_leak_it(env):
    drive, db, client = env
    response = client.post(BASE + "/connect", headers=HEADERS)
    ticket = urlparse(response.json()["authorization_url"]).fragment
    landing = client.get(BASE + "/start")
    assert ticket not in landing.text
    assert "set-cookie" not in landing.headers
    assert landing.headers["referrer-policy"] == "no-referrer"
    assert landing.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in landing.headers["content-security-policy"]
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM drive_oauth_handoff").fetchone()[0] == 1
    assert landing.text.index("history.replaceState") < landing.text.index("await fetch")


def test_drive_client_operations_and_token_refresh(env, monkeypatch):
    drive, db, client = env

    fernet = Fernet(env[0].os.getenv("TOKEN_ENCRYPTION_KEY"))
    encrypted_refresh = fernet.encrypt(b"refresh-secret-xyz").decode("utf-8")

    with db() as conn:
        conn.execute(
            "INSERT INTO drive_connection (id, account_id, account_email, refresh_token_enc, folder_id, created_at, updated_at) "
            "VALUES ('default', 'user-001', 'test@example.com', ?, 'folder-app-123', 1000, 1000)",
            (encrypted_refresh,),
        )

    # Fake Drive store
    stored_files = {}

    class FakeResponse:
        def __init__(self, status_code, json_data=None, content=b""):
            self.status_code = status_code
            self._json = json_data
            self.content = content
            self.text = content.decode("utf-8", errors="ignore") if content else str(json_data)

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP error {self.status_code}")

    refresh_calls = 0

    def fake_request(method, url, **kwargs):
        nonlocal refresh_calls
        if "oauth2.googleapis.com/token" in url:
            refresh_calls += 1
            assert kwargs.get("data", {}).get("refresh_token") == "refresh-secret-xyz"
            return FakeResponse(200, {
                "access_token": f"bearer-token-{refresh_calls}",
                "expires_in": 3600,
            })

        # All subsequent Drive calls must include Authorization: Bearer
        auth = kwargs.get("headers", {}).get("Authorization", "")
        assert auth.startswith("Bearer bearer-token-")

        if "drive/v3/files/generateIds" in url:
            return FakeResponse(200, {"ids": ["alloc-id-999"]})

        if "drive/v3/files/alloc-id-999" in url:
            if method == "GET":
                if "alloc-id-999" in stored_files:
                    f = stored_files["alloc-id-999"]
                    if "alt=media" in url:
                        return FakeResponse(200, content=f["body"])
                    return FakeResponse(200, {"id": "alloc-id-999", "name": f["name"], "parents": [f["folder"]]})
                return FakeResponse(404, {"error": "Not Found"})
            if method == "DELETE":
                stored_files.pop("alloc-id-999", None)
                return FakeResponse(204)

        if "upload/drive/v3/files" in url:
            # Multipart or media upload
            raw_data = kwargs.get("data") or b""
            # If multipart, the content is after the second \r\n\r\n
            if b"Content-Type:" in raw_data:
                parts = raw_data.split(b"\r\n\r\n")
                actual_body = parts[2].split(b"\r\n--")[0]
            else:
                actual_body = raw_data
            stored_files["alloc-id-999"] = {
                "name": "sample.webm",
                "body": actual_body,
                "folder": "folder-app-123",
            }
            return FakeResponse(200, {"id": "alloc-id-999"})

        # Check for unrelated file id
        if "drive/v3/files/unrelated-id" in url:
            if method == "GET":
                return FakeResponse(200, {"id": "unrelated-id", "name": "other.doc", "parents": ["some-other-folder"]})
            if method == "DELETE":
                return FakeResponse(404, {"error": "Not Found"})

        raise ValueError(f"Unhandled fake_request: {method} {url}")

    monkeypatch.setattr("requests.request", fake_request)

    drive_client = drive.get_drive_client(db)
    assert drive_client.folder_id == "folder-app-123"

    # 1. allocate_id
    new_id = drive_client.allocate_id()
    assert new_id == "alloc-id-999"

    # 2. put
    drive_client.put(file_id=new_id, name="sample.webm", body=b"dummy audio payload", mime="audio/webm")
    assert "alloc-id-999" in stored_files

    # 3. download
    content = drive_client.download("alloc-id-999")
    assert content == b"dummy audio payload"

    # 4. delete (idempotent)
    drive_client.delete("alloc-id-999")
    assert "alloc-id-999" not in stored_files
    # delete again when 404 should succeed silently
    drive_client.delete("alloc-id-999")

    # 5. put with unrelated id that belongs to a different folder should be rejected
    with pytest.raises(Exception, match="unrelated"):
        drive_client.put(file_id="unrelated-id", name="hack.mp3", body=b"evil", mime="audio/mpeg")




