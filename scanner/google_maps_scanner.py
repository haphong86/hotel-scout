"""
scanner/google_maps_scanner.py
Scrape Google Maps bằng Playwright — tìm homestay/villa/căn hộ/resort
Lấy: tên, phone, website, địa chỉ, rating
Hoàn toàn miễn phí — không cần API key
"""

import re
import time
import random
from typing import List, Dict

# Các loại accommodation cần scan
SEARCH_TYPES = [
    "homestay",
    "villa cho thuê",
    "căn hộ du lịch",
    "nhà nghỉ",
    "resort",
    "bungalow",
    "farmstay",
]


def _random_delay(min_s=1.5, max_s=3.5):
    time.sleep(random.uniform(min_s, max_s))


def scan_google_maps(city: str, search_type: str = "homestay", max_results: int = 20) -> List[Dict]:
    """
    Scrape Google Maps tìm accommodation theo loại và thành phố.
    Trả về list dict gồm: name, phone, website, address, rating, category
    """
    results = []
    query = f"{search_type} {city} vietnam"

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--lang=vi-VN",
                ]
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="vi-VN",
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()

            # Mở Google Maps với query
            maps_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
            page.goto(maps_url, timeout=20000, wait_until="domcontentloaded")
            _random_delay(2, 4)

            # Chờ panel kết quả xuất hiện
            try:
                page.wait_for_selector("div[role='feed']", timeout=10000)
            except PWTimeout:
                browser.close()
                return []

            # Cuộn để load thêm kết quả
            feed = page.locator("div[role='feed']")
            for _ in range(4):
                feed.evaluate("el => el.scrollTop += 800")
                _random_delay(1, 2)

            # Lấy tất cả listing cards
            cards = page.locator("div[role='feed'] > div a[href*='/maps/place/']").all()

            seen_names = set()
            for card in cards[:max_results]:
                try:
                    card.click()
                    _random_delay(1.5, 3)

                    # Đọc thông tin từ panel chi tiết bên phải
                    name    = _get_text(page, "h1.DUwDvf, h1[class*='fontHeadlineLarge']")
                    address = _get_text(page, "button[data-item-id='address'] div.Io6YTe, [data-tooltip='Sao chép địa chỉ'] div.Io6YTe")
                    phone   = _get_text(page, "button[data-item-id*='phone'] div.Io6YTe, [data-tooltip='Sao chép số điện thoại'] div.Io6YTe")
                    website = _get_attr(page,  "a[data-item-id='authority']", "href")
                    rating  = _get_text(page, "div.F7nice span[aria-hidden='true']")

                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)

                    # Lọc: chỉ lấy property liên quan accommodation
                    name_lower = name.lower()
                    if any(skip in name_lower for skip in [
                        "nhà hàng", "restaurant", "cafe", "quán", "spa only",
                        "shop", "cửa hàng", "siêu thị", "trường", "bệnh viện"
                    ]):
                        continue

                    # Clean phone
                    if phone:
                        phone = re.sub(r"[^\d+]", "", phone)
                        if len(phone) < 9:
                            phone = None

                    # Clean website
                    if website and ("google.com" in website or "maps" in website):
                        website = None

                    results.append({
                        "name":     name.strip(),
                        "phone":    phone,
                        "website":  website,
                        "address":  address,
                        "rating":   _parse_rating(rating),
                        "city":     city,
                        "category": search_type,
                        "source":   "google_maps",
                        "status":   "Mới tìm thấy",
                    })

                except Exception:
                    continue

            browser.close()

    except Exception as e:
        print(f"[GMaps Scanner] Lỗi: {e}")

    return results


def _get_text(page, selector: str) -> str:
    try:
        el = page.locator(selector).first
        el.wait_for(timeout=2000)
        return (el.inner_text() or "").strip()
    except Exception:
        return ""


def _get_attr(page, selector: str, attr: str) -> str:
    try:
        el = page.locator(selector).first
        el.wait_for(timeout=2000)
        return (el.get_attribute(attr) or "").strip()
    except Exception:
        return ""


def _parse_rating(text: str) -> float:
    try:
        return float(text.replace(",", ".").strip())
    except Exception:
        return 0.0


def scan_all_types(city: str, max_per_type: int = 15) -> List[Dict]:
    """Scan tất cả loại accommodation cho 1 thành phố"""
    all_results = []
    for stype in SEARCH_TYPES:
        try:
            found = scan_google_maps(city, search_type=stype, max_results=max_per_type)
            all_results.extend(found)
            time.sleep(random.uniform(2, 4))  # Nghỉ giữa các query
        except Exception:
            continue
    return all_results


if __name__ == "__main__":
    # Test nhanh
    print("🔍 Test scan Google Maps — Homestay Đà Nẵng")
    results = scan_google_maps("Đà Nẵng", search_type="homestay", max_results=5)
    for r in results:
        print(f"\n  📍 {r['name']}")
        print(f"     📞 {r['phone'] or '—'}")
        print(f"     🌐 {r['website'] or '—'}")
        print(f"     ⭐ {r['rating']}")
    print(f"\nTổng: {len(results)} kết quả")
