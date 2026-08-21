"""
tools/mass_exhaustive_verifier.py — CỖ MÁY SINH TRỌN BỘ MẪU EMAIL KHẢ DĨ & TEST SỐNG TRỰC TIẾP QUA SMTP
1. Quét từng khách sạn có domain trong database
2. Sinh toàn bộ ~25 mẫu email chức vụ (GM, CEO, Marcom, DOSM, Sales, Info, Res)
3. Bắt tay trực tiếp với Mail Server (SMTP Handshake Ping) để kiểm tra hòm thư có tồn tại thật hay không
4. Chỉ lưu những email TRẢ VỀ MÃ 250 OK (HÒM THƯ SỐNG 100%) vào bảng Contacts để sẵn sàng gửi
"""
import sys
import os
import re
import time
import socket
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import get_session, Hotel, Contact
from extractor.email_verifier import check_mx, check_smtp_mailbox_exists
from extractor.free_email_finder import is_blacklisted_domain, get_domain_from_website
from extractor.ai_contact_reasoner import reason_contact_role

EXHAUSTIVE_PREFIXES = [
    # 1. Ban Lãnh Đạo & Chủ Đầu Tư
    ("gm@", "Tổng Giám Đốc (General Manager)", 98),
    ("generalmanager@", "Tổng Giám Đốc (General Manager)", 98),
    ("hotelmanager@", "Giám Đốc Khách Sạn (Hotel Manager)", 95),
    ("resortmanager@", "Giám Đốc Khu Nghỉ Dưỡng (Resort Manager)", 95),
    ("director@", "Giám Đốc Điều Hành (Director)", 95),
    ("managingdirector@", "Tổng Giám Đốc Điều Hành", 95),
    ("giamdoc@", "Ban Giám Đốc", 95),
    ("ceo@", "Chủ Đầu Tư / CEO", 95),
    
    # 2. Ban Tiếp Thị & Truyền Thông
    ("marcom@", "Giám Đốc / Trưởng Phòng Marketing & Truyền Thông (Marcom)", 95),
    ("marketing@", "Phòng Tiếp Thị & Truyền Thông", 90),
    ("pr@", "Trưởng Phòng Truyền Thông & Đối Ngoại (PR)", 90),
    ("communications@", "Phòng Truyền Thông Thương Hiệu", 90),
    ("media@", "Bộ Phận Media & Visual Thương Hiệu", 90),
    ("brand@", "Quản Lý Thương Hiệu (Brand Manager)", 90),
    ("mkt@", "Phòng Marketing", 88),

    # 3. Ban Kinh Doanh & Doanh Thu
    ("dosm@", "Giám Đốc Tiếp Thị & Kinh Doanh (DOSM)", 92),
    ("dos@", "Giám Đốc Kinh Doanh (Director of Sales)", 90),
    ("sales@", "Phòng Kinh Doanh (Sales Department)", 88),
    ("sale@", "Phòng Kinh Doanh", 88),
    ("salesmanager@", "Trưởng Phòng Kinh Doanh", 88),
    ("kinhdoanh@", "Phòng Kinh Doanh", 85),

    # 4. Đầu Mối Tiếp Nhận Hợp Tác & Lễ Tân
    ("info@", "Ban Quản Lý & Tiếp Nhận Hợp Tác", 82),
    ("contact@", "Bộ Phận Tiếp Nhận Liên Hệ", 82),
    ("reservation@", "Bộ Phận Đặt Phòng & Chăm Sóc Khách Hàng", 80),
    ("reservations@", "Bộ Phận Đặt Phòng & Chăm Sóc Khách Hàng", 80),
    ("welcome@", "Bộ Phận Đón Tiếp & Hợp Tác", 80),
]


def test_and_save_hotel_emails(hotel_id: int) -> int:
    session = get_session()
    saved_count = 0
    try:
        hotel = session.query(Hotel).filter(Hotel.id == hotel_id).first()
        if not hotel or not hotel.website:
            return 0

        domain = get_domain_from_website(hotel.website)
        if not domain or is_blacklisted_domain(domain):
            return 0

        mx_host = check_mx(domain)
        if not mx_host:
            return 0

        existing_emails = {c.email.lower() for c in hotel.contacts if c.email}

        for prefix, role_title, conf_score in EXHAUSTIVE_PREFIXES:
            cand_email = f"{prefix}{domain}".lower()
            if cand_email in existing_emails:
                continue

            # BẮT TAY THỰC TẾ QUA SMTP PING
            alive = check_smtp_mailbox_exists(cand_email, mx_host, timeout=3.5)
            if alive is True:
                reasoning = reason_contact_role(cand_email)
                new_contact = Contact(
                    hotel_id=hotel.id,
                    name=f"Ban Lãnh Đạo {hotel.name}",
                    title=reasoning.get("role_title") or role_title,
                    email=cand_email,
                    confidence=conf_score,
                    source="smtp_verified_pattern",
                    is_valid=True,
                    verify_status="VALID"
                )
                session.add(new_contact)
                existing_emails.add(cand_email)
                saved_count += 1
                print(f"  🎉 [TÌM THẤY & SỐNG 100%] [{hotel.city}] {hotel.name} ➔ {cand_email} ({role_title})")
                sys.stdout.flush()

        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()
    return saved_count


def run_mass_exhaustive_scan(max_hotels: int = 150):
    session = get_session()
    hotels = (
        session.query(Hotel)
        .filter(Hotel.website != None, Hotel.website.like('http%'))
        .order_by(Hotel.rating.desc(), Hotel.stars.desc())
        .limit(max_hotels)
        .all()
    )
    hotel_ids = [h.id for h in hotels]
    session.close()

    print(f"🚀 BẮT ĐẦU QUÉT TOÀN BỘ 25 MẪU EMAIL & TEST SỐNG CHO {len(hotel_ids)} KHÁCH SẠN/RESORT...")
    print("=" * 70)
    sys.stdout.flush()

    total_discovered = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(test_and_save_hotel_emails, hid): hid for hid in hotel_ids}
        for future in as_completed(futures):
            try:
                res = future.result()
                total_discovered += res
            except Exception:
                pass

    print("=" * 70)
    print(f"🏆 HOÀN TẤT CHIẾN DỊCH! ĐÃ XÁC THỰC THÀNH CÔNG THÊM +{total_discovered} EMAIL SỐNG THẬT 100% VÀO DATABASE!")


if __name__ == "__main__":
    run_mass_exhaustive_scan(max_hotels=100)
