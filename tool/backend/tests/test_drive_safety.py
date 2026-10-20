import hashlib
import threading
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

from app.database import db, init_db
from app.drive import GoogleDriveClient
from app.drive_cleanup import cleanup_duplicates
from app.worker import enqueue_upload_job, process_outbox
from app.drive_lock import _process_lock
from test_drive_sync import FakeDriveClient


class Drive(FakeDriveClient):
    folder_id = "root"

    def ensure_folder(self, folder_id, name):
        self.files.setdefault(folder_id, {
            "name": name, "mime": "application/vnd.google-apps.folder", "parent": self.folder_id,
        })

    def trash(self, file_id):
        self.files.pop(file_id)


@pytest.fixture
def recording(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", "")
    init_db()
    body = b"audio sample"
    with db() as c:
        c.execute("INSERT INTO courses(id,title,created_at) VALUES ('c','Course',1)")
        c.execute("INSERT INTO prompts(id,course_id,text,published,created_at) VALUES ('q','c','Question',1,1)")
        c.execute("INSERT INTO participants(id,token_hash,participant_code,name,consent_version,consent_at,survey) VALUES ('p','hash','SV01','Student','v1',1,'{}')")
        c.execute("""INSERT INTO recordings(id,participant_id,prompt_id,storage_key,sha256,mime,bytes,format,created_at)
            VALUES ('recording-1','p','q','sql://recording-1',?,'audio/webm',?,'webm',1)""",
            (hashlib.sha256(body).hexdigest(), len(body)))
        c.execute("INSERT INTO recording_audio VALUES ('recording-1',?)", (body,))
        enqueue_upload_job(c, "recording-1")
    return body


def test_concurrent_workers_upload_once(recording):
    drive = Drive()
    barrier = threading.Barrier(4)
    def run():
        barrier.wait(timeout=5)
        return process_outbox(db, drive)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run(), range(4)))
    assert sum(results) == 1
    assert drive.put_calls == 1
    assert len([f for f in drive.files.values() if f["mime"] == "audio/webm"]) == 1
    assert len([f for f in drive.files.values() if f["mime"].endswith("folder")]) == 1


def test_restart_resumes_uploading_with_persisted_ids(recording):
    drive = Drive()
    with db() as c:
        c.execute("UPDATE recordings SET drive_file_id='stable-file'")
        c.execute("UPDATE participants SET drive_folder_id='stable-folder'")
        c.execute("UPDATE drive_sync_jobs SET status='uploading',drive_file_id='stable-file'")
    assert process_outbox(db, drive) == 1
    assert drive.allocate_calls == 0
    assert drive.files["stable-file"]["parent"] == "stable-folder"
    assert process_outbox(db, drive) == 0


def test_folder_creation_retry_keeps_persisted_id(recording):
    drive = Drive()
    original = drive.ensure_folder
    drive.ensure_folder = Mock(side_effect=RuntimeError("timeout"))
    assert process_outbox(db, drive) == 0
    with db() as c:
        saved = c.execute("SELECT drive_folder_id FROM participants").fetchone()[0]
    assert saved
    assert drive.put_calls == 0  # Never fall back to root on folder failure.
    drive.ensure_folder = original
    assert process_outbox(db, drive) == 1
    assert drive.allocate_calls == 2  # one audio ID and one folder ID


def test_new_audio_arriving_during_upload_is_requeued(recording):
    drive = Drive()
    original = drive.put
    updated = b"new recording"
    def put(*args, **kwargs):
        original(*args, **kwargs)
        with db() as c:
            c.execute("UPDATE recording_audio SET body=?", (updated,))
            c.execute("UPDATE recordings SET sha256=?", (hashlib.sha256(updated).hexdigest(),))
    drive.put = put
    assert process_outbox(db, drive) == 0
    with db() as c:
        assert c.execute("SELECT status FROM drive_sync_jobs").fetchone()[0] == "pending"
    drive.put = original
    assert process_outbox(db, drive) == 1
    audio = [f for f in drive.files.values() if f["mime"] == "audio/webm"]
    assert len(audio) == 1
    assert audio[0]["body"] == updated


def test_cleanup_trashes_only_verified_copy_and_empty_folder(recording):
    drive = Drive()
    process_outbox(db, drive)
    canonical_id, audio = next((fid, f) for fid, f in drive.files.items() if f["mime"] == "audio/webm")
    drive.files["extra-folder"] = {"name": "SV01 - Student", "mime": "application/vnd.google-apps.folder", "parent": "root"}
    drive.files["duplicate"] = {**audio, "parent": "extra-folder"}
    result = cleanup_duplicates(db, drive)
    assert result["deleted_files_count"] == 1
    assert result["deleted_folders_count"] == 1
    assert canonical_id in drive.files
    assert "extra-folder" not in drive.files


@pytest.mark.parametrize("failed_move", [False, True])
def test_cleanup_verifies_bytes_and_preserves_unknown_files(recording, failed_move):
    drive = Drive()
    process_outbox(db, drive)
    with db() as c:
        canonical_id = c.execute("SELECT drive_file_id FROM recordings").fetchone()[0]
        primary = c.execute("SELECT drive_folder_id FROM participants").fetchone()[0]
    audio = drive.files[canonical_id]
    drive.files["extra-folder"] = {"name": "SV01 - Student", "mime": "application/vnd.google-apps.folder", "parent": "root"}
    drive.files["duplicate"] = {**audio, "parent": "extra-folder"}
    drive.files["different-audio"] = {**audio, "parent": "extra-folder", "body": b"different"}
    drive.files["unknown"] = {**audio, "parent": "extra-folder", "name": "notes.webm"}
    audio["parent"] = "extra-folder"
    if failed_move:
        drive.move_and_rename_file = lambda *a, **kw: False
    result = cleanup_duplicates(db, drive)
    assert "different-audio" in drive.files
    assert "unknown" in drive.files
    assert "extra-folder" in drive.files
    assert canonical_id in drive.files
    assert result["deleted_files_count"] == (0 if failed_move else 1)
    assert ("duplicate" in drive.files) == failed_move
    if not failed_move:
        assert drive.files[canonical_id]["parent"] == primary
        assert cleanup_duplicates(db, drive)["deleted_files_count"] == 0


def test_drive_timeout_never_creates_replacement_file(monkeypatch):
    client = GoogleDriveClient(db, "root", "")
    monkeypatch.setattr(client, "_get_access_token", lambda: "fake")
    request = Mock(side_effect=requests.Timeout)
    monkeypatch.setattr("app.drive.requests.request", request)
    with pytest.raises(requests.Timeout):
        client.put("stable", "audio.webm", b"data", "audio/webm")
    assert request.call_count == 1
    assert request.call_args.args[0] == "GET"


def test_partial_listing_raises_instead_of_reporting_empty(monkeypatch):
    client = GoogleDriveClient(db, "root", "")
    monkeypatch.setattr(client, "_get_access_token", lambda: "fake")
    response = Mock()
    response.json.return_value = {"files": [{"id": "kept"}], "nextPageToken": "next"}
    monkeypatch.setattr("app.drive.requests.request", Mock(side_effect=[response, requests.Timeout()]))
    with pytest.raises(requests.Timeout):
        client.list_children()


def test_sqlite_lock_excludes_another_process(tmp_path):
    ready = tmp_path / "ready"
    acquired = tmp_path / "acquired"
    backend = str(Path(__file__).resolve().parents[1])
    code = (
        f"import sys; sys.path.insert(0, {backend!r}); "
        "from pathlib import Path; from app.drive_lock import _process_lock\n"
        f"Path({str(ready)!r}).touch()\n"
        f"with _process_lock(None, False, Path({str(tmp_path)!r})):\n"
        f"    Path({str(acquired)!r}).touch()\n"
    )
    child = None
    try:
        with _process_lock(None, False, tmp_path):
            child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready.exists()
            assert not acquired.exists()
        _, stderr = child.communicate(timeout=15)
        assert child.returncode == 0, stderr.decode()
        assert acquired.exists()
    finally:
        if child and child.poll() is None:
            child.kill()
            child.wait()
