"""Tests real PostgreSQL integration with psycopg, BYTEA binary audio storage,
and Google Drive sync outbox worker when a PostgreSQL instance is available.
"""
import io
import os
import sys
import zipfile
import pytest
from fastapi.testclient import TestClient

ADMIN = {"x-admin-key": "test-only-admin-secret"}
AUDIO_SAMPLE = b"\x1a\x45\xdf\xa3" + b"POSTGRES_AUDIO_" * 12


def is_pg_available():
    import socket
    try:
        s = socket.create_connection(("localhost", 5434), timeout=0.2)
        s.close()
    except OSError:
        return False
    try:
        import psycopg
        url = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:secret@localhost:5434/liemwhisper")
        conn = psycopg.connect(url, connect_timeout=1)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL test instance on port 5434 not reachable")


class FakeDriveClient:
    """Explicit fake Google Drive client for isolated backend tests."""

    def __init__(self, connected=True):
        self.connected = connected
        self.files = {}
        self.id_counter = 0
        self.allocate_calls = 0
        self.put_calls = 0
        self.download_calls = 0
        self.delete_calls = 0

    def allocate_id(self) -> str:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.allocate_calls += 1
        self.id_counter += 1
        return f"fake-drive-id-{self.id_counter}"

    def put(self, file_id: str, name: str, body: bytes, mime: str) -> None:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.put_calls += 1
        self.files[file_id] = {"name": name, "body": body, "mime": mime}

    def download(self, file_id: str) -> bytes:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.download_calls += 1
        if file_id not in self.files:
            raise KeyError(f"File {file_id} not found in fake drive")
        return self.files[file_id]["body"]

    def delete(self, file_id: str) -> None:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.delete_calls += 1
        self.files.pop(file_id, None)


from app.worker import process_outbox


def setup_pg_app(tmp_path, monkeypatch):
    pg_url = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:secret@localhost:5434/liemwhisper")
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "sql_drive")
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")

    sys.modules.pop("app.main", None)
    import importlib
    main = importlib.import_module("app.main")
    main.init_db()

    # Clean test tables
    with main.db() as c:
        c.execute("DELETE FROM drive_sync_jobs")
        c.execute("DELETE FROM recording_audio")
        c.execute("DELETE FROM recordings")
        c.execute("DELETE FROM participants")
        c.execute("DELETE FROM prompts")
        c.execute("DELETE FROM courses")

    client = TestClient(main.app)
    course = client.post("/api/v1/admin/courses", headers=ADMIN, json={"title": "Postgres Course"}).json()["id"]
    p_res = client.post(
        f"/api/v1/admin/courses/{course}/prompts/bulk",
        headers=ADMIN,
        json={"prompts": ["Postgres test prompt"]}
    ).json()
    prompt_id = p_res["prompts"][0]["id"]
    signup = client.post("/api/v1/participants", json={"consent": True, "participant_code": "SV_PG"}).json()
    token = {"x-participant-token": signup["participant_token"]}

    return main, client, course, prompt_id, token


def test_postgres_full_flow(tmp_path, monkeypatch):
    main, client, course, prompt_id, token = setup_pg_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()

    # 1. Upload audio to PostgreSQL
    upload_res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt_id, "duration": 4.0},
        files={"audio": ("voice.webm", AUDIO_SAMPLE, "audio/webm")}
    )
    assert upload_res.status_code == 200
    rec_id = upload_res.json()["recording_id"]
    assert upload_res.json()["drive_sync_status"] == "pending"

    # Verify audio stored in PostgreSQL BYTEA table
    with main.db() as c:
        audio_row = c.execute("SELECT body FROM recording_audio WHERE recording_id = ?", (rec_id,)).fetchone()
        assert audio_row is not None
        assert bytes(audio_row[0]) == AUDIO_SAMPLE
        assert bytes(audio_row["body"]) == AUDIO_SAMPLE

    # 2. HTTP Range streaming from PostgreSQL BYTEA
    url = f"/api/v1/recordings/{rec_id}/audio"
    stream_full = client.get(url, headers=token)
    assert stream_full.status_code == 200
    assert stream_full.content == AUDIO_SAMPLE

    partial = client.get(url, headers={**token, "range": "bytes=0-15"})
    assert partial.status_code == 206
    assert partial.content == AUDIO_SAMPLE[0:16]
    assert partial.headers["content-range"] == f"bytes 0-15/{len(AUDIO_SAMPLE)}"

    # 3. Outbox worker syncs to Drive
    processed = process_outbox(main.db, drive_client=fake_drive)
    assert processed == 1
    assert fake_drive.allocate_calls == 1
    assert fake_drive.put_calls == 1
    assert fake_drive.download_calls == 1

    # Status updated in PostgreSQL
    with main.db() as c:
        rec = c.execute("SELECT drive_sync_status, drive_file_id FROM recordings WHERE id = ?", (rec_id,)).fetchone()
        assert rec["drive_sync_status"] == "synced"
        assert rec["drive_file_id"] == "fake-drive-id-1"

    # 4. Review recording
    rev = client.post(
        f"/api/v1/admin/recordings/{rec_id}/review",
        headers=ADMIN,
        json={"status": "approved", "transcript": "Approved transcript"}
    )
    assert rev.status_code == 200
    assert rev.json()["drive_sync_status"] == "synced"

    # 5. Export ZIP archive pulls bytes from PostgreSQL
    archive = client.get("/api/v1/admin/export/archive.zip", headers=ADMIN)
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert z.read(f"audio/{rec_id}.webm") == AUDIO_SAMPLE

    # 6. Participant withdrawal in PostgreSQL: tombstones persist
    w = client.post("/api/v1/participants/withdraw", headers=token).json()
    assert w["withdrawn"] is True

    with main.db() as c:
        assert c.execute("SELECT 1 FROM recordings WHERE id = ?", (rec_id,)).fetchone() is None
        assert c.execute("SELECT 1 FROM recording_audio WHERE recording_id = ?", (rec_id,)).fetchone() is None
        tombstone = c.execute("SELECT * FROM drive_sync_jobs WHERE recording_id = ? AND action = 'delete'", (rec_id,)).fetchone()
        assert tombstone is not None
        assert tombstone["drive_file_id"] == "fake-drive-id-1"

    # Worker purges file on Drive
    process_outbox(main.db, drive_client=fake_drive)
    assert fake_drive.delete_calls == 1
    assert "fake-drive-id-1" not in fake_drive.files
