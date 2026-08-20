"""
scheduler/daily_runner.py — Cỗ máy tự động hoá chạy ngầm 24/7 trên Railway
Tự động thức dậy vào đúng 09:00 AM mỗi sáng (Giờ Việt Nam UTC+7):
1. Quét khách sạn mới trên các vùng trọng điểm
2. Tìm & Verify Email sạch (Loại bỏ 100% rác/NXDOMAIN)
3. Gửi 20 email chiến dịch từ sales@haphong.com (Tự động chuyển đổi Anh/Việt)
4. Bắn báo cáo tổng hợp chi tiết qua Telegram
"""

import time
import os
import sys
import threading
from datetime import datetime
from jinja2 import Template

# Thêm path gốc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import get_session, Hotel, Contact, EmailLog, ScanLog
from config import VIETNAM_REGIONS, EMAIL_CONFIG
from scanner.overpass_scanner import scan_city_osm
from pipeline import generate_candidates, verify_candidates, save_verified_contacts
from campaign.email_sender import send_email
from extractor.email_verifier import check_mx
from extractor.free_email_finder import is_blacklisted_domain
from notifications.telegram_bot import send_telegram_message, generate_daily_report


_scheduler_running = False
_scheduler_thread = None


def run_daily_autopilot_job():
    """Hàm chạy toàn bộ quy trình 4 bước mỗi 09:00 AM"""
    start_time = time.time()
    today_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"🚀 [CRON 09:00 AM] Bắt đầu chu trình tự động ngày {today_str}...")

    # Thông báo khởi động qua Telegram
    send_telegram_message(f"☀️ *[09:00 AM] HÀ PHONG VISUALS · AUTOPILOT KHỞI ĐỘNG*\n━━━━━━━━━━━━━━━━━━━━━\nĐang quét khách sạn & gửi chiến dịch hôm nay...")

    # 1. Quét các thành phố trọng điểm
    target_cities = [
        "Đà Nẵng", "Hội An", "Quảng Nam", "Huế", "Lăng Cô",
        "Quy Nhơn", "Tuy Hòa", "Nha Trang", "Cam Ranh",
        "Phan Thiết", "Đà Lạt", "Phú Quốc"
    ]

    session = get_session()
    total_found = 0
    saved_hotels = 0
    skipped_hotels = 0
    from scanner.overpass_scanner import scan_city_osm
    from scanner.google_maps_scraper import search_google_maps
    from scanner.early_signals import scrape_booking_opening_soon, scrape_recruitment_signals

    for city in target_cities:
        try:
            print(f"  • Quét đa kênh tại {city}...")
            osm = scan_city_osm(city, radius_km=15)
            gmaps = search_google_maps(f"khách sạn mới {city}", city)
            b_soon = scrape_booking_opening_soon(city)
            jobs = scrape_recruitment_signals(city)

            all_found = osm + gmaps + b_soon + jobs
            total_found += len(all_found)

            for h in all_found:
                name = (h.get("name") or "").strip()
                if not name or len(name) < 3:
                    continue
                exists = session.query(Hotel).filter(Hotel.name == name, Hotel.city == city).first()
                if not exists:
                    session.add(Hotel(
                        name=name, city=city,
                        address=h.get("address"), website=h.get("website") or h.get("source_url"),
                        phone_main=h.get("phone_main"), rating=h.get("rating"),
                        review_count=h.get("review_count", 0),
                        source=h.get("source", "multi_source"),
                        status="Đang xây / Sắp mở" if h.get("signal") else "Mới tìm thấy"
                    ))
                    saved_hotels += 1
                else:
                    skipped_hotels += 1
        except Exception as e:
            print(f"  ⚠️ Quét {city} lỗi: {e}")

    session.commit()

    # Ghi nhận ScanLog
    duration = int(time.time() - start_time)
    session.add(ScanLog(
        cities=", ".join(target_cities[:5]) + f" (+{len(target_cities)-5})",
        source="openstreetmap",
        total_found=total_found,
        new_saved=saved_hotels,
        skipped=skipped_hotels,
        duration_s=duration,
        triggered_by="cron_09am"
    ))
    session.commit()

    # 2. Tìm & Verify Email cho các khách sạn chưa có liên hệ
    hotels_to_find = (
        session.query(Hotel)
        .filter(~Hotel.contacts.any())
        .order_by(Hotel.website.desc(), Hotel.rating.desc())
        .limit(30)
        .all()
    )

    for h in hotels_to_find:
        try:
            candidates = generate_candidates(h)
            if candidates:
                verified = verify_candidates(candidates, max_verify=6)
                save_verified_contacts(h.id, verified)
        except Exception as e:
            print(f"  ⚠️ Verify lỗi cho {h.name}: {e}")

    # 3. Gửi 20 Email chiến dịch chuẩn sạch (1 Khách sạn = 1 Email duy nhất)
    raw_pending = (
        session.query(Contact)
        .join(Hotel)
        .filter(Contact.email.isnot(None), Contact.email != "", ~Contact.email_logs.any())
        .filter(Contact.verify_status.in_(["VALID", "LIKELY"]))
        .order_by(Contact.confidence.desc())
        .limit(200)
        .all()
    )

    # Nạp template Anh / Việt
    tpl_vi_path = "campaign/templates/email_01_intro.html"
    tpl_en_path = "campaign/templates/email_en_01_intro.html"
    with open(tpl_vi_path, "r", encoding="utf-8") as f:
        tpl_vi = f.read()
    with open(tpl_en_path, "r", encoding="utf-8") as f:
        tpl_en = f.read()

    intl_keywords = {
        "hyatt", "marriott", "hilton", "sheraton", "intercontinental", "novotel", "pullman",
        "radisson", "four seasons", "banyan tree", "melia", "wyndham", "anantara", "six senses",
        "renaissance", "mercure", "sofitel", "crowne plaza", "shangri-la", "jw marriott",
        "le meridien", "st. regis", "w hotel", "voco", "holiday inn", "fusion", "salinda",
        "almanity", "allegro", "belhamy", "nam an", "tia wellness", "la siesta", "premier village"
    }

    seen_hotel_ids = set()
    seen_emails = set()
    sent_count = 0

    GENERIC_DISALLOWED = {
        "info", "reservation", "reservations", "booking", "bookings",
        "contact", "reception", "letan", "stay", "hello", "frontdesk",
        "enquiry", "enquiries", "admin", "office", "fnb", "spa", "restaurant"
    }

    for c in raw_pending:
        if sent_count >= 20:
            break

        h = c.hotel
        if not h or h.id in seen_hotel_ids:
            continue
        if h.status in ["Đã liên hệ", "Đang liên hệ"] or (h.email_logs and len(h.email_logs) > 0):
            continue

        c_email = c.email.lower().strip()
        if c_email in seen_emails:
            continue

        prefix = c_email.split("@")[0].lower()
        if prefix in GENERIC_DISALLOWED:
            continue

        c_dom = c_email.split("@")[-1].strip()
        if is_blacklisted_domain(c_dom):
            continue

        # Kiểm tra máy chủ mail trước khi gửi
        mx = check_mx(c_dom)
        if not mx:
            continue

        seen_hotel_ids.add(h.id)
        seen_emails.add(c_email)

        h = c.hotel
        h_city = h.city or "Việt Nam"
        h_name_lower = h.name.lower()

        # Tạo EmailLog trước để lấy ID phục vụ tracking
        is_intl = any(k in h_name_lower for k in intl_keywords) or (c_dom.endswith(".com") and not c_dom.endswith(".vn") and h.stars and h.stars >= 4)

        if is_intl:
            subj = f"[{h.name}] — Elevating Architectural & Visual Identity in {h_city}"
            tpl_chosen = tpl_en
            contact_display = c.name or "General Manager / Marketing Director"
        else:
            subj = f"[{h.name}] — Giải pháp nâng cấp hình ảnh kiến trúc & visual khách sạn"
            tpl_chosen = tpl_vi
            contact_display = c.name or c.title or "Anh/Chị"

        # Tạo log entry
        elog = EmailLog(
            hotel_id=h.id, contact_id=c.id, sequence_num=1,
            subject=subj, status="Đang gửi", sent_at=datetime.now()
        )
        session.add(elog)
        session.flush()  # Lấy elog.id

        # Chèn Tracking Pixel & Tracking Link
        tracking_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "hotel-scout-production.up.railway.app")
        tracking_url = f"https://{tracking_domain}" if not tracking_domain.startswith("http") else tracking_domain

        body = Template(tpl_chosen).render(
            hotel_name=h.name,
            contact_name=contact_display,
            city=h_city,
            to_email=c.email,
            subject=subj,
        )

        # Chèn pixel ảnh 1x1 ẩn ở cuối email
        pixel_tag = f'<img src="{tracking_url}/track/open?id={elog.id}" width="1" height="1" style="display:none;" />'
        body_with_tracking = body.replace("</body>", f"{pixel_tag}</body>")

        res = send_email(c.email, c.name or "", subj, body_with_tracking)
        if res.get("success"):
            sent_count += 1
            elog.status = "Đã gửi"
            h.status = "Đã liên hệ"
            session.commit()
        else:
            elog.status = "Thất bại"
            elog.error_msg = res.get("message", "")
            session.commit()

        time.sleep(2.0)

    session.close()

    # 4. Gửi báo cáo Telegram tổng kết ngày
    report_msg = generate_daily_report()
    send_telegram_message(report_msg)
    print(f"✅ [CRON 09:00 AM] Hoàn tất chu trình! Đã gửi {sent_count} email và bắn báo cáo.")


def _cron_loop():
    """Vòng lặp canh giờ UTC+7 kiểm tra đúng 09:00 AM"""
    last_run_date = ""
    print("⏰ [SCHEDULER] Bộ đếm giờ tự động 09:00 AM (Vietnam Time) đã kích hoạt!")

    while _scheduler_running:
        try:
            now = datetime.now()
            # Giờ hiện tại (local time máy chủ đã đặt UTC+7 hoặc tính theo giờ VN)
            today_str = now.strftime("%Y-%m-%d")
            
            # Kiểm tra nếu đúng 09:00 (từ 09:00 đến 09:05) và hôm nay chưa chạy
            if now.hour == 9 and now.minute <= 5 and last_run_date != today_str:
                last_run_date = today_str
                run_daily_autopilot_job()

        except Exception as e:
            print(f"⚠️ [SCHEDULER ERROR]: {e}")

        # Ngủ 30 giây rồi kiểm tra tiếp
        time.sleep(30)


def start_scheduler():
    """Khởi động tiến trình chạy ngầm"""
    global _scheduler_running, _scheduler_thread
    if not _scheduler_running:
        _scheduler_running = True
        _scheduler_thread = threading.Thread(target=_cron_loop, daemon=True)
        _scheduler_thread.start()
        print("🟢 [SCHEDULER] Background daemon started successfully!")


if __name__ == "__main__":
    print("🧪 Testing daily autopilot job manually...")
    run_daily_autopilot_job()
