"""
tools/domain_email_scanner.py
Công cụ đơn giản: nhập domain → tìm email
Không SMTP verify phức tạp, không OSM, không Railway
Chạy được ngay trên máy local
"""

import re
import sys
import csv
import time
import random
from datetime import datetime
from typing import List, Tuple

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Cài thêm: pip install requests beautifulsoup4")
    sys.exit(1)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

# Các trang thường chứa email
CONTACT_PATHS = [
    "",           # homepage
    "/contact",
    "/contact/",
    "/lien-he",
    "/lien-he/",
    "/about",
    "/about-us",
    "/gioi-thieu",
]

# Email rác — bỏ qua
SKIP_EMAILS = {
    "support@", "noreply@", "no-reply@", "admin@wordpress",
    "example@", "test@", "webmaster@", "postmaster@",
    "sentry@", "privacy@", "legal@", "abuse@",
}

# Domain rác — bỏ qua toàn bộ email từ domain này
SKIP_DOMAINS = {
    "sentry.io", "sentry.wixpress.com", "sentry-next.wixpress.com",
    "wixpress.com", "wix.com", "squarespace.com",
    "wordpress.com", "wordpress.org", "w3.org",
    "schema.org", "example.com", "domain.com",
    "cloudflare.com", "amazonaws.com", "googletagmanager.com",
    "google-analytics.com", "facebook.com", "doubleclick.net",
}

EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')


def fetch(url: str, timeout: int = 8) -> str:
    """Lấy HTML từ URL"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def extract_emails_from_html(html: str) -> List[str]:
    """Tìm tất cả email trong HTML — lọc sạch rác"""
    if not html:
        return []
    emails = set(EMAIL_REGEX.findall(html))
    clean = []
    for e in emails:
        e = e.lower().strip()
        local, _, domain = e.partition("@")

        # Lọc local-part quá ngắn (dưới 3 ký tự → thường là rác hoặc bị cắt)
        if len(local) < 3:
            continue

        # Lọc domain rác
        if any(domain == skip or domain.endswith("." + skip) for skip in SKIP_DOMAINS):
            continue

        # Lọc prefix rác
        if any(e.startswith(skip) for skip in SKIP_EMAILS):
            continue

        # Phải có TLD hợp lệ
        if "." not in domain or len(domain.split(".")[-1]) < 2:
            continue

        clean.append(e)
    return sorted(clean)


def scan_domain(domain: str) -> Tuple[str, List[str]]:
    """
    Scan 1 domain → trả về (domain, [emails])
    Tự thêm https:// nếu thiếu
    """
    domain = domain.strip().lower()
    if not domain:
        return domain, []

    # Chuẩn hoá URL
    if not domain.startswith("http"):
        base = "https://" + domain
    else:
        base = domain
        domain = re.sub(r'^https?://', '', domain).split('/')[0]

    all_emails = set()

    for path in CONTACT_PATHS:
        url = base.rstrip("/") + path
        html = fetch(url)
        if not html:
            # Thử http nếu https fail
            html = fetch(url.replace("https://", "http://"))

        emails = extract_emails_from_html(html)
        all_emails.update(emails)

        if all_emails:
            break  # Tìm được rồi — dừng, không cần crawl thêm

        time.sleep(random.uniform(0.3, 0.8))

    return domain, sorted(all_emails)


def scan_domains(domains: List[str], output_csv: str = None) -> List[dict]:
    """
    Scan nhiều domain — in kết quả và tuỳ chọn lưu CSV
    """
    results = []
    total = len(domains)
    found_count = 0

    print(f"\n{'='*60}")
    print(f"🔍 Bắt đầu scan {total} domain — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    for i, domain in enumerate(domains, 1):
        domain = domain.strip()
        if not domain:
            continue

        print(f"[{i}/{total}] Đang scan: {domain}...")
        d, emails = scan_domain(domain)

        if emails:
            found_count += 1
            print(f"  ✅ Tìm được {len(emails)} email:")
            for e in emails:
                print(f"     → {e}")
        else:
            print(f"  ❌ Không tìm thấy email")

        results.append({
            "domain":  d,
            "emails":  ", ".join(emails),
            "count":   len(emails),
            "status":  "✅" if emails else "❌",
            "time":    datetime.now().strftime("%H:%M:%S"),
        })

        time.sleep(random.uniform(1.0, 2.0))  # Lịch sự — không spam

    # Tổng kết
    print(f"\n{'='*60}")
    print(f"📊 KẾT QUẢ: {found_count}/{total} domain có email")
    print(f"{'='*60}")

    # Lưu CSV
    if output_csv:
        with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["domain", "emails", "count", "status", "time"])
            writer.writeheader()
            writer.writerows(results)
        print(f"\n💾 Đã lưu: {output_csv}")

    return results


# ─────────────────────────────────────────────────────────────
# DANH SÁCH DOMAIN — Thêm domain khách sạn/resort vào đây
# ─────────────────────────────────────────────────────────────
DOMAINS_TO_SCAN = [
    # Thêm domain vào đây — 1 domain mỗi dòng
    "furamavietnam.com",
    "fullmoonbeach.com.vn",
    "sontraresort.com.vn",
    "olalani.net",
    "toomsaradanang.vn",
    "theblossomhotels.com",
    "fusionmaiadanang.com",
    "hyatt.com",
    "marriott.com",
]


if __name__ == "__main__":
    # Cho phép nhận domain từ file hoặc từ DOMAINS_TO_SCAN
    if len(sys.argv) > 1:
        # python3 tools/domain_email_scanner.py domains.txt
        input_file = sys.argv[1]
        with open(input_file, "r", encoding="utf-8") as f:
            domains = [line.strip() for line in f if line.strip()]
    else:
        domains = DOMAINS_TO_SCAN

    output = f"email_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    scan_domains(domains, output_csv=output)
