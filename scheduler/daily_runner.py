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
    # 0. Quét Tình Báo Pre-Opening Radar (Khách sạn sắp khai trương trước 3-6 tháng)
    try:
        from radar.pre_opening_radar import run_pre_opening_radar
        radar_res = run_pre_opening_radar(target_cities, notify_telegram=True)
        print(f"  🔭 Pre-Opening Radar: {radar_res['total_radar_projects']} dự án đang theo dõi ({radar_res['hot_projects_count']} dự án RẤT NÓNG).")
    except Exception as e:
        print(f"  ⚠️ Pre-Opening Radar lỗi: {e}")

    session = get_session()
    total_found = 0
    saved_hotels = 0
    skipped_hotels = 0
    from scanner.overpass_scanner import scan_city_osm
    from scanner.google_maps_scraper import search_google_maps
    from scanner.early_signals import scrape_booking_opening_soon, scrape_hotel_job_postings

    for city in target_cities:
        try:
            print(f"  • Quét đa kênh tại {city}...")
            osm = scan_city_osm(city, radius_km=15)
            gmaps = search_google_maps(f"khách sạn mới {city}", city)
            b_soon = scrape_booking_opening_soon(city)
            jobs = scrape_hotel_job_postings(city)

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

    seen_emails = set()
    sent_count = 0

    GENERIC_DISALLOWED = {
        "info", "reservation", "reservations", "booking", "bookings",
        "contact", "reception", "letan", "stay", "hello", "frontdesk",
        "enquiry", "enquiries", "admin", "office", "fnb", "spa", "restaurant"
    }
    CHAIN_GLOBAL_DOMAINS = {"hilton.com", "marriott.com", "hyatt.com", "ihg.com", "accor.com"}

    all_hotels = (
        session.query(Hotel)
        .filter(Hotel.contacts.any())
        .filter(Hotel.status != "Đã reply")
        .order_by(Hotel.rating.desc(), Hotel.review_count.desc())
        .all()
    )

    seen_emails = set()
    sent_count = 0
    now = datetime.now()

    for h in all_hotels:
        if sent_count >= 20:
            break

        past_logs = (
            session.query(EmailLog)
            .filter(EmailLog.hotel_id == h.id)
            .order_by(EmailLog.sent_at.desc())
            .all()
        )

        contacts = (
            session.query(Contact)
            .filter(Contact.hotel_id == h.id)
            .filter(Contact.email.isnot(None), Contact.email != "")
            .order_by(Contact.confidence.desc())
            .all()
        )

        target_contact = None

        if not past_logs:
            target_contact = next((c for c in contacts if (c.confidence or 0) >= 95), None)
            if not target_contact and contacts:
                target_contact = contacts[0]
        else:
            last_log = past_logs[0]
            hours_since_last = (now - last_log.sent_at).total_seconds() / 3600.0 if last_log.sent_at else 999
            if hours_since_last < 20.0:
                continue

            sent_contact_ids = {pl.contact_id for pl in past_logs}
            for c in contacts:
                if c.id not in sent_contact_ids:
                    target_contact = c
                    break

        if not target_contact:
            continue

        c = target_contact
        c_email = c.email.lower().strip()
        if c_email in seen_emails:
            continue

        prefix = c_email.split("@")[0].lower()
        if prefix in GENERIC_DISALLOWED:
            continue

        c_dom = c_email.split("@")[-1].strip()
        if is_blacklisted_domain(c_dom) or (c_dom in CHAIN_GLOBAL_DOMAINS and len(prefix) <= 3):
            continue

        # Kiểm tra máy chủ mail trước khi gửi
        mx = check_mx(c_dom)
        if not mx:
            continue

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


from scheduler.heartbeat_tracker import log_activity


def run_continuous_scout_cycle():
    """Chu kỳ quét liên tục 24/7 mỗi 60 phút: cào KS mới, quét Pre-Opening Radar, verify MX"""
    target_cities = [
        "Đà Nẵng", "Hội An", "Quảng Nam", "Huế", "Lăng Cô",
        "Quy Nhơn", "Tuy Hòa", "Nha Trang", "Cam Ranh",
        "Phan Thiết", "Đà Lạt", "Phú Quốc"
    ]
    log_activity("🔍 BẮT ĐẦU CHU KỲ QUÉT RADAR 24/7", f"Quét tín hiệu dự án tại {len(target_cities)} tỉnh thành...")

    # 1. Quét Radar Pre-Opening
    try:
        from radar.pre_opening_radar import run_pre_opening_radar
        r_res = run_pre_opening_radar(target_cities, notify_telegram=False)
        log_activity("🔭 Quét Pre-Opening Radar", f"Đang bám sát {r_res['total_radar_projects']} dự án ({r_res['hot_projects_count']} dự án RẤT NÓNG)")
    except Exception as e:
        log_activity("⚠️ Pre-Opening Radar", f"Lỗi: {e}")

    # 2. Cào khách sạn mới từ OpenStreetMap & Google Maps & Booking
    session = get_session()
    new_saved = 0
    from scanner.overpass_scanner import scan_city_osm
    from scanner.google_maps_scraper import search_google_maps
    from scanner.early_signals import scrape_booking_opening_soon

    for city in target_cities[:4]:  # Quét luân phiên
        try:
            osm = scan_city_osm(city, radius_km=15)
            gmaps = search_google_maps(f"khách sạn mới {city}", city)
            b_soon = scrape_booking_opening_soon(city)

            all_found = osm + gmaps + b_soon
            for h in all_found:
                name = (h.get("name") or "").strip()
                if not name or len(name) < 3:
                    continue
                exists = session.query(Hotel).filter(Hotel.name == name, Hotel.city == city).first()
                if not exists:
                    session.add(Hotel(
                        name=name, city=city, address=h.get("address"),
                        website=h.get("website") or h.get("source_url"),
                        phone_main=h.get("phone_main"), rating=h.get("rating"),
                        review_count=h.get("review_count", 0), source=h.get("source", "scout_daemon"),
                        status="Mới tìm thấy"
                    ))
                    new_saved += 1
            session.commit()
        except Exception:
            continue

    log_activity("🏢 Hoàn tất cào khách sạn", f"Đã lưu thêm +{new_saved} khách sạn mới vào hệ thống")

    # 3. Tự động kiểm tra MX và verify email sống cho các KS mới
    try:
        hotels_unverified = session.query(Hotel).filter(~Hotel.contacts.any()).limit(15).all()
        verified_count = 0
        for h in hotels_unverified:
            if h.website:
                cand = generate_candidates(h)
                verified = verify_candidates(cand)
                if verified:
                    save_verified_contacts(verified, session)
                    verified_count += len(verified)
        session.commit()
        log_activity("🛡️ Kiểm tra & Verify Email", f"Đã xác thực máy chủ MX và lưu {verified_count} email sống")
    except Exception as e:
        log_activity("⚠️ Verify Email", f"Lỗi: {e}")

    session.close()
    log_activity("💤 Chế độ giám sát 24/7", "Đang chờ chu kỳ quét tiếp theo (mỗi 60 phút)...")


def _cron_loop():
    """Vòng lặp chạy ngầm 24/7 liên tục trên Railway"""
    last_run_date = ""
    last_scout_time = 0
    print("⏰ [SCHEDULER] Bộ đếm giờ tự động 24/7 đã kích hoạt!")
    log_activity("🚀 KHỞI ĐỘNG HỆ THỐNG", "Bộ máy quét ngầm 24/7 & Lịch tự động 09:00 AM đã sẵn sàng")

    while _scheduler_running:
        try:
            now = datetime.now()
            now_ts = time.time()
            today_str = now.strftime("%Y-%m-%d")

            # 1. Chạy chu kỳ quét radar & cào dữ liệu liên tục mỗi 60 phút (3600 giây)
            if now_ts - last_scout_time >= 3600:
                last_scout_time = now_ts
                run_continuous_scout_cycle()

            # 2. Kiểm tra nếu đúng 09:00 AM mỗi sáng (Giờ làm việc) -> Gửi chiến dịch Email Bậc Thang
            if now.hour == 9 and now.minute <= 5 and last_run_date != today_str:
                last_run_date = today_str
                log_activity("📤 BẮT ĐẦU CHIẾN DỊCH GỬI MAIL 09:00 AM", "Đang phân bổ gửi email bậc thang...")
                run_daily_autopilot_job()

        except Exception as e:
            print(f"⚠️ [SCHEDULER ERROR]: {e}")
            log_activity("⚠️ Lỗi vòng lặp Scheduler", str(e))

        # Cập nhật nhịp tim mỗi 30 giây
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
    print("🧪 Testing continuous scout cycle manually...")
    run_continuous_scout_cycle()
