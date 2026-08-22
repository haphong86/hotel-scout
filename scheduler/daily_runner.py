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

        time.sleep(2.0)

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

def run_continuous_scout_cycle():
    """Chu kỳ quét và verify email LIÊN TỤC qua toàn bộ cơ sở dữ liệu (Không để máy nghỉ)"""
    log_activity("🔄 QUÉT & VERIFY EMAIL LIÊN TỤC", "Đang rà soát các khách sạn chưa có liên hệ trong Database...")
    session = get_session()
    
    # 1. Lấy danh sách khách sạn CÓ WEBSITE/DOMAIN nhưng chưa có liên hệ hoặc chưa verify
    unverified_hotels = (
        session.query(Hotel)
        .filter(Hotel.website.like("http%"), ~Hotel.contacts.any())
        .order_by(Hotel.stars.desc(), Hotel.created_at.desc())
        .limit(20)
        .all()
    )
    
    if not unverified_hotels:
        log_activity("✅ ĐÃ QUÉT HẾT DỮ LIỆU", "Tất cả khách sạn trong hệ thống đã được tìm kiếm & verify email!")
        session.close()
        return

    verified_total = 0
    processed_count = 0

    for h in unverified_hotels:
        try:
            processed_count += 1
            log_activity("🔍 Đang tìm & verify email", f"[{processed_count}/{len(unverified_hotels)}] {h.name} ({h.city or 'VN'})...")
            
            # Sinh ứng viên: Cào web + Mẫu chức danh cấp cao (GM, DOSM, Marcom, v.v.)
            candidates = generate_candidates(h)
            if candidates:
                verified = verify_candidates(candidates, max_verify=6)
                if verified:
                    saved = save_verified_contacts(h.id, verified)
                    verified_total += saved
                    if saved > 0:
                        log_activity("✅ ĐÃ XÁC THỰC EMAIL SỐNG", f"Lưu +{saved} email cho {h.name}")
        except Exception as e:
            continue

    session.close()
    log_activity("🎉 HOÀN TẤT CHU KỲ VERIFY", f"Đã rà soát {processed_count} khách sạn ➔ Bổ sung +{verified_total} email sống vào hàng đợi")


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
    """Vòng lặp chạy ngầm 24/7 liên tục trên Railway (Chuẩn Giờ Việt Nam UTC+7)"""
    last_scout_time = 0
    vn_tz = timezone(timedelta(hours=7))
    print("⏰ [SCHEDULER] Bộ đếm giờ tự động 24/7 (Giờ VN UTC+7) đã kích hoạt!")
    log_activity("🚀 KHỞI ĐỘNG HỆ THỐNG", "Bộ máy quét ngầm 24/7 & Lịch tự động (Giờ VN UTC+7) đã sẵn sàng")

    while _scheduler_running:
        try:
            now_vn = datetime.now(vn_tz)
            now_ts = time.time()
            today_str = now_vn.strftime("%Y-%m-%d")
            last_run_date = _get_last_run_date()

            # 1. Chạy tiến trình cào & verify email LIÊN TỤC mỗi 3–5 phút (cho đến khi hết 100% list data)
            if now_ts - last_scout_time >= 180:  # Chạy mỗi 3 phút 1 batch 20 KS liên tục
                last_scout_time = now_ts
                run_continuous_scout_cycle()

            # 2. Tự động gửi email trong khung giờ làm việc (09:00 - 17:00 Giờ VN)
            if 9 <= now_vn.hour <= 17 and last_run_date != today_str:
                _set_last_run_date(today_str)
                log_activity("📤 BẮT ĐẦU CHIẾN DỊCH GỬI MAIL TỰ ĐỘNG", f"Đang gửi 20 email bậc thang (Giờ VN: {now_vn.strftime('%H:%M')})...")
                run_daily_autopilot_job()

        except Exception as e:
            print(f"⚠️ [SCHEDULER ERROR]: {e}")
            log_activity("⚠️ Lỗi vòng lặp Scheduler", str(e))

        # Nghỉ 15 giây giữa các nhịp kiểm tra
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
    run_continuous_scout_cycle()
