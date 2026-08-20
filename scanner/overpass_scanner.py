"""
scanner/overpass_scanner.py — Tìm khách sạn qua OpenStreetMap (MIỄN PHÍ, không cần API key)
Dùng Overpass API: https://overpass-api.de
"""
import httpx
import time
from typing import List, Dict

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Tọa độ trung tâm các thành phố VN
CITY_COORDS = {
    "Đà Nẵng":           (16.0544, 108.2022, 15),
    "Hội An":            (15.8801, 108.3380, 10),
    "Quảng Nam":         (15.5394, 108.0191, 20),
    "Huế":               (16.4637, 107.5909, 15),
    "Thừa Thiên Huế":    (16.4637, 107.5909, 25),
    "Quảng Bình":        (17.4689, 106.6220, 20),
    "Nha Trang":         (12.2388, 109.1967, 15),
    "Khánh Hòa":         (12.2388, 109.1967, 25),
    "TP. Hồ Chí Minh":   (10.8231, 106.6297, 20),
    "Phú Quốc":          (10.2899, 103.9840, 20),
    "Bà Rịa - Vũng Tàu": (10.5417, 107.2429, 20),
    "Phan Thiết":        (10.9804, 108.2624, 15),
    "Mũi Né":            (10.9500, 108.2800, 10),
    "Hà Nội":            (21.0278, 105.8342, 20),
    "Hạ Long":           (20.9101, 107.1839, 20),
    "Quảng Ninh":        (20.9101, 107.1839, 30),
    "Sapa":              (22.3364, 103.8440, 15),
    "Ninh Bình":         (20.2506, 105.9745, 15),
    "Đà Lạt":            (11.9404, 108.4583, 15),
    "Lâm Đồng":          (11.9404, 108.4583, 25),
    "Phú Yên":           (13.0882, 109.0929, 20),
    "Bình Định":         (13.7765, 109.2237, 20),
    "Hải Phòng":         (20.8449, 106.6881, 20),
    "Thanh Hóa":         (19.8078, 105.7767, 20),
}


def build_overpass_query(lat: float, lng: float, radius_km: int) -> str:
    """Tạo Overpass QL query tìm khách sạn trong bán kính"""
    radius_m = radius_km * 1000
    return f"""
[out:json][timeout:30];
(
  node["tourism"="hotel"](around:{radius_m},{lat},{lng});
  node["tourism"="motel"](around:{radius_m},{lat},{lng});
  node["tourism"="resort"](around:{radius_m},{lat},{lng});
  node["tourism"="guest_house"](around:{radius_m},{lat},{lng});
  node["building"="hotel"](around:{radius_m},{lat},{lng});
  way["tourism"="hotel"](around:{radius_m},{lat},{lng});
  way["tourism"="resort"](around:{radius_m},{lat},{lng});
  relation["tourism"="hotel"](around:{radius_m},{lat},{lng});
);
out body;
>;
out skel qt;
"""


def parse_overpass_result(data: dict, city: str) -> List[Dict]:
    """Parse kết quả Overpass API thành danh sách khách sạn"""
    hotels = []
    seen_names = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name") or tags.get("name:vi") or tags.get("name:en")

        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        # Lấy tọa độ
        lat = element.get("lat") or (element.get("center", {}) or {}).get("lat")
        lng = element.get("lon") or (element.get("center", {}) or {}).get("lon")

        hotel = {
            "name":       name,
            "city":       city,
            "address":    tags.get("addr:full") or tags.get("addr:street", ""),
            "phone_main": tags.get("phone") or tags.get("contact:phone", ""),
            "website":    tags.get("website") or tags.get("contact:website", ""),
            "stars":      int(tags.get("stars", 0)) or None,
            "source":     "openstreetmap",
            "status":     "Mới tìm thấy",
            "osm_id":     str(element.get("id", "")),
            "lat":        lat,
            "lng":        lng,
        }

        # Chuẩn hóa website
        if hotel["website"] and not hotel["website"].startswith("http"):
            hotel["website"] = "https://" + hotel["website"]

        hotels.append(hotel)

    return hotels


OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def scan_city_osm(city: str, radius_km: int = None) -> List[Dict]:
    """Quét khách sạn trong 1 thành phố qua OpenStreetMap với cơ chế multi-mirror fallback"""
    if city not in CITY_COORDS:
        # Nếu chưa có tọa độ chính xác, dùng tọa độ mặc định của Đà Nẵng / Hội An
        lat, lng, default_radius = CITY_COORDS.get("Đà Nẵng", (16.0544, 108.2022, 15))
    else:
        lat, lng, default_radius = CITY_COORDS[city]

    radius = radius_km or default_radius
    query = build_overpass_query(lat, lng, radius)

    for server_url in OVERPASS_SERVERS:
        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(
                    server_url,
                    data={"data": query},
                    headers={"User-Agent": "HotelScout/1.0 (haphong.com)"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    hotels = parse_overpass_result(data, city)
                    if hotels:
                        return hotels
        except Exception:
            continue

    return []


def scan_multiple_cities_osm(cities: List[str], delay: float = 1.5) -> List[Dict]:
    """Quét nhiều thành phố, có delay để không bị block"""
    all_hotels = []
    for i, city in enumerate(cities):
        hotels = scan_city_osm(city)
        all_hotels.extend(hotels)
        if i < len(cities) - 1:
            time.sleep(delay)  # Overpass yêu cầu delay giữa các request

    # Loại trùng tên
    seen = set()
    unique = []
    for h in all_hotels:
        key = h["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(h)

    return unique
