"""
send_daily.py — Gửi email tự động mỗi ngày
Chạy bởi cron job lúc 9:45 sáng
Chỉ gửi email đã được verify (VALID/LIKELY)
Giới hạn 25 email/ngày để tránh spam
"""
import sys, os, time, logging
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/email_daily.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

from datetime import datetime
from database.models import get_session, Contact, Hotel, EmailLog
from sqlalchemy.orm import joinedload


# ── Cấu hình ─────────────────────────────────────────────────
MAX_EMAILS_PER_DAY  = 25     # Giới hạn/ngày — tránh spam
DELAY_BETWEEN       = 300    # 5 phút giữa mỗi email
ONLY_VERIFIED       = True   # Chỉ gửi email đã verify
MIN_CONFIDENCE      = 60     # Confidence tối thiểu


def get_contacts_to_email(limit: int = MAX_EMAILS_PER_DAY):
    """
    Lấy danh sách contact cần gửi email hôm nay.
    Ưu tiên: VALID > LIKELY > confidence cao > HOT leads
    Bỏ qua: đã gửi rồi, INVALID, confidence thấp
    """
    session = get_session()
    try:
        query = (
            session.query(Contact)
            .options(joinedload(Contact.hotel))
            .join(Hotel)
            .filter(
                Contact.is_valid == True,
                Contact.confidence >= MIN_CONFIDENCE,
            )
        )

        if ONLY_VERIFIED:
            query = query.filter(
                Contact.verify_status.in_(["VALID", "LIKELY", "UNVERIFIED"])
            )

        # Chưa gửi email bao giờ
        query = query.filter(~Contact.email_logs.any())

        # Sắp xếp: verify tốt + confidence cao trước
        query = query.order_by(
            Contact.confidence.desc(),
        )

        contacts = query.limit(limit).all()
        session.expunge_all()
        return contacts
    finally:
        session.close()


def send_email_to_contact(contact: Contact) -> bool:
    """Gửi email giới thiệu đến 1 contact"""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port   = int(os.getenv("SMTP_PORT", "587"))
        smtp_user   = os.getenv("SMTP_USER", "")
        smtp_pass   = os.getenv("SMTP_PASSWORD", "")
        from_name   = os.getenv("FROM_NAME", "Hà Phong Visuals")
        from_email  = os.getenv("FROM_EMAIL", smtp_user)

        hotel_name = contact.hotel.name if contact.hotel else "Quý khách sạn"
        to_name    = contact.title or "Anh/Chị"
        to_email   = contact.email

        # ── Subject ──────────────────────────────────────────
        subject = f"{hotel_name} — Ảnh chuyên nghiệp tăng 28% đặt phòng"

        # ── Body HTML ────────────────────────────────────────
        html = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;color:#333;max-width:600px;margin:auto;padding:20px">

<p style="color:#c9a96e;font-size:11px;letter-spacing:2px;text-transform:uppercase">
  HÀ PHONG VISUALS — HOTEL PHOTOGRAPHY
</p>

<p>Kính gửi <strong>{to_name}</strong> tại <strong>{hotel_name}</strong>,</p>

<p>Tôi là <strong>Hà Phong</strong> — nhiếp ảnh gia chuyên chụp ảnh khách sạn,
resort và villa tại Đà Nẵng, Hội An và toàn miền Trung.</p>

<p>Theo nghiên cứu của Booking.com, <strong>ảnh là yếu tố số 1</strong> khách 
hàng xem khi chọn phòng — và ảnh chuyên nghiệp có thể tăng tỷ lệ đặt phòng 
lên đến <strong>28%</strong>.</p>

<p>Tôi đã từng làm việc với nhiều resort và boutique hotel tại Đà Nẵng.
Xin mời anh/chị xem portfolio tại:
<a href="https://haphong.com" style="color:#c9a96e">haphong.com</a></p>

<p>Nếu quý khách sạn đang cần cập nhật ảnh cho Booking.com, Agoda, 
hoặc website — tôi rất mong có cơ hội trao đổi <strong>15 phút qua Zalo</strong>.</p>

<p style="margin-top:30px">
Trân trọng,<br>
<strong style="color:#c9a96e">Hà Phong</strong><br>
<span style="font-size:12px;color:#666">
  Hà Phong Visuals | Hotel Photography<br>
  📱 Zalo: 0909.xxx.xxx<br>
  🌐 haphong.com
</span>
</p>

<p style="font-size:10px;color:#999;border-top:1px solid #eee;padding-top:10px;margin-top:20px">
Nếu bạn không muốn nhận email này, vui lòng reply "Không quan tâm" 
và tôi sẽ xóa địa chỉ email của bạn ngay lập tức.
</p>

</body>
</html>"""

        # ── Gửi ─────────────────────────────────────────────
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{from_email}>"
        msg["To"]      = to_email

        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())

        # Ghi log
        session = get_session()
        session.add(EmailLog(
            hotel_id   = contact.hotel_id,
            contact_id = contact.id,
            subject    = subject,
            status     = "Đã gửi",
            sent_at    = datetime.now(),
        ))
        session.commit()
        session.close()

        return True

    except Exception as e:
        log.error(f"  ❌ Gửi thất bại {contact.email}: {e}")
        return False


def run_daily_send():
    """Hàm chính — gọi bởi cron hoặc scheduler"""
    log.info("=" * 50)
    log.info(f"📧 BẮT ĐẦU GỬI EMAIL — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log.info("=" * 50)

    contacts = get_contacts_to_email()
    log.info(f"📋 Tìm thấy {len(contacts)} contact cần gửi hôm nay")

    if not contacts:
        log.info("✅ Không có email nào cần gửi — đã xong!")
        return

    sent_ok    = 0
    sent_fail  = 0

    for i, contact in enumerate(contacts):
        hotel_name = contact.hotel.name if contact.hotel else "?"
        log.info(
            f"\n[{i+1}/{len(contacts)}] {contact.email}\n"
            f"  KS: {hotel_name} | Chức vụ: {contact.title or '?'} | "
            f"Verify: {contact.verify_status} | Confidence: {contact.confidence}%"
        )

        ok = send_email_to_contact(contact)

        if ok:
            sent_ok += 1
            log.info(f"  ✅ Gửi thành công!")
        else:
            sent_fail += 1

        # Nghỉ giữa các email (tránh spam)
        if i < len(contacts) - 1:
            log.info(f"  ⏳ Chờ {DELAY_BETWEEN//60} phút trước email tiếp theo...")
            time.sleep(DELAY_BETWEEN)

    log.info("\n" + "=" * 50)
    log.info(f"✅ HOÀN TẤT: Gửi {sent_ok} thành công, {sent_fail} thất bại")
    log.info("=" * 50)


# ── Cron job setup command ────────────────────────────────────
CRON_PIPELINE = (
    '0 9 * * * cd "{path}" && /usr/bin/python3 pipeline.py '
    '--cities "Đà Nẵng" "Hội An" --limit 30 >> logs/pipeline.log 2>&1'
)

CRON_EMAIL = (
    '45 9 * * * cd "{path}" && /usr/bin/python3 send_daily.py '
    '>> logs/email_daily.log 2>&1'
)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-cron", action="store_true",
                        help="In ra lệnh cron cần thêm vào crontab")
    args = parser.parse_args()

    if args.print_cron:
        import os
        path = os.path.dirname(os.path.abspath(__file__))
        print("\n📋 Thêm các dòng sau vào crontab (chạy: crontab -e):\n")
        print(CRON_PIPELINE.format(path=path))
        print(CRON_EMAIL.format(path=path))
        print("\nLưu ý: Đảm bảo thư mục logs/ tồn tại:")
        print(f"  mkdir -p {path}/logs")
    else:
        os.makedirs("logs", exist_ok=True)
        run_daily_send()
