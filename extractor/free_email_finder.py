"""
extractor/free_email_finder.py
Tìm email MIỄN PHÍ — không cần Hunter.io
Kết hợp 4 phương pháp:
  1. Crawl trực tiếp website KS (email hiện trên trang)
  2. Đoán pattern email + xác minh qua SMTP
  3. Scrape Google Search (site:domain.com email)
  4. Scrape Facebook Business Page
"""
import re
import smtplib
import socket
import dns.resolver
import httpx
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from typing import List, Dict, Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

# Pattern email theo thứ tự ưu tiên quyết định
# Dựa trên cấp bậc thực tế KS VN + chain quốc tế
# Format: (local_part, chức_vụ, confidence_score)
EMAIL_PATTERNS_RANKED = [

    # ════════════════════════════════════════════════════
    # TIER 1 — Quyết định trực tiếp (Reply 10-20%)
    # ════════════════════════════════════════════════════

    # Marketing — người cần ảnh nhất
    ("marketing",           "Marketing Manager",                92),
    ("marketing.manager",   "Marketing Manager",                90),
    ("marketingmanager",    "Marketing Manager",                88),
    ("marcom",              "Marketing & Communications Mgr",   88),
    ("marketing.comm",      "Marketing & Communications",       85),
    ("marketingcomm",       "Marketing & Communications",       85),

    # Director of Sales & Marketing (DOSM)
    ("dosm",                "Director of Sales & Marketing",    90),
    ("dsom",                "Director of Sales & Marketing",    88),
    ("dos",                 "Director of Sales",                85),
    ("dom",                 "Director of Marketing",            85),

    # General Manager
    ("gm",                  "General Manager",                  88),
    ("generalmanager",      "General Manager",                  85),
    ("general.manager",     "General Manager",                  85),
    ("manager",             "Manager",                          75),

    # ════════════════════════════════════════════════════
    # TIER 2 — Ảnh hưởng lớn (Reply 6-10%)
    # ════════════════════════════════════════════════════

    # Sales
    ("sm",                  "Sales Manager",                    80),
    ("salesmanager",        "Sales Manager",                    78),
    ("sales.manager",       "Sales Manager",                    78),
    ("sales",               "Sales",                            75),
    ("salesmarketing",      "Sales & Marketing",                72),
    ("sales.marketing",     "Sales & Marketing",                72),

    # Digital / Content / Social
    ("digital",             "Digital Marketing Manager",        78),
    ("digital.marketing",   "Digital Marketing Manager",        76),
    ("digitalmarketing",    "Digital Marketing Manager",        76),
    ("content",             "Content Manager",                  74),
    ("content.manager",     "Content Manager",                  72),
    ("social",              "Social Media Manager",             72),
    ("socialmedia",         "Social Media Manager",             70),
    ("social.media",        "Social Media Manager",             70),

    # PR & Communications
    ("pr",                  "PR Manager",                       74),
    ("publicrelations",     "Public Relations Manager",         72),
    ("public.relations",    "Public Relations Manager",         70),
    ("communications",      "Communications Manager",           70),
    ("comms",               "Communications",                   68),

    # Revenue
    ("revenue",             "Revenue Manager",                  70),
    ("rm",                  "Revenue Manager",                  68),
    ("revenue.manager",     "Revenue Manager",                  68),
    ("revenuemanagement",   "Revenue Management",               65),

    # Director cấp dưới
    ("director",            "Director",                         70),
    ("artdirector",         "Art Director",                     68),
    ("art.director",        "Art Director",                     68),
    ("creative",            "Creative Director",                68),
    ("creativedirector",    "Creative Director",                66),
    ("brand",               "Brand Manager",                    65),
    ("brandmanager",        "Brand Manager",                    65),

    # ════════════════════════════════════════════════════
    # TIER 3 — Có thể forward được (Reply 3-6%)
    # ════════════════════════════════════════════════════

    ("ecommerce",           "E-Commerce Manager",               62),
    ("ota",                 "OTA Manager",                      60),
    ("distribution",        "Distribution Manager",             58),
    ("partnership",         "Partnership Manager",              58),
    ("media",               "Media Manager",                    56),
    ("advertising",         "Advertising",                      55),
    ("ads",                 "Advertising",                      55),
    ("admin",               "Admin",                            52),
    ("office",              "Office Manager",                   50),

    # ════════════════════════════════════════════════════
    # TIER 4 — Email chung (Reply 1-2%, qua bộ lọc)
    # ════════════════════════════════════════════════════

    ("info",                "General",                          42),
    ("contact",             "General",                          40),
    ("hello",               "General",                          38),
    ("enquiry",             "Enquiries",                        38),
    ("enquiries",           "Enquiries",                        38),
    ("booking",             "Reservations",                     35),
    ("reservation",         "Reservations",                     35),
    ("reservations",        "Reservations",                     33),

    # ════════════════════════════════════════════════════
    # KHÔNG GỬI — Lễ tân / Bộ phận không có quyền ảnh
    # ════════════════════════════════════════════════════
    # reception@   frontdesk@   letan@   housekeeping@
    # restaurant@  fnb@         spa@     concierge@
]

# Chức vụ ưu tiên — người quyết định mua ảnh
PRIORITY_TITLES = [
    "marketing manager", "digital marketing", "marketing director",
    "general manager", "gm", "revenue manager",
    "sales manager", "director of sales",
    "art director", "creative director", "content manager",
    "social media", "communications manager",
]


# ═══════════════════════════════════════════════════════════════
# PHƯƠNG PHÁP 1: Crawl website KS tìm email
# ═══════════════════════════════════════════════════════════════

def crawl_website_emails(website: str) -> List[Dict]:
    """Tìm email trực tiếp từ website KS — NHANH nhất"""
    if not website:
        return []

    emails = []
    # Các trang thường có contact
    pages_to_check = [
        website.rstrip("/"),
        website.rstrip("/") + "/contact",
        website.rstrip("/") + "/lien-he",
        website.rstrip("/") + "/about",
        website.rstrip("/") + "/gioi-thieu",
        website.rstrip("/") + "/team",
    ]

    found_emails = set()
    for url in pages_to_check[:4]:  # Kiểm tra tối đa 4 trang
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
            if resp.status_code != 200:
                continue

            text = resp.text
            soup = BeautifulSoup(text, "html.parser")

            # Tìm email trong text
            raw_emails = re.findall(
                r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
                text
            )

            # Tìm mailto: links
            for a in soup.select("a[href^='mailto:']"):
                href = a.get("href", "")
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email and is_valid_email(email):
                    raw_emails.append(email)

            for email in raw_emails:
                email = email.lower().strip()
                if (is_valid_email(email)
                        and email not in found_emails
                        and not is_spam_email(email)):
                    found_emails.add(email)

                    # Tìm chức vụ gần email đó
                    context = get_email_context(soup, email)
                    title   = extract_title_from_context(context)

                    emails.append({
                        "email":      email,
                        "title":      title,
                        "source":     "website_crawl",
                        "source_url": url,
                        "confidence": score_email(email, title),
                        "method":     "1_website",
                    })

            time.sleep(0.5)
        except Exception:
            continue

    # Sắp xếp email theo độ tin cậy
    emails.sort(key=lambda x: x["confidence"], reverse=True)
    return emails


def get_email_context(soup: BeautifulSoup, email: str) -> str:
    """Lấy text xung quanh email để đoán chức vụ"""
    full_text = soup.get_text()
    idx = full_text.lower().find(email.lower())
    if idx >= 0:
        return full_text[max(0, idx-200): idx+200]
    return ""


def extract_title_from_context(context: str) -> str:
    """Trích chức vụ từ văn bản xung quanh email"""
    context_lower = context.lower()
    for title in PRIORITY_TITLES:
        if title in context_lower:
            return title.title()
    return ""


# ═══════════════════════════════════════════════════════════════
# PHƯƠNG PHÁP 2: Đoán pattern + xác minh SMTP
# ═══════════════════════════════════════════════════════════════

def get_domain_from_website(website: str) -> str:
    """Trích domain từ URL"""
    try:
        parsed = urlparse(website if website.startswith("http") else "https://" + website)
        domain = parsed.netloc.replace("www.", "")
        return domain
    except Exception:
        return ""


def verify_email_smtp(email: str, timeout: int = 5) -> bool:
    """
    Xác minh email có tồn tại không bằng SMTP RCPT TO
    KHÔNG gửi email thật — chỉ hỏi server
    """
    domain = email.split("@")[1]
    try:
        # 1. Lấy MX record
        records = dns.resolver.resolve(domain, "MX")
        mx_host = str(sorted(records, key=lambda r: r.preference)[0].exchange)

        # 2. Kết nối SMTP và check
        with smtplib.SMTP(timeout=timeout) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("haphong.com")
            smtp.mail("check@haphong.com")
            code, _ = smtp.rcpt(email)
            return code in [250, 251]

    except Exception:
        return False  # Không verify được → vẫn có thể gửi thử


def guess_emails_by_pattern(domain: str, name: str = "") -> List[Dict]:
    """
    Đoán email theo thứ tự ưu tiên cấp bậc quyết định.
    marketing@ → dosm@ → gm@ → digital@ → ... → info@ (cuối)
    """
    if not domain:
        return []

    results = []

    # Email theo cấp bậc quyết định (Tier 1 → 4)
    for local, title, base_confidence in EMAIL_PATTERNS_RANKED:
        email = f"{local}@{domain}"
        results.append({
            "email":      email,
            "title":      title,
            "source":     "pattern_guess",
            "confidence": base_confidence,
            "method":     "2_pattern",
            "tier":       1 if base_confidence >= 80 else (2 if base_confidence >= 60 else 3),
        })

    # Nếu có tên người → thêm pattern cá nhân (ưu tiên cao nhất)
    if name:
        parts = name.lower().split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            personal = [
                (f"{first}.{last}@{domain}",    "Personal"),
                (f"{first}{last[0]}@{domain}",  "Personal"),
                (f"{first[0]}{last}@{domain}",  "Personal"),
                (f"{first}@{domain}",            "Personal"),
            ]
            for email, title in personal:
                results.append({
                    "email":      email,
                    "title":      title,
                    "source":     "pattern_personal",
                    "confidence": 80,  # Tên riêng = ưu tiên cao
                    "method":     "2_pattern_personal",
                    "tier":       1,
                })

    return results



# ═══════════════════════════════════════════════════════════════
# PHƯƠNG PHÁP 3: Google Search tìm email KS
# ═══════════════════════════════════════════════════════════════

def google_search_email(hotel_name: str, domain: str = "") -> List[Dict]:
    """Tìm email qua Google Search"""
    emails = []
    queries = []

    if domain:
        queries.append(f'site:{domain} email OR "contact us"')
        queries.append(f'"@{domain}" marketing OR manager OR director')
    queries.append(f'"{hotel_name}" email marketing manager contact')
    queries.append(f'"{hotel_name}" "marketing@" OR "info@" OR "gm@"')

    found = set()
    for q in queries[:2]:  # Chỉ 2 query để tránh bị block
        try:
            url = f"https://www.google.com/search?q={quote(q)}&hl=vi&gl=vn"
            resp = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
            text = resp.text

            # Tìm email trong kết quả
            raw = re.findall(
                r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
                text
            )
            for email in raw:
                email = email.lower()
                if (is_valid_email(email)
                        and email not in found
                        and not is_spam_email(email)):
                    # Ưu tiên email cùng domain KS
                    confidence = 65 if domain and domain in email else 30
                    found.add(email)
                    emails.append({
                        "email":      email,
                        "title":      "",
                        "source":     "google_search",
                        "confidence": confidence,
                        "method":     "3_google",
                    })

            time.sleep(2)
        except Exception:
            continue

    return emails


# ═══════════════════════════════════════════════════════════════
# PHƯƠNG PHÁP 4: Facebook Business Page
# ═══════════════════════════════════════════════════════════════

def scrape_facebook_contact(hotel_name: str) -> List[Dict]:
    """Scrape email từ Facebook Page của KS"""
    emails = []
    try:
        # Tìm Facebook page
        search_url = (
            f"https://www.google.com/search?q="
            f"{quote(hotel_name + ' facebook page email')} site:facebook.com"
        )
        resp = httpx.get(search_url, headers=HEADERS, timeout=10, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Tìm link FB
        fb_link = None
        for a in soup.select("a[href*='facebook.com']"):
            href = a.get("href", "")
            if "facebook.com/" in href and "search" not in href:
                fb_link = href
                break

        if not fb_link:
            return []

        # Scrape trang FB (giới hạn thông tin)
        resp2 = httpx.get(fb_link, headers=HEADERS, timeout=10, follow_redirects=True)
        text  = resp2.text
        raw   = re.findall(
            r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
            text
        )
        for email in raw[:5]:
            email = email.lower()
            if is_valid_email(email) and not is_spam_email(email):
                emails.append({
                    "email":      email,
                    "title":      "",
                    "source":     "facebook_page",
                    "confidence": 55,
                    "method":     "4_facebook",
                })

    except Exception:
        pass

    return emails


# ═══════════════════════════════════════════════════════════════
# HELPER — Validator & Scorer
# ═══════════════════════════════════════════════════════════════

SPAM_DOMAINS = {
    "example.com", "test.com", "sample.com", "noreply.com",
    "sentry.io", "w3.org", "schema.org", "google.com",
    "facebook.com", "instagram.com", "youtube.com",
    "agoda.com", "booking.com", "tripadvisor.com",
}

def is_valid_email(email: str) -> bool:
    """Kiểm tra format email cơ bản"""
    pattern = r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) < 100

def is_spam_email(email: str) -> bool:
    """Lọc email không liên quan"""
    domain = email.split("@")[1] if "@" in email else ""
    return domain in SPAM_DOMAINS or email.startswith("no-reply")

def score_email(email: str, title: str = "") -> int:
    """Chấm điểm email 0-100"""
    score = 50  # Base

    local = email.split("@")[0].lower()
    title_lower = (title or "").lower()

    # Bonus: email cùng domain KS (không phải gmail/yahoo)
    domain = email.split("@")[1] if "@" in email else ""
    if domain and "gmail" not in domain and "yahoo" not in domain and "hotmail" not in domain:
        score += 20

    # Bonus: chức vụ quan trọng
    if any(t in local or t in title_lower for t in ["marketing", "gm", "director", "sales", "manager"]):
        score += 20

    # Penalty: email generic
    if local in ["info", "contact", "hello", "support", "admin"]:
        score -= 10

    return min(100, max(0, score))


# ═══════════════════════════════════════════════════════════════
# MAIN: Tìm email miễn phí cho 1 KS
# ═══════════════════════════════════════════════════════════════

def find_emails_free(hotel_name: str, website: str = "", limit: int = 5) -> List[Dict]:
    """
    Tổng hợp tất cả phương pháp miễn phí.
    Trả về danh sách email sắp xếp theo độ tin cậy.
    """
    all_emails   = []
    found_set    = set()

    domain = get_domain_from_website(website) if website else ""

    print(f"  🔍 Tìm email: {hotel_name} | domain={domain or 'N/A'}")

    # Phương pháp 1: Crawl website (nhanh và chính xác nhất)
    if website:
        web_emails = crawl_website_emails(website)
        for e in web_emails:
            if e["email"] not in found_set:
                found_set.add(e["email"])
                all_emails.append(e)
        print(f"    Website crawl: {len(web_emails)} email")

    # Phương pháp 2: Đoán pattern (nếu có domain)
    if domain and len(all_emails) < 3:
        pattern_emails = guess_emails_by_pattern(domain)
        for e in pattern_emails:
            if e["email"] not in found_set:
                found_set.add(e["email"])
                all_emails.append(e)
        print(f"    Pattern guess: {len(pattern_emails)} email")

    # Phương pháp 3: Google Search (nếu vẫn chưa đủ)
    if len(all_emails) < 2:
        google_emails = google_search_email(hotel_name, domain)
        for e in google_emails:
            if e["email"] not in found_set:
                found_set.add(e["email"])
                all_emails.append(e)
        print(f"    Google search: {len(google_emails)} email")

    # Phương pháp 4: Facebook (chỉ khi rất cần)
    if len(all_emails) < 2:
        fb_emails = scrape_facebook_contact(hotel_name)
        for e in fb_emails:
            if e["email"] not in found_set:
                found_set.add(e["email"])
                all_emails.append(e)
        print(f"    Facebook: {len(fb_emails)} email")

    # Sắp xếp theo confidence
    all_emails.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    result = all_emails[:limit]
    print(f"    ✅ Tổng: {len(result)} email tìm thấy")
    return result
