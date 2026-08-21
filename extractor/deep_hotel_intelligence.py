"""
extractor/deep_hotel_intelligence.py — BỘ NÃO QUÉT SÂU ĐA KÊNH & PHÂN LOẠI QUYỀN HẠN QUYẾT ĐỊNH CHỤP ẢNH
1. Quét sâu toàn diện Website: Contact, About, Team, Ban Giám Đốc, Media, Weddings, Careers/Tuyển dụng
2. Quét Social & Metadata liên quan
3. Dự đoán bộ mẫu email Lãnh đạo & Test sống 100% qua SMTP Handshake (Mã 250 OK)
4. BỘ LỌC NGHIÊM NGẶT: Chỉ lưu DUY NHẤT các bộ phận có THẨM QUYỀN QUYẾT ĐỊNH THUÊ CHỤP ẢNH / QUAY TVC:
   - 👑 Ban Giám Đốc / Chủ Đầu Tư (GM, CEO, Managing Director, Resort Manager)
   - 🎨 Ban Marketing & Truyền Thông (DOSM, Marcom Manager, PR, Brand, Media)
   - 💼 Ban Kinh Doanh & Sự Kiện (Sales Director, MICE & Wedding Manager)
"""
import re
import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Set, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from extractor.email_verifier import check_mx, check_smtp_mailbox_exists
from extractor.free_email_finder import is_blacklisted_domain, get_domain_from_website

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Các đường dẫn chuyên sâu chứa email của Ban Giám Đốc, Marketing, Sales & Tuyển dụng Lãnh đạo
DEEP_SCAN_PATHS = [
    "", "/contact", "/lien-he", "/about", "/team", "/management",
    "/press", "/weddings", "/events", "/careers", "/tuyen-dung"
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
MAILTO_REGEX = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', re.IGNORECASE)

# 🚫 CÁC BỘ PHẬN BỊ LOẠI TRỪ TUYỆT ĐỐI (Không có quyền quyết định chụp ảnh)
EXCLUDE_DEPARTMENTS = [
    "accounting@", "finance@", "ketoan@", "taichinh@", "tax@",
    "it@", "tech@", "support-tech@", "engineering@", "kythuat@", "baotri@",
    "housekeeping@", "buongphong@", "security@", "anninh@", "bep@", "chef@",
    "purchasing@", "muahang@", "legal@", "phaply@"
]

# 🎯 BẢN ĐỒ BỘ PHẬN QUYẾT ĐỊNH CHỤP ẢNH & THẨM QUYỀN
DECISION_MAKER_DEPARTMENTS = [
    {
        "type": "GM_EXECUTIVE",
        "role_title": "Tổng Giám Đốc / Ban Giám Đốc (GM / Executive)",
        "power": "🟢 QUYẾT ĐỊNH TỐI CAO (Ký duyệt ngân sách & Concept)",
        "email_patterns": ["gm@", "generalmanager@", "hotelmanager@", "resortmanager@", "director@", "managingdirector@", "giamdoc@", "ceo@", "owner@"],
        "context_keywords": ["general manager", "tổng giám đốc", "giám đốc điều hành", "hotel manager", "resort manager", "ceo", "chủ đầu tư", "ban giám đốc"],
        "priority_score": 98
    },
    {
        "type": "MARKETING_DECISION_MAKER",
        "role_title": "Giám Đốc / Trưởng Phòng Marketing & Truyền Thông (DOSM / Marcom)",
        "power": "🟢 TRỰC TIẾP LỰA CHỌN ĐƠN VỊ CHỤP ẢNH & QUAY TVC",
        "email_patterns": ["marcom@", "marketing@", "pr@", "communications@", "media@", "brand@", "mkt@", "digital@", "creative@"],
        "context_keywords": ["marketing", "marcom", "truyền thông", "tiếp thị", "quảng bá", "pr manager", "brand manager", "media", "giám đốc tiếp thị", "dosm"],
        "priority_score": 95
    },
    {
        "type": "SALES_COMMERCIAL",
        "role_title": "Giám Đốc / Trưởng Phòng Kinh Doanh & Sự Kiện (Sales & Events)",
        "power": "🟢 ĐẦU MỐI ĐỀ XUẤT HÌNH ẢNH PHÒNG & SỰ KIỆN MICE",
        "email_patterns": ["dosm@", "dos@", "sales@", "sale@", "salesmanager@", "mice@", "wedding@", "event@", "kinhdoanh@", "salesgroup@"],
        "context_keywords": ["director of sales", "sales manager", "giám đốc kinh doanh", "phòng sales", "wedding", "events", "sự kiện", "tiệc cưới"],
        "priority_score": 90
    },
    {
        "type": "CENTRAL_DESK",
        "role_title": "Ban Quản Lý & Đầu Mối Tiếp Nhận Hợp Tác (Central Desk)",
        "power": "🟡 ĐẦU MỐI TIẾP NHẬN & CHUYỂN TIẾP CHO BAN LÃNH ĐẠO",
        "email_patterns": ["info@", "contact@", "reservation@", "reservations@", "welcome@"],
        "context_keywords": ["liên hệ", "contact", "ban quản lý", "đặt phòng"],
        "priority_score": 82
    }
]


def classify_photography_decision_maker(email: str, surrounding_text: str = "") -> Optional[Dict]:
    """
    Kiểm tra email có thuộc bộ phận có quyền quyết định chụp ảnh không.
    Trả về Dict thông tin quyền hạn HOẶC None nếu là bộ phận không liên quan (Kế toán/IT/Tạp vụ).
    """
    em_l = email.strip().lower()
    ctx_l = surrounding_text.strip().lower()

    # 1. Loại bỏ các bộ phận không liên quan đến hình ảnh (Kế toán, IT, Bếp, Kỹ thuật...)
    if any(em_l.startswith(bad) for bad in EXCLUDE_DEPARTMENTS):
        return None

    # 2. Phân loại thẩm quyền
    for dept in DECISION_MAKER_DEPARTMENTS:
        # Kiểm tra tiền tố email
        prefix = em_l.split("@")[0]
        if any(prefix.startswith(p.replace("@", "")) for p in dept["email_patterns"]):
            return dept

        # Kiểm tra ngữ cảnh văn bản xung quanh
        if any(kw in ctx_l for kw in dept["context_keywords"]):
            return dept

    # Nếu là email tên riêng thuộc domain công ty nhưng không rõ phòng ban -> Xếp vào Đầu mối
    if not any(d in em_l for d in ["gmail.com", "yahoo.com", "hotmail.com"]):
        return DECISION_MAKER_DEPARTMENTS[3]

    return None


def deep_scan_hotel_intelligence(website_url: str, hotel_name: str = "") -> List[Dict]:
    """
    QUÉT SÂU TOÀN DIỆN MỌI NGUỒN CỦA WEBSITE KHÁCH SẠN:
    1. Cào sâu toàn bộ các trang Contact, About, Team, Media, Events, Careers
    2. Dự đoán toàn bộ mẫu Lãnh đạo & Bắt tay SMTP Mailbox Ping
    3. Lọc chỉ giữ lại DUY NHẤT các bộ phận quyết định chụp ảnh
    """
    if not website_url or not str(website_url).startswith("http"):
        return []

    parsed = urlparse(website_url)
    domain = get_domain_from_website(website_url)
    if not domain or is_blacklisted_domain(domain):
        return []

    mx_host = check_mx(domain)
    discovered_raw = set()

    # ══════════════════════════════════════════════════════════
    # BƯỚC 1: CÀO SÂU TOÀN BỘ CÁC TRANG TRỌNG YẾU
    # ══════════════════════════════════════════════════════════
    for path in DEEP_SCAN_PATHS:
        target_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", path)
        try:
            r = requests.get(target_url, headers=HEADERS, timeout=3.5, allow_redirects=True)
            if r.status_code == 200:
                # Trích xuất mailto:
                for m in MAILTO_REGEX.findall(r.text):
                    clean_m = m.split("?")[0].strip().lower()
                    if "@" in clean_m and len(clean_m) > 6:
                        discovered_raw.add((clean_m, "website_crawled", ""))

                # Trích xuất text regex kèm ngữ cảnh
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                page_text = soup.get_text(separator=" ", strip=True)

                for match in EMAIL_REGEX.finditer(page_text):
                    em = match.group(0).lower().strip()
                    if len(em) > 6 and not is_blacklisted_domain(em.split("@")[-1]):
                        start = max(0, match.start() - 100)
                        end = min(len(page_text), match.end() + 100)
                        ctx = page_text[start:end]
                        discovered_raw.add((em, "website_crawled", ctx))
        except Exception:
            continue

    # ══════════════════════════════════════════════════════════
    # BƯỚC 2: SINH MẪU LÃNH ĐẠO DỰ ĐOÁN & KIỂM TRA BẮT TAY SMTP PING
    # ══════════════════════════════════════════════════════════
    if mx_host:
        predicted_prefixes = [
            "gm@", "generalmanager@", "hotelmanager@", "resortmanager@", "ceo@",
            "marcom@", "marketing@", "pr@", "communications@", "media@",
            "dosm@", "dos@", "sales@", "sale@", "mice@", "wedding@",
            "info@", "contact@", "reservation@", "reservations@"
        ]
        crawled_emails = {item[0] for item in discovered_raw}
        for prefix in predicted_prefixes:
            cand_email = f"{prefix}{domain}".lower()
            if cand_email not in crawled_emails:
                # Bắt tay SMTP kiểm tra hòm thư có tồn tại thực sự (250 OK)
                alive = check_smtp_mailbox_exists(cand_email, mx_host, timeout=3.0)
                if alive is True:
                    discovered_raw.add((cand_email, "smtp_verified_pattern", ""))

    # ══════════════════════════════════════════════════════════
    # BƯỚC 3: LỌC NGHIÊM NGẶT — CHỈ GIỮ BỘ PHẬN QUYẾT ĐỊNH CHỤP ẢNH
    # ══════════════════════════════════════════════════════════
    final_decision_makers = []
    seen = set()

    for em, source, ctx in discovered_raw:
        if em in seen:
            continue

        decision_info = classify_photography_decision_maker(em, surrounding_text=ctx)
        if decision_info is not None:
            # Kiểm tra MX hợp lệ
            em_dom = em.split("@")[-1]
            if check_mx(em_dom):
                final_decision_makers.append({
                    "email": em,
                    "role_type": decision_info["type"],
                    "role_title": decision_info["role_title"],
                    "decision_power": decision_info["power"],
                    "confidence": decision_info["priority_score"],
                    "source": source,
                    "hotel_name": hotel_name
                })
                seen.add(em)

    # Sắp xếp theo thứ tự quyền hạn: Ban Giám Đốc (GM) -> Marketing (Marcom) -> Sales -> Ban Quản Lý
    final_decision_makers.sort(key=lambda x: -x["confidence"])
    return final_decision_makers
