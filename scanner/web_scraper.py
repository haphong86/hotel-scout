"""
scanner/web_scraper.py — Scrape tin tức KS mới khai trương từ báo Việt Nam
"""
import httpx
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
from urllib.parse import quote


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def scrape_vnexpress(city: str) -> List[Dict]:
    """Tìm tin khai trương KS mới trên VnExpress"""
    hotels = []
    queries = [
        f"khai trương khách sạn {city}",
        f"resort mới {city}",
        f"hotel mới khai trương {city}",
    ]

    for query in queries:
        try:
            url = f"https://vnexpress.net/tim-kiem?q={quote(query)}&cate_code=&media_type=&fromdate=&todate=&latest=1"
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")

            articles = soup.select("article.item-news, .item-news-common")
            for art in articles[:10]:
                title_el = art.select_one("h3.title-news a, h2.title-news a")
                desc_el  = art.select_one("p.description")
                date_el  = art.select_one("span.time-count")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                link  = title_el.get("href", "")
                desc  = desc_el.get_text(strip=True) if desc_el else ""

                # Chỉ lấy bài liên quan đến KS
                keywords = ["khách sạn", "resort", "hotel", "khai trương", "khai truong"]
                if not any(kw in title.lower() + desc.lower() for kw in keywords):
                    continue

                # Trích tên KS từ tiêu đề
                hotel_name = extract_hotel_name_from_title(title)
                if hotel_name:
                    hotels.append({
                        "name": hotel_name,
                        "city": city,
                        "source": "vnexpress",
                        "source_url": link,
                        "source_title": title,
                        "status": "Mới tìm thấy",
                    })

        except Exception as e:
            print(f"  ⚠️ VnExpress lỗi: {e}")

    return deduplicate(hotels)


def scrape_booking_new(city: str) -> List[Dict]:
    """Tìm property mới trên Booking.com"""
    hotels = []
    try:
        # Booking.com có trang lọc "Newly opened"
        city_enc = quote(city)
        url = (
            f"https://www.booking.com/searchresults.vi.html"
            f"?ss={city_enc}&nflt=ht_id%3D204%3B&order=new_filter_popularity"
        )
        resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select('[data-testid="property-card"]')
        for card in cards[:20]:
            name_el = card.select_one('[data-testid="title"]')
            addr_el = card.select_one('[data-testid="address"]')
            score_el = card.select_one('[data-testid="review-score"] .ac4a7896c7')

            if not name_el:
                continue

            hotels.append({
                "name": name_el.get_text(strip=True),
                "city": city,
                "address": addr_el.get_text(strip=True) if addr_el else "",
                "rating": float(score_el.get_text(strip=True)) if score_el else None,
                "source": "booking.com",
                "status": "Mới tìm thấy",
            })

    except Exception as e:
        print(f"  ⚠️ Booking.com lỗi: {e}")

    return hotels


def extract_hotel_name_from_title(title: str) -> str:
    """Trích xuất tên KS từ tiêu đề bài báo"""
    # Loại pattern phổ biến: "Khai trương [Tên KS]", "[Tên KS] chính thức mở cửa"
    patterns = [
        r'khai tr[ươu]ơng\s+(.+?)(?:\s+tại|\s+ở|\s+–|\s+-|,|\.)',
        r'([A-Z][A-Za-z\s]+(?:Hotel|Resort|Villa|Boutique|Suites?))',
        r'(?:khách sạn|resort|hotel)\s+([A-Z][A-Za-zÀ-ỹ\s]+)',
    ]
    for p in patterns:
        m = re.search(p, title, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if 3 < len(name) < 100:
                return name
    return ""


def deduplicate(hotels: List[Dict]) -> List[Dict]:
    """Loại bỏ KS trùng tên"""
    seen = set()
    unique = []
    for h in hotels:
        key = h.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


def scan_news_for_city(city: str) -> List[Dict]:
    """Tổng hợp từ nhiều nguồn báo"""
    results = []
    print(f"  📰 Scraping tin tức KS mới tại {city}...")
    results.extend(scrape_vnexpress(city))
    results.extend(scrape_booking_new(city))
    return deduplicate(results)
