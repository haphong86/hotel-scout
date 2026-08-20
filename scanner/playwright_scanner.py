"""
scanner/playwright_scanner.py — Scrape KS mới & sắp mở bằng Playwright (real browser)
Vượt qua anti-bot của Booking.com, TripAdvisor, VietnamWorks
"""
import time
import re
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime


def get_browser_page(playwright):
    """Tạo browser page với settings chống bị detect"""
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
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
    # Chặn ảnh/font để load nhanh hơn
    page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2}", lambda r: r.abort())
    return browser, page


# ═══════════════════════════════════════════════════════════════
# BOOKING.COM — KS mới & sắp khai trương
# ═══════════════════════════════════════════════════════════════

def scrape_booking_new_playwright(city: str, max_results: int = 50) -> List[Dict]:
    """Scrape Booking.com dùng Playwright — vượt anti-bot"""
    from playwright.sync_api import sync_playwright

    hotels = []
    print(f"  🌐 Playwright → Booking.com: {city}...")

    with sync_playwright() as p:
        browser, page = get_browser_page(p)
        try:
            # Tìm KS mới khai trương
            url = (
                f"https://www.booking.com/searchresults.vi.html"
                f"?ss={quote(city + ' Vietnam')}"
                f"&nflt=is_newly_opened%3D1"
                f"&order=review_score_and_count"
            )
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Cuộn để load lazy content
            for _ in range(3):
                page.keyboard.press("End")
                page.wait_for_timeout(1000)

            soup = BeautifulSoup(page.content(), "html.parser")
            cards = soup.select('[data-testid="property-card"]')

            for card in cards[:max_results]:
                name_el  = card.select_one('[data-testid="title"]')
                addr_el  = card.select_one('[data-testid="address"]')
                score_el = card.select_one('[data-testid="review-score"]')
                badge_el = card.select_one('[data-testid="badge"], .b30f8eb2d4')
                link_el  = card.select_one('a[href*="/hotel/"]')

                if not name_el:
                    continue

                name  = name_el.get_text(strip=True).replace("Mở trong cửa sổ mới", "").strip()
                score_text = score_el.get_text(strip=True) if score_el else ""
                rating = parse_rating(score_text)
                badge  = badge_el.get_text(strip=True) if badge_el else ""
                link   = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.booking.com" + link

                is_opening_soon = any(kw in badge.lower() for kw in
                                      ["opening", "mới", "new", "khai", "sắp"])

                hotels.append({
                    "name":       name,
                    "city":       city,
                    "address":    addr_el.get_text(strip=True) if addr_el else "",
                    "rating":     rating,
                    "source":     "booking.com",
                    "source_url": link,
                    "status":     "Đang xây / Sắp mở" if is_opening_soon else "Mới tìm thấy",
                    "signal":     "🏨 Booking: Mới khai trương" if not is_opening_soon else "⏰ Booking: Sắp mở",
                    "priority":   "🟠 SỚM" if is_opening_soon else "🟡 TRUNG BÌNH",
                })

            print(f"     ✅ Booking.com: {len(hotels)} KS")

        except Exception as e:
            print(f"     ❌ Lỗi: {e}")
        finally:
            browser.close()

    return hotels


# ═══════════════════════════════════════════════════════════════
# VIETNAMWORKS — KS đang tuyển dụng (sắp khai trương!)
# ═══════════════════════════════════════════════════════════════

def scrape_jobs_playwright(city: str) -> List[Dict]:
    """
    Tìm KS đang tuyển nhân viên mới — dấu hiệu sắp khai trương.
    Tuyển GM + Front Office + Housekeeping = sắp mở trong 2-4 tháng!
    """
    from playwright.sync_api import sync_playwright

    signals = []
    print(f"  👔 Playwright → VietnamWorks jobs: {city}...")

    # Từ khóa tuyển dụng mạnh nhất = "pre-opening" hoặc "hotel mới"
    search_terms = [
        f"pre-opening hotel {city}",
        f"hotel resort mới khai trương {city}",
        f"general manager hotel {city}",
    ]

    with sync_playwright() as p:
        browser, page = get_browser_page(p)
        try:
            for term in search_terms[:2]:
                url = f"https://www.vietnamworks.com/tim-viec-lam?q={quote(term)}&l=0"
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)

                soup = BeautifulSoup(page.content(), "html.parser")

                # Tìm job cards
                job_cards = soup.select(
                    '.job-item, [class*="JobCard"], [class*="job-card"], '
                    'div[data-job-id], li[data-job-id]'
                )

                for card in job_cards[:15]:
                    company_el = card.select_one(
                        '.company-name, [class*="CompanyName"], [class*="company"]'
                    )
                    title_el   = card.select_one(
                        '.job-title, [class*="JobTitle"], h2, h3'
                    )
                    if not company_el or not title_el:
                        continue

                    company   = company_el.get_text(strip=True)
                    job_title = title_el.get_text(strip=True)
                    combined  = (company + " " + job_title).lower()

                    # Lọc chỉ lấy liên quan KS
                    hotel_kw = ["hotel", "resort", "villa", "khách sạn", "hospitality", "lodge"]
                    if not any(kw in combined for kw in hotel_kw):
                        continue

                    # Phát hiện "pre-opening"
                    preopening_kw = ["pre-opening", "pre opening", "mới khai", "sắp khai",
                                     "opening team", "grand opening", "soft opening"]
                    is_pre = any(kw in combined for kw in preopening_kw)

                    signals.append({
                        "name":       company,
                        "city":       city,
                        "job_title":  job_title,
                        "source":     "vietnamworks",
                        "status":     "Đang xây / Sắp mở",
                        "signal":     "🔴 Tuyển pre-opening!" if is_pre else "👔 Đang tuyển nhân viên",
                        "priority":   "🔴 RẤT SỚM" if is_pre else "🟡 TRUNG BÌNH",
                        "note":       f"Vị trí tuyển: {job_title}",
                    })

                time.sleep(1.5)

            print(f"     ✅ Jobs: {len(signals)} tín hiệu")

        except Exception as e:
            print(f"     ❌ Jobs lỗi: {e}")
        finally:
            browser.close()

    return deduplicate(signals)


# ═══════════════════════════════════════════════════════════════
# GOOGLE NEWS — KS đang xây / vừa công bố
# ═══════════════════════════════════════════════════════════════

def scrape_google_news_playwright(city: str) -> List[Dict]:
    """Scrape Google News tìm tin xây dựng KS mới"""
    from playwright.sync_api import sync_playwright

    hotels = []
    year   = datetime.now().year
    print(f"  📰 Playwright → Google News: {city}...")

    queries = [
        f"khách sạn resort đang xây {city} {year}",
        f"resort hotel sắp khai trương {city} {year}",
        f"dự án du lịch resort {city} khai trương {year}",
    ]

    with sync_playwright() as p:
        browser, page = get_browser_page(p)
        try:
            for q in queries[:2]:
                url = f"https://news.google.com/search?q={quote(q)}&hl=vi&gl=VN&ceid=VN:vi"
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                soup = BeautifulSoup(page.content(), "html.parser")

                for article in soup.select("article")[:10]:
                    title_el = article.select_one("h3, h4, a[href]")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    hotel_kw = ["khách sạn", "resort", "hotel", "villa", "khu nghỉ"]
                    if not any(kw in title.lower() for kw in hotel_kw):
                        continue

                    name = extract_name_from_headline(title)
                    if name:
                        hotels.append({
                            "name":         name,
                            "city":         city,
                            "source":       "google_news",
                            "source_title": title,
                            "status":       "Đang xây / Sắp mở",
                            "signal":       "📰 Báo đưa tin xây dựng",
                            "priority":     "🟠 SỚM",
                        })

                time.sleep(2)

            print(f"     ✅ Google News: {len(hotels)} tin")

        except Exception as e:
            print(f"     ❌ Google News lỗi: {e}")
        finally:
            browser.close()

    return deduplicate(hotels)


# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def scan_early_signals_playwright(city: str) -> List[Dict]:
    """
    Tổng hợp tất cả nguồn phát hiện KS sắp khai trương
    Dùng Playwright để vượt anti-bot
    """
    print(f"\n🔭 Early Signal Scan (Playwright): {city}")
    all_signals = []

    # 1. Booking.com mới khai trương
    booking = scrape_booking_new_playwright(city)
    all_signals.extend(booking)

    # 2. Job postings (tuyển nhân viên = sắp mở)
    jobs = scrape_jobs_playwright(city)
    all_signals.extend(jobs)

    # 3. Google News (báo đưa tin xây dựng)
    news = scrape_google_news_playwright(city)
    all_signals.extend(news)

    # Sắp xếp theo priority
    priority_order = {"🔴 RẤT SỚM": 0, "🟠 SỚM": 1, "🟡 TRUNG BÌNH": 2}
    all_signals.sort(key=lambda x: priority_order.get(x.get("priority", ""), 3))

    result = deduplicate(all_signals)
    print(f"\n✅ Tổng early signals tại {city}: {len(result)}")

    # In tóm tắt
    hot = [h for h in result if h.get("priority") == "🔴 RẤT SỚM"]
    if hot:
        print(f"🔴 HOT LEADS ({len(hot)} KS pre-opening):")
        for h in hot:
            print(f"  → {h['name']} | {h.get('signal')} | {h.get('note','')}")

    return result


def parse_rating(text: str) -> float:
    m = re.search(r'(\d+[.,]\d+)', text)
    return float(m.group(1).replace(',', '.')) if m else 0.0


def extract_name_from_headline(title: str) -> str:
    patterns = [
        r'([A-Z][A-Za-zÀ-ỹ\s]+(?:Hotel|Resort|Villa|Boutique|Suites?|Lodge))',
        r'(?:xây dựng|khai trương|mở cửa)\s+([A-ZÀ-Ỹ][A-Za-zÀ-ỹ\s]{3,40})',
    ]
    for p in patterns:
        m = re.search(p, title)
        if m:
            name = m.group(1).strip()
            if 4 < len(name) < 80:
                return name
    return ""


def deduplicate(items: List[Dict]) -> List[Dict]:
    seen, unique = set(), []
    for item in items:
        key = item.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
