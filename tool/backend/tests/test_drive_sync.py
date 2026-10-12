"""Tests for durable Google Drive sync outbox, idempotence, SHA256 verification, and deletion tombstones.
Explicitly uses FakeDriveClient for tests without live Google APIs.
"""
import hashlib
import io
import os
import sys
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.worker import process_outbox


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
        self.fail_put_once = False
        self.corrupt_download = False

    def allocate_id(self) -> str:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.allocate_calls += 1
        self.id_counter += 1
        return f"fake-drive-id-{self.id_counter}"

    def put(self, file_id: str, name: str, body: bytes, mime: str) -> None:
        if not self.connected:
            raise Exception("Drive unconnected")
        if self.fail_put_once:
            self.fail_put_once = False
            raise RuntimeError("Transient Drive upload error")
        self.put_calls += 1
        self.files[file_id] = {"name": name, "body": body, "mime": mime}

    def download(self, file_id: str) -> bytes:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.download_calls += 1
        if file_id not in self.files:
            raise KeyError(f"File {file_id} not found in fake drive")
        if self.corrupt_download:
            return b"corrupted-bytes-payload"
        return self.files[file_id]["body"]

    def delete(self, file_id: str) -> None:
        if not self.connected:
            raise Exception("Drive unconnected")
        self.delete_calls += 1
        self.files.pop(file_id, None)


ADMIN = {"x-admin-key": "test-only-admin-secret"}
AUDIO_SAMPLE = b"\x1a\x45\xdf\xa3" + b"AUDIO_DATA_" * 10


def setup_drive_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "sql_drive")
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("app.main", None)
    import importlib
    main = importlib.import_module("app.main")
    client = TestClient(main.app)

    course = client.post("/api/v1/admin/courses", headers=ADMIN, json={"title": "Drive Sync Course"}).json()["id"]
    p_res = client.post(
        f"/api/v1/admin/courses/{course}/prompts/bulk",
        headers=ADMIN,
        json={"prompts": ["Prompt 1", "Prompt 2"]}
    ).json()
    prompt1 = p_res["prompts"][0]["id"]
    prompt2 = p_res["prompts"][1]["id"]

    signup = client.post("/api/v1/participants", json={"consent": True, "participant_code": "SV_DRIVE"}).json()
    token = {"x-participant-token": signup["participant_token"]}

    return main, client, course, prompt1, prompt2, token


def test_outbox_upload_idempotent_and_verifies_sha256(tmp_path, monkeypatch):
    main, client, course, prompt1, _, token = setup_drive_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()

    # Upload audio in sql_drive mode
    res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt1, "duration": 2.5},
        files={"audio": ("sample.webm", AUDIO_SAMPLE, "audio/webm")}
    )
    assert res.status_code == 200
    rec_id = res.json()["recording_id"]
    assert res.json()["drive_sync_status"] == "pending"

    # Tasks endpoint returns drive_sync_status
    tasks = client.get("/api/v1/tasks", params={"course_id": course}, headers=token).json()
    task = next(t for t in tasks if t["id"] == prompt1)
    assert task["drive_sync_status"] == "pending"

    # Process outbox
    processed = process_outbox(main.db, drive_client=fake_drive)
    assert processed == 1
    assert fake_drive.allocate_calls == 1
    assert fake_drive.put_calls == 1
    assert fake_drive.download_calls == 1
    file_id = f"fake-drive-id-1"
    assert file_id in fake_drive.files
    assert fake_drive.files[file_id]["body"] == AUDIO_SAMPLE

    # Verify status in database and review queue
    with main.db() as c:
        rec = c.execute("SELECT drive_sync_status, drive_file_id FROM recordings WHERE id=?", (rec_id,)).fetchone()
        assert rec["drive_sync_status"] == "synced"
        assert rec["drive_file_id"] == file_id

        job = c.execute("SELECT status FROM drive_sync_jobs WHERE recording_id=?", (rec_id,)).fetchone()
        assert job["status"] == "synced"

    # Second process_outbox run does nothing (idempotent)
    processed_again = process_outbox(main.db, drive_client=fake_drive)
    assert processed_again == 0
    assert fake_drive.put_calls == 1

    # Review returns drive_sync_status
    rev = client.post(
        f"/api/v1/admin/recordings/{rec_id}/review",
        headers=ADMIN,
        json={"status": "approved", "transcript": "Verified transcript"}
    )
    assert rev.status_code == 200
    assert rev.json()["drive_sync_status"] == "synced"


def test_stable_id_survives_retry(tmp_path, monkeypatch):
    main, client, course, prompt1, _, token = setup_drive_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()
    fake_drive.fail_put_once = True

    res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt1, "duration": 2.5},
        files={"audio": ("sample.webm", AUDIO_SAMPLE, "audio/webm")}
    )
    rec_id = res.json()["recording_id"]

    # First attempt fails during put, but ID was already allocated and persisted!
    process_outbox(main.db, drive_client=fake_drive)
    assert fake_drive.allocate_calls == 1

    with main.db() as c:
        job = c.execute("SELECT status, drive_file_id, attempts FROM drive_sync_jobs WHERE recording_id=?", (rec_id,)).fetchone()
        assert job["status"] in ("retrying", "pending")
        allocated_id = job["drive_file_id"]
        assert allocated_id == "fake-drive-id-1"
        assert job["attempts"] == 1

    # Second attempt succeeds using the EXACT SAME allocated file_id
    process_outbox(main.db, drive_client=fake_drive)
    assert fake_drive.allocate_calls == 1  # No duplicate allocation!
    assert fake_drive.put_calls == 1

    with main.db() as c:
        rec = c.execute("SELECT drive_sync_status, drive_file_id FROM recordings WHERE id=?", (rec_id,)).fetchone()
        assert rec["drive_sync_status"] == "synced"
        assert rec["drive_file_id"] == allocated_id


def test_sha256_mismatch_prevents_synced_status(tmp_path, monkeypatch):
    main, client, course, prompt1, _, token = setup_drive_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()
    fake_drive.corrupt_download = True

    res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt1, "duration": 2.5},
        files={"audio": ("sample.webm", AUDIO_SAMPLE, "audio/webm")}
    )
    rec_id = res.json()["recording_id"]

    process_outbox(main.db, drive_client=fake_drive)

    with main.db() as c:
        rec = c.execute("SELECT drive_sync_status FROM recordings WHERE id=?", (rec_id,)).fetchone()
        assert rec["drive_sync_status"] != "synced"
        job = c.execute("SELECT status, last_error FROM drive_sync_jobs WHERE recording_id=?", (rec_id,)).fetchone()
        assert job["status"] in ("retrying", "failed")
        assert "mismatch" in job["last_error"].lower()


def test_withdrawal_persists_deletion_tombstone_without_cascade(tmp_path, monkeypatch):
    main, client, course, prompt1, _, token = setup_drive_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()

    res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt1, "duration": 2.5},
        files={"audio": ("sample.webm", AUDIO_SAMPLE, "audio/webm")}
    )
    rec_id = res.json()["recording_id"]

    # Sync to fake drive
    process_outbox(main.db, drive_client=fake_drive)
    file_id = "fake-drive-id-1"
    assert file_id in fake_drive.files

    # Participant withdraws
    w = client.post("/api/v1/participants/withdraw", headers=token).json()
    assert w["withdrawn"] is True

    # Recording row is deleted
    with main.db() as c:
        assert c.execute("SELECT 1 FROM recordings WHERE id=?", (rec_id,)).fetchone() is None
        # Deletion tombstone job MUST persist!
        del_job = c.execute("SELECT * FROM drive_sync_jobs WHERE recording_id=? AND action='delete'", (rec_id,)).fetchone()
        assert del_job is not None
        assert del_job["drive_file_id"] == file_id
        assert del_job["status"] == "pending"

    # Worker processes tombstone
    process_outbox(main.db, drive_client=fake_drive)
    assert fake_drive.delete_calls == 1
    assert file_id not in fake_drive.files  # Purged from fake Drive!

    with main.db() as c:
        del_job = c.execute("SELECT status FROM drive_sync_jobs WHERE recording_id=? AND action='delete'", (rec_id,)).fetchone()
        assert del_job["status"] == "completed"


def test_export_dual_mode_restricted_to_synced(tmp_path, monkeypatch):
    main, client, course, prompt1, prompt2, token = setup_drive_app(tmp_path, monkeypatch)
    fake_drive = FakeDriveClient()

    # Upload rec1
    r1 = client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt1, "duration": 2}, files={"audio": ("1.webm", AUDIO_SAMPLE, "audio/webm")}).json()["recording_id"]
    # Upload rec2
    r2 = client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt2, "duration": 3}, files={"audio": ("2.webm", AUDIO_SAMPLE + b"_2", "audio/webm")}).json()["recording_id"]

    # Approve both
    client.post(f"/api/v1/admin/recordings/{r1}/review", headers=ADMIN, json={"status": "approved"})
    client.post(f"/api/v1/admin/recordings/{r2}/review", headers=ADMIN, json={"status": "approved"})

    # Sync ONLY r1 manually in DB
    with main.db() as c:
        c.execute("UPDATE recordings SET drive_sync_status='synced', drive_file_id='fid-1' WHERE id=?", (r1,))

    # In dual mode, export only includes synced r1
    manifest = client.get("/api/v1/admin/export/manifest.json", headers=ADMIN).json()
    assert len(manifest) == 1
    assert manifest[0]["recording_id"] == r1

    # Now sync r2
    with main.db() as c:
        c.execute("UPDATE recordings SET drive_sync_status='synced', drive_file_id='fid-2' WHERE id=?", (r2,))

    manifest2 = client.get("/api/v1/admin/export/manifest.json", headers=ADMIN).json()
    assert len(manifest2) == 2


def test_reject_storage_backend_drive_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "drive")
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")
    sys.modules.pop("app.main", None)
    import importlib
    main = importlib.import_module("app.main")
    client = TestClient(main.app)

    res = client.post(
        "/api/v1/recordings",
        data={"prompt_id": "any", "duration": 1.0},
        files={"audio": ("a.webm", b"123" * 50, "audio/webm")}
    )
    assert res.status_code == 503
    assert "sql_drive" in res.json()["detail"]
