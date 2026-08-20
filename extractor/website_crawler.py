"""
extractor/website_crawler.py — Crawl website KS để tìm email & phone
"""
import httpx
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Tuple
import phonenumbers
import validators


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Regex email & phone Việt Nam
EMAIL_REGEX   = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
VN_PHONE_REGEX = re.compile(r'(?:0|\+?84)\s*[3-9]\d[\s\-.]?\d{3}[\s\-.]?\d{4}')

# Các trang thường chứa thông tin liên hệ
CONTACT_PATHS = [
    "/contact", "/contact-us", "/lien-he", "/lien-he-chung-toi",
    "/about", "/about-us", "/ve-chung-toi",
    "/team", "/our-team", "/nhan-su",
    "/management", "/ban-quan-ly",
]

# Chức vụ liên quan đến hình ảnh
TARGET_TITLES_KEYWORDS = [
    "general manager", "gm", "hotel manager", "resort manager",
    "marketing", "sales", "pr ", "public relation",
    "brand", "content", "social media", "creative", "art director",
    "communications", "revenue",
    "giám đốc", "quản lý", "trưởng phòng", "marketing", "kinh doanh",
]


def clean_phone(phone_str: str) -> str:
    """Chuẩn hóa số điện thoại Việt Nam"""
    cleaned = re.sub(r'[\s\-\.]', '', phone_str)
    if cleaned.startswith('+84'):
        cleaned = '0' + cleaned[3:]
    return cleaned


def is_valid_email(email: str) -> bool:
    """Kiểm tra email hợp lệ, loại spam/generic nếu cần"""
    spam_domains = ['example.com', 'test.com', 'domain.com', 'email.com']
    try:
        if not validators.email(email):
            return False
        domain = email.split('@')[1].lower()
        if domain in spam_domains:
            return False
        return True
    except Exception:
        return False


def score_email(email: str, context: str = "") -> int:
    """Chấm điểm mức độ ưu tiên email (0-100)"""
    score = 50
    email_lower = email.lower()
    context_lower = context.lower()

    # Email domain riêng (không phải gmail/yahoo) → tốt hơn
    if not any(d in email_lower for d in ['gmail', 'yahoo', 'hotmail', 'outlook']):
        score += 20

    # Email chứa tên chức vụ liên quan
    priority_keywords = ['gm', 'general', 'manager', 'marketing', 'sales',
                         'director', 'ceo', 'owner', 'phong', 'giám đốc']
    for kw in priority_keywords:
        if kw in email_lower or kw in context_lower:
            score += 15
            break

    # Generic email → giảm điểm (vẫn giữ lại để liên hệ)
    generic = ['info@', 'contact@', 'hello@', 'admin@', 'support@', 'booking@']
    if any(email_lower.startswith(g) for g in generic):
        score -= 10

    return min(max(score, 0), 100)


def extract_contacts_from_text(text: str, html: str = "") -> Tuple[List[str], List[str]]:
    """Trích email & phone từ text/html thô"""
    emails = list(set(EMAIL_REGEX.findall(text)))
    emails = [e for e in emails if is_valid_email(e)]

    phones_raw = VN_PHONE_REGEX.findall(text)
    phones = list(set(clean_phone(p) for p in phones_raw))
    phones = [p for p in phones if len(p) >= 10]

    return emails, phones


def crawl_page(url: str, timeout: int = 12) -> Tuple[str, str]:
    """Tải 1 trang web, trả về (plain_text, html)"""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout,
                         follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # Xóa script/style
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return text, resp.text
    except Exception as e:
        return "", ""


def extract_staff_info(html: str) -> List[Dict]:
    """Cố gắng trích thông tin nhân viên (tên + chức vụ + email)"""
    soup = BeautifulSoup(html, "lxml")
    staff_list = []

    # Tìm các block thường chứa staff info
    selectors = [
        '.team-member', '.staff-card', '.person-card',
        '.management-team', '.our-team .item',
        '[class*="team"]', '[class*="staff"]', '[class*="person"]',
    ]

    for sel in selectors:
        members = soup.select(sel)
        for m in members:
            text = m.get_text(separator=' ', strip=True)
            emails, phones = extract_contacts_from_text(text)

            # Kiểm tra có chức vụ liên quan không
            has_target_title = any(t in text.lower() for t in TARGET_TITLES_KEYWORDS)
            if not has_target_title and not emails:
                continue

            name_el  = m.select_one('h3, h4, .name, [class*="name"]')
            title_el = m.select_one('.title, .position, .role, [class*="title"], [class*="position"]')

            staff_list.append({
                "name":   name_el.get_text(strip=True) if name_el else "",
                "title":  title_el.get_text(strip=True) if title_el else "",
                "emails": emails,
                "phones": phones,
            })

    return staff_list


def crawl_hotel_website(website_url: str) -> Dict:
    """
    Crawl toàn bộ website KS:
    - Trang chính
    - Trang contact/about
    Trả về: {emails, phones, staff}
    """
    if not website_url or not website_url.startswith('http'):
        return {"emails": [], "phones": [], "staff": []}

    base_url = f"{urlparse(website_url).scheme}://{urlparse(website_url).netloc}"
    all_emails, all_phones, all_staff = [], [], []

    # Crawl trang chính
    print(f"    🌐 Crawling: {website_url}")
    text, html = crawl_page(website_url)
    if text:
        emails, phones = extract_contacts_from_text(text)
        all_emails.extend(emails)
        all_phones.extend(phones)
        staff = extract_staff_info(html)
        all_staff.extend(staff)

    # Crawl các trang contact/about
    for path in CONTACT_PATHS:
        url = urljoin(base_url, path)
        text, html = crawl_page(url)
        if not text:
            continue
        emails, phones = extract_contacts_from_text(text)
        all_emails.extend(emails)
        all_phones.extend(phones)
        staff = extract_staff_info(html)
        all_staff.extend(staff)

    # Deduplicate và score
    unique_emails = list(set(all_emails))
    unique_phones = list(set(all_phones))

    scored_emails = sorted(
        [{"email": e, "score": score_email(e), "source": "website"} for e in unique_emails],
        key=lambda x: -x["score"]
    )

    return {
        "emails": scored_emails,
        "phones": unique_phones,
        "staff": all_staff,
    }
