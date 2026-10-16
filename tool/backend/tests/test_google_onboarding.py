"""First-visit survey persistence through Google onboarding."""
from test_collection import setup_test_app


def google_draft(client, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "verify_google_id_token", lambda credential: {
        "sub": "google-test-participant", "email": "volunteer@example.com", "name": "Volunteer"
    })
    response = client.post("/api/v1/auth/google", json={"credential": "test-id-token"})
    assert response.status_code == 200
    assert response.json()["needs_onboarding"] is True
    return response.json()["temp_token"]


def test_google_survey_saves_english_and_optional_reporting_fields(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    token = google_draft(client, monkeypatch)
    response = client.post("/api/v1/auth/google/onboard", json={
        "temp_token": token, "consent": True,
        "participant_code": " SE123456 ", "english_level": "B1",
        "class_name": " SE18A ", "referring_lecturer": " Nguyễn Văn A ",
    })
    assert response.status_code == 200
    me = client.get("/api/v1/participants/me", headers={"x-participant-token": token}).json()
    assert me["participant_code"] == "SE123456"
    assert me["survey"]["english_level"] == "B1"
    assert me["survey"]["class_name"] == "SE18A"
    assert me["survey"]["referring_lecturer"] == "Nguyễn Văn A"
    assert me["survey"]["student_id"] == "SE123456"


def test_google_onboarding_requires_explicit_nonblank_english_level(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    token = google_draft(client, monkeypatch)
    for fields in ({}, {"english_level": ""}, {"english_level": "   "}):
        response = client.post("/api/v1/auth/google/onboard", json={
            "temp_token": token, "consent": True, **fields,
        })
        assert response.status_code == 422


def test_google_onboarding_accepts_omitted_optional_reporting_fields(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    token = google_draft(client, monkeypatch)
    response = client.post("/api/v1/auth/google/onboard", json={
        "temp_token": token, "consent": True, "english_level": "Chưa rõ",
    })
    assert response.status_code == 200
    me = client.get("/api/v1/participants/me", headers={"x-participant-token": token}).json()
    assert me["participant_code"].startswith("P_")
    assert me["survey"]["student_id"] == ""
    assert me["survey"]["class_name"] == ""
    assert me["survey"]["referring_lecturer"] == ""
