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

# CHỈ GIỮ LẠI CÁC EMAIL CÓ QUYỀN QUYẾT ĐỊNH CHỤP ẢNH (GM, DOSM, SM, MARKETING, SALES)
# TUYỆT ĐỐI KHÔNG GỬI VÀO INFO, RESERVATION, BOOKING
EMAIL_PATTERNS_RANKED = [
    # ── CẤP 1: TỔNG GIÁM ĐỐC (GM) — QUYẾT ĐỊNH CAO NHẤT ──
    ("gm",                  "Tổng Giám Đốc (General Manager)",      98),
    ("generalmanager",      "Tổng Giám Đốc (General Manager)",      96),
    ("general.manager",     "Tổng Giám Đốc (General Manager)",      96),

    # ── CẤP 2: GIÁM ĐỐC SALES & MARKETING (DOSM) — TRỰC TIẾP DUYỆT NGÂN SÁCH ẢNH ──
    ("dosm",                "Director of Sales & Marketing (DOSM)",  95),
    ("dos",                 "Director of Sales",                    94),
    ("dom",                 "Director of Marketing",                94),

    # ── CẤP 3: SALES MANAGER (SM) ──
    ("sm",                  "Sales Manager",                        92),
    ("salesmanager",        "Sales Manager",                        90),
    ("sales.manager",       "Sales Manager",                        90),

    # ── CẤP 4: PHÒNG MARKETING & TRUYỀN THÔNG ──
    ("marketing",           "Marketing Manager",                    90),
    ("marketing.manager",   "Marketing Manager",                    88),
    ("marcom",              "Marketing & Communications Manager",   88),
    ("digital",             "Digital Marketing Manager",            86),

    # ── CẤP 5: PHÒNG KINH DOANH (SALES DEPT) ──
    ("sales",               "Phòng Kinh Doanh (Sales Dept)",        85),
    ("salesmarketing",      "Sales & Marketing",                    82),
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

def _fetch_with_playwright(url: str) -> str:
    """Tier 3: Playwright headless Chromium — render JS-only pages"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # Chờ JS render xong
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""


def _is_js_only(html: str) -> bool:
    """Phát hiện trang JS-only (React/Vue/SPA) — email không có trong HTML thô"""
    if not html:
        return True
    import re as _re
    # Ít text content + nhiều script = JS-only
    text_len = len(_re.sub(r'<[^>]+>', '', html))
    script_count = html.lower().count('<script')
    return text_len < 500 and script_count > 5


def _fetch_page(url: str) -> str:
    """3-tier fetch:
      Tier 1: httpx (nhanh, nhẹ)
      Tier 2: requests (ổn định hơn trên Railway)
      Tier 3: Playwright (JS-only sites, chậm nhưng đầy đủ)
    """
    html = ""

    # Tier 1: httpx
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=8.0, follow_redirects=True)
        if resp.status_code == 200:
            html = resp.text
    except Exception:
        pass

    # Tier 2: requests fallback
    if not html:
        try:
            import requests as _req
            resp = _req.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                html = resp.text
        except Exception:
            pass

    # Tier 3: Playwright nếu HTML trống hoặc JS-only
    if _is_js_only(html):
        pw_html = _fetch_with_playwright(url)
        if pw_html:
            html = pw_html

    return html


def crawl_website_emails(website: str) -> List[Dict]:
    """Tìm email trực tiếp từ website KS — NHANH nhất"""
    if not website:
        return []

    emails = []
    base = website.rstrip("/")
    # Crawl đủ các trang thường có email — bao gồm cả trailing slash
    pages_to_check = [
        base,
        base + "/contact",
        base + "/contact/",       # trailing slash quan trọng!
        base + "/lien-he",
        base + "/lien-he/",
        base + "/about",
        base + "/about-us",
        base + "/gioi-thieu",
    ]

    found_emails = set()
    for url in pages_to_check[:5]:  # Crawl 5 trang
        try:
            text = _fetch_page(url)
            if not text:
                continue

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


PLATFORM_BLACKLIST_DOMAINS = {
    "facebook.com", "m.facebook.com", "fb.com", "instagram.com", "tiktok.com",
    "booking.com", "agoda.com", "tripadvisor.com", "tripadvisor.com.vn", "airbnb.com", "airbnb.com.vn",
    "traveloka.com", "expedia.com", "hotels.com", "google.com", "google.com.vn",
    "youtube.com", "zalo.me", "wixsite.com", "wordpress.com", "blogspot.com",
    "apple.com", "microsoft.com", "sentry.io", "github.com", "cloudflare.com",
    "twitter.com", "x.com", "linkedin.com", "pinterest.com",
    "api-next.com", "wb.com", "dot.com.vn", "midtowncomics.com", "dcentertainment.com",
    "w3.org", "wordpress.org", "schema.org", "themeforest.net", "envato.com",
    "dream-theme.com", "example.com", "domain.com", "email.com", "test.com", "flow.com.vn"
}


def is_blacklisted_domain(domain: str) -> bool:
    """Kiểm tra tên miền có phải là MXH hoặc sàn OTA (không phải domain riêng của KS)"""
    if not domain:
        return True
    domain_clean = domain.lower().strip().replace("www.", "")
    for blocked in PLATFORM_BLACKLIST_DOMAINS:
        if domain_clean == blocked or domain_clean.endswith("." + blocked):
            return True
    return False


def get_domain_from_website(website: str) -> str:
    """Trích domain sạch từ URL website — loại bỏ 100% SĐT, chuỗi lỗi, email"""
    if not website or not isinstance(website, str):
        return ""
    website = website.strip().lower()
    # Nếu chứa @ -> đây là email hoặc chuỗi rác, không phải website
    if "@" in website or " " in website or len(website) < 4:
        return ""
    try:
        if not website.startswith("http://") and not website.startswith("https://"):
            website = "https://" + website
        parsed = urlparse(website)
        domain = parsed.netloc or parsed.path
        domain = domain.split(":")[0].replace("www.", "").strip().lower()
        # Kiểm tra regex domain chuẩn quốc tế: chỉ chứa chữ, số, dấu gạch ngang, dấu chấm
        if not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$', domain):
            return ""
        # Phải có đuôi TLD hợp lệ (ít nhất 2 ký tự chữ cái)
        tld = domain.split(".")[-1]
        if not tld.isalpha() or len(tld) < 2:
            return ""
        if is_blacklisted_domain(domain):
            return ""
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
    TUYỆT ĐỐI KHÔNG đoán trên domain MXH, OTA, hoặc domain rác!
    """
    if not domain or is_blacklisted_domain(domain):
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
