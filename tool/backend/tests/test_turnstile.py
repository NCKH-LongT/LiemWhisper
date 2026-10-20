import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import turnstile


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TURNSTILE_ALLOWED_HOSTNAMES", "example.com")


def test_valid_token(monkeypatch):
    post = Mock(return_value=Mock(json=lambda: {
        "success": True, "action": "google_login", "hostname": "example.com",
    }))
    monkeypatch.setattr(turnstile.requests, "post", post)
    turnstile.verify_turnstile("token", "google_login")
    assert post.call_args.kwargs["timeout"] == 10
    assert post.call_args.kwargs["data"] == {"secret": "test-secret", "response": "token"}


@pytest.mark.parametrize("result", [
    {"success": False, "error-codes": ["timeout-or-duplicate"]},
    {"success": True, "action": "signup", "hostname": "example.com"},
    {"success": True, "action": "google_login", "hostname": "attacker.com"},
])
def test_rejects_invalid_reused_or_wrong_context(monkeypatch, result):
    monkeypatch.setattr(turnstile.requests, "post", Mock(return_value=Mock(json=lambda: result)))
    with pytest.raises(turnstile.HTTPException) as error:
        turnstile.verify_turnstile("token", "google_login")
    assert error.value.status_code == 400


def test_missing_token_does_not_contact_cloudflare(monkeypatch):
    post = Mock()
    monkeypatch.setattr(turnstile.requests, "post", post)
    with pytest.raises(turnstile.HTTPException):
        turnstile.verify_turnstile("", "admin_login")
    post.assert_not_called()


def test_network_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(turnstile.requests, "post", Mock(side_effect=turnstile.requests.Timeout))
    with pytest.raises(turnstile.HTTPException) as error:
        turnstile.verify_turnstile("token", "admin_login")
    assert error.value.status_code == 503


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("TURNSTILE_SECRET_KEY")
    with pytest.raises(turnstile.HTTPException) as error:
        turnstile.verify_turnstile("token", "admin_login")
    assert error.value.status_code == 503


def test_unconfigured_local_development(monkeypatch):
    monkeypatch.delenv("TURNSTILE_SECRET_KEY")
    monkeypatch.setenv("TURNSTILE_ENABLED", "false")
    turnstile.verify_turnstile("", "admin_login")
