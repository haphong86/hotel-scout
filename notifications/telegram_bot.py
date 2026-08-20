"""
notifications/telegram_bot.py — Gửi báo cáo & thông báo tự động qua Telegram
"""
import os
import sys
import httpx
import logging
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import APP_CONFIG
from database.models import get_session, Hotel, Contact, EmailLog, ScanLog

log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


def get_chat_id_from_bot() -> Optional[str]:
    """Tự động lấy chat_id từ tin nhắn người dùng gửi cho Bot"""
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            data = resp.json()
            if data.get("ok") and data.get("result"):
                # Lấy tin nhắn mới nhất
                last_msg = data["result"][-1]
                chat_id = str(last_msg.get("message", {}).get("chat", {}).get("id"))
                if chat_id and chat_id != "None":
                    return chat_id
    except Exception as e:
        log.error(f"Lỗi lấy chat_id: {e}")
    return None


def send_telegram_message(text: str, chat_id: Optional[str] = None) -> bool:
    """Gửi 1 tin nhắn văn bản Markdown qua Telegram Bot"""
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    target_chat = chat_id or os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)

    # Nếu chưa có chat_id trong .env, thử tự động dò
    if not target_chat:
        target_chat = get_chat_id_from_bot()

    if not token or not target_chat:
        log.warning("⚠️ Chưa có Chat ID. Hãy mở Bot trên Telegram và bấm START!")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            data = resp.json()
            if data.get("ok"):
                log.info("✅ Đã gửi báo cáo Telegram thành công!")
                return True
            else:
                log.error(f"❌ Telegram API lỗi: {data.get('description')}")
                return False
    except Exception as e:
        log.error(f"❌ Lỗi kết nối Telegram: {e}")
        return False


def generate_daily_report() -> str:
    """Tạo nội dung báo cáo tổng kết 1 ngày làm việc của hệ thống"""
    session = get_session()
    today_str = datetime.now().strftime("%d/%m/%Y")

    try:
        # Thống kê tổng
        total_hotels = session.query(Hotel).count()
        total_contacts = session.query(Contact).count()

        # Thống kê hôm nay (tính từ 0h hôm nay)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        new_hotels_today = session.query(Hotel).filter(Hotel.created_at >= today_start).count()
        new_contacts_today = session.query(Contact).filter(Contact.created_at >= today_start).count()
        emails_sent_today = session.query(EmailLog).filter(EmailLog.sent_at >= today_start).count()
        emails_opened_today = session.query(EmailLog).filter(
            EmailLog.opened_at >= today_start,
            EmailLog.status.in_(["Đã mở", "Đã click", "Đã reply"])
        ).count()

        # Lấy 3 khách sạn mới/nổi bật hôm nay
        recent_hotels = (
            session.query(Hotel)
            .filter(Hotel.created_at >= today_start)
            .order_by(Hotel.rating.desc(), Hotel.created_at.desc())
            .limit(3)
            .all()
        )

        hotel_highlights = ""
        if recent_hotels:
            hotel_highlights = "\n🏨 *Khách sạn mới tiêu biểu:*\n"
            for h in recent_hotels:
                stars = f"{h.stars}⭐" if h.stars else ""
                hotel_highlights += f"• *{h.name}* ({h.city}) {stars}\n"
        else:
            hotel_highlights = "\n🏨 *Trạng thái:* Đang khai thác kho khách sạn sẵn có.\n"

        report = f"""
📷 *HÀ PHONG VISUALS · BÁO CÁO HÀNG NGÀY*
📅 Ngày: *{today_str}*
━━━━━━━━━━━━━━━━━━━━━

📊 *KẾT QUẢ TRONG NGÀY:*
• 🏨 Khách sạn mới quét được: *+{new_hotels_today}*
• 📧 Email đã xác thực (Verify): *+{new_contacts_today}*
• 📤 Email chiến dịch đã gửi: *{emails_sent_today} thư*
• 👁️ Lượt mở thư (Open): *{emails_opened_today}*

🗄️ *TỔNG QUY MÔ HỆ THỐNG:*
• Tổng kho khách sạn: *{total_hotels} cơ sở*
• Tổng liên hệ sạch: *{total_contacts} contacts*
{hotel_highlights}
━━━━━━━━━━━━━━━━━━━━━
🌐 *Dashboard Online:* `http://localhost:8501`
⚡ Hệ thống tự động hoạt động ổn định 24/7.
"""
        return report.strip()
    finally:
        session.close()


def send_daily_telegram_report() -> bool:
    """Tự động tạo và gửi báo cáo ngày qua Telegram"""
    report_text = generate_daily_report()
    return send_telegram_message(report_text)


def send_hot_lead_alert(
    hotel_name: str,
    city: str,
    stars: Optional[int] = None,
    email: str = "",
    phone: str = "",
    website: str = "",
    reason: str = "Khách sạn / Resort tiềm năng mới phát hiện"
) -> bool:
    """Bắn thông báo TỨC THÌ qua Telegram khi tìm thấy Khách sạn / Resort tiềm năng cao"""
    stars_str = f" ({stars}⭐)" if stars else ""
    phone_clean = phone.replace(" ", "").replace(".", "")
    zalo_link = f"[Nhắn Zalo](https://zalo.me/{phone_clean})" if phone_clean else "Đang cập nhật"

    text = f"""
🔥 *PHÁT HIỆN HOT LEAD MỚI!*
━━━━━━━━━━━━━━━━━━━━━
🏨 *Cơ sở:* *{hotel_name}*{stars_str}
📍 *Khu vực:* {city}
📧 *Email:* `{email}`
📞 *Hotline/Zalo:* {phone or 'Đang cập nhật'} ({zalo_link})
🌐 *Website:* {website or 'Chưa có website riêng'}
💡 *Đánh giá:* {reason}
━━━━━━━━━━━━━━━━━━━━━
⚡ *Hà Phong Visuals · Real-time Scout Alert*
"""
    return send_telegram_message(text.strip())


if __name__ == "__main__":
    print("📋 Báo cáo xem trước:")
    print(generate_daily_report())
