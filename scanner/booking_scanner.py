"""
scanner/booking_scanner.py
Scrape Booking.com bằng Playwright — tìm hotel/villa/homestay
Lấy: tên, địa chỉ, rating, website riêng (nếu có)
Sau đó scan_domain() để lấy email
"""

import re
import time
import random
from typing import List, Dict

# Loại accommodation trên Booking.com (ht_id)
PROPERTY_TYPES = {
    "hotel":     204,
    "resort":    220,
    "villa":     218,
    "homestay":  214,
    "apartment": 213,
    "hostel":    216,
    "bnb":       219,
}

# OTA domain — bỏ qua, không phải website riêng
OTA_DOMAINS = [
    "booking.com", "agoda.com", "airbnb.com", "traveloka.com",
    "expedia.com", "tripadvisor.com", "hotels.com", "klook.com",
    "google.com", "facebook.com", "instagram.com", "youtube.com",
]


def _is_ota(url: str) -> bool:
    if not url:
        return True
    return any(d in url.lower() for d in OTA_DOMAINS)


def _random_delay(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


def scan_booking(city: str, prop_type: str = "hotel", max_results: int = 20) -> List[Dict]:
    """
    Scrape Booking.com → trả về list property:
    {name, address, rating, website, city, source}
    """
    results = []
    ht_id   = PROPERTY_TYPES.get(prop_type, 204)

    # URL search Booking.com — tiếng Việt
    search_url = (
        f"https://www.booking.com/searchresults.vi.html"
        f"?ss={city}&lang=vi&dest_type=city"
        f"&nflt=ht_id%3D{ht_id}&rows=25&offset=0"
    )

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"]
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="vi-VN",
                viewport={"width": 1366, "height": 768},
            )
            page = ctx.new_page()

            # Mở trang search
            page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
            _random_delay(2, 4)

            # Đóng popup cookie nếu có
            try:
                page.locator("button#onetrust-accept-btn-handler").click(timeout=3000)
                _random_delay(0.5, 1)
            except Exception:
                pass

            # Lấy danh sách property cards
            cards = page.locator("[data-testid='property-card']").all()[:max_results]

            for card in cards:
                try:
                    name    = card.locator("[data-testid='title']").inner_text(timeout=2000).strip()
                    address = card.locator("[data-testid='address']").inner_text(timeout=2000).strip()
                    score   = card.locator("[data-testid='review-score']").inner_text(timeout=2000).strip()
                    detail_url = card.locator("a[data-testid='title-link']").get_attribute("href", timeout=2000)

                    # Parse rating
                    score_match = re.search(r'\d+[.,]\d+', score or "")
                    rating = float(score_match.group().replace(",", ".")) if score_match else 0.0

                    results.append({
                        "name":     name,
                        "address":  address,
                        "rating":   rating,
                        "website":  None,           # Sẽ tìm từ detail page
                        "detail_url": detail_url,
                        "city":     city,
                        "category": prop_type,
                        "source":   "booking",
                    })
                except Exception:
                    continue

            # Với mỗi property, vào detail page tìm website riêng
            for item in results[:10]:  # Giới hạn 10 để không quá lâu
                detail_url = item.pop("detail_url", None)
                if not detail_url:
                    continue
                try:
                    page.goto(detail_url, timeout=15000, wait_until="domcontentloaded")
                    _random_delay(1.5, 3)

                    # Tìm link website riêng của KS
                    # Booking.com đôi khi hiện "Trang web chính thức" hoặc link ngoài
                    page_html = page.content()

                    # Tìm URL trong HTML không phải OTA
                    urls = re.findall(
                        r'https?://(?!www\.booking\.com|www\.agoda|www\.tripadvisor|'
                        r'www\.facebook|www\.instagram|www\.google|www\.youtube)'
                        r'[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:/[^\s"\'<>]*)?',
                        page_html
                    )
                    for url in urls:
                        url = url.split("?")[0].rstrip("/")
                        if (len(url) > 12 and not _is_ota(url)
                                and url.count("/") <= 2):  # URL gốc, không phải deep link
                            item["website"] = url
                            break

                except Exception:
                    pass

            browser.close()

    except Exception as e:
        print(f"[Booking Scanner] Lỗi: {e}")

    return [r for r in results if r.get("name")]


def scan_all_types(city: str, max_per_type: int = 10) -> List[Dict]:
    """Scan tất cả loại accommodation tại 1 thành phố"""
    all_results = []
    for ptype in ["hotel", "resort", "villa", "homestay", "apartment"]:
        try:
            found = scan_booking(city, prop_type=ptype, max_results=max_per_type)
            all_results.extend(found)
            time.sleep(random.uniform(3, 6))  # Nghỉ giữa các request
        except Exception:
            continue
    return all_results


if __name__ == "__main__":
    print("🔍 Test Booking.com Scanner — Hotel Đà Nẵng")
    results = scan_booking("Đà Nẵng", prop_type="resort", max_results=5)
    for r in results:
        print(f"\n  📍 {r['name']} ({r['rating']}⭐)")
        print(f"     📮 {r['address']}")
        print(f"     🌐 {r['website'] or '—'}")
    print(f"\nTổng: {len(results)} kết quả")
