"""
scanner/google_maps_scraper.py — Scrape Google Maps KHÔNG cần API key
Dùng httpx để gọi Google Maps search endpoint (miễn phí)
"""
import httpx
import re
import json
import time
from typing import List, Dict
from urllib.parse import quote

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def search_google_maps(query: str, city: str) -> List[Dict]:
    """
    Tìm KS trên Google Search (Knowledge Panel)
    Không cần API — dùng Google Search thường
    """
    hotels = []
    search_queries = [
        f"khách sạn mới khai trương {city} 2025",
        f"resort mới khai trương {city} 2025 2026",
        f"hotel mới {city} site:booking.com OR site:agoda.com",
    ]

    for q in search_queries:
        try:
            url = f"https://www.google.com/search?q={quote(q)}&hl=vi&gl=vn&num=20"
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)

            # Tìm tên KS trong kết quả search
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract tiêu đề từ search results
            for result in soup.select("div.g, div[data-sokoban-container]"):
                title_el = result.select_one("h3")
                link_el  = result.select_one("a[href]")
                desc_el  = result.select_one("div[data-sncf], .VwiC3b")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                link  = link_el.get("href", "") if link_el else ""
                desc  = desc_el.get_text(strip=True)[:200] if desc_el else ""

                # Lọc kết quả liên quan
                hotel_kws = ["khách sạn", "resort", "hotel", "villa", "boutique"]
                if not any(kw in (title + desc).lower() for kw in hotel_kws):
                    continue

                name = clean_hotel_name(title)
                if name:
                    hotels.append({
                        "name":       name,
                        "city":       city,
                        "source":     "google_search",
                        "source_url": link,
                        "status":     "Mới tìm thấy",
                    })

            time.sleep(2)  # Tránh bị block

        except Exception as e:
            print(f"  ⚠️ Google Search lỗi: {e}")
            continue

    return deduplicate(hotels)


def scrape_booking_newly_opened(city: str) -> List[Dict]:
    """
    Scrape Booking.com tìm property mới tại thành phố
    Filter "Newly opened" — không cần API
    """
    hotels = []
    city_enc = quote(city)

    urls_to_try = [
        # Tìm KS mới theo thành phố
        f"https://www.booking.com/searchresults.vi.html?ss={city_enc}&nflt=is_newly_opened%3D1",
        f"https://www.booking.com/searchresults.vi.html?ss={city_enc}+Vietnam&nflt=ht_id%3D204",
    ]

    for url in urls_to_try:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Property cards
            cards = soup.select('[data-testid="property-card"], .sr_property_block')
            for card in cards[:25]:
                name_el  = card.select_one('[data-testid="title"], .sr-hotel__name, h3')
                addr_el  = card.select_one('[data-testid="address"], .sr_card_address')
                score_el = card.select_one('[data-testid="review-score"] span, .review-score-badge')
                link_el  = card.select_one('a[href*="/hotel/"]')

                if not name_el:
                    continue

                hotel_url = link_el.get("href", "") if link_el else ""
                if hotel_url and not hotel_url.startswith("http"):
                    hotel_url = "https://www.booking.com" + hotel_url

                hotels.append({
                    "name":       name_el.get_text(strip=True),
                    "city":       city,
                    "address":    addr_el.get_text(strip=True) if addr_el else "",
                    "rating":     parse_rating(score_el.get_text(strip=True) if score_el else ""),
                    "source":     "booking.com",
                    "source_url": hotel_url,
                    "status":     "Mới tìm thấy",
                })

            time.sleep(1)

        except Exception as e:
            print(f"  ⚠️ Booking.com scrape lỗi: {e}")

    return deduplicate(hotels)


def scrape_tripadvisor_new(city: str) -> List[Dict]:
    """Scrape TripAdvisor tìm KS mới"""
    hotels = []
    try:
        city_enc = quote(city + " Vietnam")
        url = f"https://www.tripadvisor.com/Search?q={city_enc}&searchSessionId=&sid=&blockRedirect=true&geo=&category=hotels"
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select('[data-automation="hotel-card-title"], .listing_title a')[:15]:
            name = card.get_text(strip=True)
            if name:
                hotels.append({
                    "name":   name,
                    "city":   city,
                    "source": "tripadvisor",
                    "status": "Mới tìm thấy",
                })
    except Exception as e:
        print(f"  ⚠️ TripAdvisor lỗi: {e}")

    return hotels


def clean_hotel_name(title: str) -> str:
    """Làm sạch tên KS từ tiêu đề"""
    # Bỏ domain, rating, giá
    noise = [
        r'\s*-\s*Booking\.com.*', r'\s*\|\s*Agoda.*', r'\s*\|\s*TripAdvisor.*',
        r'\s*\d+\.\d+\s*sao.*', r'\s*từ\s*\d+.*', r'\s*\(\d+\s*đánh giá\).*',
    ]
    for pattern in noise:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    title = title.strip()
    if 3 < len(title) < 120:
        return title
    return ""


def parse_rating(text: str) -> float:
    """Trích rating từ text"""
    m = re.search(r'(\d+[.,]\d+)', text)
    if m:
        return float(m.group(1).replace(',', '.'))
    return 0.0


def deduplicate(hotels: List[Dict]) -> List[Dict]:
    seen, unique = set(), []
    for h in hotels:
        key = h.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


def scan_all_free_sources(city: str) -> List[Dict]:
    """
    Tổng hợp tất cả nguồn MIỄN PHÍ:
    1. OpenStreetMap
    2. Booking.com scrape
    3. Google Search scrape
    """
    print(f"\n🔍 Quét miễn phí: {city}")
    all_hotels = []

    # 1. OpenStreetMap (nhập khẩu từ overpass_scanner)
    from scanner.overpass_scanner import scan_city_osm
    osm = scan_city_osm(city)
    all_hotels.extend(osm)
    print(f"  📍 OSM: {len(osm)} KS")

    # 2. Booking.com
    booking = scrape_booking_newly_opened(city)
    all_hotels.extend(booking)
    print(f"  🏨 Booking: {len(booking)} KS")

    # 3. Tin tức VN
    from scanner.web_scraper import scrape_vnexpress
    news = scrape_vnexpress(city)
    all_hotels.extend(news)
    print(f"  📰 Báo VN: {len(news)} KS")

    result = deduplicate(all_hotels)
    print(f"  ✅ Tổng cộng: {len(result)} KS duy nhất tại {city}")
    return result
