"""Pilot integration smoke tests. No real participant data."""
import importlib
import os
import sys

from fastapi.testclient import TestClient


def test_collection_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")
    sys.modules.pop("app.main", None)
    from app import main
    importlib.reload(main)
    client = TestClient(main.app)
    key = {"x-admin-key": "test-only-admin-secret"}
    assert client.get("/health").status_code == 200
    assert client.post("/api/v1/admin/courses", json={"title": "Software Testing"}).status_code == 403
    course = client.post("/api/v1/admin/courses", headers=key, json={"title": "Software Testing"})
    assert course.status_code == 200
    course_id = course.json()["id"]
    prompt = client.post(f"/api/v1/admin/courses/{course_id}/prompts", headers=key,
                         json={"text": "Explain regression testing.", "language": "vi-en"})
    assert prompt.status_code == 200
    prompt_id = prompt.json()["id"]
    assert client.get("/api/v1/courses").json() == []
    client.post(f"/api/v1/admin/prompts/{prompt_id}/publish", headers=key)
    assert len(client.get("/api/v1/courses").json()) == 1

    assert client.post("/api/v1/participants", json={
        "consent": False, "consent_version": "pilot-v1"}).status_code == 400
    p = client.post("/api/v1/participants", json={
        "consent": True, "consent_version": "pilot-v1", "familiarity": "beginner"})
    assert p.status_code == 200
    token = {"x-participant-token": p.json()["participant_token"]}
    tasks = client.get("/api/v1/tasks", params={"course_id": course_id}, headers=token)
    assert tasks.status_code == 200 and len(tasks.json()) == 1
    assert client.get("/api/v1/tasks", params={"course_id": course_id}).status_code == 401
    assert client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt_id},
                       files={"audio": ("clip.webm", b"garbage", "audio/webm")}).status_code == 422
    payload = b"\x1a\x45\xdf\xa3" + b"\x00" * 120
    # A magic-byte-only payload is intentionally accepted in the PILOT backend:
    # this test is not evidence that audio is properly decoded.
    result = client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt_id},
                         files={"audio": ("clip.webm", payload, "audio/webm")})
    assert result.status_code == 200
    rec = result.json()["recording_id"]
    duplicate = client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt_id},
                            files={"audio": ("clip.webm", payload, "audio/webm")})
    assert duplicate.status_code == 409
    assert client.get(f"/api/v1/admin/recordings/{rec}/audio", headers=key).content == payload
    reviewed = client.post(f"/api/v1/admin/recordings/{rec}/review", headers=key,
                           json={"approved": True, "transcript": "Explain regression testing."})
    assert reviewed.json()["status"] == "approved"
