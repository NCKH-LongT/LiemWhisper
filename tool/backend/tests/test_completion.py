"""Test participant session completion and thank-you email dispatch."""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.mailer import send_thank_you_email
from test_collection import setup_test_app


def test_mailer_simulated_mode_without_credentials(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    for key in ("SMTP_USER", "SMTP_PASSWORD", "GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    res = send_thank_you_email(
        to_email="student@fpt.edu.vn",
        participant_name="Nguyen Van A",
        participant_code="SE194007",
        total_recordings=15
    )
    assert res["sent"] is False
    assert res["simulated"] is True
    assert res["recipient"] == "student@fpt.edu.vn"
    assert "SE194007" in res["subject"]


def test_participant_completion_endpoint(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    from app.database import db

    # Create participant directly
    token = "test-participant-secret-token-12345"
    from hashlib import sha256
    token_hash = sha256(token.encode()).hexdigest()

    with db() as c:
        c.execute(
            """INSERT INTO participants(id, token_hash, participant_code, consent_version, consent_at, survey, email, name, onboarded)
               VALUES (?, ?, ?, 'v1.0', 1000, '{}', 'student@example.com', 'Nguyen Van B', 1)""",
            ("p-test-001", token_hash, "SE194008")
        )

    headers = {"x-participant-token": token}

    # Verify participant_me before completion
    me_before = client.get("/api/v1/participants/me", headers=headers).json()
    assert me_before["email"] == "student@example.com"
    assert me_before["completed_at"] == 0

    # Call complete endpoint
    res = client.post("/api/v1/participants/complete", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["completed"] is True
    assert data["completed_at"] > 0
    assert data["email"] == "student@example.com"
    assert "email_delivery" in data

    # Verify participant_me after completion reflects completed_at
    me_after = client.get("/api/v1/participants/me", headers=headers).json()
    assert me_after["completed_at"] == data["completed_at"]

    # Call complete endpoint again (anti-spam test)
    res_again = client.post("/api/v1/participants/complete", headers=headers)
    assert res_again.status_code == 200
    data_again = res_again.json()
    assert data_again["status"] == "success"
    assert data_again["completed"] is True
    assert data_again.get("already_completed") is True
    assert data_again["completed_at"] == data["completed_at"]
    assert data_again["email_delivery"]["status"] == "pending"
    assert data_again["email_delivery"]["sent"] is False
    from app.email_delivery import process_email_queue
    calls = []
    def fake_send(*args, **kwargs):
        calls.append(args)
        return {"sent": True, "message_id": "gmail-test"}
    monkeypatch.setattr("app.mailer.send_thank_you_email", fake_send)
    process_email_queue(db)
    process_email_queue(db)
    assert len(calls) == 1
    assert client.get("/api/v1/participants/me", headers=headers).json()["email_delivery"]["sent"] is True

    # Attempting to upload recording after completion should be rejected with 403
    webm_payload = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
    res_upload = client.post(
        "/api/v1/recordings",
        headers=headers,
        data={"prompt_id": "prompt-1", "duration": 2.0},
        files={"audio": ("test.webm", webm_payload, "audio/webm")}
    )
    assert res_upload.status_code == 403
    assert "Bài thi đã hoàn thành" in res_upload.json()["detail"]


def test_rerecord_overwrites_with_latest_audio_only(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    from app.database import db

    token = "test-rerecord-token-999"
    from hashlib import sha256
    token_hash = sha256(token.encode()).hexdigest()

    with db() as c:
        c.execute(
            """INSERT INTO participants(id, token_hash, participant_code, consent_version, consent_at, survey, email, name, onboarded)
               VALUES (?, ?, ?, 'v1.0', 1000, '{}', 'student2@example.com', 'Nguyen Van C', 1)""",
            ("p-test-002", token_hash, "SE194009")
        )
        c.execute(
            """INSERT INTO courses(id, title, description, created_at)
               VALUES ('c-1', 'Test Course', 'Desc', 1000)"""
        )
        c.execute(
            """INSERT INTO prompts(id, course_id, text, language, target_terms, difficulty, category, published, created_at)
               VALUES ('prompt-1', 'c-1', 'Câu hỏi kiểm thử 1', 'vi', '[]', 'easy', 'general', 1, 1000)"""
        )

    headers = {"x-participant-token": token}
    audio_v1 = b"\x1a\x45\xdf\xa3" + b"AUDIO_TAKE_1_" * 20
    audio_v2 = b"\x1a\x45\xdf\xa3" + b"AUDIO_TAKE_2_LATEST_" * 25

    # First take
    res1 = client.post(
        "/api/v1/recordings",
        headers=headers,
        data={"prompt_id": "prompt-1", "duration": 4.2},
        files={"audio": ("take1.webm", audio_v1, "audio/webm")}
    )
    assert res1.status_code == 200
    rec_id_1 = res1.json()["recording_id"]

    with db() as c:
        recs = c.execute("SELECT id, duration_seconds, sha256 FROM recordings WHERE prompt_id='prompt-1' AND participant_id='p-test-002'").fetchall()
        assert len(recs) == 1
        assert abs(recs[0]["duration_seconds"] - 4.2) < 0.01

    # Second take (Re-recording before completion): should update/overwrite cleanly, not throw 409
    res2 = client.post(
        "/api/v1/recordings",
        headers=headers,
        data={"prompt_id": "prompt-1", "duration": 6.8},
        files={"audio": ("take2.webm", audio_v2, "audio/webm")}
    )
    assert res2.status_code == 200
    rec_id_2 = res2.json()["recording_id"]
    assert rec_id_1 == rec_id_2  # Kept the same recording ID

    # Verify only 1 recording exists in database and contains the latest audio take
    with db() as c:
        recs_after = c.execute("SELECT id, duration_seconds, sha256 FROM recordings WHERE prompt_id='prompt-1' AND participant_id='p-test-002'").fetchall()
        assert len(recs_after) == 1
        assert abs(recs_after[0]["duration_seconds"] - 6.8) < 0.01
        assert recs_after[0]["sha256"] == sha256(audio_v2).hexdigest()

        audio_row = c.execute("SELECT body FROM recording_audio WHERE recording_id=?", (rec_id_2,)).fetchone()
        if audio_row:
            assert audio_row[0] == audio_v2

