import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi import HTTPException
from test_collection import setup_test_app


def test_admin_email_crud_functions(tmp_path, monkeypatch):
    from app.database import db
    from app.auth import (
        add_admin_email,
        is_admin_email,
        list_admin_emails,
        remove_admin_email,
        setup_auth
    )

    client = setup_test_app(tmp_path, monkeypatch)

    # 1. Initially, non-admin email returns False
    assert is_admin_email(db, "teacher@gmail.com") is False

    # 2. Add admin email
    res = add_admin_email(db, "teacher@gmail.com", created_by="test-suite")
    assert res["email"] == "teacher@gmail.com"
    assert is_admin_email(db, "teacher@gmail.com") is True
    assert is_admin_email(db, "TEACHER@GMAIL.COM") is True  # Case insensitive

    # 3. Duplicate rejected
    with pytest.raises(HTTPException) as exc:
        add_admin_email(db, "Teacher@Gmail.com")
    assert exc.value.status_code == 400

    # 4. Invalid email format rejected
    for invalid in ["not-an-email", "foo@", "@bar.com", "", "   "]:
        with pytest.raises(HTTPException) as exc:
            add_admin_email(db, invalid)
        assert exc.value.status_code == 400

    # 5. List admin emails
    admins = list_admin_emails(db)
    emails = [a["email"] for a in admins]
    assert "teacher@gmail.com" in emails

    # 6. Remove admin email
    assert remove_admin_email(db, "teacher@gmail.com") is True
    assert is_admin_email(db, "teacher@gmail.com") is False
    assert remove_admin_email(db, "teacher@gmail.com") is False


def test_admin_email_from_env_variable(tmp_path, monkeypatch):
    from app.database import db
    from app.auth import is_admin_email, list_admin_emails, remove_admin_email

    monkeypatch.setenv("ADMIN_EMAILS", "superadmin@gmail.com, nckh.lead@gmail.com")
    setup_test_app(tmp_path, monkeypatch)

    assert is_admin_email(db, "superadmin@gmail.com") is True
    assert is_admin_email(db, "nckh.lead@gmail.com") is True
    assert is_admin_email(db, "other@gmail.com") is False

    # Env admin shows in list
    admins = list_admin_emails(db)
    emails = [a["email"] for a in admins]
    assert "superadmin@gmail.com" in emails

    # Removing env admin raises error
    with pytest.raises(HTTPException) as exc:
        remove_admin_email(db, "superadmin@gmail.com")
    assert exc.value.status_code == 400


def test_google_login_auto_grants_admin_session(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    from app import main

    # Add admin email
    main.add_admin_email(main.db, "admin.researcher@gmail.com", created_by="test")

    # Mock Google ID token
    monkeypatch.setattr(main, "verify_google_id_token", lambda credential: {
        "sub": "google-admin-123",
        "email": "admin.researcher@gmail.com",
        "name": "Dr. Researcher",
        "picture": "https://example.com/avatar.jpg"
    })

    # Google auth
    res = client.post("/api/v1/auth/google", json={"credential": "valid-google-cred"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["is_admin"] is True
    assert data["role"] == "admin"
    assert data["admin_token"] is not None
    admin_token = data["admin_token"]

    # Verify that the returned admin_token can access protected admin routes
    stats_res = client.get("/api/v1/admin/stats", headers={"x-admin-key": admin_token})
    assert stats_res.status_code == 200


def test_admin_email_management_endpoints_require_admin(tmp_path, monkeypatch):
    from app import main

    client = setup_test_app(tmp_path, monkeypatch)

    # Unauthorized access rejected
    assert client.get("/api/v1/admin/admins").status_code == 403
    assert client.post("/api/v1/admin/admins", json={"email": "new@gmail.com"}).status_code == 403
    assert client.delete("/api/v1/admin/admins/new@gmail.com").status_code == 403
    assert client.get("/api/v1/admin/participants").status_code == 403

    # Authorized with admin key
    headers = {"x-admin-key": "test-only-admin-secret"}

    # Add admin via API
    add_res = client.post("/api/v1/admin/admins", json={"email": "colleague@gmail.com"}, headers=headers)
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "success"

    # List admins via API
    list_res = client.get("/api/v1/admin/admins", headers=headers)
    assert list_res.status_code == 200
    admins = list_res.json()["admins"]
    assert any(a["email"] == "colleague@gmail.com" for a in admins)

    # Participants list via API
    part_res = client.get("/api/v1/admin/participants", headers=headers)
    assert part_res.status_code == 200

    # Delete admin via API
    del_res = client.delete("/api/v1/admin/admins/colleague@gmail.com", headers=headers)
    assert del_res.status_code == 200

    # Delete again -> 404
    del_res2 = client.delete("/api/v1/admin/admins/colleague@gmail.com", headers=headers)
    assert del_res2.status_code == 404
