"""
campaign/email_sender.py — Gửi email thông minh, tránh spam
"""
import smtplib
import ssl
import certifi
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime
from typing import Optional, Dict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import EMAIL_CONFIG, APP_CONFIG


def build_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    reply_to: Optional[str] = None,
) -> MIMEMultipart:
    """Tạo email MIME đúng chuẩn chống spam"""
    # Sử dụng email chính danh doanh nghiệp sales@haphong.com
    actual_sender = EMAIL_CONFIG.get("sender_email") or "sales@haphong.com"
    sender_name   = EMAIL_CONFIG["sender_name"]

    msg = MIMEMultipart("alternative")
    msg["From"]     = formataddr((sender_name, actual_sender))
    msg["To"]       = formataddr((to_name, to_email)) if to_name else to_email
    msg["Subject"]  = subject
    msg["Reply-To"] = reply_to or actual_sender

    # Message-ID & Date chuẩn RFC
    from email.utils import make_msgid, formatdate
    msg["Message-ID"] = make_msgid(domain="haphong.com")
    msg["Date"]       = formatdate(localtime=True)

    # Plain text version (bắt buộc để đạt điểm Inbox cao)
    plain = html_to_plain(html_body)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    return msg


def html_to_plain(html: str) -> str:
    """Chuyển HTML sang plain text đơn giản"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
) -> Dict:
    """
    Gửi 1 email qua Gmail SMTP.
    Trả về: {"success": True/False, "error": "..."}
    """
    try:
        msg = build_email(to_email, to_name, subject, html_body)

        context = ssl.create_default_context(cafile=certifi.where())
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
            server.sendmail(
                EMAIL_CONFIG["sender_email"],
                to_email,
                msg.as_string()
            )

        print(f"  ✅ Đã gửi → {to_email}")
        return {"success": True, "error": None}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Auth failed — kiểm tra App Password"}
    except smtplib.SMTPRecipientsRefused:
        return {"success": False, "error": "Email không tồn tại"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_with_delay(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    min_delay: int = None,
    max_delay: int = None,
) -> Dict:
    """
    Gửi email + delay ngẫu nhiên sau đó (tránh spam filter).
    Delay mặc định: 5–20 phút.
    """
    result = send_email(to_email, to_name, subject, html_body)

    min_d = min_delay or APP_CONFIG["min_delay_between_emails"]
    max_d = max_delay or APP_CONFIG["max_delay_between_emails"]
    delay = random.randint(min_d, max_d)

    print(f"  ⏳ Chờ {delay//60} phút {delay%60} giây trước email tiếp theo...")
    time.sleep(delay)

    return result


def test_smtp_connection() -> Dict:
    """Test kết nối SMTP, trả về kết quả"""
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
        return {"success": True, "message": "✅ Kết nối SMTP thành công!"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "❌ Lỗi xác thực — kiểm tra App Password"}
    except Exception as e:
        return {"success": False, "message": f"❌ Lỗi: {e}"}
