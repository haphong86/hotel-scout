"""
campaign/tracking_server.py — Máy chủ theo dõi Mở Thư (Open) & Bấm Xem Ảnh (Click) Thời Gian Thực
1. Khi khách mở email: Trả về ảnh 1x1 trong suốt + BẮN TELEGRAM NGAY LẬP TỨC
2. Khi khách bấm link haphong.com: Chuyển hướng 302 sang haphong.com + BẮN TELEGRAM CẢNH BÁO HOT LEAD!
"""

import os
import sys
import urllib.parse
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import get_session, EmailLog, Hotel, Contact
from notifications.telegram_bot import send_telegram_message

# 1x1 Transparent GIF Byte array (Chuẩn RFC)
TRANSPARENT_GIF_1X1 = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def record_email_open(log_id: int) -> bool:
    """Xử lý sự kiện khách mở email"""
    session = get_session()
    try:
        log = session.query(EmailLog).filter(EmailLog.id == log_id).first()
        if not log:
            return False

        # Kiểm tra xem đây có phải lần đầu mở không
        is_first_open = log.opened_at is None
        log.opened_at = datetime.now()
        if log.status != "Đã click":
            log.status = "Đã mở"
        session.commit()

        hotel = log.hotel
        contact = log.contact
        h_name = hotel.name if hotel else "Khách sạn"
        h_city = hotel.city if hotel else "Việt Nam"
        c_email = contact.email if contact else "—"
        c_title = contact.title if (contact and contact.title) else "Quản lý / Marketing"

        # Bắn Telegram nếu là lần mở mới
        if is_first_open:
            time_now = datetime.now().strftime("%H:%M:%S · %d/%m/%Y")
            msg = f"""
👁️ *KHÁCH VỪA MỞ ĐỌC EMAIL!*
━━━━━━━━━━━━━━━━━━━━━
🏨 *Cơ sở:* *{h_name}* ({h_city})
📧 *Người nhận:* `{c_email}` ({c_title})
💌 *Tiêu đề:* {log.subject}
🕒 *Thời gian:* {time_now}
━━━━━━━━━━━━━━━━━━━━━
👉 Khách đang online đọc thư của anh, có thể chủ động kết nối Zalo!
"""
            send_telegram_message(msg.strip())
            print(f"🔔 [TRACKING] Đã bắn Telegram báo khách {h_name} vừa mở email!")
        return True
    except Exception as e:
        print(f"❌ [TRACKING ERROR] Lỗi record_open: {e}")
        return False
    finally:
        session.close()


def record_email_click(log_id: int, target_url: str = "https://haphong.com") -> str:
    """Xử lý sự kiện khách bấm vào link Portfolio trên haphong.com"""
    session = get_session()
    try:
        log = session.query(EmailLog).filter(EmailLog.id == log_id).first()
        if log:
            log.clicked_at = datetime.now()
            log.status = "Đã click"
            session.commit()

            hotel = log.hotel
            contact = log.contact
            h_name = hotel.name if hotel else "Khách sạn"
            h_city = hotel.city if hotel else "Việt Nam"
            c_email = contact.email if contact else "—"
            c_phone = hotel.phone_main if hotel else ""

            time_now = datetime.now().strftime("%H:%M:%S · %d/%m/%Y")
            phone_clean = c_phone.replace(" ", "").replace(".", "") if c_phone else ""
            zalo_btn = f" | [Nhắn Zalo](https://zalo.me/{phone_clean})" if phone_clean else ""

            msg = f"""
🔥 *HOT! KHÁCH VỪA BẤM VÀO XEM PORTFOLIO!*
━━━━━━━━━━━━━━━━━━━━━
🏨 *Cơ sở:* *{h_name}* ({h_city})
📧 *Người nhận:* `{c_email}`
🌐 *Đang xem:* {target_url}
📞 *Hotline/Zalo:* {c_phone or 'Đang cập nhật'}{zalo_btn}
🕒 *Thời gian:* {time_now}
━━━━━━━━━━━━━━━━━━━━━
⚡ *Khách hàng cực kỳ tiềm năng! Hãy ưu tiên liên hệ tư vấn ngay!*
"""
            send_telegram_message(msg.strip())
            print(f"🔥 [TRACKING] Đã bắn Telegram báo khách {h_name} vừa bấm xem ảnh!")
    except Exception as e:
        print(f"❌ [TRACKING ERROR] Lỗi record_click: {e}")
    finally:
        session.close()

    return target_url
