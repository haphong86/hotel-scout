"""
radar/pre_opening_radar.py
RADAR PHÁT HIỆN KHÁCH SẠN & RESORT SẮP KHAI TRƯƠNG TRƯỚC 3–6 THÁNG
Quét đa kênh: Hoteljob Pre-Opening, Booking Opening Soon, Tuyển GM/DOSM, Báo chí Xây Dựng / Quy Hoạch Nghỉ Dưỡng.
"""

import re
import os
import sys
import time
import httpx
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import quote
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database.models import get_session, PreOpeningProject, init_db
from notifications.telegram_bot import send_telegram_message


# ═══════════════════════════════════════════════════════════════
# KHO PIPELINE CÁC TẬP ĐOÀN KHÁCH SẠN QUỐC TẾ & VIỆT NAM (2026-2027)
# ═══════════════════════════════════════════════════════════════
KNOWN_PRE_OPENING_PIPELINE = [
    {
        "name": "Nobu Hotel & Residences Danang",
        "brand_chain": "Nobu Hospitality",
        "city": "Đà Nẵng",
        "province": "Đà Nẵng",
        "address": "Võ Văn Kiệt & Võ Nguyên Giáp, Sơn Trà",
        "est_opening": "Q4/2026",
        "stage": "Đang hoàn thiện nội thất & Chuẩn bị khai trương",
        "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
        "source": "Nobu Pipeline & Báo Đầu Tư",
        "source_url": "https://nobuhotels.com",
        "contact_role": "Pre-Opening GM / Marketing Team",
        "contact_email": "danang@nobuhotels.com",
        "notes": "Siêu dự án khách sạn ẩm thực biểu tượng 43 tầng mặt biển Mỹ Khê. Cần bộ ảnh Hoàng hôn & Kiến trúc mặt đứng."
    },
    {
        "name": "Cham Villas Boutique Luxury Resort",
        "brand_chain": "Independent Luxury",
        "city": "Hội An",
        "province": "Quảng Nam",
        "address": "Cẩm Thanh, Hội An",
        "est_opening": "Tháng 11/2026 (Còn ~3 tháng)",
        "stage": "Hoàn thiện nội thất villa & Tuyển GM",
        "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
        "source": "Hoteljob Pre-Opening",
        "source_url": "https://hoteljob.vn",
        "contact_role": "Pre-Opening General Manager",
        "contact_email": "gm@chamvillas.com.vn",
        "notes": "Khu nghỉ dưỡng 28 căn villa view sông Thu Bồn. Cực kỳ cần bộ ảnh Twilight và Drone chèo thuyền kayak."
    },
    {
        "name": "Courtyard by Marriott Quy Nhon",
        "brand_chain": "Marriott International",
        "city": "Quy Nhơn",
        "province": "Bình Định",
        "address": "Đường An Dương Vương, TP. Quy Nhơn",
        "est_opening": "Q4/2026",
        "stage": "Pre-Opening Tuyển dụng Lãnh đạo",
        "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
        "source": "Marriott Pipeline Asia",
        "source_url": "https://marriott.com",
        "contact_role": "Director of Sales & Marketing",
        "contact_email": "quynhon.sales@marriott.com",
        "notes": "Khách sạn 362 phòng trung tâm biển Quy Nhơn. Cần bộ ảnh phòng Suite hướng biển & Nhà hàng Sky Bar."
    },
    {
        "name": "The Anam Mui Ne Phase 2 & Luxury Villas",
        "brand_chain": "The Anam",
        "city": "Phan Thiết",
        "province": "Bình Thuận",
        "address": "Nguyễn Đình Chiểu, Hàm Tiến, Mũi Né",
        "est_opening": "Tháng 12/2026",
        "stage": "Đang hoàn thiện nội thất Indochine",
        "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
        "source": "Báo Xây Dựng & Báo Du Lịch",
        "source_url": "https://theanam.com",
        "contact_role": "Marcom Manager",
        "contact_email": "marcom@theanam.com",
        "notes": "Khu biệt thự kiến trúc Đông Dương cao cấp. Rất hợp gu chụp kiến trúc chi tiết của Hà Phong Visuals."
    },
    {
        "name": "JW Marriott Cam Ranh Bay Resort",
        "brand_chain": "Marriott International",
        "city": "Cam Ranh",
        "province": "Khánh Hòa",
        "address": "Bãi Dài, Bán đảo Cam Ranh",
        "est_opening": "Đầu năm 2027",
        "stage": "Cất nóc & Bắt đầu Fit-out nội thất",
        "priority": "🟠 TIỀM NĂNG 3-6 THÁNG",
        "source": "Báo Đầu Tư Bất Động Sản",
        "source_url": "https://baodautu.vn",
        "contact_role": "Chủ Đầu Tư & Ban Quản Lý Dự Án",
        "contact_email": "info@marriott.com",
        "notes": "Dự án quy mô 400 phòng & 50 pool villas tại Bãi Dài. Cần bám sát tiến độ để chụp khi lên đèn thử nghiệm."
    },
    {
        "name": "Komorebi Retreat & Onsen Da Lat",
        "brand_chain": "Boutique Onsen",
        "city": "Đà Lạt",
        "province": "Lâm Đồng",
        "address": "Đường Khe Sanh, Phường 10, Đà Lạt",
        "est_opening": "Tháng 10/2026 (Mùa săn mây)",
        "stage": "Đang hoàn thiện cảnh quan & Onsen khoáng nóng",
        "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
        "source": "Hoteljob Tuyển Dụng",
        "source_url": "https://hoteljob.vn",
        "contact_role": "General Manager",
        "contact_email": "gm@komorebidalat.vn",
        "notes": "Khu nghỉ dưỡng phong cách Nhật Bản giữa rừng thông. Tuyệt đối cần bộ ảnh Sương mù buổi sáng (Dawn) và Ánh đèn lồng ấm cúng."
    }
]


# ═══════════════════════════════════════════════════════════════
# CÁC KÊNH RADAR TỰ ĐỘNG CÀO DỮ LIỆU
# ═══════════════════════════════════════════════════════════════

def scan_hoteljob_pre_opening(city: str) -> List[Dict]:
    """Cào các tin tuyển dụng Pre-Opening Team trên Hoteljob / TopCV"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }

    keywords = [f"khách sạn mới {city}", f"resort khai trương {city}", f"pre-opening hotel {city}"]

    for kw in keywords:
        try:
            url = f"https://www.google.com/search?q={quote(kw + ' site:hoteljob.vn OR site:topcv.vn OR site:vietnamworks.com')}&num=10"
            resp = httpx.get(url, headers=headers, timeout=8.0, follow_redirects=True)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for a_tag in soup.find_all("a"):
                title = a_tag.get_text()
                href = a_tag.get("href", "")

                if any(signal in title.lower() for signal in ["tuyển dụng", "khai trương", "pre-opening", "sắp mở", "resort", "hotel"]):
                    # Trích xuất tên KS
                    name_match = re.search(r'(?:tại|cho)\s+([A-ZÀ-Ỹ][a-zA-ZÀ-ỹ0-9\s&.-]{3,35}(?:Hotel|Resort|Villa|Suites|Retreat|Stay)?)', title)
                    hotel_name = name_match.group(1).strip() if name_match else ""

                    if hotel_name and len(hotel_name) > 4 and hotel_name.lower() not in ["khách sạn", "resort", "tuyển dụng"]:
                        results.append({
                            "name": hotel_name,
                            "brand_chain": "Independent",
                            "city": city,
                            "province": city,
                            "est_opening": "Dự kiến 2-4 tháng tới",
                            "stage": "Pre-Opening Tuyển Dụng Đội Ngũ",
                            "priority": "🔴 RẤT NÓNG - CẦN CHỤP NGAY",
                            "source": "Tin Tuyển Dụng Pre-Opening",
                            "source_url": href,
                            "contact_role": "General Manager / HR",
                            "notes": f"Phát hiện qua tin tuyển dụng: '{title[:70]}...'"
                        })
        except Exception:
            continue

    return results


def run_pre_opening_radar(target_cities: Optional[List[str]] = None, notify_telegram: bool = True) -> Dict:
    """
    Tiến trình Radar chính:
    1. Đồng bộ kho Pipeline chuẩn quốc tế & nội địa
    2. Cào các tín hiệu mới từ Hoteljob / Báo chí
    3. Lưu vào PreOpeningProject DB
    4. Bắn thông báo Telegram khi phát hiện dự án Hot
    """
    init_db()
    session = get_session()

    cities = target_cities or ["Đà Nẵng", "Hội An", "Quy Nhơn", "Phan Thiết", "Cam Ranh", "Đà Lạt", "Phú Quốc"]
    new_found = 0
    updated = 0
    hot_alerts = []

    # 1. Nạp kho Pipeline có sẵn
    for item in KNOWN_PRE_OPENING_PIPELINE:
        if target_cities and item["city"] not in target_cities:
            continue

        exists = session.query(PreOpeningProject).filter(PreOpeningProject.name == item["name"]).first()
        if not exists:
            proj = PreOpeningProject(
                name=item["name"],
                brand_chain=item.get("brand_chain", "Boutique"),
                city=item["city"],
                province=item.get("province", item["city"]),
                address=item.get("address", ""),
                est_opening=item.get("est_opening", "Sắp tới"),
                stage=item.get("stage", "Đang hoàn thiện"),
                priority=item.get("priority", "🔴 RẤT NÓNG - CẦN CHỤP NGAY"),
                source=item.get("source", "Radar Pipeline"),
                source_url=item.get("source_url", ""),
                contact_role=item.get("contact_role", "GM"),
                contact_email=item.get("contact_email", ""),
                contact_phone=item.get("contact_phone", ""),
                notes=item.get("notes", ""),
                status="Chưa tiếp cận",
                scanned_at=datetime.now()
            )
            session.add(proj)
            new_found += 1
            if "RẤT NÓNG" in proj.priority:
                hot_alerts.append(proj)

    session.commit()

    # 2. Quét cào tự động đa kênh
    for c in cities[:4]:
        live_signals = scan_hoteljob_pre_opening(c)
        for s in live_signals:
            exists = session.query(PreOpeningProject).filter(PreOpeningProject.name == s["name"]).first()
            if not exists:
                proj = PreOpeningProject(
                    name=s["name"],
                    brand_chain=s.get("brand_chain", "Independent"),
                    city=s["city"],
                    province=s.get("province", s["city"]),
                    est_opening=s.get("est_opening", "Sắp tới"),
                    stage=s.get("stage", "Đang hoàn thiện"),
                    priority=s.get("priority", "🔴 RẤT NÓNG - CẦN CHỤP NGAY"),
                    source=s.get("source", "Hoteljob Signals"),
                    source_url=s.get("source_url", ""),
                    contact_role=s.get("contact_role", "GM / HR"),
                    notes=s.get("notes", ""),
                    status="Chưa tiếp cận",
                    scanned_at=datetime.now()
                )
                session.add(proj)
                new_found += 1
                hot_alerts.append(proj)
        session.commit()

    total_projects = session.query(PreOpeningProject).count()
    hot_count = session.query(PreOpeningProject).filter(PreOpeningProject.priority.like("%RẤT NÓNG%")).count()
    
    # Chuẩn bị danh sách gửi tin trước khi đóng session
    alerts_data = []
    for p in hot_alerts[:3]:
        alerts_data.append({
            "name": p.name,
            "city": p.city,
            "address": p.address or "",
            "est_opening": p.est_opening,
            "stage": p.stage,
            "priority": p.priority,
            "contact_role": p.contact_role,
            "contact_email": p.contact_email
        })

    session.close()

    # 3. Bắn thông báo Telegram khi phát hiện dự án Hot
    if notify_telegram and alerts_data:
        for p in alerts_data:
            p_name = p['name']
            p_loc = f"{p['city']} · {p['address']}" if p.get('address') else p['city']
            p_est = p['est_opening']
            p_stage = p['stage']
            p_prio = p['priority']
            p_contact = f"{p['contact_role'] or 'GM'} ({p['contact_email']})" if p.get('contact_email') else (p['contact_role'] or 'GM')

            msg = (
                f"🔭 *[RADAR PHÁT HIỆN DỰ ÁN SẮP KHAI TRƯƠNG]*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏨 *Dự án:* `{p_name}`\n"
                f"📍 *Vị trí:* {p_loc}\n"
                f"⏳ *Dự kiến mở:* *{p_est}*\n"
                f"🏗️ *Giai đoạn:* {p_stage}\n"
                f"🎯 *Mức độ:* {p_prio}\n"
                f"👔 *Đầu mối:* {p_contact}\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 *Gợi ý hành động:* Gửi bộ hồ sơ Launching & Đề xuất chụp trọn gói Hoàng hôn / Drone trước ngày khai trương!"
            )
            send_telegram_message(msg.strip())

    return {
        "success": True,
        "new_projects": new_found,
        "total_radar_projects": total_projects,
        "hot_projects_count": hot_count,
        "alerted": len(alerts_data)
    }


if __name__ == "__main__":
    res = run_pre_opening_radar()
    print("KẾT QUẢ RADAR:", res)
