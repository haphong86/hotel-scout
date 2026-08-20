"""
scanner/overpass_scanner.py — Tìm khách sạn qua OpenStreetMap (MIỄN PHÍ, không cần API key)
Dùng Overpass API: https://overpass-api.de
"""
import httpx
import time
from typing import List, Dict

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CITY_COORDS = {
    # Miền Trung & Nam Trung Bộ
    "Đà Nẵng":           (16.0544, 108.2022, 15),
    "Hội An":            (15.8801, 108.3380, 10),
    "Quảng Nam":         (15.5394, 108.0191, 20),
    "Huế":               (16.4637, 107.5909, 15),
    "Thừa Thiên Huế":    (16.4637, 107.5909, 25),
    "Lăng Cô":           (16.2300, 108.0000, 15),
    "Quy Nhơn":          (13.7820, 109.2197, 15),
    "Bình Định":         (13.7765, 109.2237, 25),
    "Tuy Hòa":           (13.0882, 109.0929, 15),
    "Phú Yên":           (13.0882, 109.0929, 25),
    "Nha Trang":         (12.2388, 109.1967, 15),
    "Cam Ranh":          (11.9214, 109.1591, 15),
    "Khánh Hòa":         (12.2388, 109.1967, 25),
    "Vĩnh Hy":           (11.7167, 109.1833, 15),
    "Phan Rang":         (11.5667, 108.9833, 15),
    "Ninh Thuận":        (11.5667, 108.9833, 25),
    "Phan Thiết":        (10.9804, 108.2624, 15),
    "Mũi Né":            (10.9500, 108.2800, 12),
    "Lagi":              (10.6667, 107.7500, 15),
    "Phú Quý":           (10.5200, 108.9400, 10),
    "Bình Thuận":        (10.9804, 108.2624, 25),
    "Quảng Bình":        (17.4689, 106.6220, 20),
    "Đồng Hới":          (17.4700, 106.6000, 15),
    "Phong Nha":         (17.5800, 106.2800, 15),
    "Quảng Trị":         (16.7500, 107.1800, 20),
    "Quảng Ngãi":        (15.1205, 108.7923, 15),
    "Lý Sơn":            (15.3780, 109.1200, 10),

    # Tây Nguyên & Nghỉ dưỡng Núi
    "Đà Lạt":            (11.9404, 108.4583, 15),
    "Bảo Lộc":           (11.5450, 107.8080, 15),
    "Lâm Đồng":          (11.9404, 108.4583, 25),
    "Măng Đen":          (14.6000, 108.2900, 15),
    "Kon Tum":           (14.3500, 108.0000, 15),
    "Buôn Ma Thuột":     (12.6667, 108.0500, 15),
    "Đắk Lắk":           (12.6667, 108.0500, 25),
    "Pleiku":            (13.9833, 108.0000, 15),
    "Gia Lai":           (13.9833, 108.0000, 25),

    # Miền Nam & Hải Đảo
    "Phú Quốc":          (10.2899, 103.9840, 20),
    "Kiên Giang":        (10.0000, 105.1000, 25),
    "Vũng Tàu":          (10.3460, 107.0843, 15),
    "Hồ Tràm":           (10.4600, 107.4500, 15),
    "Long Hải":          (10.3700, 107.2400, 15),
    "Côn Đảo":           (8.6833, 106.6000, 12),
    "Bà Rịa - Vũng Tàu": (10.5417, 107.2429, 20),
    "TP. Hồ Chí Minh":   (10.8231, 106.6297, 20),
    "Cần Thơ":           (10.0452, 105.7469, 15),

    # Miền Bắc & Vịnh
    "Sa Pa":             (22.3364, 103.8440, 15),
    "Sapa":              (22.3364, 103.8440, 15),
    "Lào Cai":           (22.4856, 103.9707, 20),
    "Hà Giang":          (22.8233, 104.9833, 15),
    "Mù Cang Chải":      (21.8500, 104.0833, 15),
    "Hạ Long":           (20.9101, 107.1839, 20),
    "Bãi Cháy":          (20.9500, 107.0300, 15),
    "Cát Bà":            (20.7200, 107.0500, 15),
    "Vân Đồn":           (21.0500, 107.4500, 20),
    "Cô Tô":             (20.9800, 107.7600, 15),
    "Quảng Ninh":        (20.9101, 107.1839, 30),
    "Ninh Bình":         (20.2506, 105.9745, 15),
    "Tràng An":          (20.2550, 105.9150, 12),
    "Tam Cốc":           (20.2180, 105.9350, 10),
    "Hà Nội":            (21.0278, 105.8342, 20),
    "Mai Châu":          (20.6600, 105.0800, 15),
    "Pù Luông":          (20.4700, 105.1800, 15),
    "Mộc Châu":          (20.8400, 104.6400, 15),
    "Hải Phòng":         (20.8449, 106.6881, 20),
    "Sầm Sơn":           (19.7400, 105.9000, 15),
    "Thanh Hóa":         (19.8078, 105.7767, 20),
    "Cửa Lò":            (18.8000, 105.7100, 15),
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
