"""Test auto-approval of recordings and removal of admin moderation requirement."""
import importlib
import sys

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient


def setup_test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-secret")
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    return TestClient(main.app), main


def test_recording_auto_approved_on_upload(tmp_path, monkeypatch):
    client, main = setup_test_app(tmp_path, monkeypatch)
    key = {"x-admin-key": "test-admin-secret"}

    # Setup course & prompt
    course = client.post("/api/v1/admin/courses", headers=key, json={"title": "Testing Course"}).json()
    client.post(
        f"/api/v1/admin/courses/{course['id']}/prompts/bulk",
        headers=key,
        json={"raw_text": "Câu hỏi kiểm thử phần mềm 1\nCâu hỏi kiểm thử 2", "publish_immediately": True}
    )
    part = client.post("/api/v1/participants", json={"consent": True, "consent_version": "v1.0", "participant_code": "SV01"}).json()
    token = {"x-participant-token": part["participant_token"]}

    tasks = client.get("/api/v1/tasks", params={"course_id": course["id"]}, headers=token).json()
    prompt_id = tasks[0]["id"]

    # Upload recording
    payload = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
    res = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt_id, "duration": 2.5},
        files={"audio": ("audio.webm", payload, "audio/webm")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved", "Recordings must be auto-approved without admin review"

    # Verify directly counted in stats without manual review
    stats = client.get("/api/v1/admin/stats", headers=key).json()
    assert stats["total_recordings"] == 1
    assert stats["approved_recordings"] == 1

    # Verify directly exportable without manual review
    manifest = client.get("/api/v1/admin/export/manifest.json", headers=key).json()
    assert len(manifest) == 1
    assert manifest[0]["prompt_id"] == prompt_id
