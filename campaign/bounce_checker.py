"""
campaign/bounce_checker.py
Tự động đồng bộ các thư bị trả về (Mailer-Daemon / 550 No Such User) từ hòm thư Gmail.
Cập nhật trạng thái EmailLog và Contact trong Database.
"""
import imaplib
import email
import re
from email.header import decode_header
from typing import List, Dict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import EMAIL_CONFIG
from database.models import get_session, EmailLog, Contact, Hotel


def sync_email_bounces(max_emails_to_check: int = 100) -> Dict:
    """
    Quét hộp thư Gmail để tìm các thông báo Mailer-Daemon / Address not found.
    Cập nhật status trong EmailLog thành '❌ Bị trả về (550 No Such User)'.
    """
    user = EMAIL_CONFIG.get("smtp_user")
    password = EMAIL_CONFIG.get("smtp_password")

    if not user or not password:
        return {"success": False, "error": "Chưa cấu hình SMTP/IMAP credentials", "bounced_count": 0}

    bounced_emails = set()

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.select("INBOX")

        # Tìm các email từ mailer-daemon hoặc có thông báo failure
        status, messages = mail.search(None, '(FROM "mailer-daemon")')
        if status != "OK" or not messages[0]:
            mail.logout()
            return {"success": True, "bounced_count": 0, "bounced_list": []}

        mail_ids = messages[0].split()
        # Lấy tối đa N thư gần nhất
        recent_ids = mail_ids[-max_emails_to_check:]

        for m_id in recent_ids:
            try:
                res, msg_data = mail.fetch(m_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        body_text = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                ctype = part.get_content_type()
                                cdisp = str(part.get("Content-Disposition"))
                                if ctype in ["text/plain", "text/html"] and "attachment" not in cdisp:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body_text += payload.decode(errors="ignore") + "\n"
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(errors="ignore")

                        # Bắt các pattern email bị lỗi (e.g. "Your message wasn't delivered to xxx@domain")
                        # "550" or "No Such User" or "wasn't delivered to"
                        matches = re.findall(r'(?:wasn\'t delivered to|failed permanently to|undelivered to|delivery to)\s+<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?', body_text, re.IGNORECASE)
                        for m in matches:
                            bounced_emails.add(m.lower().strip())

                        # Thêm pattern generic trong body có 550
                        if "550" in body_text or "No Such User" in body_text or "Address not found" in body_text:
                            all_found = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', body_text)
                            for f in all_found:
                                f_lower = f.lower().strip()
                                if f_lower not in [user.lower(), "sales@haphong.com", "mailer-daemon@googlemail.com"]:
                                    bounced_emails.add(f_lower)
            except Exception:
                continue

        mail.logout()

        # Cập nhật Database
        session = get_session()
        updated_logs = 0
        updated_contacts = 0

        for b_email in bounced_emails:
            # 1. Cập nhật EmailLog
            logs = session.query(EmailLog).join(Contact).filter(Contact.email == b_email).all()
            for l in logs:
                if l.status != "❌ Bị trả về (550 No Such User)":
                    l.status = "❌ Bị trả về (550 No Such User)"
                    updated_logs += 1

            # 2. Cập nhật Contact
            contacts = session.query(Contact).filter(Contact.email == b_email).all()
            for c in contacts:
                c.verify_status = "INVALID"
                c.confidence = 0
                updated_contacts += 1

        session.commit()
        session.close()

        return {
            "success": True,
            "bounced_count": len(bounced_emails),
            "updated_logs": updated_logs,
            "updated_contacts": updated_contacts,
            "bounced_list": list(bounced_emails)
        }

    except Exception as e:
        return {"success": False, "error": str(e), "bounced_count": 0}


if __name__ == "__main__":
    res = sync_email_bounces(50)
    print(res)
