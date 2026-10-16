"""Test participant session completion and thank-you email dispatch."""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.mailer import send_thank_you_email
from test_collection import setup_test_app


def test_mailer_simulated_mode_without_credentials():
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
