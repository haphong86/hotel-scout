"""
scanner/google_maps.py — Tìm khách sạn mới qua Google Places API
"""
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import GOOGLE_MAPS_API_KEY


PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GEOCODE_URL       = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode_city(city: str) -> Optional[Dict]:
    """Chuyển tên thành phố thành tọa độ lat/lng"""
    if not GOOGLE_MAPS_API_KEY:
        return None
    resp = requests.get(GEOCODE_URL, params={
        "address": f"{city}, Vietnam",
        "key": GOOGLE_MAPS_API_KEY,
        "language": "vi",
    }, timeout=10)
    data = resp.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return {"lat": loc["lat"], "lng": loc["lng"], "city": city}
    return None


def search_hotels_nearby(lat: float, lng: float, radius_m: int = 20000,
                          keyword: str = "hotel") -> List[Dict]:
    """Tìm khách sạn trong bán kính radius_m mét"""
    if not GOOGLE_MAPS_API_KEY:
        return []

    hotels = []
    params = {
        "location": f"{lat},{lng}",
        "radius": radius_m,
        "type": "lodging",
        "keyword": keyword,
        "key": GOOGLE_MAPS_API_KEY,
        "language": "vi",
    }

    while True:
        resp = requests.get(PLACES_NEARBY_URL, params=params, timeout=15)
        data = resp.json()

        for place in data.get("results", []):
            hotels.append({
                "google_maps_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "review_count": place.get("user_ratings_total", 0),
                "source": "google_maps",
            })

        next_token = data.get("next_page_token")
        if not next_token:
            break
        time.sleep(2)  # Bắt buộc chờ trước khi dùng next_page_token
        params = {"pagetoken": next_token, "key": GOOGLE_MAPS_API_KEY}

    return hotels


def get_place_details(place_id: str) -> Dict:
    """Lấy chi tiết của 1 địa điểm: website, phone, opening hours"""
    if not GOOGLE_MAPS_API_KEY:
        return {}

    resp = requests.get(PLACES_DETAIL_URL, params={
        "place_id": place_id,
        "fields": "name,formatted_phone_number,website,rating,user_ratings_total,"
                  "formatted_address,opening_hours,price_level,editorial_summary",
        "key": GOOGLE_MAPS_API_KEY,
        "language": "vi",
    }, timeout=15)

    result = resp.json().get("result", {})
    return {
        "phone_main": result.get("formatted_phone_number"),
        "website": result.get("website"),
        "address": result.get("formatted_address"),
        "rating": result.get("rating"),
        "review_count": result.get("user_ratings_total", 0),
        "description": result.get("editorial_summary", {}).get("overview", ""),
    }


def scan_city(city: str, radius_km: int = 20,
              max_review_count: int = 100) -> List[Dict]:
    """
    Scan toàn bộ khách sạn trong 1 thành phố.
    Lọc lấy các KS mới (review_count thấp = mới khai trương).
    """
    print(f"🔍 Đang quét: {city}...")
    coords = geocode_city(city)
    if not coords:
        print(f"  ❌ Không tìm được tọa độ của {city}")
        return []

    raw = search_hotels_nearby(
        lat=coords["lat"],
        lng=coords["lng"],
        radius_m=radius_km * 1000,
    )
    print(f"  📍 Tìm thấy {len(raw)} địa điểm, đang lọc KS mới...")

    new_hotels = []
    for h in raw:
        # Lọc KS mới = ít review (chưa có nhiều khách)
        if h.get("review_count", 999) <= max_review_count:
            # Lấy thêm chi tiết (website, phone)
            if h.get("google_maps_id"):
                details = get_place_details(h["google_maps_id"])
                h.update(details)
                time.sleep(0.1)  # Tránh rate limit

            h["city"] = city
            h["status"] = "Mới tìm thấy"
            new_hotels.append(h)

    print(f"  ✅ {len(new_hotels)} KS mới (≤{max_review_count} review)")
    return new_hotels


def scan_multiple_cities(cities: List[str],
                          radius_km: int = 20,
                          max_review_count: int = 100) -> List[Dict]:
    """Quét nhiều thành phố cùng lúc"""
    all_hotels = []
    for city in cities:
        hotels = scan_city(city, radius_km, max_review_count)
        all_hotels.extend(hotels)
        time.sleep(1)
    return all_hotels
