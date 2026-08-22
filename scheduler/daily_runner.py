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
    """Hàm chạy toàn bộ quy trình: GỬI EMAIL TRƯỚC (Ưu tiên hàng đầu) ➔ Quét Data sau"""
    start_time = time.time()
    today_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"🚀 [CRON] Bắt đầu chu trình tự động ngày {today_str}...")

    # Thông báo khởi động qua Telegram
    send_telegram_message(f"☀️ *HÀ PHONG VISUALS · AUTOPILOT KHỞI ĐỘNG*\n━━━━━━━━━━━━━━━━━━━━━\nĐang gửi 20 email chiến dịch hôm nay...")

    target_cities = [
        "Đà Nẵng", "Hội An", "Quảng Nam", "Huế", "Lăng Cô",
        "Quy Nhơn", "Tuy Hòa", "Nha Trang", "Cam Ranh",
        "Phan Thiết", "Đà Lạt", "Phú Quốc"
    ]
    session = get_session()

    # =========================================================================
    # BƯỚC 1: GỬI 20 EMAIL TỪ PRIORITY QUEUE NGAY LẬP TỨC (Không để khách chờ)
    # =========================================================================
    from campaign.priority_queue import get_prioritized_outreach_queue
    from database.models import PreOpeningProject, safe_commit, get_now_vn

    prioritized_list = get_prioritized_outreach_queue(limit=20, selected_cities=target_cities)
    sent_count = 0

    with open("campaign/templates/email_01_intro.html", "r", encoding="utf-8") as f:
        tpl_vi = f.read()
    with open("campaign/templates/email_en_01_intro.html", "r", encoding="utf-8") as f:
        tpl_en = f.read()
    with open("campaign/templates/email_pre_opening.html", "r", encoding="utf-8") as f:
        tpl_pre = f.read()

    tracking_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "hotel-scout-production.up.railway.app")
    tracking_url = f"https://{tracking_domain}" if not tracking_domain.startswith("http") else tracking_domain

    for item in prioritized_list:
        p_type = item.get("type", "hotel")
        h_name = item["hotel_name"]
        h_city = item["city"]
        to_mail = item["recipient_email"]
        rec_name = item["recipient_name"]
        rec_role = item["recipient_role"]

        if p_type == "pre_opening":
            subj = f"[{h_name}] — Giải pháp Visual & Bộ ảnh Kiến trúc Launching khai trương tại {h_city}"
            body = Template(tpl_pre).render(
                hotel_name=h_name, contact_name=rec_name or rec_role or "Ban Lãnh Đạo",
                city=h_city, est_opening=item.get("est_opening", "sắp tới"),
                tracking_url=tracking_url, contact_id=item.get("id") or item.get("project_id") or 999
            )
        elif item.get("is_international"):
            subj = f"[{h_name}] — Elevating Architectural & Visual Identity in {h_city}"
            body = Template(tpl_en).render(
                hotel_name=h_name, contact_name=rec_name or rec_role or "General Manager",
                city=h_city, tracking_url=tracking_url, contact_id=item.get("id") or item.get("contact_id") or 999
            )
        else:
            subj = f"[{h_name}] — Giải pháp nâng cấp hình ảnh kiến trúc & visual khách sạn"
            body = Template(tpl_vi).render(
                hotel_name=h_name, contact_name=rec_name or rec_role or "Tổng Giám Đốc",
                city=h_city, tracking_url=tracking_url, contact_id=item.get("id") or item.get("contact_id") or 999
            )

        # =====================================================================
        # CỔNG KIỂM TRA HÒM THƯ TRỰC TIẾP (ZERO-BOUNCE MAILBOX PING GATE)
        # =====================================================================
        from extractor.email_verifier import check_mx, check_smtp_mailbox_exists
        dom = to_mail.split("@")[-1]
        mx_server = check_mx(dom)
        if mx_server:
            is_alive = check_smtp_mailbox_exists(to_mail, mx_server)
            if is_alive is False:
                print(f"  🚫 BỎ QUA [HÒM THƯ KHÔNG TỒN TẠI]: {h_name} -> {to_mail} (Mail Server báo 550 User Inactive/Not Found)")
                continue

        # Gửi email an toàn khi hòm thư đã xác thực tồn tại
        try:
            res = send_email(to_mail, subj, body, is_html=True)
            if res.get("success"):
                sent_count += 1
                now_vn = get_now_vn()
                
                # Cập nhật PreOpeningProject hoặc Hotel Lead
                if p_type == "pre_opening":
                    p_id = item.get("id") or item.get("project_id")
                    if p_id:
                        proj = session.query(PreOpeningProject).filter(PreOpeningProject.id == p_id).first()
                        if proj:
                            proj.status = "Đã gửi Email Launching"
                            safe_commit(session)
                else:
                    h_obj = session.query(Hotel).filter(Hotel.id == item["hotel_id"]).first()
                    c_obj = session.query(Contact).filter(Contact.id == item["contact_id"]).first() if item.get("contact_id") else None
                    if h_obj:
                        h_obj.status = "Đã liên hệ"
                    log_entry = EmailLog(
                        hotel_id=item["hotel_id"],
                        contact_id=item.get("contact_id"),
                        subject=subj,
                        body_preview=body[:200],
                        status="Đã gửi",
                        sent_at=now_vn
                    )
                    session.add(log_entry)
                    safe_commit(session)

                print(f"  [{sent_count}/20] ✅ ĐÃ GỬI: {h_name} -> {to_mail}")
            else:
                print(f"  ⚠️ Gửi thất bại: {h_name} -> {res.get('error')}")
        except Exception as ex:
            print(f"  ⚠️ Lỗi ngoại lệ khi gửi {h_name}: {ex}")

        # Nghỉ ngẫu nhiên 3-7 phút giữa mỗi email — tránh spam filter
        import random
        delay = random.randint(180, 420)  # 3–7 phút
        print(f"  ⏳ Chờ {delay//60} phút {delay%60}s trước email tiếp theo...")
        time.sleep(delay)


    print(f"✅ Đã gửi thành công {sent_count}/20 email hôm nay!")
    session.close()

    # =========================================================================
    # BƯỚC 2: CRAWL EMAIL CHO 40 KS CHƯA CÓ EMAIL (Nạp Queue Liên Tục)
    # =========================================================================
    print("\n📡 [BƯỚC 2] Crawl email cho KS chưa có liên hệ...")
    try:
        from pipeline import get_hotels_to_process, generate_candidates, verify_candidates, save_verified_contacts
        hotels_to_crawl = get_hotels_to_process(
            cities=target_cities,
            limit=40,
            only_without_contact=True
        )
        crawl_new = 0
        for hc in hotels_to_crawl:
            try:
                candidates = generate_candidates(hc)
                if candidates:
                    verified = verify_candidates(candidates, max_verify=8)   # ← sửa: chỉ truyền max_verify
                    saved = save_verified_contacts(hc, verified)
                    if saved:
                        crawl_new += saved
                        print(f"  ✅ {hc.name[:35]} → +{saved} email")
            except Exception as e:
                print(f"  ⚠️ {getattr(hc, 'name', '?')[:30]}: {e}")
        print(f"  📬 Tổng email mới crawl được: +{crawl_new}")
    except Exception as e:
        print(f"  ⚠️ Crawl lỗi: {e}")

    # =========================================================================
    # BƯỚC 3: QUÉT PRE-OPENING RADAR & DATA MỚI TRONG NỀN
    # =========================================================================
    try:
        from radar.pre_opening_radar import run_pre_opening_radar
        radar_res = run_pre_opening_radar(target_cities, notify_telegram=False)
        print(f"  🔭 Pre-Opening Radar: {radar_res['total_radar_projects']} dự án đang theo dõi.")
    except Exception as e:
        print(f"  ⚠️ Pre-Opening Radar lỗi: {e}")

    # Báo cáo Telegram
    report_msg = generate_daily_report()
    send_telegram_message(report_msg)

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

def run_continuous_scout_cycle(cities=None):
    """
    Chu kỳ 3 phút chạy liên tục 24/7:
    1. Scan KS mới từ OSM → lưu vào DB
    2. Crawl website tìm email → verify SMTP → lưu Contact
    """
    if cities is None:
        cities = ["Đà Nẵng", "Hội An", "Quảng Nam"]

    log_activity("🗺️ Bắt đầu quét OSM", f"Đang tìm KS mới tại: {', '.join(cities)}")
    session = get_session()
    new_hotels = 0
    new_emails  = 0

    # ── PHẦN 1: Scan KS mới từ OSM ────────────────────────────
    try:
        from scanner.overpass_scanner import scan_city_osm
        for city in cities:
            try:
                log_activity("🔭 Quét OpenStreetMap", f"Đang tìm khách sạn tại {city}...")
                osm_hotels = scan_city_osm(city, radius_km=15)
                city_new = 0
                for h in osm_hotels:
                    name = (h.get("name") or "").strip()
                    if not name or len(name) < 3:
                        continue
                    exists = session.query(Hotel).filter(
                        Hotel.name == name, Hotel.city == city
                    ).first()
                    if not exists:
                        session.add(Hotel(
                            name=name, city=city,
                            address=h.get("address"),
                            website=h.get("website") or h.get("source_url"),
                            phone_main=h.get("phone_main"),
                            rating=h.get("rating"),
                            stars=h.get("stars", 3),
                            source="osm", status="Mới tìm thấy"
                        ))
                        new_hotels += 1
                        city_new += 1
                session.commit()
                if city_new > 0:
                    log_activity("🏢 KS mới phát hiện", f"+{city_new} KS mới tại {city}")
                else:
                    log_activity("✔️ Quét xong", f"{city} — không có KS mới (đã đủ)")
            except Exception as e:
                log_activity("⚠️ Lỗi OSM", f"{city}: {str(e)[:60]}")
                session.rollback()
    except Exception as e:
        log_activity("⚠️ Lỗi scanner", str(e)[:80])

    # ── PHẦN 2: Crawl email cho KS chưa có contact ─────────────
    try:
        unverified = (
            session.query(Hotel)
            .filter(Hotel.website.like("http%"), ~Hotel.contacts.any())
            .order_by(Hotel.stars.desc(), Hotel.created_at.desc())
            .limit(15)
            .all()
        )
        session.close()
        log_activity("📧 Crawl email", f"Đang xử lý {len(unverified)} KS chưa có email...")
        for idx, h in enumerate(unverified):
            try:
                log_activity(
                    f"🔍 [{idx+1}/{len(unverified)}] Crawl",
                    f"{h.name} ({h.city or 'VN'}) — {(h.website or '')[:45]}"
                )
                candidates = generate_candidates(h)
                if not candidates:
                    log_activity("➖ Bỏ qua", f"{h.name} — không tìm thấy email trên website")
                    continue
                log_activity(
                    "🔬 Verify SMTP",
                    f"{h.name} — đang kiểm tra {len(candidates)} email ứng viên..."
                )
                verified = verify_candidates(candidates, max_verify=6)
                saved = save_verified_contacts(h, verified)
                if saved > 0:
                    new_emails += saved
                    valid_list = [c.get("email","") for c in verified if c.get("verify_status")=="VALID"]
                    log_activity("✅ Email VALID lưu", f"{h.name}: {', '.join(valid_list)[:55]}")
                else:
                    log_activity("❌ Không có email sống", f"{h.name} — {len(candidates)} email đều DEAD/RISKY")
            except Exception as ex:
                log_activity("⚠️ Lỗi crawl", f"{h.name}: {str(ex)[:60]}")
                continue
    except Exception as e:
        log_activity("⚠️ Crawl lỗi", str(e)[:80])
        try:
            session.close()
        except Exception:
            pass

    log_activity(
        "🎉 Chu kỳ xong",
        f"KS mới: +{new_hotels} | Email VALID: +{new_emails} | Nghỉ 3 phút..."
    )

    # ── PHẦN 3: Re-verify email LIKELY cũ trong DB ─────────────
    # Cứ mỗi chu kỳ, lấy 5 email LIKELY → verify lại → upgrade VALID hoặc xóa
    try:
        from extractor.email_verifier import verify_email
        rev_session = get_session()
        likely_contacts = (
            rev_session.query(Contact)
            .filter(Contact.verify_status == "LIKELY")
            .order_by(Contact.id.asc())
            .limit(5)
            .all()
        )
        upgraded = 0
        removed  = 0
        for c in likely_contacts:
            try:
                result = verify_email(c.email)
                if result.status == "VALID":
                    c.verify_status = "VALID"
                    c.is_valid = True
                    upgraded += 1
                elif result.status in ("INVALID", "NO_MX"):
                    rev_session.delete(c)
                    removed += 1
                # LIKELY giữ nguyên → thử lại lần sau
            except Exception:
                pass
        rev_session.commit()
        rev_session.close()
        if upgraded or removed:
            log_activity("🔬 Re-verify LIKELY",
                         f"Nâng cấp {upgraded} → VALID | Xóa {removed} email chết")
    except Exception as e:
        log_activity("⚠️ Re-verify lỗi", str(e))


from datetime import datetime, timezone, timedelta
import json

LAST_RUN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "last_run.json")


def _get_last_run_date() -> str:
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("last_run_date", "")
        except Exception:
            pass
    return ""


def _set_last_run_date(date_str: str):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    try:
        with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_run_date": date_str, "updated_at": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M:%S")}, f)
    except Exception:
        pass


def _cron_loop():
    """
    Vòng lặp 24/7:
    - 9:00 AM mỗi ngày → Gửi 20 email (3-7 phút/email)
    - Cả ngày liên tục → Quét KS mới + Crawl email (xoay vòng 12 tỉnh)
    """
    vn_tz = timezone(timedelta(hours=7))
    print("⏰ [SCHEDULER] 24/7 khởi động!")
    log_activity("🚀 KHỞI ĐỘNG", "Hệ thống 24/7 sẵn sàng — 9AM gửi email, cả ngày săn data mới")

    # Toàn bộ 12 tỉnh thành trọng điểm — xoay vòng liên tục
    ALL_CITIES = [
        "Đà Nẵng", "Hội An", "Quảng Nam", "Huế", "Lăng Cô",
        "Quy Nhơn", "Tuy Hòa", "Nha Trang", "Cam Ranh",
        "Phan Thiết", "Đà Lạt", "Phú Quốc"
    ]
    city_index = 0          # Xoay vòng từng thành phố
    last_scout_time = 0
    SCOUT_INTERVAL = 180    # Quét mỗi 3 phút

    while _scheduler_running:
        try:
            now_vn = datetime.now(vn_tz)
            now_ts = time.time()
            today_str = now_vn.strftime("%Y-%m-%d")
            last_run_date = _get_last_run_date()

            # ── 1. GỬI EMAIL lúc đúng 9:00 AM (1 lần/ngày) ────────────────
            if now_vn.hour == 9 and last_run_date != today_str:
                _set_last_run_date(today_str)
                log_activity("📤 GỬI EMAIL 9AM", "Bắt đầu gửi 20 email với delay 3-7 phút/email...")
                run_daily_autopilot_job()

            # ── 2. SCAN + CRAWL DATA liên tục cả ngày ───────────────────────
            if now_ts - last_scout_time >= SCOUT_INTERVAL:
                last_scout_time = now_ts

                # Lấy 3 thành phố tiếp theo trong vòng xoay
                batch_cities = []
                for _ in range(3):
                    batch_cities.append(ALL_CITIES[city_index % len(ALL_CITIES)])
                    city_index += 1

                log_activity("🔍 SCAN DATA", f"Đang quét: {', '.join(batch_cities)}")
                run_continuous_scout_cycle(batch_cities)

        except Exception as e:
            print(f"⚠️ [SCHEDULER ERROR]: {e}")
            log_activity("⚠️ Lỗi Scheduler", str(e))

        time.sleep(15)


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
    run_continuous_scout_cycle(["Đà Nẵng", "Hội An", "Huế"])
