# ============================================================
# config.py — Cấu hình Hotel Scout App
# Sao chép file này thành .env và điền thông tin thật
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ── Email Sender (Gmail + Cloudflare Routing) ──────────────
EMAIL_CONFIG = {
    "sender_name":  os.getenv("SENDER_NAME", "Phong | Hà Phong Visuals"),
    "sender_email": os.getenv("SENDER_EMAIL", "sales@haphong.com"),
    "smtp_server":  os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port":    int(os.getenv("SMTP_PORT", "587")),
    "smtp_user":    os.getenv("SMTP_USER", "haphong86@gmail.com"),
    "smtp_password": os.getenv("SMTP_PASSWORD", ""),  # App Password 16 ký tự
}

# ── Google Maps / Places API ───────────────────────────────
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Hunter.io API (tìm email theo domain) ─────────────────
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")

# ── Khu vực Việt Nam ──────────────────────────────────────
VIETNAM_REGIONS = {
    "🏖️ Miền Trung (Ưu tiên)": [
        "Đà Nẵng", "Hội An", "Quảng Nam", "Huế", "Thừa Thiên Huế",
        "Quảng Bình", "Quảng Trị", "Quảng Ngãi", "Bình Định", "Phú Yên",
        "Khánh Hòa", "Nha Trang"
    ],
    "🌆 Miền Nam": [
        "TP. Hồ Chí Minh", "Bà Rịa - Vũng Tàu", "Phú Quốc", "Kiên Giang",
        "Bình Thuận", "Phan Thiết", "Mũi Né", "Cần Thơ", "Đồng Nai", "Bình Dương"
    ],
    "🏛️ Miền Bắc": [
        "Hà Nội", "Hạ Long", "Quảng Ninh", "Sapa", "Lào Cai",
        "Ninh Bình", "Hải Phòng", "Nam Định", "Thanh Hóa"
    ],
    "🏔️ Tây Nguyên": [
        "Đà Lạt", "Lâm Đồng", "Buôn Ma Thuột", "Đắk Lắk", "Kon Tum", "Gia Lai"
    ],
}

# ── Chức vụ ưu tiên tìm email ─────────────────────────────
TARGET_JOB_TITLES = [
    # Quyết định hình ảnh / marketing
    "General Manager", "Hotel Manager", "Resort Manager",
    "Marketing Manager", "Digital Marketing Manager",
    "Sales Manager", "Director of Sales", "Revenue Manager",
    "Brand Manager", "Communications Manager", "PR Manager",
    "Content Manager", "Social Media Manager",
    "Art Director", "Creative Director",
    # Tiếng Việt
    "Giám đốc", "Tổng quản lý", "Giám đốc Marketing",
    "Trưởng phòng Marketing", "Giám đốc Kinh doanh",
    "Quản lý", "Trưởng phòng Kinh doanh",
]

# ── Database ───────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database/hotel_scout.db")

# ── App Settings ───────────────────────────────────────────
APP_CONFIG = {
    "app_name": "Hotel Scout 🏨",
    "version": "1.0.0",
    "max_emails_per_day": 50,         # Giới hạn an toàn tránh spam
    "min_delay_between_emails": 300,   # 5 phút giữa các email (giây)
    "max_delay_between_emails": 1200,  # 20 phút
    "followup_days": [7, 14],          # Ngày gửi follow-up
    "scan_interval_hours": 24,         # Quét khách sạn mới mỗi 24h
}
