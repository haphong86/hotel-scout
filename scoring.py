"""
scoring.py — Hệ thống chấm điểm tiềm năng khách sạn
Tự động đánh giá 0-100 dựa trên nhiều yếu tố
"""

# ── Trọng số từng tiêu chí ──────────────────────────────────
WEIGHTS = {
    "source_booking":   30,  # Đăng ký Booking.com = KS thật, có nhu cầu ảnh
    "source_osm":        5,  # OpenStreetMap = đang hoạt động
    "has_website":      15,  # Có website = KS chuyên nghiệp, cần ảnh đẹp
    "has_phone":        10,  # Có phone = liên hệ được
    "name_luxury":      20,  # Tên có "Resort/Boutique/Villa/Spa"
    "name_basic":        5,  # Tên có "Hotel/Homestay"
    "rating_good":      10,  # Rating 7-8.9 = muốn improve thêm
    "rating_low":       15,  # Rating < 7 = CẦN ảnh mới gấp!
    "stars_high":       10,  # 4-5 sao = budget cao
    "stars_mid":         5,  # 3 sao
    "no_contact_yet":    5,  # Chưa được tiếp cận = opportunity
    "location_beach":   10,  # Tên/địa chỉ gần biển = khách quốc tế nhiều
    "location_heritage": 8,  # Hội An, phố cổ = premium market
}

# Từ khóa phát hiện loại KS
LUXURY_KEYWORDS = [
    "resort", "boutique", "villa", "spa", "retreat", "sanctuary",
    "grand", "royal", "palace", "luxury", "premium", "deluxe",
    "5 star", "five star", "nghỉ dưỡng", "khu nghỉ",
]

BASIC_KEYWORDS = [
    "hotel", "khách sạn", "homestay", "motel", "hostel",
    "guesthouse", "nhà nghỉ",
]

BEACH_KEYWORDS = [
    "beach", "ocean", "sea", "bay", "coast", "shore", "wave",
    "biển", "bãi biển", "vịnh", "bờ biển", "mỹ khê", "non nước",
    "mân thái", "sơn trà",
]

HERITAGE_KEYWORDS = [
    "hội an", "hoi an", "old town", "phố cổ", "heritage", "ancient",
    "lantern", "silk", "lụa",
]


def score_hotel(hotel) -> dict:
    """
    Chấm điểm tiềm năng 1 khách sạn.
    Trả về: {score: int, grade: str, reasons: list, label: str}
    """
    score   = 0
    reasons = []

    name    = (hotel.name or "").lower()
    website = hotel.website or ""
    phone   = hotel.phone_main or ""
    source  = hotel.source or ""
    rating  = hotel.rating or 0
    stars   = hotel.stars or 0
    city    = (hotel.city or "").lower()
    address = (hotel.address or "").lower()
    try:
        contacts = len(hotel.contacts)
    except Exception:
        contacts = 0  # Session đã đóng — bỏ qua

    # ── Nguồn ──────────────────────────────────────────────
    if "booking" in source:
        score += WEIGHTS["source_booking"]
        reasons.append("✅ Đăng ký Booking.com")
    elif "openstreetmap" in source or "osm" in source:
        score += WEIGHTS["source_osm"]
        reasons.append("📍 Xác nhận OSM")

    # ── Website / Contact ───────────────────────────────────
    if website and website not in ["—", ""]:
        score += WEIGHTS["has_website"]
        reasons.append("🌐 Có website")

    if phone and phone not in ["—", ""]:
        score += WEIGHTS["has_phone"]
        reasons.append("📞 Có hotline")

    # ── Loại KS ─────────────────────────────────────────────
    is_luxury = any(kw in name for kw in LUXURY_KEYWORDS)
    is_basic  = any(kw in name for kw in BASIC_KEYWORDS)

    if is_luxury:
        score += WEIGHTS["name_luxury"]
        reasons.append("🏆 Resort/Villa/Boutique")
    elif is_basic:
        score += WEIGHTS["name_basic"]
        reasons.append("🏨 Hotel/Homestay")

    # ── Vị trí ──────────────────────────────────────────────
    loc_text = name + " " + city + " " + address
    if any(kw in loc_text for kw in BEACH_KEYWORDS):
        score += WEIGHTS["location_beach"]
        reasons.append("🌊 Gần biển")

    if any(kw in loc_text for kw in HERITAGE_KEYWORDS):
        score += WEIGHTS["location_heritage"]
        reasons.append("🏮 Phố cổ/Heritage")

    # ── Rating ──────────────────────────────────────────────
    if rating >= 9.0:
        reasons.append("⭐ Rating xuất sắc (ảnh tốt rồi)")
        # Không cộng điểm — họ đã ok
    elif 7.0 <= rating < 9.0:
        score += WEIGHTS["rating_good"]
        reasons.append(f"📈 Rating {rating} — muốn cải thiện")
    elif 0 < rating < 7.0:
        score += WEIGHTS["rating_low"]
        reasons.append(f"⚠️ Rating {rating} — CẦN ảnh mới gấp!")

    # ── Số sao ──────────────────────────────────────────────
    if stars >= 4:
        score += WEIGHTS["stars_high"]
        reasons.append(f"{'★'*stars} {stars} sao — budget cao")
    elif stars == 3:
        score += WEIGHTS["stars_mid"]
        reasons.append("★★★ 3 sao")

    # ── Chưa được tiếp cận ──────────────────────────────────
    if contacts == 0:
        score += WEIGHTS["no_contact_yet"]
        reasons.append("🎯 Chưa có contact — opportunity!")

    # ── Giới hạn 0-100 ──────────────────────────────────────
    score = min(100, max(0, score))

    # ── Xếp loại ────────────────────────────────────────────
    if score >= 70:
        grade = "🔥 HOT"
        label = "HOT LEAD"
    elif score >= 50:
        grade = "⭐ Tiềm năng"
        label = "POTENTIAL"
    elif score >= 30:
        grade = "👀 Theo dõi"
        label = "WATCH"
    else:
        grade = "❄️ Thấp"
        label = "LOW"

    return {
        "score":   score,
        "grade":   grade,
        "label":   label,
        "reasons": reasons,
    }


def score_all_hotels(hotels: list) -> list:
    """Chấm điểm tất cả KS, trả về list đã sắp xếp theo điểm giảm dần"""
    results = []
    for hotel in hotels:
        s = score_hotel(hotel)
        results.append({
            "hotel": hotel,
            **s,
        })
    # Sắp xếp: HOT trước
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_lead_summary(hotels: list) -> dict:
    """Thống kê phân loại leads"""
    scored = score_all_hotels(hotels)
    hot       = [h for h in scored if h["score"] >= 70]
    potential = [h for h in scored if 50 <= h["score"] < 70]
    watch     = [h for h in scored if 30 <= h["score"] < 50]
    low       = [h for h in scored if h["score"] < 30]
    return {
        "hot":       hot,
        "potential": potential,
        "watch":     watch,
        "low":       low,
        "total":     len(scored),
    }
