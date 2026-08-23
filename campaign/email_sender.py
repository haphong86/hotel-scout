"""
campaign/email_sender.py — Gửi email thông minh, tránh spam
"""
import socket

# Ép buộc Socket phân giải IPv4 trên Railway/Linux Container để triệt tiêu lỗi [Errno 101] Network is unreachable
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except Exception:
        return _orig_getaddrinfo(host, port, 0, type, proto, flags)

socket.getaddrinfo = _ipv4_only_getaddrinfo

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


def get_smtp_session(timeout: int = 15):
    """
    Kết nối SMTP thông minh:
    1. Thử Port 465 (SSL trực tiếp — siêu nhanh, tránh treo timeout trên cloud)
    2. Fallback sang Port 587 (STARTTLS)
    """
    context = ssl.create_default_context(cafile=certifi.where())
    smtp_server = EMAIL_CONFIG.get("smtp_server", "smtp.gmail.com")
    user = EMAIL_CONFIG.get("smtp_user")
    pwd = EMAIL_CONFIG.get("smtp_password")

    # Ưu tiên Port 465 (SSL)
    try:
        server = smtplib.SMTP_SSL(smtp_server, 465, context=context, timeout=timeout)
        server.ehlo("haphong.com")
        server.login(user, pwd)
        return server
    except Exception:
        pass

    # Fallback Port 587
    server = smtplib.SMTP(smtp_server, 587, timeout=timeout)
    server.ehlo("haphong.com")
    server.starttls(context=context)
    server.ehlo("haphong.com")
    server.login(user, pwd)
    return server


def send_email(
    to_email: str,
    arg2: str = "",
    arg3: str = "",
    arg4: str = "",
    to_name: str = "",
    subject: str = "",
    html_body: str = "",
    is_html: bool = True,
    **kwargs
) -> Dict:
    """
    Gửi 1 email — ƯU TIÊN Resend API (Railway-safe), fallback sang Gmail SMTP.
    Hỗ trợ:
      1. send_email(to_email, subject, html_body)
      2. send_email(to_email, to_name, subject, html_body)
    """
    # Xử lý tham số linh hoạt
    if arg4:
        final_to_name = arg2
        final_subject = arg3
        final_body    = arg4
    elif arg3:
        final_to_name = to_name or "Quý Đối Tác"
        final_subject = arg2
        final_body    = arg3
    else:
        final_to_name = to_name or "Quý Đối Tác"
        final_subject = subject or arg2
        final_body    = html_body or ""

    # ── Ưu tiên 1: Resend API (HTTPS — không bị Railway chặn) ──
    resend_key = EMAIL_CONFIG.get("resend_api_key", "")
    if resend_key:
        try:
            import httpx
            payload = {
                "from": f"{EMAIL_CONFIG.get('sender_name', 'Hà Phong Visuals')} <{EMAIL_CONFIG.get('sender_email', 'sales@haphong.com')}>",
                "to": [to_email],
                "subject": final_subject,
                "html": final_body,
                "reply_to": EMAIL_CONFIG.get("sender_email", "sales@haphong.com"),
            }
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=20,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"success": True, "message_id": data.get("id", ""), "method": "resend"}
            else:
                # Resend thất bại → thử SMTP
                pass
        except Exception:
            pass  # Fallback sang SMTP

    # ── Fallback: Gmail SMTP (chỉ hoạt động local, Railway thường bị block) ──
    try:
        msg = build_email(
            to_email=to_email,
            to_name=final_to_name,
            subject=final_subject,
            html_body=final_body
        )
        server = get_smtp_session(timeout=15)
        sender_addr = EMAIL_CONFIG.get("smtp_user") or "haphong86@gmail.com"
        server.send_message(msg, from_addr=sender_addr, to_addrs=[to_email])
        server.quit()
        return {"success": True, "method": "smtp"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Auth failed — kiểm tra App Password Gmail"}
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
        server = get_smtp_session(timeout=10)
        server.quit()
        return {"success": True, "message": "✅ Kết nối SMTP thành công!"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "❌ Lỗi xác thực — kiểm tra App Password"}
    except Exception as e:
        return {"success": False, "message": f"❌ Lỗi: {e}"}
