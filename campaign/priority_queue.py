import sys, os, re
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import get_session, Hotel, Contact, EmailLog, PreOpeningProject
from scoring import score_hotel
from extractor.free_email_finder import is_blacklisted_domain


def is_strictly_valid_email(email: str) -> bool:
    """Kiểm tra email chuẩn RFC 5322: 1 dấu @, không khoảng trắng, không http, đuôi domain hợp lệ"""
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if " " in email or "http" in email or ":" in email or "/" in email or email.count("@") != 1:
        return False
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
        return False
    domain = email.split("@")[1]
    tld = domain.split(".")[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False
    return True


def get_prioritized_outreach_queue(limit: int = 20, selected_cities: list = None) -> List[Dict]:
    """
    Xây dựng danh sách hàng đợi gửi thư từ #1 đến #limit.
    Tự động LOẠI BỎ 100% các khách sạn & email đã gửi, luôn đẩy các email CHƯA GỬI lên đầu.
    """
    session = get_session()
    now = datetime.now()
    queue = []
    seen_hotel_names = set()
    
    # 1. Thu thập danh sách email và hotel_id ĐÃ TỪNG GỬI để loại trừ tuyệt đối
    sent_logs = session.query(EmailLog).all()
    seen_emails = {
        l.subject.lower() for l in sent_logs if l.subject
    }
    sent_hotel_ids = {
        l.hotel_id for l in sent_logs if l.hotel_id
    }
    for l in sent_logs:
        if l.contact and l.contact.email:
            seen_emails.add(l.contact.email.strip().lower())

    # ══════════════════════════════════════════════════════════
    # NHÓM 1: DỰ ÁN PRE-OPENING / SẮP KHAI TRƯƠNG (ƯU TIÊN SỐ 1 TUYỆT ĐỐI)
    # ══════════════════════════════════════════════════════════
    q_pre = session.query(PreOpeningProject).filter(
        PreOpeningProject.status == "Chưa tiếp cận",
        PreOpeningProject.contact_email.isnot(None),
        PreOpeningProject.contact_email != ""
    )
    if selected_cities:
        q_pre = q_pre.filter(PreOpeningProject.city.in_(selected_cities))

    pre_projects = q_pre.all()
    pre_projects.sort(key=lambda p: 0 if "RẤT NÓNG" in (p.priority or "") else 1)

    for p in pre_projects:
        if len(queue) >= limit:
            break
        c_email = (p.contact_email or "").strip().lower()
        if not is_strictly_valid_email(c_email) or c_email in seen_emails or is_blacklisted_domain(c_email.split("@")[-1]):
            continue

        queue.append({
            "queue_index": len(queue) + 1,
            "priority_tier": "🌟 BẬC 1: PRE-OPENING (SẮP KHAI TRƯƠNG)",
            "priority_badge": "🔴 RẤT GẤP",
            "type": "pre_opening",
            "project_id": p.id,
            "hotel_id": None,
            "contact_id": None,
            "hotel_name": p.name,
            "city": p.city,
            "stage": p.stage or "Đang hoàn thiện nội thất",
            "est_opening": p.est_opening or "Sắp mở",
            "recipient_name": p.contact_name or p.contact_role or "General Manager",
            "recipient_role": p.contact_role or "General Manager",
            "recipient_email": c_email,
            "email_status": "✅ VALID (Chính danh)",
            "template_type": "email_pre_opening.html",
            "reason": f"Khai trương {p.est_opening} · {p.stage}. Cần bộ ảnh trước 60 ngày để mở bán OTA.",
            "lead_score": 98
        })
        seen_hotel_names.add(p.name.lower())
        seen_emails.add(c_email)

    # ══════════════════════════════════════════════════════════
    # NHÓM 2: KHÁCH SẠN MỚI & CHƯA TỪNG GỬI EMAIL (WATERFALL CADENCE)
    # ══════════════════════════════════════════════════════════
    if len(queue) < limit:
        # Lấy các khách sạn CHƯA TỪNG LIÊN HỆ
        q_hotels = session.query(Hotel).filter(
            Hotel.status.notin_(["Đã liên hệ", "Đã reply", "Không quan tâm"]),
            Hotel.id.notin_(sent_hotel_ids) if sent_hotel_ids else True
        )
        if selected_cities:
            q_hotels = q_hotels.filter(Hotel.city.in_(selected_cities))

        candidate_hotels = q_hotels.all()

        # Tính điểm Lead Score cho từng khách sạn
        scored_hotels = []
        for h in candidate_hotels:
            if h.name.lower() in seen_hotel_names:
                continue

            score_data = score_hotel(h)
            scored_hotels.append((h, score_data))

        # Sắp xếp theo Lead Score từ cao xuống thấp
        scored_hotels.sort(key=lambda x: x[1]["score"], reverse=True)

        for h, score_data in scored_hotels:
            if len(queue) >= limit:
                break

            contacts = h.contacts or []
            if not contacts:
                continue

            # Áp dụng Waterfall Cadence: GM -> DOSM -> Marketing -> Sales
            # Tìm danh sách email đã gửi trước đây
            sent_contact_ids = {
                l.contact_id for l in session.query(EmailLog).filter(EmailLog.hotel_id == h.id).all()
            }

            def role_rank(c):
                t = (c.title or "").lower()
                e = (c.email or "").lower()
                if "general manager" in t or "gm@" in e or "ceo" in t or "tổng giám đốc" in t:
                    return 1
                if "director of sales" in t or "dosm" in t or "giám đốc sales" in t:
                    return 2
                if "marketing" in t or "marcom" in t or "mkt" in e:
                    return 3
                if "sales" in t:
                    return 4
                return 5

            sorted_contacts = sorted(contacts, key=role_rank)
            
            # Chọn contact tiếp theo trong Waterfall Cadence
            chosen_c = None
            for c in sorted_contacts:
                if c.id not in sent_contact_ids:
                    c_email = (c.email or "").strip().lower()
                    if is_strictly_valid_email(c_email) and c_email not in seen_emails and not is_blacklisted_domain(c_email.split("@")[-1]):
                        chosen_c = c
                        break

            if not chosen_c:
                continue

            tier_label = "🔥 BẬC 2: HOT LEADS (SCORE ≥ 70)" if score_data["score"] >= 70 else "⭐ BẬC 3: TIỀM NĂNG (SCORE 50–69)"
            badge = "🔴 HOT" if score_data["score"] >= 70 else "🟠 TIỀM NĂNG"

            queue.append({
                "queue_index": len(queue) + 1,
                "priority_tier": tier_label,
                "priority_badge": badge,
                "type": "hotel",
                "project_id": None,
                "hotel_id": h.id,
                "contact_id": chosen_c.id,
                "hotel_name": h.name,
                "city": h.city or "Việt Nam",
                "stage": f"Đang hoạt động ({h.stars or 4}★)",
                "est_opening": "Đang kinh doanh",
                "recipient_name": chosen_c.name or chosen_c.title or "Ban Lãnh Đạo",
                "recipient_role": chosen_c.title or "General Manager",
                "recipient_email": chosen_c.email,
                "email_status": "✅ VALID (MX Checked)" if chosen_c.verify_status == "VALID" else "⚠️ LIKELY",
                "template_type": "email_hotel_pitch_vi.html",
                "reason": " · ".join(score_data["reasons"][:2]),
                "lead_score": score_data["score"]
            })
            seen_hotel_names.add(h.name.lower())
            seen_emails.add(chosen_c.email.lower())

    session.close()
    return queue


if __name__ == "__main__":
    q = get_prioritized_outreach_queue(limit=10)
    print(f"📋 HÀNG ĐỢI GỬI EMAIL ƯU TIÊN ({len(q)} email):")
    for item in q:
        print(f" #{item['queue_index']} [{item['priority_badge']}] {item['hotel_name']} ({item['city']}) ➔ {item['recipient_email']} ({item['recipient_role']}) - Score: {item['lead_score']}")
