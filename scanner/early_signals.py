"""
scanner/early_signals.py — Phát hiện KS đang xây / sắp khai trương
Đây là "early warning system" — tiếp cận trước đối thủ!

Nguồn 1: dangkykinhdoanh.gov.vn — Đăng ký DN mới ngành KS
Nguồn 2: Booking.com "Opening soon" — KS đã đăng ký nhưng chưa mở
Nguồn 3: VietnamWorks / TopCV — Tuyển dụng nhân viên KS mới
Nguồn 4: Facebook — Page KS mới tạo, chưa có ảnh chuyên nghiệp
Nguồn 5: Google Maps "Temporarily closed / Coming soon"
"""
import httpx
import re
import time
import json
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from typing import List, Dict
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


# ═══════════════════════════════════════════════════════════════
# NGUỒN 1: Đăng ký Doanh nghiệp mới — dangkykinhdoanh.gov.vn
# Tìm công ty mới đăng ký ngành kinh doanh KS/resort
# ═══════════════════════════════════════════════════════════════

# Mã ngành VSIC liên quan đến KS/lưu trú
HOTEL_INDUSTRY_CODES = [
    "5510",  # Hoạt động của các cơ sở lưu trú ngắn ngày
    "5511",  # Hoạt động của khách sạn và các cơ sở lưu trú tương tự
    "5512",  # Hoạt động của khu nghỉ dưỡng và bãi cắm trại
    "5590",  # Hoạt động lưu trú khác
]

PROVINCE_CODES = {
    "Đà Nẵng":           "48",
    "Quảng Nam":         "49",
    "Thừa Thiên Huế":   "46",
    "Huế":               "46",
    "Khánh Hòa":        "56",
    "Nha Trang":         "56",
    "TP. Hồ Chí Minh":  "79",
    "Hà Nội":            "01",
    "Quảng Ninh":        "22",
    "Hạ Long":           "22",
    "Lâm Đồng":          "68",
    "Đà Lạt":            "68",
    "Bình Thuận":        "60",
    "Phan Thiết":        "60",
    "Kiên Giang":        "91",
    "Phú Quốc":          "91",
}


def scrape_business_registration(province: str, days_back: int = 90) -> List[Dict]:
    """
    Scrape dangkykinhdoanh.gov.vn tìm công ty KS mới đăng ký.
    Đây là dữ liệu chính thức, cập nhật hàng ngày.
    """
    hotels = []
    province_code = PROVINCE_CODES.get(province, "")
    if not province_code:
        return []

    try:
        # API tìm kiếm doanh nghiệp mới đăng ký
        url = "https://dangkykinhdoanh.gov.vn/vn/Pages/Timkiemdoanhnghiep.aspx"
        # Thử API endpoint
        api_url = "https://dangkykinhdoanh.gov.vn/api/doanhnghiep/search"

        params = {
            "tinh": province_code,
            "nganhNghe": "5511",     # Mã ngành KS
            "tuNgay": (datetime.now() - timedelta(days=days_back)).strftime("%d/%m/%Y"),
            "denNgay": datetime.now().strftime("%d/%m/%Y"),
            "trangThai": "1",         # Đang hoạt động
        }

        resp = httpx.get(url, params=params, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse kết quả (cấu trúc trang có thể thay đổi)
        rows = soup.select("table tr, .result-item, .company-row")
        for row in rows:
            cells = row.select("td")
            if len(cells) >= 3:
                name = cells[0].get_text(strip=True) if cells else ""
                tax_id = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                reg_date = cells[2].get_text(strip=True) if len(cells) > 2 else ""

                if name and any(kw in name.lower() for kw in
                                ["hotel", "resort", "khách sạn", "villa", "boutique", "lodge"]):
                    hotels.append({
                        "name":      name,
                        "city":      province,
                        "tax_id":    tax_id,
                        "reg_date":  reg_date,
                        "source":    "business_registration",
                        "status":    "Đang xây / Sắp mở",
                        "signal":    "🏗️ Vừa đăng ký DN",
                        "priority":  "🔴 RẤT SỚM",
                    })

    except Exception as e:
        print(f"  ⚠️ Business registration lỗi: {e}")

    # Fallback: tìm qua Google
    if not hotels:
        hotels = search_new_hotel_companies(province, days_back)

    return hotels


def search_new_hotel_companies(province: str, days_back: int = 90) -> List[Dict]:
    """Fallback: Google search tìm công ty KS mới đăng ký"""
    hotels = []
    year = datetime.now().year
    queries = [
        f"đăng ký thành lập công ty khách sạn resort {province} {year}",
        f"hotel resort mới thành lập {province} {year} giấy phép kinh doanh",
    ]
    for q in queries:
        try:
            url = f"https://www.google.com/search?q={quote(q)}&hl=vi&gl=vn"
            resp = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")

            for result in soup.select("div.g")[:5]:
                title_el = result.select_one("h3")
                if title_el:
                    title = title_el.get_text(strip=True)
                    name = clean_company_name(title)
                    if name:
                        hotels.append({
                            "name":   name,
                            "city":   province,
                            "source": "google_search_biz",
                            "status": "Đang xây / Sắp mở",
                            "signal": "🏗️ DN mới đăng ký",
                            "priority": "🔴 RẤT SỚM",
                        })
            time.sleep(2)
        except Exception:
            pass
    return hotels


# ═══════════════════════════════════════════════════════════════
# NGUỒN 2: Booking.com "Opening Soon"
# KS đã đăng ký Booking nhưng chưa mở — ĐÂY LÀ LEAD VÀNG!
# ═══════════════════════════════════════════════════════════════

def scrape_booking_opening_soon(city: str) -> List[Dict]:
    """
    Tìm KS trên Booking.com có trạng thái "Opening soon" / "Sắp khai trương"
    Đây là lead RẤT HOT — họ đang chuẩn bị ảnh nhưng chưa có!
    """
    hotels = []
    search_terms = [city, f"{city} Vietnam", f"{city} Viet Nam"]

    for term in search_terms:
        try:
            url = (
                f"https://www.booking.com/searchresults.vi.html"
                f"?ss={quote(term)}"
                f"&nflt=is_newly_opened%3D1"
                f"&order=review_score_and_count"
            )
            resp = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select('[data-testid="property-card"]')
            for card in cards[:30]:
                name_el  = card.select_one('[data-testid="title"]')
                badge_el = card.select_one('[data-testid="badge"]')
                addr_el  = card.select_one('[data-testid="address"]')
                link_el  = card.select_one('a[href*="/hotel/"]')

                if not name_el:
                    continue

                badge_text = badge_el.get_text(strip=True).lower() if badge_el else ""
                is_new = any(kw in badge_text for kw in
                             ["new", "mới", "opening", "khai trương", "vừa mở"])

                hotel_url = link_el.get("href", "") if link_el else ""

                hotels.append({
                    "name":       name_el.get_text(strip=True),
                    "city":       city,
                    "address":    addr_el.get_text(strip=True) if addr_el else "",
                    "source":     "booking_opening_soon",
                    "source_url": hotel_url,
                    "status":     "Đang xây / Sắp mở",
                    "badge":      badge_text,
                    "signal":     "🏨 Booking: Sắp mở",
                    "priority":   "🟠 SỚM" if is_new else "🟡 TRUNG BÌNH",
                })

            time.sleep(1.5)
            break  # Dùng term đầu tiên thành công

        except Exception as e:
            print(f"  ⚠️ Booking opening soon lỗi: {e}")
            continue

    return hotels


# ═══════════════════════════════════════════════════════════════
# NGUỒN 3: Tuyển dụng nhân viên KS mới — VietnamWorks / TopCV
# KS tuyển GM, FOM, Housekeeping = sắp khai trương trong 2-4 tháng!
def scrape_recruitment_signals(city: str) -> List[Dict]:
    """Tìm KS đang tuyển dụng nhân viên — dấu hiệu sắp khai trương."""
    return scrape_hotel_job_postings(city)


def scrape_hotel_job_postings(city: str) -> List[Dict]:
    """
    Tìm KS đang tuyển dụng nhân viên — dấu hiệu sắp khai trương.
    Khi KS tuyển GM + Front Office + Housekeeping = sắp mở!
    """
    hotels = []

    # Các vị trí tuyển = dấu hiệu KS sắp mở
    opening_signals = [
        "general manager hotel",
        "hotel manager resort mới",
        "front office manager khai trương",
        "pre-opening hotel",
        "opening team resort",
    ]

    sources = [
        ("VietnamWorks", "https://www.vietnamworks.com/viec-lam/khach-san-resort-{city}"),
        ("TopCV",        "https://topcv.vn/viec-lam/khach-san?location={city}"),
    ]

    for source_name, url_tpl in sources:
        try:
            url = f"https://www.vietnamworks.com/tim-viec-lam?q=hotel+resort+pre-opening&l={quote(city)}"
            resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Job cards
            for card in soup.select(".job-item, .job-card, [class*='job']")[:20]:
                company_el = card.select_one(".company-name, [class*='company']")
                title_el   = card.select_one(".job-title, h2, h3")
                date_el    = card.select_one(".posted-date, [class*='date']")

                if not company_el or not title_el:
                    continue

                company = company_el.get_text(strip=True)
                job_title = title_el.get_text(strip=True)

                # Kiểm tra dấu hiệu "pre-opening"
                is_preopening = any(kw in (company + job_title).lower() for kw in
                                    ["pre-opening", "mới khai trương", "opening team",
                                     "hotel mới", "resort mới", "sắp khai trương"])

                if any(kw in (company + job_title).lower() for kw in
                       ["hotel", "resort", "villa", "khách sạn", "hospitality"]):
                    hotels.append({
                        "name":     company,
                        "city":     city,
                        "job_title": job_title,
                        "source":   f"jobs_{source_name.lower()}",
                        "status":   "Đang xây / Sắp mở",
                        "signal":   "👔 Đang tuyển nhân viên",
                        "priority": "🔴 RẤT SỚM" if is_preopening else "🟡 TRUNG BÌNH",
                    })

        except Exception as e:
            print(f"  ⚠️ Job scrape {source_name} lỗi: {e}")

    return deduplicate_by_name(hotels)


# ═══════════════════════════════════════════════════════════════
# NGUỒN 4: Google Search — KS đang xây / vừa công bố
# ═══════════════════════════════════════════════════════════════

def search_under_construction(city: str) -> List[Dict]:
    """
    Tìm KS đang xây qua Google News / báo địa phương
    """
    hotels = []
    year = datetime.now().year
    queries = [
        f"khách sạn resort đang xây dựng {city} {year}",
        f"dự án khách sạn resort {city} {year} khai trương",
        f"hotel resort {city} dự kiến khai trương {year}",
        f"resort {city} sắp mở cửa {year}",
        f'site:vnexpress.net OR site:baodautu.vn "khách sạn" "resort" "{city}" "{year}"',
    ]

    for q in queries[:3]:  # Giới hạn 3 query để tránh bị block
        try:
            url = f"https://www.google.com/search?q={quote(q)}&hl=vi&gl=vn&tbs=qdr:y"
            resp = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")

            for result in soup.select("div.g")[:8]:
                title_el = result.select_one("h3")
                desc_el  = result.select_one(".VwiC3b")
                link_el  = result.select_one("a[href]")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                desc  = desc_el.get_text(strip=True) if desc_el else ""
                link  = link_el.get("href", "") if link_el else ""

                hotel_name = extract_hotel_name(title + " " + desc)
                if hotel_name:
                    hotels.append({
                        "name":       hotel_name,
                        "city":       city,
                        "source":     "google_news",
                        "source_url": link,
                        "source_title": title,
                        "status":     "Đang xây / Sắp mở",
                        "signal":     "📰 Báo đưa tin xây dựng",
                        "priority":   "🟠 SỚM",
                    })

            time.sleep(2.5)  # Delay tránh bị block

        except Exception as e:
            print(f"  ⚠️ Search under construction lỗi: {e}")

    return deduplicate_by_name(hotels)


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def extract_hotel_name(text: str) -> str:
    patterns = [
        r'([A-Z][A-Za-zÀ-ỹ\s]+(?:Hotel|Resort|Villa|Boutique|Suites?|Lodge|Retreat))',
        r'(?:khách sạn|resort|hotel)\s+([A-ZÀ-Ỹ][A-Za-zÀ-ỹ\s]{3,40})',
        r'((?:[A-Z][a-zA-ZÀ-ỹ]+\s){1,4}(?:Hotel|Resort|Villa))',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            name = m.group(1).strip()
            if 4 < len(name) < 80:
                return name
    return ""


def clean_company_name(title: str) -> str:
    noise = [r'\s*-.*', r'\s*\|.*', r'\s*–.*']
    for n in noise:
        title = re.sub(n, '', title)
    return title.strip() if 3 < len(title.strip()) < 100 else ""


def deduplicate_by_name(items: List[Dict]) -> List[Dict]:
    seen, unique = set(), []
    for item in items:
        key = item.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ═══════════════════════════════════════════════════════════════
# MAIN: Quét tất cả nguồn early signals
# ═══════════════════════════════════════════════════════════════

def scan_early_signals(city: str) -> List[Dict]:
    """
    Tổng hợp tất cả nguồn phát hiện KS sớm:
    Trả về danh sách KS sắp khai trương, ưu tiên theo mức độ sớm
    """
    print(f"\n🔭 Early Signal Scanner: {city}")
    all_signals = []

    print("  1️⃣ Booking.com 'Opening Soon'...")
    booking_soon = scrape_booking_opening_soon(city)
    all_signals.extend(booking_soon)
    print(f"     → {len(booking_soon)} KS sắp mở trên Booking")

    print("  2️⃣ Tìm KS đang xây qua báo VN...")
    under_construction = search_under_construction(city)
    all_signals.extend(under_construction)
    print(f"     → {len(under_construction)} KS đang xây")

    print("  3️⃣ Tuyển dụng nhân viên KS mới...")
    jobs = scrape_hotel_job_postings(city)
    all_signals.extend(jobs)
    print(f"     → {len(jobs)} KS đang tuyển dụng")

    # Sắp xếp theo priority
    priority_order = {"🔴 RẤT SỚM": 0, "🟠 SỚM": 1, "🟡 TRUNG BÌNH": 2}
    all_signals.sort(key=lambda x: priority_order.get(x.get("priority", ""), 3))

    result = deduplicate_by_name(all_signals)
    print(f"\n  ✅ Tổng: {len(result)} tín hiệu KS sắp mở tại {city}")
    return result


# Alias cho module khác gọi tiện lợi
scrape_recruitment_signals = scrape_hotel_job_postings
