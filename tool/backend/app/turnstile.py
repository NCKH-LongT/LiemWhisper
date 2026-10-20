"""Server-side Cloudflare Turnstile verification for public authentication."""
import os

import requests
from fastapi import HTTPException


def verify_turnstile(token: str, action: str) -> None:
    secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    enabled = os.getenv("TURNSTILE_ENABLED", "").lower() in {"1", "true", "yes"} or bool(secret)
    if not enabled:
        return
    if not secret:
        raise HTTPException(503, "CAPTCHA chưa được cấu hình trên máy chủ.")
    if not token or len(token) > 2048:
        raise HTTPException(400, "Vui lòng hoàn thành xác minh CAPTCHA.")
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(503, "Không thể xác minh CAPTCHA. Vui lòng thử lại.") from None
    if not isinstance(result, dict):
        raise HTTPException(503, "Phản hồi CAPTCHA không hợp lệ. Vui lòng thử lại.")
    allowed = {host.strip().lower() for host in os.getenv("TURNSTILE_ALLOWED_HOSTNAMES", "").split(",") if host.strip()}
    if (
        result.get("success") is not True
        or result.get("action") != action
        or (allowed and result.get("hostname", "").lower() not in allowed)
    ):
        raise HTTPException(400, "CAPTCHA không hợp lệ hoặc đã hết hạn. Vui lòng xác minh lại.")
