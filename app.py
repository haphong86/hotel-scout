"""
app.py — Hotel Scout Dashboard (Streamlit)
Chạy: streamlit run app.py
"""
import streamlit as st
import pandas as pd
import json
import os
import sys
import time
import io
import re
from jinja2 import Template
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

os.environ["TZ"] = "Asia/Ho_Chi_Minh"
try:
    time.tzset()
except Exception:
    pass

import socket

# Ép buộc Socket phân giải IPv4 trên Railway/Linux Container để triệt tiêu lỗi [Errno 101] Network is unreachable
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except Exception:
        return _orig_getaddrinfo(host, port, 0, type, proto, flags)

socket.getaddrinfo = _ipv4_only_getaddrinfo

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(__file__))

from config import VIETNAM_REGIONS, APP_CONFIG, EMAIL_CONFIG
from database.models import init_db, get_session, Hotel, Contact, EmailLog, Campaign, ScanLog
from sqlalchemy.orm import joinedload
from scheduler.daily_runner import start_scheduler

# Khởi động bộ đếm giờ tự động 09:00 AM chạy ngầm
start_scheduler()

# ── WEBHOOK TRACKING HANDLER (OPEN & CLICK) ────────────────
params = st.query_params
if "track" in params:
    track_action = params.get("track")
    log_id_str = params.get("id")
    if log_id_str and log_id_str.isdigit():
        log_id_val = int(log_id_str)
        from campaign.tracking_server import record_email_open, record_email_click
        if track_action == "open":
            record_email_open(log_id_val)
        elif track_action == "click":
            dest_url = params.get("dest", "https://haphong.com")
            record_email_click(log_id_val, dest_url)
            st.markdown(f'<meta http-equiv="refresh" content="0; url={dest_url}" />', unsafe_allow_html=True)
            st.markdown(f'<p style="color:#E50914; text-align:center; margin-top:50px;">Đang chuyển hướng tới <a href="{dest_url}">{dest_url}</a>...</p>', unsafe_allow_html=True)
            st.stop()

# ── Cấu hình trang ──────────────────────────────────────────
st.set_page_config(
    page_title="Hà Phong Visuals · Hotel Scout",
    page_icon="📷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — Hà Phong Visuals Design System ────────────────────
# Palette: #0d0d0d bg · #E50914 gold · #FFFFFF cream · #1a1a1a dark
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600&display=swap');

/* ── Global Black, Red & White Brand Theme ── */
html, body, [class*="css"] {
  font-family: 'Inter', sans-serif;
  background-color: #050505 !important;
  color: #F0F0F0 !important;
}
.main .block-container {
  background: #050505 !important;
  padding-top: 1.8rem;
  max-width: 1440px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: #000000 !important;
  border-right: 1px solid #1f1f1f !important;
}
[data-testid="stSidebar"] * { color: #d0d0d0 !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] .stSlider label {
  color: #E50914 !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
}
[data-testid="stSidebar"] hr { border-color: #222222 !important; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
  background: #111111 !important;
  border: 1px solid #222222 !important;
  border-top: 3px solid #E50914 !important;
  padding: 16px 18px !important;
  border-radius: 4px !important;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
}
[data-testid="metric-container"] label {
  color: #A0A0A0 !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'Montserrat', sans-serif !important;
  font-size: 32px !important;
  color: #FFFFFF !important;
  font-weight: 700 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid #222222 !important;
  gap: 8px;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  color: #888888 !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
  padding: 12px 20px !important;
  border-bottom: 2px solid transparent !important;
  font-family: 'Inter', sans-serif !important;
  transition: all 0.2s ease-in-out !important;
}
.stTabs [data-baseweb="tab"]:hover {
  color: #FFFFFF !important;
}
.stTabs [aria-selected="true"] {
  color: #FFFFFF !important;
  border-bottom: 2px solid #E50914 !important;
  background: rgba(229, 9, 20, 0.08) !important;
  border-radius: 4px 4px 0 0 !important;
}

/* ── Headings ── */
h1, h2, h3 {
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: 1px !important;
  color: #FFFFFF !important;
}
h1 { font-size: 28px !important; }
h2 { font-size: 22px !important; }
h3 { font-size: 16px !important; color: #E50914 !important; }

/* ── Buttons ── */
.stButton > button {
  background: #161616 !important;
  border: 1px solid #333333 !important;
  color: #FFFFFF !important;
  font-size: 11px !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
  padding: 10px 20px !important;
  border-radius: 4px !important;
  transition: all 0.2s !important;
}
.stButton > button:hover {
  background: #222222 !important;
  border-color: #E50914 !important;
  color: #FFFFFF !important;
  box-shadow: 0 0 10px rgba(229, 9, 20, 0.3) !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #E50914 0%, #B8000A 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 14px rgba(229, 9, 20, 0.4) !important;
}
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg, #FF1E27 0%, #D90429 100%) !important;
  box-shadow: 0 6px 20px rgba(229, 9, 20, 0.6) !important;
}

/* ── Inputs ── */
.stTextInput input, .stSelectbox select, .stTextArea textarea {
  background: #111111 !important;
  border: 1px solid #282828 !important;
  color: #FFFFFF !important;
  border-radius: 4px !important;
}
.stTextInput input:focus, .stSelectbox select:focus, .stTextArea textarea:focus {
  border-color: #E50914 !important;
  box-shadow: 0 0 0 1px #E50914 !important;
}
.stMultiSelect [data-baseweb="select"] {
  background: #111111 !important;
  border: 1px solid #282828 !important;
  border-radius: 4px !important;
}

/* ── Progress bar ── */
.stProgress > div > div {
  background: linear-gradient(90deg, #E50914 0%, #FF3B30 100%) !important;
}

/* ── Alerts & Expanders ── */
.stAlert {
  background: #111111 !important;
  border: 1px solid #282828 !important;
  border-left: 4px solid #E50914 !important;
  border-radius: 4px !important;
  color: #E0E0E0 !important;
}
.streamlit-expanderHeader {
  background: #111111 !important;
  border: 1px solid #222222 !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
  border: 1px solid #222222 !important;
  border-radius: 4px !important;
}
.stDataFrame thead th {
  background: #141414 !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
  border-bottom: 2px solid #E50914 !important;
}
.stDataFrame tbody tr { background: #0A0A0A !important; }
.stDataFrame tbody tr:hover { background: #161616 !important; }
.stDataFrame tbody td { color: #E0E0E0 !important; border-color: #1A1A1A !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #080808; }
::-webkit-scrollbar-thumb { background: #262626; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #E50914; }

""", unsafe_allow_html=True)


# ── Khởi tạo DB ─────────────────────────────────────────────
@st.cache_resource
def setup_db():
    return init_db()

setup_db()


# ── Hàm tiện ích ────────────────────────────────────────────
def get_all_hotels(filters: dict = None) -> pd.DataFrame:
    """Lấy danh sách KS từ DB, có thể filter"""
    session = get_session()
    try:
        query = session.query(Hotel)
        if filters:
            if filters.get("cities"):
                query = query.filter(Hotel.city.in_(filters["cities"]))
            if filters.get("stars"):
                # Hiển thị KS có sao theo chọn + KS không có dữ liệu sao (NULL)
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        Hotel.stars.in_(filters["stars"]),
                        Hotel.stars.is_(None),   # ← Bao gồm KS chưa có dữ liệu sao
                    )
                )
            if filters.get("status"):
                query = query.filter(Hotel.status == filters["status"])
            # Bỏ filter "days" để luôn hiển thị tất cả KS đã scan

        hotels = query.order_by(Hotel.created_at.desc()).all()
        if not hotels:
            return pd.DataFrame()

        data = []
        for h in hotels:
            contact_count = len(h.contacts)
            has_email = any(c.email for c in h.contacts)
            data.append({
                "ID": h.id,
                "Tên khách sạn": h.name,
                "Thành phố": h.city,
                "Sao": "⭐" * (h.stars or 0) if h.stars else "—",
                "Website": h.website or "—",
                "Phone": h.phone_main or "—",
                "Contacts": contact_count,
                "Email": "✅" if has_email else "❌",
                "Trạng thái": h.status,
                "Nguồn": h.source or "—",
                "Tìm thấy": h.created_at.strftime("%d/%m/%Y") if h.created_at else "—",
            })
        return pd.DataFrame(data)
    finally:
        session.close()


def get_contacts_df(hotel_id: int = None) -> pd.DataFrame:
    """Lấy danh sách contacts"""
    session = get_session()
    try:
        query = session.query(Contact, Hotel.name.label("hotel_name"), Hotel.city).join(Hotel)
        if hotel_id:
            query = query.filter(Contact.hotel_id == hotel_id)

        rows = query.order_by(Contact.confidence.desc()).all()
        if not rows:
            return pd.DataFrame()

        data = []
        for c, hotel_name, city in rows:
            data.append({
                "ID": c.id,
                "Tên": c.name or "—",
                "Chức vụ": c.title or "—",
                "Email": c.email or "—",
                "Phone": c.phone or "—",
                "Độ tin cậy": f"{c.confidence}%" if c.confidence else "—",
                "Khách sạn": hotel_name,
                "Thành phố": city,
                "Nguồn": c.source or "—",
                "LinkedIn": "🔗" if c.linkedin_url else "—",
            })
        return pd.DataFrame(data)
    finally:
        session.close()


def get_stats() -> dict:
    """Thống kê tổng quan"""
    session = get_session()
    try:
        total_hotels   = session.query(Hotel).count()
        new_hotels     = session.query(Hotel).filter(Hotel.status == "Mới tìm thấy").count()
        contacted      = session.query(Hotel).filter(Hotel.status == "Đã liên hệ").count()
        replied        = session.query(Hotel).filter(Hotel.status == "Đã reply").count()
        total_contacts = session.query(Contact).count()
        emails_sent    = session.query(EmailLog).filter(
            EmailLog.status.in_(["Đã gửi", "Đã mở", "Đã click", "Đã reply"])
        ).count()
        emails_opened  = session.query(EmailLog).filter(
            EmailLog.status.in_(["Đã mở", "Đã click", "Đã reply"])
        ).count()
        return {
            "total_hotels":   total_hotels,
            "new_hotels":     new_hotels,
            "contacted":      contacted,
            "replied":        replied,
            "total_contacts": total_contacts,
            "emails_sent":    emails_sent,
            "open_rate":      f"{emails_opened/emails_sent*100:.1f}%" if emails_sent > 0 else "—",
        }
    finally:
        session.close()


def get_app_version() -> str:
    """Lấy số phiên bản và mã commit mới nhất của hệ thống"""
    # 1. Đọc từ file version.json
    try:
        import json
        if os.path.exists("version.json"):
            with open("version.json", "r", encoding="utf-8") as f:
                vdata = json.load(f)
                return f"{vdata.get('version', 'v2.6.2')} • #{vdata.get('commit', '9d5992e')} ({vdata.get('build_time', '21/08 07:30')})"
    except Exception:
        pass

    # 2. Fallback từ git
    try:
        import subprocess
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        git_date = subprocess.check_output(["git", "log", "-1", "--format=%cd", "--date=format:%d/%m %H:%M"], stderr=subprocess.DEVNULL).decode().strip()
        return f"v2.6.2 • #{git_hash} ({git_date})"
    except Exception:
        return "v2.6.2 • 21/08/2026 (Live Production)"

CURRENT_VERSION = get_app_version()


# ── SIDEBAR ─────────────────────────────────────────────────
with st.sidebar:
    # Brand logo & header
    if os.path.exists("static/logo.jpg"):
        try:
            st.image("static/logo.jpg", use_column_width=True)
        except Exception:
            st.image("static/logo.jpg")
    else:
        st.markdown("""
        <div style="text-align:center; padding:16px 0 8px;">
          <div style="font-family:'Montserrat',sans-serif; font-size:22px; font-weight:800; color:#FFFFFF; letter-spacing:2px;">HÀ PHONG</div>
          <div style="font-size:11px; letter-spacing:4px; color:#E50914; font-weight:700;">VISUALS</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="margin-bottom:20px; text-align:center;">
      <div style="font-size:8px;letter-spacing:2px;color:#888;margin-top:4px;text-transform:uppercase;">Hotel Scout System</div>
      <div style="font-size:10px;color:#FFFFFF;background:#1A0506;border:1px solid #E50914;border-radius:4px;padding:4px 8px;margin-top:8px;text-align:center;font-weight:700;letter-spacing:0.5px;">
        ⚡ BẢN {CURRENT_VERSION}
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#E50914;text-transform:uppercase;margin-bottom:8px;">KHU VỰC QUÉT</p>', unsafe_allow_html=True)
    selected_region = st.selectbox(
        "Chọn vùng",
        options=list(VIETNAM_REGIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )

    available_cities = VIETNAM_REGIONS[selected_region]
    selected_cities = st.multiselect(
        "Thành phố",
        options=available_cities,
        default=available_cities[:3] if len(available_cities) >= 3 else available_cities,
    )

    st.divider()
    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#E50914;text-transform:uppercase;margin-bottom:8px;">BỘ LỌC</p>', unsafe_allow_html=True)

    filter_stars = st.multiselect(
        "Số sao",
        options=[3, 4, 5],
        default=[3, 4, 5],
        format_func=lambda x: f"{'★'*x}",
    )

    filter_days = st.selectbox(
        "Khai trương trong",
        options=[30, 60, 90, 180, 365],
        format_func=lambda x: f"{x} ngày qua",
        index=2,
    )

    filter_max_reviews = st.slider(
        "Review tối đa",
        min_value=10, max_value=500, value=100, step=10,
    )

    st.divider()
    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#E50914;text-transform:uppercase;margin-bottom:8px;">TÀI KHOẢN EMAIL</p>', unsafe_allow_html=True)
    email_ok = bool(EMAIL_CONFIG.get("smtp_password"))
    if email_ok:
        st.markdown(f'<p style="font-size:11px;color:#4a7c59;">● {EMAIL_CONFIG["sender_email"]}</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="font-size:11px;color:#7c4a4a;">● Chưa cấu hình SMTP</p>', unsafe_allow_html=True)

    st.markdown("""
    <div style="position:absolute;bottom:24px;left:0;right:0;text-align:center;padding:16px;">
      <a href="https://haphong.com" target="_blank"
         style="font-size:9px;letter-spacing:2px;color:#333;text-decoration:none;text-transform:uppercase;">
         haphong.com
      </a>
    </div>
    """, unsafe_allow_html=True)


# ── MAIN CONTENT ─────────────────────────────────────────────
st.markdown(f"""
<div class="hp-header">
  <div>
    <div class="hp-subtitle">Hotel Intelligence System</div>
    <div class="hp-logo-text">HÀ PHONG <span class="hp-gold">VISUALS</span></div>
  </div>
  <div style="margin-left:auto;text-align:right;">
    <div style="font-size:9px;letter-spacing:2px;color:#333;text-transform:uppercase;">
      {datetime.now().strftime('%d · %m · %Y')}
    </div>
    <div style="font-size:9px;letter-spacing:2px;color:#555;margin-top:4px;">
      Đà Nẵng · Hội An · Việt Nam
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# Metrics
stats = get_stats()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("TỔNG KS",         stats["total_hotels"])
c2.metric("KS MỚI",          stats["new_hotels"])
c3.metric("ĐÃ LIÊN HỆ",      stats["contacted"])
c4.metric("ĐÃ REPLY",        stats["replied"])
c5.metric("OPEN RATE",       stats["open_rate"])

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── TABS (GỌN GÀNG, KHÔNG BỊ TRÀN MÀN HÌNH) ───────────────────
tab_today, tab_backlog, tab3, tab_logs = st.tabs([
    "🚀 TOP 20 HÔM NAY",
    "📋 DỰ BỊ (#21+)",
    "✉️ CHIẾN DỊCH",
    "⏱️ GIÁM SÁT 24/7",
])


# ─────────────────────────────────────────────────────────────
# TAB 1: HÀNG ĐỢI HÔM NAY (TOP 20 EMAIL)
# ─────────────────────────────────────────────────────────────
with tab_today:
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #121212 0%, #0d0d0d 100%);
                border: 1px solid #E50914; border-radius: 4px; padding: 24px 28px; margin-bottom: 24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="font-size:10px;letter-spacing:3px;color:#E50914;text-transform:uppercase;font-weight:600;">
            HỆ THỐNG TỰ ĐỘNG HÓA TOÀN DIỆN
          </div>
          <div style="font-family:'Montserrat',sans-serif;font-weight:700;font-size:26px;color:#FFFFFF;margin:4px 0 6px;">
            1-Click Master Auto-Pilot
          </div>
          <div style="font-size:12px;color:#999;max-width:650px;line-height:1.6;">
            Chỉ với 1 nút bấm: Hệ thống tự động <b>Quét KS mới</b> ➔ <b>Đoán & Verify Email sống</b> ➔ <b>Gửi 20–25 email từ sales@haphong.com</b> ➔ <b>Bắn báo cáo về Telegram</b>.
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:10px;letter-spacing:1px;color:#4a7c59;text-transform:uppercase;font-weight:bold;">
            ● 24/7 Server Status: ONLINE
          </div>
          <div style="font-size:11px;color:#666;margin-top:4px;">
            ⏰ Tự động chạy mỗi sáng lúc <b>09:00 AM</b>
          </div>
          <div style="font-size:10px;color:#E50914;margin-top:6px;background:#18140c;border:1px solid #33080A;border-radius:3px;padding:3px 8px;font-weight:600;display:inline-block;">
            ⚡ BẢN {CURRENT_VERSION}
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Đồng bộ khu vực quét trực tiếp từ Sidebar điều khiển chung
    target_cities = selected_cities if selected_cities else ["Đà Nẵng", "Hội An"]
    cities_display = " · ".join(target_cities) if len(target_cities) <= 6 else f"{' · '.join(target_cities[:6])} và +{len(target_cities)-6} địa điểm khác"

    col_cfg1, col_cfg2, col_btn = st.columns([3, 2, 2])

    with col_cfg1:
        st.markdown(f"""
        <div style="background:#141414; border:1px solid #262626; border-left:3px solid #E50914;
                    padding:12px 16px; border-radius:3px;">
          <div style="font-size:9px; letter-spacing:2px; color:#E50914; text-transform:uppercase;">
            ĐỊA ĐIỂM QUÉT (ĐỒNG BỘ TỪ CỘT TRÁI)
          </div>
          <div style="font-size:13px; color:#FFFFFF; margin-top:4px; font-weight:500;">
            📍 {selected_region}
          </div>
          <div style="font-size:11px; color:#888; margin-top:2px;">
            {cities_display} ({len(target_cities)} thành phố)
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_cfg2:
        auto_email_limit = st.slider("Số email gửi trong lượt này:", min_value=5, max_value=30, value=20, step=5)
        tg_c1, tg_c2 = st.columns([2, 1])
        with tg_c1:
            auto_telegram = st.checkbox("Bắn báo cáo Telegram", value=True)
        with tg_c2:
            if st.button("🔔 Test Bot", help="Bấm để kiểm tra nhận thông báo từ Bot Telegram @HaPhongScanHotelResort_Bot"):
                from notifications.telegram_bot import send_telegram_message, get_chat_id_from_bot
                cid = get_chat_id_from_bot()
                if cid:
                    send_telegram_message("🔔 [Hà Phong Visuals] Kết nối Bot thành công! Hệ thống đã sẵn sàng bắn thông báo realtime cho anh.", chat_id=cid)
                    st.success("✅ Đã bắn thông báo test về Telegram của anh!")
                else:
                    st.warning("⚠️ Mở Telegram tìm bot **@HaPhongScanHotelResort_Bot** và bấm **START** trước nhé!")

    with col_btn:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        start_autopilot_btn = st.button(
            "⚡ START AUTOPILOT",
            type="primary",
            use_container_width=True,
            help="Chạy toàn bộ quy trình: Quét -> Tìm Email -> Verify -> Gửi Chiến Dịch -> Báo Cáo Telegram"
        )

    # ── HÀNG ĐỢI GỬI EMAIL ƯU TIÊN (PRIORITIZED OUTREACH QUEUE) ──
    from campaign.priority_queue import get_prioritized_outreach_queue
    outreach_queue = get_prioritized_outreach_queue(limit=auto_email_limit, selected_cities=target_cities)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    with st.expander(f"📋 DANH SÁCH & HÀNG ĐỢI EMAIL ƯU TIÊN HÔM NAY ({len(outreach_queue)} Khách Sạn Xếp Hạng #1 ➔ #{len(outreach_queue)})", expanded=True):
        st.markdown("""
        <div style="font-size:12px;color:#aaa;margin-bottom:12px;line-height:1.6;">
          Hệ thống tự động xếp hạng ưu tiên: <b>🌟 Bậc 1: Dự án Pre-Opening / Sắp khai trương</b> (Cần gấp ảnh trước 60 ngày) ➔ <b>🔥 Bậc 2: Khách sạn Mới 4–5★ & Hot Leads</b> ➔ <b>⭐ Bậc 3: Tiềm năng</b>.
        </div>
        """, unsafe_allow_html=True)

        if not outreach_queue:
            st.info("Hiện tại chưa có email nào trong hàng đợi. Nhấn **START AUTOPILOT** để quét thêm khách sạn mới!")
        else:
            table_rows_html = []
            for item in outreach_queue:
                badge_color = "#e63946" if "RẤT GẤP" in item['priority_badge'] or "HOT" in item['priority_badge'] else "#f4a261"
                table_rows_html.append(f"""
                <tr style="border-bottom:1px solid #222; transition:background 0.2s;" onmouseover="this.style.background='#1c1c1c'" onmouseout="this.style.background='transparent'">
                  <td style="padding:10px 12px; font-weight:bold; color:#E50914;">#{item['queue_index']}</td>
                  <td style="padding:10px 12px;"><span style="background:{badge_color}22; color:{badge_color}; border:1px solid {badge_color}55; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:600;">{item['priority_badge']}</span></td>
                  <td style="padding:10px 12px; font-weight:500; color:#FFFFFF;">{item['hotel_name']}</td>
                  <td style="padding:10px 12px; color:#aaa;">{item['city']}</td>
                  <td style="padding:10px 12px; color:#ddd;"><span style="color:#E50914;">{item['recipient_role']}</span></td>
                  <td style="padding:10px 12px; font-family:monospace; color:#8ecae6;">{item['recipient_email']}</td>
                  <td style="padding:10px 12px; color:#888; font-size:11px;">{item['reason']}</td>
                </tr>
                """)

            html_table = f"""
            <div style="overflow-x:auto; border:1px solid #2d2d2d; border-radius:4px; margin-top:4px;">
              <table style="width:100%; border-collapse:collapse; font-size:12px; text-align:left;">
                <thead>
                  <tr style="background:#181818; border-bottom:1px solid #333; color:#E50914; text-transform:uppercase; font-size:10px; letter-spacing:1px;">
                    <th style="padding:10px 12px;">#</th>
                    <th style="padding:10px 12px;">Ưu Tiên</th>
                    <th style="padding:10px 12px;">Khách Sạn / Dự Án</th>
                    <th style="padding:10px 12px;">Khu Vực</th>
                    <th style="padding:10px 12px;">Đầu Mối</th>
                    <th style="padding:10px 12px;">Email Sạch</th>
                    <th style="padding:10px 12px;">Lý Do Ưu Tiên</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(table_rows_html)}
                </tbody>
              </table>
            </div>
            """
            st.html(html_table)

    # ── THỰC THI TOÀN BỘ QUY TRÌNH 1-CLICK ────────────────────
    if start_autopilot_btn:
        import time as _t
        start_time = _t.time()

        status_box = st.status("🚀 Đang khởi động quy trình Auto-Pilot...", expanded=True)
        log_box = st.empty()
        p_bar = st.progress(0.0)
        logs = []

        from database.models import get_now_vn

        def add_log(msg):
            logs.append(f"[{get_now_vn().strftime('%H:%M:%S')}] {msg}")
            log_box.code("\n".join(logs[-16:]))

        # ── GIAI ĐOẠN 1: QUÉT KHÁCH SẠN ──────────────────────
        status_box.update(label="🔍 Bước 1/4: Đang quét khách sạn mới...")
        add_log("🚀 BẮT ĐẦU GIAI ĐOẠN 1: Quét khách sạn mới...")
        p_bar.progress(0.15)

        total_scanned = 0
        saved_hotels = 0
        from scanner.overpass_scanner import scan_city_osm
        from scanner.google_maps_scraper import search_google_maps
        from scanner.early_signals import scrape_booking_opening_soon, scrape_hotel_job_postings, scrape_recruitment_signals

        session = get_session()
        target_cities = selected_cities if selected_cities else ["Đà Nẵng", "Hội An"]

        for idx, city in enumerate(target_cities):
            try:
                add_log(f"  • [{idx+1}/{len(target_cities)}] 🌐 ĐANG QUÉT ĐA KÊNH TẠI {city.upper()}...")
                
                # 1. OpenStreetMap
                osm = scan_city_osm(city, radius_km=15)
                add_log(f"    ↳ OSM: Tìm thấy {len(osm)} cơ sở.")
                
                # 2. Google Maps / Search
                gmaps = search_google_maps(f"khách sạn mới {city}", city)
                add_log(f"    ↳ Google Maps & Search: Tìm thấy {len(gmaps)} KS/Resort.")

                # 3. Booking.com Newly Opened / Opening Soon
                b_soon = scrape_booking_opening_soon(city)
                add_log(f"    ↳ Booking (Mới mở / Sắp mở): Tìm thấy {len(b_soon)} lead nóng.")

                # 4. Tin tuyển dụng GM/Marketing (Hoteljob, TopCV)
                jobs = scrape_hotel_job_postings(city)
                add_log(f"    ↳ Tuyển dụng GM/MKT (Hoteljob/TopCV): Tìm thấy {len(jobs)} tín hiệu.")

                all_found = osm + gmaps + b_soon + jobs
                total_scanned += len(all_found)

                for h in all_found:
                    name = (h.get("name") or "").strip()
                    if not name or len(name) < 3:
                        continue
                    exists = session.query(Hotel).filter(Hotel.name == name, Hotel.city == city).first()
                    if not exists:
                        session.add(Hotel(
                            name=name, city=city,
                            address=h.get("address"), website=h.get("website") or h.get("source_url"),
                            phone_main=h.get("phone_main"), rating=h.get("rating"),
                            review_count=h.get("review_count", 0),
                            source=h.get("source", "multi_source"),
                            status="Đang xây / Sắp mở" if h.get("signal") else "Mới tìm thấy"
                        ))
                        saved_hotels += 1
            except Exception as e:
                add_log(f"  ⚠️ Quét {city}: {e}")

        session.commit()
        session.close()
        add_log(f"✅ GIAI ĐOẠN 1 XONG: Đã quét Đa Kênh, +{saved_hotels} khách sạn mới lưu vào kho.")
        p_bar.progress(0.40)

        # ── GIAI ĐOẠN 2: TÌM & VERIFY EMAIL ───────────────────
        status_box.update(label="🔎 Bước 2/4: Đang tìm kiếm & verify email sống...")
        add_log("🚀 BẮT ĐẦU GIAI ĐOẠN 2: Tìm kiếm & xác thực Email...")

        from pipeline import run_pipeline
        pipe_res = run_pipeline(
            cities=target_cities if target_cities else None,
            limit=25,
            log_fn=add_log,
        )
        add_log(f"✅ GIAI ĐOẠN 2 XONG: Tìm được {pipe_res.get('emails_saved', 0)} email đã verify sạch.")
        p_bar.progress(0.70)

        # ── GIAI ĐOẠN 3: GỬI CHIẾN DỊCH BẬC THANG THEO HÀNG ĐỢI ƯU TIÊN ──
        status_box.update(label=f"📤 Bước 3/4: Đang gửi email theo Hàng Đợi Ưu Tiên (Tối đa {auto_email_limit} thư)...")
        add_log(f"🚀 BẮT ĐẦU GIAI ĐOẠN 3: Lấy danh sách từ Hàng Đợi Ưu Tiên #1 ➔ #{auto_email_limit}...")

        from campaign.email_sender import send_email
        from campaign.priority_queue import get_prioritized_outreach_queue
        from jinja2 import Template

        prioritized_items = get_prioritized_outreach_queue(limit=auto_email_limit, selected_cities=target_cities)

        sent_count = 0
        if not prioritized_items:
            add_log("  ℹ️ Không có khách sạn hoặc dự án nào trong hàng đợi cần gửi.")
        else:
            add_log(f"  📬 Sẵn sàng gửi {len(prioritized_items)} email xếp hạng ưu tiên cao nhất...")

            with open("campaign/templates/email_01_intro.html", "r", encoding="utf-8") as f:
                tpl_vi = f.read()
            with open("campaign/templates/email_en_01_intro.html", "r", encoding="utf-8") as f:
                tpl_en = f.read()
            with open("campaign/templates/email_pre_opening.html", "r", encoding="utf-8") as f:
                tpl_pre = f.read()

            intl_keywords = {
                "hyatt", "marriott", "hilton", "sheraton", "intercontinental", "novotel", "pullman",
                "radisson", "four seasons", "banyan tree", "melia", "wyndham", "anantara", "six senses",
                "renaissance", "mercure", "sofitel", "crowne plaza", "shangri-la", "jw marriott",
                "le meridien", "st. regis", "w hotel", "voco", "holiday inn", "fusion", "salinda"
            }

            tracking_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "hotel-scout-production.up.railway.app")
            tracking_base = f"https://{tracking_domain}" if not tracking_domain.startswith("http") else tracking_domain

        from database.models import safe_commit

        for idx, item in enumerate(prioritized_items):
            try:
                p_type = item.get("type", "hotel")
                h_name = item["hotel_name"]
                h_city = item["city"]
                to_mail = item["recipient_email"]
                rec_name = item["recipient_name"]
                rec_role = item["recipient_role"]

                if p_type == "pre_opening":
                    subj = f"[{h_name}] — Giải pháp Visual & Bộ ảnh Kiến trúc Launching khai trương tại {h_city}"
                    body = Template(tpl_pre).render(
                        hotel_name=h_name,
                        contact_name=rec_name or rec_role or "Ban Lãnh Đạo",
                        city=h_city,
                        to_email=to_mail,
                        subject=subj,
                    )
                    lang_tag = "🌟 PRE-OPENING"
                    add_log(f"  📤 [{idx+1}/{len(prioritized_items)}] {lang_tag} Gửi → {to_mail} ({h_name[:22]})...")
                    res = send_email(to_mail, rec_name or "", subj, body)
                    if res.get("success"):
                        sent_count += 1
                        db_proj = session.query(PreOpeningProject).get(item.get("project_id"))
                        if db_proj:
                            db_proj.status = "Đã gửi Email Launching"
                            safe_commit(session)
                    _t.sleep(1.5)
                else:
                    c_dom = to_mail.split("@")[-1].lower().strip()
                    is_intl = any(k in h_name.lower() for k in intl_keywords) or (c_dom.endswith(".com") and not c_dom.endswith(".vn"))

                    if is_intl:
                        subj = f"[{h_name}] — Elevating Architectural & Visual Identity in {h_city}"
                        body_raw = Template(tpl_en).render(
                            hotel_name=h_name, contact_name=rec_name or "General Manager",
                            city=h_city, to_email=to_mail, subject=subj
                        )
                        lang_tag = "🌐 EN"
                    else:
                        subj = f"[{h_name}] — Giải pháp nâng cấp hình ảnh kiến trúc & visual khách sạn"
                        body_raw = Template(tpl_vi).render(
                            hotel_name=h_name, contact_name=rec_name or "Anh/Chị",
                            city=h_city, to_email=to_mail, subject=subj
                        )
                        lang_tag = "🇻🇳 VI"

                    elog = EmailLog(
                        hotel_id=item.get("hotel_id"), contact_id=item.get("contact_id"), sequence_num=1,
                        subject=subj, status="Đang gửi", sent_at=get_now_vn()
                    )
                    session.add(elog)
                    safe_commit(session)

                    click_tracked_url = f"{tracking_base}/?track=click&id={elog.id}&dest=https://haphong.com"
                    body_with_links = body_raw.replace('href="https://haphong.com"', f'href="{click_tracked_url}"')
                    pixel_tag = f'<img src="{tracking_base}/?track=open&id={elog.id}" width="1" height="1" style="display:none;" />'
                    body_final = body_with_links.replace("</body>", f"{pixel_tag}</body>") if "</body>" in body_with_links else body_with_links + pixel_tag

                    add_log(f"  📤 [{idx+1}/{len(prioritized_items)}] {lang_tag} Gửi → {to_mail} ({h_name[:22]})...")
                    res = send_email(to_mail, rec_name or "", subj, body_final)
                    if res.get("success"):
                        sent_count += 1
                        elog.status = "Đã gửi"
                        db_h = session.query(Hotel).get(item.get("hotel_id"))
                        if db_h:
                            db_h.status = "Đã liên hệ"
                        safe_commit(session)
                    else:
                        elog.status = "Thất bại"
                        elog.error_msg = res.get("error", "") or res.get("message", "")
                        safe_commit(session)
                    _t.sleep(1.5)
            except Exception as e_item:
                add_log(f"  ⚠️ Lỗi xử lý gửi: {e_item}")
                continue

        session.close()
        add_log(f"✅ GIAI ĐOẠN 3 XONG: Đã gửi thành công {sent_count} email!")
        p_bar.progress(0.90)

        # ── GIAI ĐOẠN 4: BÁO CÁO TELEGRAM ────────────────────
        status_box.update(label="📱 Bước 4/4: Đang gửi báo cáo qua Telegram...")
        if auto_telegram:
            add_log("🚀 BẮT ĐẦU GIAI ĐOẠN 4: Gửi báo cáo Telegram...")
            try:
                from notifications.telegram_bot import send_daily_telegram_report
                tg_ok = send_daily_telegram_report()
                if tg_ok:
                    add_log("  ✅ Đã gửi báo cáo chi tiết về Telegram!")
                else:
                    add_log("  ℹ️ Đã hoàn thành (Chưa cấu hình Telegram Chat ID hoặc bỏ qua).")
            except Exception as e:
                add_log(f"  ⚠️ Lỗi gửi Telegram: {e}")

        p_bar.progress(1.0)
        elapsed = int(_t.time() - start_time)
        status_box.update(label=f"🎉 QUY TRÌNH HOÀN TẤT TRONG {elapsed} GIÂY!", state="complete", expanded=True)

        st.success(
            f"🎉 **Quy trình 1-Click Autopilot hoàn tất thành công!**  \n"
            f"• Khách sạn mới: **+{saved_hotels}**  \n"
            f"• Email đã verify: **+{pipe_res.get('emails_saved', 0)}**  \n"
            f"• Email đã gửi: **{sent_count} thư** (từ sales@haphong.com)  \n"
            f"• Thời gian chạy: **{elapsed} giây**"
        )




# ─────────────────────────────────────────────────────────────
# TAB 2: HÀNG ĐỢI DỰ BỊ (#21 ➔ HẾT DỮ LIỆU)
# ─────────────────────────────────────────────────────────────
with tab_backlog:
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #121212 0%, #0d0d0d 100%);
                border: 1px solid #E50914; border-radius: 4px; padding: 22px 26px; margin-bottom: 20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="font-size:10px;letter-spacing:3px;color:#E50914;text-transform:uppercase;font-weight:600;">
            KHO DỮ LIỆU EMAIL SỐNG DỰ BỊ (BACKLOG QUEUE)
          </div>
          <div style="font-family:'Montserrat',sans-serif;font-weight:700;font-size:26px;color:#FFFFFF;margin:4px 0 6px;">
            Hàng Đợi Email Sống Dự Bị (#21 ➔ Hết Dữ Liệu)
          </div>
          <div style="font-size:12px;color:#999;max-width:750px;line-height:1.6;">
            Toàn bộ danh sách này là các email <b>ĐÃ ĐƯỢC XÁC THỰC SỐNG 100%</b> sẵn sàng gửi. Khi bất kỳ email nào trong Top 20 ở Trang Chủ được gửi đi (09:00 - 17:00), email đầu tiên tại đây (#21) sẽ <b>tự động được đôn lên thay thế vào Top 20</b>!
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;letter-spacing:1px;color:#4a7c59;text-transform:uppercase;font-weight:bold;">
            ● Trạng thái: TỰ ĐỘNG ĐÔN HÀNG ĐỢI
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    from campaign.priority_queue import get_backlog_queue_21_plus
    backlog_items = get_backlog_queue_21_plus(selected_cities=target_cities, limit=300)

    st.markdown(f"#### 📋 Danh sách {len(backlog_items)} Email Dự Bị Đang Xếp Hàng")

    if not backlog_items:
        st.info("Hệ thống đang chạy ngầm quét & xác thực email sống cho các khách sạn còn lại. Các email mới sẽ tự động hiển thị tại đây!")
    else:
        b_rows = []
        for item in backlog_items:
            b_rows.append({
                "Thứ Tự": f"#{item['queue_index']}",
                "Ưu Tiên": item['priority_badge'],
                "Khách Sạn / Dự Án": item['hotel_name'],
                "Khu Vực": item['city'],
                "Người Nhận": f"{item['recipient_role']} ({item['recipient_name']})",
                "Email Sống": item['recipient_email'],
                "Điểm Lead": f"{item.get('lead_score', 50)}/100",
                "Lý Do": item.get('reason', 'Tiềm năng'),
            })
        df_backlog = pd.DataFrame(b_rows)
        st.dataframe(df_backlog, use_container_width=True, height=500)


with tab3:
    st.markdown("## 📤 Email Campaign")

    # Test SMTP
    col_test, _ = st.columns([2, 3])
    with col_test:
        if st.button("🔌 Test kết nối SMTP"):
            from campaign.email_sender import test_smtp_connection
            result = test_smtp_connection()
            if result["success"]:
                st.success(result["message"])
            else:
                st.error(result["message"])

    st.divider()

    # Preview template
    st.markdown("### 👁️ Preview & Quản Lý 5 Email Templates")

    TEMPLATES_DICT = {
        "Email 1 — Hero Intro (3s Quyết Định)": {
            "file": "campaign/templates/email_01_intro.html",
            "subject": "[{hotel_name}] — Giải pháp nâng cấp hình ảnh kiến trúc & visual khách sạn",
            "desc": "Tập trung vào 3 giây đầu tiên của du khách, thư viết tay cá nhân tinh tế, link portfolio & hotline."
        },
        "Email 2 — Tân Trang Visual (Mùa Cao Điểm)": {
            "file": "campaign/templates/email_02_season_refresh.html",
            "subject": "[{hotel_name}] — Chuẩn bị bộ ảnh mới đón mùa cao điểm du lịch {city}",
            "desc": "Chiến lược làm mới visual OTA trước mùa đón khách, gia tăng giá trị nhận diện & giá phòng."
        },
        "Email 3 — Resort & Boutique Luxury": {
            "file": "campaign/templates/email_03_resort_boutique.html",
            "subject": "[{hotel_name}] — Bộ ảnh visual kiến trúc & không gian nghỉ dưỡng cao cấp",
            "desc": "Dành riêng cho Resort / Boutique / Villa cao cấp: Tôn vinh kiến trúc, ánh sáng hoàng hôn & flycam."
        },
        "Email 4 — Tư Vấn Visual Audit": {
            "file": "campaign/templates/email_04_visual_audit.html",
            "subject": "[{hotel_name}] — Gợi ý tối ưu góc ảnh & visual hiển thị trên OTA",
            "desc": "Follow-up tinh tế mang giá trị tư vấn: Đưa ra 3 điểm cải thiện visual trực quan, mời nhận audit miễn phí."
        },
        "Email 5 — Gói Chụp Tinh Gọn 72 Giờ": {
            "file": "campaign/templates/email_05_quick_shoot.html",
            "subject": "[{hotel_name}] — Kế hoạch sản xuất visual khách sạn & bàn giao trong 72h",
            "desc": "Quy trình chụp 1-2 ngày không ảnh hưởng khách ở, bàn giao file chuẩn đa nền tảng trong 72 giờ."
        },
    }

    tpl_choice = st.selectbox(
        "Chọn mẫu email template:",
        options=list(TEMPLATES_DICT.keys()),
        index=0,
    )

    cur_tpl = TEMPLATES_DICT[tpl_choice]
    st.caption(f"💡 **Mục đích:** {cur_tpl['desc']}")

    preview_col, settings_col = st.columns([3, 2])
    with settings_col:
        prev_hotel_name    = st.text_input("Tên KS (test)", value="Grand Sunrise Boutique Resort")
        prev_contact_name  = st.text_input("Tên người (test)", value="Anh Minh (GM)")
        prev_city          = st.text_input("Thành phố (test)", value="Đà Nẵng")
        prev_email         = st.text_input("Email test gửi đến", value="bccb898@gmail.com")
        send_test_btn      = st.button("📨 Gửi email test", type="primary", use_container_width=True)

    with preview_col:
        from jinja2 import Template
        tpl_file = cur_tpl["file"]
        try:
            with open(tpl_file, encoding="utf-8") as f:
                tpl_html = f.read()
            subject = cur_tpl["subject"].format(
                hotel_name=prev_hotel_name,
                city=prev_city,
            )
            rendered = Template(tpl_html).render(
                hotel_name=prev_hotel_name,
                contact_name=prev_contact_name,
                city=prev_city,
                to_email=prev_email or "test@example.com",
                subject=subject,
            )
            st.html(f'<div style="height:620px;overflow:auto;background:#fff;border-radius:4px;border:1px solid #e8e2d8;">{rendered}</div>')
        except Exception as e:
            st.error(f"Lỗi render template: {e}")

    if send_test_btn:
        if not prev_email:
            st.warning("Nhập email test trước!")
        elif not EMAIL_CONFIG.get("smtp_password"):
            st.error("Chưa cấu hình SMTP password trong file .env!")
        else:
            from campaign.email_sender import send_email
            from jinja2 import Template
            with open(tpl_file, encoding="utf-8") as f:
                tpl_html = f.read()
            subject = cur_tpl["subject"].format(
                hotel_name=prev_hotel_name,
                city=prev_city,
            )
            body = Template(tpl_html).render(
                hotel_name=prev_hotel_name,
                contact_name=prev_contact_name,
                city=prev_city,
                to_email=prev_email,
                subject=subject,
            )
            with st.spinner("Đang gửi..."):
                result = send_email(prev_email, prev_contact_name, subject, body)
            if result["success"]:
                st.success(f"✅ Đã gửi email test đến {prev_email}!")
            else:
                st.error(f"❌ Lỗi: {result['error']}")

    st.divider()

    # Gửi campaign thật
    st.markdown("### 🚀 Chạy Campaign Thật")

    session_c = get_session()
    pending_contacts = session_c.query(Contact).filter(
        Contact.email.isnot(None),
        Contact.email != "",
        ~Contact.email_logs.any(),
    ).all()
    session_c.close()

    st.info(f"📬 **{len(pending_contacts)}** contacts chưa được liên hệ, sẵn sàng gửi email.")

    camp_tpl_choice = st.selectbox(
        "Mẫu template áp dụng cho Campaign:",
        options=list(TEMPLATES_DICT.keys()),
        index=0,
        key="camp_tpl_select",
    )

    camp_col1, camp_col2 = st.columns(2)
    emails_per_day = camp_col1.slider("Số email/ngày", min_value=5, max_value=50, value=20, step=5)
    min_delay_min  = camp_col2.slider("Delay tối thiểu giữa email (phút)", 3, 30, 10)

    warn_col, btn_col = st.columns([4, 1])
    warn_col.warning(
        f"⚠️ Sẽ gửi tối đa **{emails_per_day} email hôm nay**. "
        f"Delay ngẫu nhiên {min_delay_min}–{min_delay_min*2} phút/email. "
        f"Tổng thời gian ≈ {emails_per_day * min_delay_min} phút."
    )
    run_campaign_btn = btn_col.button("▶️ Chạy ngay", type="primary", use_container_width=True)

    if run_campaign_btn:
        if not EMAIL_CONFIG.get("smtp_password"):
            st.error("❌ Chưa có App Password trong .env!")
        elif not pending_contacts:
            st.warning("Không có contact nào để gửi!")
        else:
            from campaign.email_sender import send_email
            from jinja2 import Template
            import random, time

            camp_file = TEMPLATES_DICT[camp_tpl_choice]["file"]
            camp_subj_fmt = TEMPLATES_DICT[camp_tpl_choice]["subject"]

            with open(camp_file, encoding="utf-8") as f:
                tpl_html = f.read()

            session = get_session()
            to_send  = pending_contacts[:emails_per_day]
            sent_ok  = 0
            progress_camp = st.progress(0)
            status_area   = st.empty()

            for idx, contact in enumerate(to_send):
                hotel = contact.hotel
                hotel_city = hotel.city or "Việt Nam"
                subject = camp_subj_fmt.format(hotel_name=hotel.name, city=hotel_city)
                body = Template(tpl_html).render(
                    hotel_name=hotel.name,
                    contact_name=contact.name or "",
                    city=hotel_city,
                    to_email=contact.email,
                    subject=subject,
                )

                status_area.info(f"📤 Đang gửi ({idx+1}/{len(to_send)}): {contact.email}")
                result = send_email(contact.email, contact.name or "", subject, body)

                log = EmailLog(
                    hotel_id=hotel.id,
                    contact_id=contact.id,
                    sequence_num=1,
                    subject=subject,
                    status="Đã gửi" if result["success"] else "Lỗi gửi",
                    sent_at=datetime.now() if result["success"] else None,
                    error_msg=result.get("error"),
                )
                session.add(log)
                session.commit()

                if result["success"]:
                    sent_ok += 1

                progress_camp.progress((idx + 1) / len(to_send))

                if idx < len(to_send) - 1:
                    delay = random.randint(min_delay_min * 60, min_delay_min * 2 * 60)
                    status_area.info(f"⏳ Chờ {delay//60} phút trước email tiếp theo...")
                    time.sleep(delay)

            session.close()
            st.success(f"🎉 Đã gửi thành công {sent_ok}/{len(to_send)} email!")


# ─────────────────────────────────────────────────────────────
# TAB: GIÁM SÁT 24/7 (SYSTEM MONITOR & UPTIME)
# ─────────────────────────────────────────────────────────────
with tab_logs:
    from scheduler.heartbeat_tracker import get_heartbeat_status
    hb = get_heartbeat_status()

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #121212 0%, #0d0d0d 100%);
                border: 1px solid #E50914; border-radius: 4px; padding: 22px 26px; margin-bottom: 20px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="font-size:10px;letter-spacing:3px;color:#E50914;text-transform:uppercase;font-weight:600;">
            TRUNG TÂM GIÁM SÁT HỆ THỐNG TOÀN DIỆN (SYSTEM UPTIME & 24/7/365 MONITOR)
          </div>
          <div style="font-family:'Montserrat',sans-serif;font-weight:700;font-size:26px;color:#FFFFFF;margin:4px 0 6px;">
            Giám Sát Hoạt Động & Tiến Trình Tự Động 24/7/365
          </div>
          <div style="font-size:12px;color:#999;max-width:750px;line-height:1.6;">
            Theo dõi minh bạch 100% thời gian thực: Máy chủ hoạt động 24/7, Tiến trình quét ngầm (mỗi 60 phút), Xác thực hộp thư sống, Lịch trình gửi email chiến dịch lúc <b>09:00 AM hàng ngày</b>, và Báo cáo Telegram.
          </div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;letter-spacing:1px;color:#4a7c59;text-transform:uppercase;font-weight:bold;">
            ● {hb.get('status', '🟢 DAEMON ACTIVE 24/7/365')}
          </div>
          <div style="font-size:11px;color:#888;margin-top:4px;">
            🕒 Cập nhật: <b style="color:#E50914;">{hb.get('last_heartbeat', 'Đang kết nối...')}</b>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    session_log = get_session()
    all_email_logs = (
        session_log.query(EmailLog)
        .options(joinedload(EmailLog.contact), joinedload(EmailLog.hotel))
        .order_by(EmailLog.sent_at.desc())
        .limit(200)
        .all()
    )
    all_scan_logs = session_log.query(ScanLog).order_by(ScanLog.scanned_at.desc()).limit(100).all()

    email_rows = []
    for l in all_email_logs:
        c = l.contact
        h = l.hotel
        email_rows.append({
            "Thời gian": l.sent_at.strftime("%d/%m/%Y %H:%M:%S") if l.sent_at else "—",
            "Khách sạn / Resort": h.name if h else "—",
            "Thành phố": h.city if h else "—",
            "Email nhận": c.email if c else "—",
            "Chức vụ": c.title if c else "—",
            "Tiêu đề email": l.subject or "—",
            "Trạng thái": l.status or "Đã gửi",
        })

    scan_rows = []
    for s in all_scan_logs:
        dur_str = f"{s.duration_s}s" if s.duration_s else "—"
        scan_rows.append({
            "Thời gian": s.scanned_at.strftime("%d/%m/%Y %H:%M:%S") if s.scanned_at else "—",
            "Thành phố": s.cities or "—",
            "Tìm thấy": s.total_found,
            "Mới lưu": s.new_saved,
            "Bị trùng": s.skipped,
            "Thời lượng": dur_str,
            "Kích hoạt": s.triggered_by or "Tự động 24/7",
        })

    session_log.close()

    # Thống kê tổng quan hệ thống 24/7
    log_c1, log_c2, log_c3, log_c4 = st.columns(4)
    log_c1.metric("TRẠNG THÁI SERVER", "🟢 ONLINE 24/7/365")
    log_c2.metric("LỊCH CRON TIẾP THEO", "09:00 AM Hàng Ngày")
    log_c3.metric("TỔNG EMAIL ĐÃ GỬI", f"{len(email_rows)} email")
    log_c4.metric("LƯỢT QUÉT NGẦM", f"{len(scan_rows)} chu kỳ")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Khối trạng thái tiến trình thời gian thực
    with st.expander("📡 TIẾN TRÌNH THỜI GIAN THỰC & NHẬT KÝ HOẠT ĐỘNG GẦN NHẤT", expanded=True):
        hb_col1, hb_col2 = st.columns([3, 1])
        with hb_col1:
            st.markdown(f"""
            **Nhiệm vụ đang thực hiện:** ⚙️ *{hb.get('current_task', 'Đang giám sát chu kỳ tự động 24/7 (mỗi 60 phút)...')}*  
            **Ghi nhận lần cuối:** `{hb.get('last_heartbeat', '—')}`
            """)
        with hb_col2:
            if st.button("🔄 Làm mới trạng thái", key="refresh_monitor_btn", use_container_width=True, help="Cập nhật trạng thái hệ thống ngầm ngay lập tức"):
                st.rerun()

        st.markdown("<div style='font-size:11px;color:#E50914;font-weight:bold;margin:8px 0 4px;'>📜 HOẠT ĐỘNG HỆ THỐNG GẦN ĐÂY (ACTIVITY STREAM):</div>", unsafe_allow_html=True)
        activities = hb.get("recent_activities", [])
        if activities:
            for act in activities[:10]:
                st.caption(f"• `{act}`")
        else:
            st.caption("• Hệ thống đang chạy giám sát 24/7, sẵn sàng cho chu kỳ tiếp theo...")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Danh sách các Tab con chi tiết
    log_sub1, log_sub2, log_sub3 = st.tabs([
        f"📬 Nhật Ký Gửi Email ({len(email_rows)})",
        f"🗺️ Lịch Sử Quét Khách Sạn ({len(scan_rows)})",
        "🖥️ Console & Live Stream Logs"
    ])

    with log_sub1:
        sync_c1, sync_c2 = st.columns([3, 1])
        with sync_c1:
            st.caption("Trạng thái được cập nhật trực tiếp theo thời gian thực từ SMTP, Webhook Theo Dõi Mở Thư, và Mailer-Daemon IMAP.")
        with sync_c2:
            sync_btn = st.button("🔄 Đồng Bộ Thư Bị Trả Về", help="Quét hộp thư Gmail để tự động phát hiện các thư bị lỗi 550 No Such User / Address not found")
            if sync_btn:
                from campaign.bounce_checker import sync_email_bounces
                b_res = sync_email_bounces(max_emails_to_check=50)
                if b_res.get("success"):
                    st.success(f"✅ Đã đồng bộ: Phát hiện {b_res.get('updated_logs', 0)} email bị trả về và cập nhật nhật ký!")
                    st.rerun()
                else:
                    st.error(f"⚠️ Lỗi đồng bộ: {b_res.get('error')}")

        if not email_rows:
            st.info("Chưa có nhật ký gửi email nào.")
        else:
            df_elog = pd.DataFrame(email_rows)
            st.dataframe(df_elog, use_container_width=True, height=450)

    with log_sub2:
        if not scan_rows:
            st.info("Chưa có lịch sử scan nào được ghi nhận.")
        else:
            df_slog = pd.DataFrame(scan_rows)
            st.dataframe(df_slog, use_container_width=True, height=400)

    with log_sub3:
        raw_log_content = ""
        for log_file in ["logs/email_daily.log", "logs/streamlit.log"]:
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        raw_log_content += f"=== {log_file} (Last 80 lines) ===\n" + "".join(lines[-80:]) + "\n\n"
                except Exception as e:
                    raw_log_content += f"Lỗi đọc {log_file}: {e}\n"

        if not raw_log_content:
            raw_log_content = "Hệ thống đang hoạt động bình thường, chưa có lỗi phát sinh."

        st.code(raw_log_content, language="bash")
        st.download_button(
            "📥 Tải toàn bộ file log (.txt)",
            data=raw_log_content,
            file_name=f"haphong_system_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )



# ── Footer ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:60px;padding:24px 0;border-top:1px solid #1e1e1e;text-align:center;">
  <div style="font-family:'Montserrat',sans-serif;font-weight:700;font-size:16px;letter-spacing:4px;
              color:#333;text-transform:uppercase;margin-bottom:8px;">
    HÀ PHONG VISUALS
  </div>
  <div style="font-size:9px;letter-spacing:2px;color:#444;text-transform:uppercase;">
    Hotel Scout v1.0 · Architectural & Hotel Photography · Đà Nẵng, Việt Nam
  </div>
  <div style="font-size:9px;letter-spacing:1px;color:#333;margin-top:6px;">
    <a href="https://haphong.com" target="_blank"
       style="color:#E50914;text-decoration:none;">haphong.com</a>
    &nbsp;·&nbsp; +84 383 305 909
    &nbsp;·&nbsp; sales@haphong.com
  </div>
</div>
""", unsafe_allow_html=True)
