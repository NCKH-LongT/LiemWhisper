"""Production collection API test suite. Covers multi-format audio, streaming, bulk import, review, stats, and dataset export."""
import importlib
import io
import os
import sys
import zipfile

from fastapi.testclient import TestClient


def setup_test_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    return TestClient(main.app)


def test_collection_flow(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    key = {"x-admin-key": "test-only-admin-secret"}

    # Health & Capabilities
    assert client.get("/health").status_code == 200
    caps = client.get("/api/v1/capabilities").json()
    assert caps["recording_upload_enabled"] is True

    # Course Creation
    assert client.post("/api/v1/admin/courses", json={"title": "Software Testing"}).status_code == 403
    course = client.post("/api/v1/admin/courses", headers=key, json={"title": "Software Testing"})
    assert course.status_code == 200
    course_id = course.json()["id"]

    # Bulk Prompt Creation
    bulk_res = client.post(
        f"/api/v1/admin/courses/{course_id}/prompts/bulk",
        headers=key,
        json={
            "prompts": [
                "Giải thích khái niệm regression testing trong dự án.",
                "Thực hiện boundary value analysis cho input tuổi từ 18 đến 60."
            ],
            "raw_text": "Unit test là bước kiểm thử cơ bản nhất.\nCode refactoring giúp cải thiện chất lượng mã nguồn.",
            "publish_immediately": True
        }
    )
    assert bulk_res.status_code == 200
    assert bulk_res.json()["created_count"] == 4

    # Participant Signup
    assert client.post("/api/v1/participants", json={"consent": False, "consent_version": "v1.0"}).status_code == 400
    p = client.post("/api/v1/participants", json={
        "consent": True,
        "consent_version": "v1.0",
        "participant_code": "SV_TEST_01",
        "familiarity": "intermediate",
        "english_level": "intermediate",
        "microphone": "headset"
    })
    assert p.status_code == 200
    p_data = p.json()
    assert p_data["participant_code"] == "SV_TEST_01"
    token = {"x-participant-token": p_data["participant_token"]}

    # Verify participant self-check
    me = client.get("/api/v1/participants/me", headers=token)
    assert me.status_code == 200
    assert me.json()["participant_code"] == "SV_TEST_01"

    # Tasks retrieval
    tasks = client.get("/api/v1/tasks", params={"course_id": course_id}, headers=token).json()
    assert len(tasks) == 4
    prompt1_id = tasks[0]["id"]
    prompt2_id = tasks[1]["id"]

    # 1. Upload WebM audio
    webm_payload = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
    res1 = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt1_id, "duration": 3.5},
        files={"audio": ("sample.webm", webm_payload, "audio/webm")}
    )
    assert res1.status_code == 200
    assert res1.json()["format"] == "webm"
    rec1_id = res1.json()["recording_id"]

    # 2. Upload MP4 audio (Safari iOS compatibility)
    mp4_payload = b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 200
    res2 = client.post(
        "/api/v1/recordings",
        headers=token,
        data={"prompt_id": prompt2_id, "duration": 4.2},
        files={"audio": ("voice.mp4", mp4_payload, "audio/mp4")}
    )
    assert res2.status_code == 200
    assert res2.json()["format"] == "mp4"
    rec2_id = res2.json()["recording_id"]

    # Audio playback streaming (via query param key)
    stream_res1 = client.get(f"/api/v1/admin/recordings/{rec1_id}/audio?key=test-only-admin-secret")
    assert stream_res1.status_code == 200
    assert stream_res1.content == webm_payload

    stream_res2 = client.get(f"/api/v1/admin/recordings/{rec2_id}/audio?key=test-only-admin-secret")
    assert stream_res2.status_code == 200
    assert stream_res2.content == mp4_payload

    # Admin review queue
    queue = client.get("/api/v1/admin/recordings", headers=key).json()
    assert len(queue) == 2

    # Review rec1 -> approved with verbatim transcript
    rev1 = client.post(
        f"/api/v1/admin/recordings/{rec1_id}/review",
        headers=key,
        json={"status": "approved", "transcript": "Giải thích khái niệm regression testing trong dự án."}
    )
    assert rev1.status_code == 200
    assert rev1.json()["status"] == "approved"

    # Review rec2 -> approved
    rev2 = client.post(
        f"/api/v1/admin/recordings/{rec2_id}/review",
        headers=key,
        json={"status": "approved", "transcript": "Thực hiện boundary value analysis cho input tuổi từ 18 đến 60."}
    )
    assert rev2.status_code == 200

    # Admin stats
    stats = client.get("/api/v1/admin/stats", headers=key).json()
    assert stats["total_recordings"] == 2
    assert stats["approved_recordings"] == 2
    assert stats["total_participants"] == 1

    # Export Manifest JSON
    manifest_json = client.get("/api/v1/admin/export/manifest.json", headers=key).json()
    assert len(manifest_json) == 2
    assert manifest_json[0]["participant_code"] == "SV_TEST_01"

    # Export Manifest CSV
    manifest_csv = client.get("/api/v1/admin/export/manifest.csv", headers=key)
    assert manifest_csv.status_code == 200
    assert "recording_id" in manifest_csv.text

    # Export Archive ZIP
    zip_res = client.get("/api/v1/admin/export/archive.zip", headers=key)
    assert zip_res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_res.content)) as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "manifest.csv" in namelist
        assert f"audio/{rec1_id}.webm" in namelist
        assert f"audio/{rec2_id}.mp4" in namelist
        # Verify file contents inside zip
        assert zf.read(f"audio/{rec1_id}.webm") == webm_payload

    # Participant withdraws consent
    withdraw = client.post("/api/v1/participants/withdraw", headers=token).json()
    assert withdraw["withdrawn"] is True
    assert withdraw["deleted_recordings"] == 2

    # After withdrawal, recordings and participant are purged
    assert len(client.get("/api/v1/admin/recordings", headers=key).json()) == 0
