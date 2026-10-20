"""Durable thank-you delivery with atomic claiming and automatic retries."""
import logging
import time

REASONS = {
    "gmail_not_connected": "Chưa liên kết tài khoản Google gửi thư.",
    "gmail_permission_required": "Bật Gmail API trong Google Cloud rồi liên kết lại Google Drive để cấp quyền gửi thư.",
    "gmail_reconnect_required": "Phiên Google không hợp lệ. Vui lòng liên kết lại Google Drive.",
    "gmail_permission_or_api_disabled": "Kiểm tra Gmail API đã bật và đã cấp quyền gửi thư khi liên kết lại Google.",
    "gmail_rate_limited": "Google giới hạn gửi thư. Có thể thử lại sau.",
    "gmail_rejected": "Google từ chối thư. Kiểm tra địa chỉ người nhận.",
    "smtp_not_configured": "Chưa cấu hình SMTP.",
    "smtp_auth_failed": "SMTP từ chối thông tin đăng nhập.",
    "invalid_provider": "EMAIL_PROVIDER không hợp lệ.",
    "invalid_email": "Người tham gia chưa có email hợp lệ.",
    "delivery_unknown": "Chưa xác định Google đã nhận thư hay chưa. Kiểm tra thư đã gửi; hệ thống không tự gửi lại để tránh trùng.",
}


def init_email_tables(db):
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS gmail_authorization (
            id TEXT PRIMARY KEY, scopes TEXT NOT NULL, updated_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS email_deliveries (
            participant_id TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            reason TEXT, provider_message_id TEXT, updated_at INTEGER NOT NULL)""")


def delivery_status(c, pid):
    row = c.execute("SELECT status,reason,attempts,updated_at FROM email_deliveries WHERE participant_id=?", (pid,)).fetchone()
    if not row:
        return {"status": "untracked", "sent": False, "message": "Chưa có lịch sử gửi thư được xác minh."}
    result = dict(row)
    result["sent"] = result["status"] == "sent"
    result["message"] = REASONS.get(result.get("reason"), "")
    return result


def enqueue_email(c, pid):
    c.execute("""INSERT INTO email_deliveries(participant_id,status,updated_at)
        VALUES (?, 'pending', ?) ON CONFLICT(participant_id) DO NOTHING""", (pid, int(time.time())))


def process_email_queue(db, limit=5):
    from app.mailer import send_thank_you_email
    now = int(time.time())
    with db() as c:
        # A crash after send may have delivered the email. Never retry blindly.
        c.execute("""UPDATE email_deliveries SET status='unknown',reason='delivery_unknown'
            WHERE status='sending' AND updated_at < ?""", (now - 300,))
        # Retry only confirmed failures. Ambiguous sends remain unknown to prevent duplicates.
        failed = c.execute("SELECT participant_id,reason,attempts,updated_at FROM email_deliveries WHERE status='failed'").fetchall()
        retryable = {"gmail_not_connected", "gmail_permission_required", "gmail_reconnect_required",
                     "gmail_permission_or_api_disabled", "gmail_rate_limited", "smtp_not_configured", "smtp_auth_failed"}
        for row in failed:
            delay = min(3600, 60 * (2 ** min(max(row["attempts"] - 1, 0), 6)))
            if row["reason"] in retryable and now - row["updated_at"] >= delay:
                c.execute("UPDATE email_deliveries SET status='pending' WHERE participant_id=? AND status='failed'",
                          (row["participant_id"],))
        pending = c.execute("SELECT participant_id FROM email_deliveries WHERE status='pending' ORDER BY updated_at LIMIT ?", (limit,)).fetchall()
    for item in pending:
        pid = item["participant_id"]
        with db() as c:
            claimed = c.execute("""UPDATE email_deliveries SET status='sending',attempts=attempts+1,updated_at=?
                WHERE participant_id=? AND status='pending' RETURNING participant_id""", (int(time.time()), pid)).fetchone()
            if not claimed:
                continue
            person = c.execute("SELECT email,name,participant_code,completed_at FROM participants WHERE id=?", (pid,)).fetchone()
            if not person or not person["completed_at"]:
                c.execute("DELETE FROM email_deliveries WHERE participant_id=?", (pid,))
                continue
            count = c.execute("SELECT COUNT(*) FROM recordings WHERE participant_id=?", (pid,)).fetchone()[0]
        try:
            result = send_thank_you_email(
                person["email"] or "", person["name"] or "", person["participant_code"] or "",
                count, db_factory=db,
            )
        except Exception:
            logging.getLogger(__name__).exception("Thank-you email worker failed")
            result = {"sent": False, "status": "unknown", "reason": "delivery_unknown"}
        status = "sent" if result.get("sent") else ("unknown" if result.get("status") == "unknown" else "failed")
        if status != "sent":
            logging.getLogger(__name__).warning(
                "Thank-you delivery status=%s reason=%s", status, result.get("reason", "unspecified")
            )
        with db() as c:
            c.execute("""UPDATE email_deliveries SET status=?,reason=?,provider_message_id=?,updated_at=?
                WHERE participant_id=? AND status IN ('sending','unknown')""",
                (status, result.get("reason"), result.get("message_id"), int(time.time()), pid))
