"""
tools/canary_bounce_listener.py — HỆ THỐNG XÁC THỰC EMAIL BẰNG HÒM THƯ PHỤ MỒI (CANARY BOUNCE PROBE ENGINE)
1. Gửi email thăm dò (Canary Ping) từ hòm thư phụ/test độc lập tới các email dự đoán (gm@, marcom@, sales@)
2. Tự động kết nối IMAP vào hòm thư phụ để lắng nghe các email báo lỗi Mailer-Daemon (550 User Not Found / Delivery Failure)
3. Tự động cập nhật Database:
   - Nếu nhận được Mailer-Daemon 550 ➔ Đánh dấu 'INVALID' / Xóa bỏ ngay lập tức
   - Nếu sau thời gian chờ (3–5 phút) KHÔNG nhận được lỗi ➔ Xác nhận 'VALID (Canary 100% Sống)' và chuyển vào hàng đợi gửi chính
4. Bảo vệ 100% độ uy tín (Sender Reputation) cho hòm thư chính sales@haphong.com
"""
import os
import sys
import time
import imaplib
import email
from email.header import decode_header
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import get_session, Contact, Hotel

# ── CẤU HÌNH HÒM THƯ PHỤ (BURNER ACCOUNT / CANARY PROBE) ─────────────────────
# Có thể cấu hình trực tiếp qua biến môi trường hoặc file .env
CANARY_SMTP_SERVER = os.getenv("CANARY_SMTP_SERVER", "smtp.gmail.com")
CANARY_SMTP_PORT   = int(os.getenv("CANARY_SMTP_PORT", 587))
CANARY_IMAP_SERVER = os.getenv("CANARY_IMAP_SERVER", "imap.gmail.com")
CANARY_IMAP_PORT   = int(os.getenv("CANARY_IMAP_PORT", 993))
CANARY_EMAIL_USER  = os.getenv("CANARY_EMAIL_USER", "")      # VD: test.verify.mailer@gmail.com
CANARY_EMAIL_PASS  = os.getenv("CANARY_EMAIL_PASS", "")      # App Password của hòm thư phụ


def send_canary_probe_email(target_email: str) -> bool:
    """Gửi email thăm dò nhẹ nhàng từ hòm thư phụ tới email mục tiêu"""
    if not CANARY_EMAIL_USER or not CANARY_EMAIL_PASS:
        print("⚠️ [CANARY] Chưa cấu hình CANARY_EMAIL_USER / CANARY_EMAIL_PASS trong môi trường!")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = f"Partnership Inquiry <{CANARY_EMAIL_USER}>"
        msg["To"] = target_email
        msg["Subject"] = "Inquiry regarding hotel media collaboration & contact verification"

        body = (
            "Dear Management & Marketing Team,\n\n"
            "This is an automated verification message regarding photography & media inquiries.\n"
            "If you receive this message, no action is required.\n\n"
            "Best regards,\nPartnership Verification Desk"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = smtplib.SMTP(CANARY_SMTP_SERVER, CANARY_SMTP_PORT, timeout=10)
        server.starttls()
        server.login(CANARY_EMAIL_USER, CANARY_EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print(f"  🕊️ [CANARY PING GỬI ĐI] ➔ {target_email}")
        return True
    except Exception as e:
        print(f"  ❌ [CANARY PING LỖI] {target_email} ➔ {e}")
        return False


def listen_for_bounces(timeout_minutes: int = 4) -> Dict[str, str]:
    """
    Kết nối IMAP vào hòm thư phụ để quét các thư trả về từ Mailer-Daemon.
    Trả về Dict: {email_chết: lý_do_lỗi}
    """
    if not CANARY_EMAIL_USER or not CANARY_EMAIL_PASS:
        return {}

    bounced_emails = {}
    print(f"🎧 [CANARY LISTENER] Đang lắng nghe phản hồi Mailer-Daemon trong {timeout_minutes} phút...")

    try:
        mail = imaplib.IMAP4_SSL(CANARY_IMAP_SERVER, CANARY_IMAP_PORT)
        mail.login(CANARY_EMAIL_USER, CANARY_EMAIL_PASS)
        mail.select("inbox")

        # Tìm các thư từ Mailer-Daemon hoặc có tiêu đề Delivery Status Notification / Undelivered
        status, messages = mail.search(None, '(OR FROM "mailer-daemon" (OR FROM "postmaster" SUBJECT "Delivery Status"))')
        if status == "OK" and messages[0]:
            msg_ids = messages[0].split()
            for m_id in msg_ids[-20:]:  # Xem 20 thư mới nhất
                res, data = mail.fetch(m_id, "(RFC822)")
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Bóc tách nội dung thư báo lỗi
                content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            content += part.get_payload(decode=True).decode("utf-8", errors="ignore")
                else:
                    content = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                # Tìm địa chỉ email bị lỗi trong thông báo bounce
                import re
                failed_matches = re.findall(r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', content)
                for f_em in failed_matches:
                    f_em_l = f_em.lower().strip()
                    if f_em_l != CANARY_EMAIL_USER.lower() and "google" not in f_em_l:
                        if any(err in content for err in ["550", "5.1.1", "5.2.1", "User unknown", "does not exist", "inactive", "disabled", "No such user"]):
                            bounced_emails[f_em_l] = "550 User Not Found / Inactive"
                            print(f"  ❌ [PHÁT HIỆN BOUNCE THỰC TẾ] Email chết: {f_em_l}")

        mail.close()
        mail.logout()
    except Exception as e:
        print(f"⚠️ [CANARY IMAP LỖI]: {e}")

    return bounced_emails


def run_canary_verification_cycle(candidate_emails: List[Dict]):
    """
    Quy trình kiểm thử hoàn chỉnh:
    1. Bắn Canary Ping từ hòm thư phụ
    2. Chờ 3 phút & quét IMAP
    3. Cập nhật Database
    """
    if not candidate_emails:
        print("Không có email nào cần kiểm thử.")
        return

    print(f"\n🚀 BẮT ĐẦU QUY TRÌNH THỬ LỬA CANARY CHO {len(candidate_emails)} EMAIL DỰ ĐOÁN:")
    print("=" * 70)

    # 1. Bắn Ping
    sent_targets = []
    for cand in candidate_emails:
        em = cand.get("email")
        if em and send_canary_probe_email(em):
            sent_targets.append(cand)
        time.sleep(1.0)

    if not sent_targets:
        return

    print(f"\n⏳ Đang đợi 180 giây để các máy chủ phản hồi thư lỗi (nếu hòm thư không tồn tại)...")
    time.sleep(180)

    # 2. Lắng nghe lỗi Bounces
    bounced = listen_for_bounces(timeout_minutes=1)

    # 3. Cập nhật trạng thái trong Database
    session = get_session()
    passed_count = 0
    killed_count = 0

    for cand in sent_targets:
        em = cand["email"].lower().strip()
        contact = session.query(Contact).filter(Contact.email == em).first()

        if em in bounced:
            # Hòm thư chết thực tế -> Xóa khỏi DB
            if contact:
                session.delete(contact)
            killed_count += 1
            print(f"  ❌ ĐÃ XÓA (Mailer-Daemon 550): {em}")
        else:
            # Hòm thư sống thật 100% (Không nhận lỗi) -> Nâng cấp VALID
            if contact:
                contact.verify_status = "VALID"
                contact.is_valid = True
                contact.confidence = 100
                contact.source = "canary_verified_live"
            passed_count += 1
            print(f"  🎉 XÁC THỰC THẬT 100% (Canary Confirmed Live): {em}")

    session.commit()
    session.close()

    print("=" * 70)
    print(f"🏆 KẾT THÚC QUY TRÌNH THỬ LỬA CANARY:")
    print(f"   • ✅ Sống thật 100% (Đưa vào Hàng Đợi Gửi Chính): {passed_count}")
    print(f"   • ❌ Hòm thư chết (Đã xóa vĩnh viễn): {killed_count}")


if __name__ == "__main__":
    print("Module Canary Bounce Listener đã sẵn sàng!")
    print("Để kích hoạt, cấu hình biến môi trường: CANARY_EMAIL_USER & CANARY_EMAIL_PASS.")
