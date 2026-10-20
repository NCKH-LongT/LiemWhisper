"""Email notifications for participant session completion."""
import os
import base64
import logging
from html import escape
import requests
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict


def send_thank_you_email(
    to_email: str,
    participant_name: str,
    participant_code: str,
    total_recordings: int,
    course_title: str = "Phiên thu âm LiemWhisper",
    db_factory=None
) -> Dict[str, Any]:
    """Send a formal thank-you email to research participant upon session completion."""
    if not to_email or "@" not in to_email:
        return {"sent": False, "reason": "invalid_email", "recipient": to_email}

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = os.getenv("SMTP_PORT", "587").strip() or "587"
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip() or os.getenv("GMAIL_APP_PASSWORD", "").strip()
    from_name = os.getenv("SMTP_FROM_NAME", "Dự án NCKH LiemWhisper").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", "").strip() or smtp_user or "noreply@liemwhisper.edu.vn"

    display_name = participant_name.strip() or participant_code or "Bạn"

    subject = f"[LiemWhisper NCKH] Thư cảm ơn đóng góp dữ liệu giọng nói kỹ thuật - {participant_code or display_name}"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 24px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; padding: 28px 24px; text-align: center; }}
        .badge {{ display: inline-block; background: #22c55e; color: #ffffff; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }}
        .title {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }}
        .body {{ padding: 28px 24px; }}
        .greeting {{ font-size: 16px; font-weight: 600; color: #0f172a; margin-bottom: 12px; }}
        .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 18px 0; }}
        .row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed #cbd5e1; font-size: 13px; }}
        .row:last-child {{ border-bottom: none; }}
        .label {{ color: #64748b; font-weight: 500; }}
        .value {{ color: #0f172a; font-weight: 600; text-align: right; }}
        .footer {{ background: #f1f5f9; padding: 18px 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div class="badge">Xác nhận hoàn thành</div>
          <h1 class="title">Đề tài Nghiên cứu Khoa học LiemWhisper</h1>
        </div>
        <div class="body">
          <div class="greeting">Xin chào {escape(display_name)},</div>
          <p>
            Thay mặt nhóm nghiên cứu đề tài <strong>LiemWhisper</strong> (<em>Mô hình nhận dạng giọng nói tiếng Việt chêm thuật ngữ kỹ thuật - Code-Switched Speech</em>), chúng tôi xin gửi lời cảm ơn chân thành nhất đến bạn vì đã dành thời gian quý báu tham gia thu âm đóng góp cho bộ ngữ liệu khoa học.
          </p>
          <div class="card">
            <div style="font-size: 13px; font-weight: 700; color: #334155; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.04em;">Thông tin ghi nhận đóng góp</div>
            <div class="row"><span class="label">Mã định danh tham gia:</span><span class="value">{escape(participant_code or "N/A")}</span></div>
            <div class="row"><span class="label">Chủ đề thu âm:</span><span class="value">{escape(course_title)}</span></div>
            <div class="row"><span class="label">Tổng số câu đã hoàn thành:</span><span class="value">{total_recordings} câu</span></div>
            <div class="row"><span class="label">Tình trạng:</span><span class="value" style="color: #16a34a;">Đã ghi nhận phiên thu âm</span></div>
          </div>
          <p style="font-size: 13px; color: #475569;">
            Dữ liệu âm thanh của bạn đã được lưu trữ an toàn, phục vụ mục đích huấn luyện mô hình AI học thuật và hoàn toàn tuân thủ các cam kết bảo mật quyền riêng tư đã nêu trong bản thỏa thuận đồng thuận tham gia nghiên cứu.
          </p>
          <p style="margin-top: 20px; font-size: 14px; color: #0f172a;">
            Trân trọng cảm ơn sự đóng góp quý báu của bạn cho nghiên cứu khoa học!<br>
            <strong>Nhóm Nghiên cứu LiemWhisper</strong>
          </p>
        </div>
        <div class="footer">
          Email này được gửi tự động từ Hệ thống Thu thập Dữ liệu LiemWhisper.<br>
          © 2026 LiemWhisper Research Project.
        </div>
      </div>
    </body>
    </html>
    """

    plain_content = f"""Xin chào {display_name},

Thay mặt nhóm nghiên cứu đề tài LiemWhisper (Mô hình nhận dạng giọng nói tiếng Việt chêm thuật ngữ kỹ thuật - Code-Switched Speech), chúng tôi xin gửi lời cảm ơn chân thành nhất đến bạn vì đã dành thời gian quý báu tham gia thu âm đóng góp cho bộ ngữ liệu khoa học.

THÔNG TIN GHI NHẬN ĐÓNG GÓP:
- Mã định danh tham gia: {participant_code or "N/A"}
- Chủ đề thu âm: {course_title}
- Tổng số câu hoàn thành: {total_recordings} câu
- Tình trạng: Đã hoàn tất thành công

Dữ liệu âm thanh của bạn được lưu trữ an toàn phục vụ mục đích nghiên cứu học thuật và tuân thủ thỏa thuận bảo mật quyền riêng tư.

Trân trọng,
Nhóm Nghiên cứu LiemWhisper
"""

    provider = os.getenv("EMAIL_PROVIDER", "gmail_api").strip().lower()
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["To"] = to_email
        msg.attach(MIMEText(plain_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        if provider == "gmail_api":
            return _send_gmail(msg, db_factory)
        if provider != "smtp":
            return {"sent": False, "reason": "invalid_provider"}
        if not smtp_user or not smtp_password:
            return {"sent": False, "simulated": True, "reason": "smtp_not_configured", "recipient": to_email, "subject": subject}
        smtp_port = int(smtp_port)
        msg["From"] = f"{from_name} <{from_email}>"
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())

        return {"sent": True, "provider": "smtp", "recipient": to_email}
    except smtplib.SMTPAuthenticationError:
        return {"sent": False, "reason": "smtp_auth_failed"}
    except Exception:
        logging.getLogger(__name__).warning("Thank-you email SMTP operation failed")
        return {"sent": False, "reason": "delivery_unknown", "status": "unknown"}


def _send_gmail(msg, db_factory):
    if db_factory is None:
        return {"sent": False, "reason": "gmail_not_connected"}
    from app.drive import get_drive_client
    with db_factory() as c:
        account = c.execute("SELECT account_email FROM drive_connection WHERE id='default'").fetchone()
        grant = c.execute("SELECT scopes FROM gmail_authorization WHERE id='default'").fetchone()
    if not account or not account["account_email"]:
        return {"sent": False, "reason": "gmail_not_connected"}
    if not grant or "https://www.googleapis.com/auth/gmail.send" not in grant["scopes"].split():
        return {"sent": False, "reason": "gmail_permission_required"}
    try:
        access_token = get_drive_client(db_factory)._get_access_token()
    except Exception:
        return {"sent": False, "reason": "gmail_reconnect_required"}
    msg["From"] = account["account_email"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    try:
        response = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw}, timeout=20,
        )
    except requests.RequestException:
        # The provider may have accepted the message before the connection failed.
        return {"sent": False, "status": "unknown", "reason": "delivery_unknown"}
    if response.status_code in (401, 403):
        return {"sent": False, "reason": "gmail_permission_or_api_disabled"}
    if response.status_code == 429:
        return {"sent": False, "reason": "gmail_rate_limited"}
    if response.status_code >= 500:
        return {"sent": False, "status": "unknown", "reason": "delivery_unknown"}
    if not response.ok:
        return {"sent": False, "reason": "gmail_rejected"}
    try:
        message_id = response.json().get("id")
    except (ValueError, AttributeError):
        message_id = None
    if not message_id:
        return {"sent": False, "status": "unknown", "reason": "delivery_unknown"}
    return {"sent": True, "provider": "gmail_api", "message_id": message_id}
