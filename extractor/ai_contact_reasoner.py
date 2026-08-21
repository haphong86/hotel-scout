"""
extractor/ai_contact_reasoner.py — BỘ NÃO SUY LUẬN DANH TÍNH & CHỨC VỤ THÔNG MINH (AI ROLE REASONING ENGINE)
Phân tích ngữ cảnh web (DOM context, Section, Chức danh, Tiền tố email):
1. Suy luận chính xác: Người này là AI? Làm gì? Giữ chức vụ gì?
2. Đánh giá Mức độ quyền hạn (Quyết định ngân sách / Quyết định thuê thợ / Đầu mối chuyển tiếp)
3. Tự động cá nhân hóa thông điệp gửi thư theo đúng chuyên môn của từng người
"""
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Optional


# Bản đồ phân tích từ khóa chức vụ và phòng ban trong ngành Khách Sạn / Resort
ROLE_PATTERNS = [
    {
        "type": "GM_EXECUTIVE",
        "display_vi": "Tổng Giám Đốc (General Manager)",
        "display_en": "General Manager / Managing Director",
        "decision_power": "🟢 QUYẾT ĐỊNH TỐI CAO (Ký duyệt ngân sách)",
        "email_keywords": ["gm@", "generalmanager", "ceo@", "owner@", "managingdirector", "director@", "giamdoc@"],
        "context_keywords": ["general manager", "tổng giám đốc", "giám đốc điều hành", "hotel manager", "resort manager", "managing director", "ceo", "chủ đầu tư", "ban giám đốc"],
        "pitch_angle": "Tối ưu hóa hình ảnh kiến trúc giúp nâng tầm thương hiệu và tăng 35% tỷ lệ đặt phòng trực tiếp (Direct Booking ROI)."
    },
    {
        "type": "MARKETING_DECISION_MAKER",
        "display_vi": "Giám Đốc / Trưởng Phòng Marketing & Truyền Thông (DOSM / Marcom)",
        "display_en": "Director of Marketing & Communications / Marcom",
        "decision_power": "🟢 TRỰC TIẾP CHỌN ĐƠN VỊ CHỤP ẢNH & VISUAL",
        "email_keywords": ["marcom@", "marketing@", "mkt@", "pr@", "communications@", "brand@", "media@", "creative@"],
        "context_keywords": ["marketing", "marcom", "truyền thông", "tiếp thị", "quảng bá", "pr manager", "brand manager", "content", "giám đốc tiếp thị", "trưởng phòng marketing", "dosm"],
        "pitch_angle": "Giải pháp bộ ảnh kiến trúc chuẩn tạp chí, hình ảnh hoàng hôn Twilight & Video TVC không gian giúp chiến dịch truyền thông bùng nổ tương tác."
    },
    {
        "type": "SALES_DIRECTOR",
        "display_vi": "Giám Đốc / Trưởng Phòng Kinh Doanh (Sales Director)",
        "display_en": "Director of Sales / Sales Manager",
        "decision_power": "🟢 ĐẦU MỐI ĐỀ XUẤT NÂNG CẤP HÌNH ẢNH ĐỂ BÁN PHÒNG",
        "email_keywords": ["sales@", "dos@", "salesmanager@", "sale@", "kinhdoanh@", "b2b@"],
        "context_keywords": ["director of sales", "sales manager", "giám đốc kinh doanh", "trưởng phòng kinh doanh", "phòng sales", "kinh doanh & tiếp thị"],
        "pitch_angle": "Bộ ảnh chuẩn OTA (Booking.com, Agoda) và Profile bán phòng sang trọng giúp đẩy nhanh tốc độ chốt hợp đồng khách sạn và đối tác lữ hành."
    },
    {
        "type": "CENTRAL_DESK",
        "display_vi": "Ban Quản Lý & Đầu Mối Tiếp Nhận Hợp Tác",
        "display_en": "Executive Office & Partnership Desk",
        "decision_power": "🟡 ĐẦU MỐI TIẾP NHẬN & CHUYỂN TIẾP CHO BAN LÃNH ĐẠO",
        "email_keywords": ["info@", "contact@", "reservation@", "res@", "welcome@", "hello@", "support@", "admin@"],
        "context_keywords": ["liên hệ", "contact us", "đặt phòng", "văn phòng", "hỗ trợ", "ban quản lý"],
        "pitch_angle": "Kính gửi Ban Quản Lý và Bộ phận Hợp tác Truyền thông chuyển tiếp đề xuất giải pháp hình ảnh thương hiệu tới Ban Giám Đốc."
    }
]


def reason_contact_role(email: str, surrounding_text: str = "", html_card: str = "") -> Dict:
    """
    Bộ suy luận AI: Phân tích Email + Ngữ cảnh văn bản + Khối HTML xung quanh
    để xác định danh tính, chức vụ, quyền hạn và kịch bản pitch chuẩn xác nhất.
    """
    email_l = email.strip().lower()
    combined_context = f"{email_l} {surrounding_text.lower()} {html_card.lower()}"

    # 1. Trích xuất tên riêng nếu xuất hiện trong ngữ cảnh (VD: "Mr. David Nguyen", "Ông Trần Hoàng")
    extracted_name = ""
    name_patterns = [
        r'(?:ông|bà|mr\.|ms\.|mrs\.)\s+([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,3})',
        r'([A-ZÀ-Ỹ][a-zà-ỹ]+\s+[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)?)\s*[-–—:]\s*(?:General Manager|Giám Đốc|Marketing|Sales|Trưởng Phòng)'
    ]
    for np in name_patterns:
        match = re.search(np, f"{surrounding_text} {html_card}", re.IGNORECASE)
        if match:
            extracted_name = match.group(1).strip()
            break

    # 2. Suy luận chức vụ theo độ ưu tiên
    matched_role = ROLE_PATTERNS[3]  # Mặc định là Central Desk

    # Ưu tiên kiểm tra email prefix trước
    prefix = email_l.split("@")[0]
    for r in ROLE_PATTERNS:
        if any(prefix.startswith(k.replace("@", "")) for k in r["email_keywords"]):
            matched_role = r
            break

    # Nếu email chung chung (như info@), kiểm tra ngữ cảnh xung quanh để suy luận chức vụ thực tế
    if matched_role["type"] == "CENTRAL_DESK":
        for r in ROLE_PATTERNS[:3]:  # Kiểm tra GM, Marketing, Sales
            if any(k in combined_context for k in r["context_keywords"]):
                matched_role = r
                break

    return {
        "email": email,
        "person_name": extracted_name or ("Quý Đối Tác" if matched_role["type"] == "CENTRAL_DESK" else matched_role["display_vi"]),
        "role_type": matched_role["type"],
        "role_title": matched_role["display_vi"],
        "role_title_en": matched_role["display_en"],
        "decision_power": matched_role["decision_power"],
        "pitch_angle": matched_role["pitch_angle"],
        "is_decision_maker": "QUYẾT ĐỊNH" in matched_role["decision_power"]
    }


def extract_emails_with_ai_reasoning(html: str) -> List[Dict]:
    """
    Bóc tách toàn bộ email trong trang HTML kèm đoạn ngữ cảnh xung quanh (150 chars)
    và chạy suy luận danh tính AI cho từng email.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Xóa script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text_all = soup.get_text(separator=" ", strip=True)
    
    # Tìm email kèm ngữ cảnh
    email_regex = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
    discovered = []
    seen = set()

    for match in email_regex.finditer(text_all):
        em = match.group(0).lower().strip()
        if em in seen or len(em) < 6:
            continue
        
        # Lấy 150 ký tự trước và sau email để làm ngữ cảnh suy luận
        start = max(0, match.start() - 150)
        end = min(len(text_all), match.end() + 150)
        context = text_all[start:end]

        reasoning = reason_contact_role(em, surrounding_text=context)
        discovered.append(reasoning)
        seen.add(em)

    # Sắp xếp ưu tiên: Người có quyền quyết định (GM / Marketing / Sales) lên trên cùng
    discovered.sort(key=lambda x: 0 if x["is_decision_maker"] else 1)
    return discovered
