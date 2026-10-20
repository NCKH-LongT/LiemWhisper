import base64
from email import message_from_bytes
from unittest.mock import Mock

import pytest
import requests
from test_collection import setup_test_app


def prepare(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_api")
    from app.database import db
    with db() as c:
        c.execute("""INSERT INTO participants(id,token_hash,participant_code,consent_version,consent_at,survey,email,name,completed_at)
            VALUES ('mail-p','mail-token','MAIL1','v1',1,'{}','student@example.com','Student',1)""")
        from app.email_delivery import enqueue_email
        enqueue_email(c, "mail-p")
    return client, db


def test_failed_retry_and_unknown_are_not_resent(tmp_path, monkeypatch):
    client, db = prepare(tmp_path, monkeypatch)
    from app.email_delivery import process_email_queue
    sender = Mock(return_value={"sent": False, "reason": "gmail_permission_required"})
    monkeypatch.setattr("app.mailer.send_thank_you_email", sender)
    process_email_queue(db)
    process_email_queue(db)
    assert sender.call_count == 1
    url = "/api/v1/admin/email/mail-p/retry"
    assert client.post(url).status_code == 403
    headers = {"x-admin-key": "test-only-admin-secret"}
    assert client.post(url, headers=headers).status_code == 200
    sender.return_value = {"sent": False, "status": "unknown", "reason": "delivery_unknown"}
    process_email_queue(db)
    assert client.post(url, headers=headers).status_code == 409
    process_email_queue(db)
    assert sender.call_count == 2
    status = client.get("/api/v1/admin/email/status", headers=headers).json()
    assert status["deliveries"][0]["status"] == "unknown"


@pytest.mark.parametrize("outcome, expected", [("success", True), ("denied", False), ("timeout", False)])
def test_gmail_transport(tmp_path, monkeypatch, outcome, expected):
    _, db = prepare(tmp_path, monkeypatch)
    with db() as c:
        c.execute("""INSERT INTO drive_connection(id,account_id,account_email,folder_id,refresh_token_enc,created_at,updated_at)
            VALUES ('default','google-id','sender@example.com','folder','encrypted',1,1)""")
        c.execute("""INSERT INTO gmail_authorization VALUES ('default','https://www.googleapis.com/auth/gmail.send',1)""")
    drive = Mock()
    drive._get_access_token.return_value = "fake-access-token"
    monkeypatch.setattr("app.drive.get_drive_client", lambda _: drive)
    post = Mock()
    if outcome == "timeout":
        post.side_effect = requests.Timeout()
    else:
        post.return_value = Mock(status_code=200 if expected else 403, ok=expected)
        post.return_value.json.return_value = {"id": "gmail-id"}
    monkeypatch.setattr("app.mailer.requests.post", post)
    from app.mailer import send_thank_you_email
    result = send_thank_you_email("student@example.com", "<Student>", "MAIL1", 5, db_factory=db)
    assert result["sent"] is expected
    if outcome == "timeout":
        assert result["status"] == "unknown"
    payload = post.call_args.kwargs["json"]
    message = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
    assert message["From"] == "sender@example.com"
    assert message["To"] == "student@example.com"
    assert post.call_args.args[0] == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def test_parallel_workers_claim_once(tmp_path, monkeypatch):
    _, db = prepare(tmp_path, monkeypatch)
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.email_delivery import process_email_queue
    entered, release = Event(), Event()
    def send(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return {"sent": True, "message_id": "once"}
    sender = Mock(side_effect=send)
    monkeypatch.setattr("app.mailer.send_thank_you_email", sender)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(process_email_queue, db)
        try:
            assert entered.wait(10)
            second = pool.submit(process_email_queue, db)
            second.result(timeout=10)
        finally:
            release.set()
        first.result(timeout=10)
    assert sender.call_count == 1


def test_missing_permission_does_not_send(tmp_path, monkeypatch):
    _, db = prepare(tmp_path, monkeypatch)
    post = Mock(side_effect=AssertionError("Must not send without authorization"))
    monkeypatch.setattr("app.mailer.requests.post", post)
    from app.mailer import send_thank_you_email
    result = send_thank_you_email("student@example.com", "Student", "MAIL1", 5, db_factory=db)
    assert result == {"sent": False, "reason": "gmail_not_connected"}
    post.assert_not_called()
