"""
app.py — Hotel Scout Dashboard (Streamlit)
Chạy: streamlit run app.py
"""
import streamlit as st
import pandas as pd
import json
import os
import sys
from datetime import datetime, timedelta

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(__file__))

from config import VIETNAM_REGIONS, APP_CONFIG, EMAIL_CONFIG
from database.models import init_db, get_session, Hotel, Contact, EmailLog, Campaign, ScanLog
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
            st.markdown(f'<p style="color:#c9a96e; text-align:center; margin-top:50px;">Đang chuyển hướng tới <a href="{dest_url}">{dest_url}</a>...</p>', unsafe_allow_html=True)
            st.stop()

# ── Cấu hình trang ──────────────────────────────────────────
st.set_page_config(
    page_title="Hà Phong Visuals · Hotel Scout",
    page_icon="📷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — Hà Phong Visuals Design System ────────────────────
# Palette: #0d0d0d bg · #c9a96e gold · #f0ebe3 cream · #1a1a1a dark
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Inter:wght@300;400;500&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
  font-family: 'Inter', sans-serif;
  background-color: #0d0d0d !important;
  color: #e8e0d0 !important;
}
.main .block-container {
  background: #0d0d0d !important;
  padding-top: 2rem;
  max-width: 1400px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: #080808 !important;
  border-right: 1px solid #2a2a2a !important;
}
[data-testid="stSidebar"] * { color: #b0a898 !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] .stSlider label {
  color: #c9a96e !important;
  font-size: 11px !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
}
[data-testid="stSidebar"] hr { border-color: #2a2a2a !important; }

/* ── Sidebar brand header ── */
.sidebar-brand {
  text-align: center;
  padding: 24px 16px 8px;
  border-bottom: 1px solid #2a2a2a;
  margin-bottom: 20px;
}
.sidebar-brand .brand-name {
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px;
  font-weight: 300;
  letter-spacing: 3px;
  color: #f0ebe3 !important;
  text-transform: uppercase;
}
.sidebar-brand .brand-sub {
  font-size: 9px;
  letter-spacing: 3px;
  color: #c9a96e !important;
  text-transform: uppercase;
  margin-top: 4px;
}

/* ── Page header ── */
.hp-header {
  border-bottom: 1px solid #2a2a2a;
  padding-bottom: 20px;
  margin-bottom: 28px;
  display: flex;
  align-items: flex-end;
  gap: 16px;
}
.hp-header .hp-logo-text {
  font-family: 'Cormorant Garamond', serif;
  font-size: 36px;
  font-weight: 300;
  letter-spacing: 4px;
  color: #f0ebe3;
  text-transform: uppercase;
  line-height: 1;
}
.hp-header .hp-gold { color: #c9a96e; }
.hp-header .hp-subtitle {
  font-size: 10px;
  letter-spacing: 2.5px;
  color: #666;
  text-transform: uppercase;
  margin-bottom: 4px;
}

/* ── Metric cards ── */
.hp-metric {
  background: #111 !important;
  border: 1px solid #2a2a2a;
  border-top: 2px solid #c9a96e;
  padding: 20px 16px 16px;
  border-radius: 2px;
  text-align: center;
}
.hp-metric .hp-m-num {
  font-family: 'Cormorant Garamond', serif;
  font-size: 40px;
  font-weight: 300;
  color: #f0ebe3;
  line-height: 1;
}
.hp-metric .hp-m-label {
  font-size: 9px;
  letter-spacing: 2px;
  color: #c9a96e;
  text-transform: uppercase;
  margin-top: 6px;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid #2a2a2a !important;
  gap: 0;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  color: #666 !important;
  font-size: 10px !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
  padding: 12px 24px !important;
  border-bottom: 2px solid transparent !important;
  font-family: 'Inter', sans-serif !important;
}
.stTabs [aria-selected="true"] {
  color: #c9a96e !important;
  border-bottom: 2px solid #c9a96e !important;
}

/* ── Section headings ── */
h1, h2, h3 {
  font-family: 'Cormorant Garamond', serif !important;
  font-weight: 300 !important;
  letter-spacing: 2px !important;
  color: #f0ebe3 !important;
}
h2 { font-size: 24px !important; }
h3 { font-size: 18px !important; color: #c9a96e !important; }

/* ── Buttons ── */
.stButton > button {
  background: transparent !important;
  border: 1px solid #c9a96e !important;
  color: #c9a96e !important;
  font-size: 10px !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
  padding: 10px 24px !important;
  border-radius: 1px !important;
  transition: all 0.3s !important;
}
.stButton > button:hover {
  background: #c9a96e !important;
  color: #0d0d0d !important;
}
.stButton > button[kind="primary"] {
  background: #c9a96e !important;
  color: #0d0d0d !important;
  border: none !important;
  font-weight: 500 !important;
}
.stButton > button[kind="primary"]:hover {
  background: #b8935a !important;
}

/* ── Info/warning boxes ── */
.stAlert {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
  border-left: 3px solid #c9a96e !important;
  border-radius: 1px !important;
  color: #b0a898 !important;
}
[data-testid="stNotification"] {
  background: #111 !important;
}

/* ── Dataframe / table ── */
[data-testid="stDataFrame"] {
  border: 1px solid #2a2a2a !important;
}
.stDataFrame thead th {
  background: #111 !important;
  color: #c9a96e !important;
  font-size: 10px !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
  border-bottom: 1px solid #2a2a2a !important;
}
.stDataFrame tbody tr { background: #0d0d0d !important; }
.stDataFrame tbody tr:hover { background: #141414 !important; }
.stDataFrame tbody td { color: #b0a898 !important; border-color: #1e1e1e !important; }

/* ── Form inputs ── */
.stTextInput input, .stSelectbox select, .stTextArea textarea {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
  color: #e8e0d0 !important;
  border-radius: 1px !important;
}
.stTextInput input:focus {
  border-color: #c9a96e !important;
  box-shadow: 0 0 0 1px #c9a96e33 !important;
}
.stMultiSelect [data-baseweb="select"] {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
}

/* ── Progress bar ── */
.stProgress > div > div {
  background: #c9a96e !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
  color: #c9a96e !important;
  font-size: 11px !important;
  letter-spacing: 1.5px !important;
}

/* ── Download button ── */
.stDownloadButton > button {
  background: transparent !important;
  border: 1px solid #2a2a2a !important;
  color: #666 !important;
  font-size: 10px !important;
  letter-spacing: 1.5px !important;
}
.stDownloadButton > button:hover {
  border-color: #c9a96e !important;
  color: #c9a96e !important;
}

/* ── Radio ── */
.stRadio label { color: #b0a898 !important; font-size: 13px !important; }
.stRadio [data-testid="stMarkdownContainer"] p { color: #b0a898 !important; }

/* ── Divider ── */
hr { border-color: #2a2a2a !important; }

/* ── Caption / small text ── */
.stCaption, small { color: #555 !important; font-size: 11px !important; }

/* ── Success/Error states ── */
.stSuccess { background: #0a1a0a !important; border-left-color: #4a7c59 !important; }
.stError   { background: #1a0a0a !important; border-left-color: #7c4a4a !important; }
.stWarning { background: #1a1400 !important; border-left-color: #c9a96e !important; }

/* ── Code blocks ── */
.stCode, code { background: #111 !important; color: #c9a96e !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0d0d0d; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #c9a96e; }

/* ── Signal priority badges ── */
.badge-hot    { color: #ff6b6b; font-weight: 600; letter-spacing: 1px; }
.badge-soon   { color: #c9a96e; font-weight: 600; letter-spacing: 1px; }
.badge-normal { color: #666;    font-weight: 400; letter-spacing: 1px; }

/* ── Metric row ── */
[data-testid="metric-container"] {
  background: #111 !important;
  border: 1px solid #2a2a2a !important;
  border-top: 2px solid #c9a96e !important;
  padding: 16px !important;
  border-radius: 2px !important;
}
[data-testid="metric-container"] label {
  color: #c9a96e !important;
  font-size: 9px !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'Cormorant Garamond', serif !important;
  font-size: 36px !important;
  color: #f0ebe3 !important;
  font-weight: 300 !important;
}
</style>
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


# ── SIDEBAR ─────────────────────────────────────────────────
with st.sidebar:
    # Brand header
    st.markdown("""
    <div class="sidebar-brand">
      <div class="brand-name">Hà Phong</div>
      <div style="font-size:10px;letter-spacing:2px;color:#c9a96e;margin-top:2px;">VISUALS</div>
      <div style="font-size:8px;letter-spacing:2px;color:#444;margin-top:8px;text-transform:uppercase;">Hotel Scout System</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#c9a96e;text-transform:uppercase;margin-bottom:8px;">KHU VỰC QUÉT</p>', unsafe_allow_html=True)
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
    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#c9a96e;text-transform:uppercase;margin-bottom:8px;">BỘ LỌC</p>', unsafe_allow_html=True)

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
    st.markdown('<p style="font-size:9px;letter-spacing:2.5px;color:#c9a96e;text-transform:uppercase;margin-bottom:8px;">TÀI KHOẢN EMAIL</p>', unsafe_allow_html=True)
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

# ── TABS ─────────────────────────────────────────────────────
tab_auto, tab1, tab2, tab3, tab4, tab_logs = st.tabs([
    "🚀 1-CLICK AUTOPILOT",
    "SCANNER",
    "CONTACTS",
    "EMAIL CAMPAIGN",
    "ANALYTICS",
    "📜 SYSTEM LOGS",
])


# ─────────────────────────────────────────────────────────────
# TAB 0: 1-CLICK AUTOPILOT
# ─────────────────────────────────────────────────────────────
with tab_auto:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #181510 0%, #0d0d0d 100%);
                border: 1px solid #c9a96e; border-radius: 4px; padding: 24px 28px; margin-bottom: 24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="font-size:10px;letter-spacing:3px;color:#c9a96e;text-transform:uppercase;font-weight:600;">
            HỆ THỐNG TỰ ĐỘNG HÓA TOÀN DIỆN
          </div>
          <div style="font-family:'Cormorant Garamond',serif;font-size:26px;color:#f0ebe3;margin:4px 0 6px;">
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
        <div style="background:#141414; border:1px solid #262626; border-left:3px solid #c9a96e;
                    padding:12px 16px; border-radius:3px;">
          <div style="font-size:9px; letter-spacing:2px; color:#c9a96e; text-transform:uppercase;">
            ĐỊA ĐIỂM QUÉT (ĐỒNG BỘ TỪ CỘT TRÁI)
          </div>
          <div style="font-size:13px; color:#f0ebe3; margin-top:4px; font-weight:500;">
            📍 {selected_region}
          </div>
          <div style="font-size:11px; color:#888; margin-top:2px;">
            {cities_display} ({len(target_cities)} thành phố)
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_cfg2:
        auto_email_limit = st.slider("Số email gửi trong lượt này:", min_value=5, max_value=30, value=20, step=5)
        auto_telegram = st.checkbox("Bắn báo cáo Telegram sau khi xong", value=True)

    with col_btn:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        start_autopilot_btn = st.button(
            "⚡ START AUTOPILOT",
            type="primary",
            use_container_width=True,
            help="Chạy toàn bộ quy trình: Quét -> Tìm Email -> Verify -> Gửi Chiến Dịch -> Báo Cáo Telegram"
        )

    # ── THỰC THI TOÀN BỘ QUY TRÌNH 1-CLICK ────────────────────
    if start_autopilot_btn:
        import time as _t
        start_time = _t.time()

        status_box = st.status("🚀 Đang khởi động quy trình Auto-Pilot...", expanded=True)
        log_box = st.empty()
        p_bar = st.progress(0.0)
        logs = []

        def add_log(msg):
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
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

        # ── GIAI ĐOẠN 3: GỬI CHIẾN DỊCH EMAIL ────────────────
        status_box.update(label="📨 Bước 3/4: Đang gửi email chính danh từ sales@haphong.com...")
        add_log("🚀 BẮT ĐẦU GIAI ĐOẠN 3: Gửi email chiến dịch...")

        from campaign.email_sender import send_email
        from extractor.free_email_finder import is_blacklisted_domain
        from jinja2 import Template

        session = get_session()
        raw_pending = (
            session.query(Contact)
            .join(Hotel)
            .filter(Contact.email.isnot(None), Contact.email != "", ~Contact.email_logs.any())
            .filter(Contact.verify_status.in_(["VALID", "LIKELY"]))
            .order_by(Contact.confidence.desc())
            .limit(auto_email_limit * 15)
            .all()
        )

        # BỘ LỌC ĐẶC CÁCH: GỬI THEO TỪNG KHÁCH SẠN (HOTEL-BY-HOTEL)
        # Khách sạn A: Gửi cho GM + DOSM + SM + Marketing + Sales của KS A
        # Sau đó mới chuyển sang Khách sạn B: Gửi GM + DOSM + Marketing của KS B
        GENERIC_DISALLOWED = {
            "info", "reservation", "reservations", "booking", "bookings",
            "contact", "reception", "letan", "stay", "hello", "frontdesk",
            "enquiry", "enquiries", "admin", "office", "fnb", "spa", "restaurant"
        }

        # Các domain chuỗi toàn cầu không có hộp thư ngắn hạn như gm@hilton.com
        CHAIN_GLOBAL_DOMAINS = {"hilton.com", "marriott.com", "hyatt.com", "ihg.com", "accor.com"}

        session = get_session()
        hotels_to_process = (
            session.query(Hotel)
            .filter(Hotel.contacts.any())
            .order_by(Hotel.rating.desc(), Hotel.review_count.desc())
            .all()
        )

        seen_emails = set()
        pending = []

        for h in hotels_to_process:
            # Lấy tất cả các email lãnh đạo chưa gửi của khách sạn này
            hotel_contacts = (
                session.query(Contact)
                .filter(Contact.hotel_id == h.id)
                .filter(Contact.email.isnot(None), Contact.email != "", ~Contact.email_logs.any())
                .order_by(Contact.confidence.desc())
                .all()
            )

            for c in hotel_contacts:
                c_email = c.email.lower().strip()
                if c_email in seen_emails:
                    continue

                prefix = c_email.split("@")[0].lower()
                if prefix in GENERIC_DISALLOWED:
                    continue

                dom = c_email.split("@")[-1].strip()
                if is_blacklisted_domain(dom) or (dom in CHAIN_GLOBAL_DOMAINS and len(prefix) <= 3):
                    continue

                seen_emails.add(c_email)
                pending.append(c)
                if len(pending) >= auto_email_limit:
                    break

            if len(pending) >= auto_email_limit:
                break

        sent_count = 0
        if not pending:
            add_log("  ℹ️ Không có khách sạn mới có email Giám đốc/Marketing hợp lệ cần gửi.")
        else:
            add_log(f"  📬 Sẵn sàng gửi {len(pending)} email tới {len(pending)} Giám Đốc / Marketing / Sales của các KS khác nhau...")
            # Nạp 2 mẫu template: Tiếng Việt (nội địa) & Tiếng Anh (quốc tế / chuỗi 4-5 sao)
            with open("campaign/templates/email_01_intro.html", "r", encoding="utf-8") as f:
                tpl_vi = f.read()
            with open("campaign/templates/email_en_01_intro.html", "r", encoding="utf-8") as f:
                tpl_en = f.read()

            intl_keywords = {
                "hyatt", "marriott", "hilton", "sheraton", "intercontinental", "novotel", "pullman",
                "radisson", "four seasons", "banyan tree", "melia", "wyndham", "anantara", "six senses",
                "renaissance", "mercure", "sofitel", "crowne plaza", "shangri-la", "jw marriott",
                "le meridien", "st. regis", "w hotel", "voco", "holiday inn", "fusion", "salinda",
                "almanity", "allegro", "belhamy", "nam an", "tia wellness", "la siesta", "premier village"
            }

            for idx, c in enumerate(pending):
                h = c.hotel
                h_city = h.city or "Việt Nam"
                c_dom = c.email.split("@")[-1].lower().strip()
                h_name_lower = h.name.lower()

                # BẢO VỆ 100%: Kiểm tra trực tiếp máy chủ Mail Server sống trước khi bấm gửi
                from extractor.email_verifier import check_mx
                mx_host = check_mx(c_dom)
                if not mx_host or is_blacklisted_domain(c_dom):
                    add_log(f"  ⏭️ Bỏ qua {c.email} (Không tìm thấy máy chủ mail hợp lệ)")
                    continue

                # Tự động phát hiện khách sạn Quốc tế / Quản lý nước ngoài
                is_intl = any(k in h_name_lower for k in intl_keywords) or (c_dom.endswith(".com") and not c_dom.endswith(".vn") and h.stars and h.stars >= 4)

                if is_intl:
                    subj = f"[{h.name}] — Elevating Architectural & Visual Identity in {h_city}"
                    body = Template(tpl_en).render(
                        hotel_name=h.name,
                        contact_name=c.name or "General Manager / Marketing Director",
                        city=h_city,
                        to_email=c.email,
                        subject=subj,
                    )
                    lang_tag = "🌐 EN"
                else:
                    subj = f"[{h.name}] — Giải pháp nâng cấp hình ảnh kiến trúc & visual khách sạn"
                    body = Template(tpl_vi).render(
                        hotel_name=h.name,
                        contact_name=c.name or c.title or "Anh/Chị",
                        city=h_city,
                        to_email=c.email,
                        subject=subj,
                    )
                    lang_tag = "🇻🇳 VI"

                # Tạo EmailLog trước để lấy ID phục vụ tracking tức thì
                elog = EmailLog(
                    hotel_id=h.id, contact_id=c.id, sequence_num=1,
                    subject=subj, status="Đang gửi", sent_at=datetime.now()
                )
                session.add(elog)
                session.flush()

                # Cấu hình đường link tracking theo domain Railway hoặc custom domain
                tracking_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "hotel-scout-production.up.railway.app")
                tracking_base = f"https://{tracking_domain}" if not tracking_domain.startswith("http") else tracking_domain

                # 1. Chèn tracking link khi khách bấm xem portfolio haphong.com
                click_tracked_url = f"{tracking_base}/?track=click&id={elog.id}&dest=https://haphong.com"
                body_with_links = body.replace('href="https://haphong.com"', f'href="{click_tracked_url}"')

                # 2. Chèn tracking pixel 1x1 ẩn ở cuối email
                pixel_tag = f'<img src="{tracking_base}/?track=open&id={elog.id}" width="1" height="1" style="display:none;" />'
                body_final = body_with_links.replace("</body>", f"{pixel_tag}</body>") if "</body>" in body_with_links else body_with_links + pixel_tag

                add_log(f"  📤 [{idx+1}/{len(pending)}] {lang_tag} Gửi → {c.email} ({h.name[:22]})...")
                res = send_email(c.email, c.name or "", subj, body_final)
                if res.get("success"):
                    sent_count += 1
                    elog.status = "Đã gửi"
                    h.status = "Đã liên hệ"
                    session.commit()
                else:
                    elog.status = "Thất bại"
                    elog.error_msg = res.get("message", "")
                    session.commit()
                _t.sleep(1.5)

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
# TAB 1: SCANNER
# ─────────────────────────────────────────────────────────────
with tab1:

    # ══════════════════════════════════════════════════════════
    # PHẦN A — ĐIỀU KHIỂN SCAN
    # ══════════════════════════════════════════════════════════
    st.markdown("""
    <p style="font-size:9px;letter-spacing:2.5px;color:#c9a96e;
              text-transform:uppercase;margin-bottom:12px;">
      QUÉT KHÁCH SẠN MỚI
    </p>""", unsafe_allow_html=True)

    # Thông tin scan hiện tại
    scan_col1, scan_col2 = st.columns([3, 1])
    with scan_col1:
        cities_str = " · ".join(selected_cities) if selected_cities else "Chưa chọn thành phố"
        st.markdown(f"""
        <div style="background:#111;border:1px solid #2a2a2a;border-left:3px solid #c9a96e;
                    padding:14px 18px;border-radius:2px;">
          <div style="font-size:9px;letter-spacing:2px;color:#555;text-transform:uppercase;
                      margin-bottom:8px;">CẤU HÌNH SCAN</div>
          <div style="display:flex;gap:32px;flex-wrap:wrap;">
            <div>
              <div style="font-size:9px;color:#666;letter-spacing:1px;text-transform:uppercase">
                Khu vực</div>
              <div style="color:#f0ebe3;font-size:13px;margin-top:2px">{selected_region}</div>
            </div>
            <div>
              <div style="font-size:9px;color:#666;letter-spacing:1px;text-transform:uppercase">
                Thành phố</div>
              <div style="color:#c9a96e;font-size:13px;margin-top:2px">{cities_str}</div>
            </div>
            <div>
              <div style="font-size:9px;color:#666;letter-spacing:1px;text-transform:uppercase">
                Nguồn quét</div>
              <div style="color:#f0ebe3;font-size:12px;margin-top:2px">
                🌐 Đa Kênh (OSM · Google Maps · Booking · Tuyển dụng)</div>
            </div>
            <div>
              <div style="font-size:9px;color:#666;letter-spacing:1px;text-transform:uppercase">
                Review tối đa</div>
              <div style="color:#f0ebe3;font-size:13px;margin-top:2px">≤ {filter_max_reviews}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with scan_col2:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        scan_btn = st.button(
            "🚀  QUÉT NGAY",
            type="primary",
            use_container_width=True,
            help="Quét KS mới từ OSM, Google Maps, Booking và Tin tuyển dụng"
        )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Chạy scan ────────────────────────────────────────────
    if scan_btn:
        if not selected_cities:
            st.warning("Vui lòng chọn ít nhất 1 thành phố!")
        else:
            import time as _time
            t_start   = _time.time()
            progress  = st.progress(0, text="Khởi động multi-source scanner...")
            log_area  = st.empty()
            logs      = []
            all_found = []
            total     = len(selected_cities)

            for i, city in enumerate(selected_cities):
                progress.progress(i / total, text=f"🔍 Đang quét đa kênh: {city}...")
                logs.append(f"▶ BẮT ĐẦU QUÉT: {city.upper()}")
                log_area.code("\n".join(logs[-20:]))
                city_hotels = []

                # Nguồn 1: OpenStreetMap
                try:
                    from scanner.overpass_scanner import scan_city_osm
                    osm = scan_city_osm(city, radius_km=20)
                    city_hotels.extend(osm)
                    logs.append(f"  ✅ [1/4] OpenStreetMap: Tìm thấy {len(osm)} cơ sở")
                except Exception as e:
                    logs.append(f"  ⚠️ OSM lỗi: {str(e)[:60]}")
                log_area.code("\n".join(logs[-20:]))

                # Nguồn 2: Google Maps & Google Search
                try:
                    from scanner.google_maps_scraper import search_google_maps
                    gmaps = search_google_maps(f"khách sạn mới {city}", city)
                    city_hotels.extend(gmaps)
                    logs.append(f"  ✅ [2/4] Google Maps & Search: Tìm thấy {len(gmaps)} KS")
                except Exception as e:
                    logs.append(f"  ⚠️ Google Maps lỗi: {str(e)[:60]}")
                log_area.code("\n".join(logs[-20:]))

                # Nguồn 3: Booking.com Opening Soon
                try:
                    from scanner.early_signals import scrape_booking_opening_soon
                    b_soon = scrape_booking_opening_soon(city)
                    city_hotels.extend(b_soon)
                    logs.append(f"  ✅ [3/4] Booking (Sắp mở/Mới mở): {len(b_soon)} lead nóng")
                except Exception as e:
                    logs.append(f"  ⚠️ Booking lỗi: {str(e)[:60]}")
                log_area.code("\n".join(logs[-20:]))

                # Nguồn 4: Tin tuyển dụng GM/MKT (Hoteljob, TopCV, VietnamWorks)
                try:
                    from scanner.early_signals import scrape_hotel_job_postings
                    jobs = scrape_hotel_job_postings(city)
                    city_hotels.extend(jobs)
                    logs.append(f"  ✅ [4/4] Tuyển dụng GM/MKT: {len(jobs)} tín hiệu")
                except Exception as e:
                    logs.append(f"  ⚠️ Tuyển dụng lỗi: {str(e)[:60]}")
                log_area.code("\n".join(logs[-20:]))

                all_found.extend(city_hotels)
                logs.append(f"  ↳ Tổng {city}: {len(city_hotels)} KS · Cộng dồn kho: {len(all_found)}\n")
                log_area.code("\n".join(logs[-20:]))

            progress.progress(1.0, text="✅ Hoàn tất!")

            # Lưu KS vào DB
            session = get_session()
            saved = skipped = 0
            for h in all_found:
                name = (h.get("name") or "").strip()
                city = (h.get("city") or "").strip()
                if not name:
                    continue
                existing = session.query(Hotel).filter(
                    Hotel.name == name, Hotel.city == city
                ).first()
                if not existing:
                    session.add(Hotel(
                        name=name, city=city,
                        address=h.get("address"),
                        website=h.get("website"),
                        phone_main=h.get("phone_main"),
                        rating=h.get("rating"),
                        review_count=h.get("review_count", 0),
                        google_maps_id=h.get("google_maps_id") or h.get("osm_id"),
                        source=h.get("source", "openstreetmap"),
                        status="Mới tìm thấy",
                    ))
                    saved += 1
                else:
                    skipped += 1

            # Lưu lịch sử scan
            duration = int(_time.time() - t_start)
            session.add(ScanLog(
                cities      = ", ".join(selected_cities),
                source      = "openstreetmap+booking",
                total_found = len(all_found),
                new_saved   = saved,
                skipped     = skipped,
                duration_s  = duration,
                triggered_by= "manual",
            ))
            session.commit()
            session.close()

            if saved > 0:
                st.success(
                    f"✅ **Scan hoàn tất** — Tìm thấy **{len(all_found)}** KS · "
                    f"Mới: **{saved}** · Trùng bỏ qua: **{skipped}** · "
                    f"Thời gian: **{duration}s**"
                )
            else:
                st.info(f"Tìm thấy {len(all_found)} KS nhưng tất cả đã có trong DB ({skipped} trùng).")
            st.rerun()

    # ══════════════════════════════════════════════════════════
    # PHẦN B — LỊCH SỬ SCAN
    # ══════════════════════════════════════════════════════════
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    _sess = get_session()
    _scanlogs = _sess.query(ScanLog).order_by(ScanLog.scanned_at.desc()).limit(20).all()
    _sess.close()

    with st.expander(
        f"📋  LỊCH SỬ SCAN  ({len(_scanlogs)} lần gần đây)",
        expanded=len(_scanlogs) > 0
    ):
        if not _scanlogs:
            st.caption("Chưa có lần scan nào. Nhấn QUÉT NGAY để bắt đầu!")
        else:
            rows = []
            for sl in _scanlogs:
                dt = sl.scanned_at
                rows.append({
                    "Thời gian":    dt.strftime("%d/%m/%Y %H:%M") if dt else "—",
                    "Thành phố":    sl.cities or "—",
                    "Tìm thấy":     sl.total_found or 0,
                    "Mới lưu":      sl.new_saved or 0,
                    "Trùng":        sl.skipped or 0,
                    "Thời lượng":   f"{sl.duration_s}s" if sl.duration_s else "—",
                    "Kích hoạt":    "⏰ Tự động" if sl.triggered_by == "cron" else "👤 Thủ công",
                })
            df_log = pd.DataFrame(rows)
            st.dataframe(
                df_log,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Mới lưu": st.column_config.NumberColumn(
                        "Mới lưu", help="KS mới thêm vào DB"
                    ),
                },
            )

            # Tổng cộng
            total_new  = sum(sl.new_saved or 0  for sl in _scanlogs)
            total_found= sum(sl.total_found or 0 for sl in _scanlogs)
            st.caption(
                f"Tổng {len(_scanlogs)} lần scan · "
                f"Đã tìm: {total_found} KS · "
                f"Đã lưu mới: {total_new} KS"
            )

    # ── Lead Score Dashboard ──────────────────────────────────
    from scoring import score_all_hotels, get_lead_summary
    import io

    session_s = get_session()
    from sqlalchemy import or_
    from sqlalchemy.orm import joinedload
    q = session_s.query(Hotel).options(joinedload(Hotel.contacts))
    if selected_cities:
        q = q.filter(Hotel.city.in_(selected_cities))
    all_hotels_raw = q.all()
    session_s.close()

    if not all_hotels_raw:
        st.info("Chưa có dữ liệu. Nhấn **QUÉT NGAY** để bắt đầu!")
    else:
        summary = get_lead_summary(all_hotels_raw)

        # ── Tổng quan phân loại ──────────────────────────────
        st.markdown("""
        <p style="font-size:9px;letter-spacing:2px;color:#c9a96e;
                  text-transform:uppercase;margin-bottom:12px;">
          PHÂN LOẠI TIỀM NĂNG
        </p>""", unsafe_allow_html=True)

        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("🔥 HOT LEADS",   len(summary["hot"]),
                   help="Score ≥ 70 — Ưu tiên liên hệ ngay!")
        lc2.metric("⭐ Tiềm năng",   len(summary["potential"]),
                   help="Score 50–69 — Đáng để gửi email")
        lc3.metric("👀 Theo dõi",    len(summary["watch"]),
                   help="Score 30–49 — Theo dõi thêm")
        lc4.metric("❄️ Thấp",        len(summary["low"]),
                   help="Score < 30 — Chưa đủ thông tin")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # ── Tabs phân loại ───────────────────────────────────
        hot_tab, all_tab, add_tab = st.tabs([
            f"🔥 HOT ({len(summary['hot'])})",
            f"📋 Tất cả ({len(all_hotels_raw)})",
            "➕ Thêm thủ công",
        ])

        def build_scored_df(scored_list: list, limit: int = 200) -> pd.DataFrame:
            rows = []
            for item in scored_list[:limit]:
                h = item["hotel"]
                rows.append({
                    "Score":        item["score"],
                    "Xếp loại":     item["grade"],
                    "Tên khách sạn": h.name,
                    "Thành phố":    h.city or "—",
                    "Website":      h.website or "—",
                    "Phone":        h.phone_main or "—",
                    "Lý do":        " · ".join(item["reasons"][:3]),
                    "Nguồn":        h.source or "—",
                    "Trạng thái":   h.status or "—",
                })
            return pd.DataFrame(rows)

        # ── HOT LEADS tab ────────────────────────────────────
        with hot_tab:
            if not summary["hot"]:
                st.info("Chưa có HOT LEAD nào. Thử scan thêm thành phố hoặc thu thập website/phone của các KS.")
            else:
                st.markdown(f"""
                <div style="background:#1a0f00;border:1px solid #c9a96e;border-left:3px solid #c9a96e;
                            padding:12px 16px;border-radius:2px;margin-bottom:16px;">
                  <span style="font-size:10px;letter-spacing:2px;color:#c9a96e;text-transform:uppercase;">
                    🔥 {len(summary["hot"])} HOT LEADS — Đây là những KS nên liên hệ NGAY
                  </span>
                </div>
                """, unsafe_allow_html=True)

                df_hot = build_scored_df(summary["hot"] + summary["potential"])
                st.dataframe(
                    df_hot,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Score": st.column_config.ProgressColumn(
                            "Score",
                            help="Điểm tiềm năng 0-100",
                            min_value=0,
                            max_value=100,
                            format="%d",
                        ),
                        "Website": st.column_config.LinkColumn("Website"),
                    },
                )

                # Export HOT leads
                buf_hot = io.BytesIO()
                df_hot.to_excel(buf_hot, index=False, engine="openpyxl")
                st.download_button(
                    "📥 Export HOT Leads",
                    data=buf_hot.getvalue(),
                    file_name=f"hot_leads_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )

        # ── TẤT CẢ tab ───────────────────────────────────────
        with all_tab:
            # Bộ lọc nhanh
            fc1, fc2 = st.columns([2, 3])
            sort_by = fc1.selectbox(
                "Sắp xếp",
                ["Score (cao → thấp)", "Tên A→Z", "Thành phố", "Nguồn"],
                label_visibility="collapsed",
            )
            search_kw = fc2.text_input(
                "Tìm kiếm",
                placeholder="Tìm tên KS...",
                label_visibility="collapsed",
            )

            all_scored = summary["hot"] + summary["potential"] + summary["watch"] + summary["low"]

            # Tìm kiếm
            if search_kw:
                all_scored = [
                    s for s in all_scored
                    if search_kw.lower() in s["hotel"].name.lower()
                ]

            df_all = build_scored_df(all_scored, limit=500)

            # Sắp xếp
            if "Score" in sort_by:
                df_all = df_all.sort_values("Score", ascending=False)
            elif "Tên" in sort_by:
                df_all = df_all.sort_values("Tên khách sạn")
            elif "Thành phố" in sort_by:
                df_all = df_all.sort_values("Thành phố")
            elif "Nguồn" in sort_by:
                df_all = df_all.sort_values("Nguồn")

            st.caption(f"Hiển thị {len(df_all)} khách sạn")
            st.dataframe(
                df_all,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn(
                        "Score",
                        help="Điểm tiềm năng 0-100",
                        min_value=0, max_value=100,
                        format="%d",
                    ),
                    "Website": st.column_config.LinkColumn("Website"),
                },
            )

            buf_all = io.BytesIO()
            df_all.to_excel(buf_all, index=False, engine="openpyxl")
            st.download_button(
                "📥 Export Excel",
                data=buf_all.getvalue(),
                file_name=f"hotels_scored_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        # ── THÊM THỦ CÔNG tab ────────────────────────────────
        with add_tab:
            with st.form("add_hotel_form"):
                c1, c2, c3 = st.columns(3)
                h_name    = c1.text_input("Tên khách sạn *")
                h_city    = c2.selectbox("Thành phố", options=available_cities)
                h_stars   = c3.selectbox("Số sao", [1, 2, 3, 4, 5], index=2)
                h_website = st.text_input("Website (https://...)")
                h_phone   = st.text_input("Hotline")

                if st.form_submit_button("Thêm", type="primary"):
                    if h_name:
                        session = get_session()
                        session.add(Hotel(
                            name=h_name, city=h_city, stars=h_stars,
                            website=h_website, phone_main=h_phone,
                            source="manual", status="Mới tìm thấy",
                        ))
                        session.commit()
                        session.close()
                        st.success(f"✅ Đã thêm: {h_name}")
                        st.rerun()
                    else:
                        st.error("Vui lòng nhập tên khách sạn!")


# ─────────────────────────────────────────────────────────────
# TAB 2: CONTACTS
# ─────────────────────────────────────────────────────────────
with tab2:
    st.markdown("## 📧 Contacts — Email & Phone")

    st.markdown("""
    <p style="font-size:9px;letter-spacing:2px;color:#c9a96e;text-transform:uppercase;">
      TÌM EMAIL LIÊN HỆ
    </p>""", unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns([3, 1, 1])
    with col_a:
        st.info(
            "🔍 **Full Pipeline**: Đoán 61 patterns → Verify DNS → Chỉ lưu email hoạt động\n\n"
            "⚡ **Quick Crawl**: Tìm email hiển thị trực tiếp trên website KS"
        )
    with col_b:
        pipeline_btn = st.button(
            "🔍 Full Pipeline",
            type="primary",
            use_container_width=True,
            help="Đoán 61 email patterns + verify từng email trước khi lưu"
        )
    with col_c:
        quick_btn = st.button(
            "⚡ Quick Crawl",
            use_container_width=True,
            help="Chỉ crawl website — nhanh hơn nhưng ít email hơn"
        )

    # ── FULL PIPELINE (Verify trước khi lưu) ─────────────────
    if pipeline_btn:
        from pipeline import run_pipeline
        from scoring import get_lead_summary
        from sqlalchemy.orm import joinedload

        # Xác định số KS xử lý
        lim_col1, lim_col2 = st.columns([2, 3])
        limit_n = lim_col1.number_input(
            "Số KS tối đa", min_value=5, max_value=100,
            value=20, step=5, label_visibility="visible",
            key="pipeline_limit",
        )

        st.markdown("---")
        st.markdown("#### 🔄 Pipeline đang chạy...")

        prog   = st.progress(0, text="Khởi động...")
        log_box = st.empty()
        logs   = []

        def append_log(msg: str):
            logs.append(msg)
            log_box.code("\n".join(logs[-30:]), language=None)

        def update_progress(pct: float, text: str):
            prog.progress(pct, text=text)

        result = run_pipeline(
            cities     = selected_cities if selected_cities else None,
            limit      = int(limit_n),
            log_fn     = append_log,
            progress_fn= update_progress,
        )

        prog.progress(1.0, text="✅ Hoàn tất!")
        st.success(
            f"🎉 **Pipeline hoàn tất!**  \n"
            f"KS xử lý: **{result['hotels_processed']}**  ·  "
            f"Email tìm: **{result['emails_found']}**  ·  "
            f"Email đã verify & lưu: **{result['emails_saved']}**  ·  "
            f"Bỏ qua: **{result['skipped']}**"
        )
        st.rerun()

    # ── QUICK CRAWL (chỉ website) ────────────────────────────
    elif quick_btn:

        from sqlalchemy.orm import joinedload
        from scoring import get_lead_summary

        # Lấy KS có website, chưa có contact — ưu tiên HOT leads
        session = get_session()
        hotels_with_web = (
            session.query(Hotel)
            .options(joinedload(Hotel.contacts))
            .filter(Hotel.website.isnot(None), Hotel.website != "")
            .filter(~Hotel.contacts.any())
            .all()
        )
        session.close()

        if not hotels_with_web:
            # Thử lấy cả KS không có website nhưng chưa có contact
            session = get_session()
            hotels_with_web = (
                session.query(Hotel)
                .filter(~Hotel.contacts.any())
                .limit(20).all()
            )
            session.close()

        if not hotels_with_web:
            st.warning("Tất cả KS đã có contact rồi!")
        else:
            # Sắp xếp theo Lead Score — HOT trước
            scored = get_lead_summary(hotels_with_web)
            priority_hotels = (
                [s["hotel"] for s in scored["hot"]] +
                [s["hotel"] for s in scored["potential"]] +
                [s["hotel"] for s in scored["watch"]]
            )[:20]  # Tối đa 20 KS/lần

            if not priority_hotels:
                priority_hotels = hotels_with_web[:20]

            st.info(
                f"📋 Sẽ tìm email cho **{len(priority_hotels)} KS** "
                f"(ưu tiên HOT → Tiềm năng)"
            )
            progress2 = st.progress(0, text="Bắt đầu...")
            log2 = st.empty()
            logs2 = []

            from extractor.free_email_finder import find_emails_free

            session  = get_session()
            total_new = 0

            for i, hotel in enumerate(priority_hotels):
                progress2.progress(
                    i / len(priority_hotels),
                    text=f"[{i+1}/{len(priority_hotels)}] {hotel.name[:40]}..."
                )

                emails = find_emails_free(
                    hotel_name=hotel.name,
                    website=hotel.website or "",
                    limit=5,
                )

                hotel_new = 0
                for e in emails:
                    if not e.get("email"):
                        continue
                    exists = session.query(Contact).filter(
                        Contact.hotel_id == hotel.id,
                        Contact.email    == e["email"],
                    ).first()
                    if not exists:
                        session.add(Contact(
                            hotel_id   = hotel.id,
                            email      = e["email"],
                            title      = e.get("title", ""),
                            confidence = e.get("confidence", 50),
                            source     = e.get("method", "free_finder"),
                        ))
                        hotel_new  += 1
                        total_new  += 1

                logs2.append(
                    f"{'✅' if hotel_new > 0 else '—'} "
                    f"{hotel.name[:35]} → {hotel_new} email mới"
                )
                log2.code("\n".join(logs2[-15:]))

            session.commit()
            session.close()
            progress2.progress(1.0, text="✅ Hoàn tất!")
            st.success(
                f"🎉 Tìm được **{total_new} email mới** "
                f"từ {len(priority_hotels)} KS — **100% miễn phí!**"
            )
            st.rerun()


    # ── GIAO DIỆN PHÂN LOẠI THEO TỪNG KHÁCH SẠN / RESORT ───
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    
    view_mode = st.radio(
        "Chế độ hiển thị danh bạ:",
        ["🏢 Phân loại theo từng Khách sạn / Resort", "📋 Bảng tổng hợp tất cả Contact"],
        horizontal=True
    )

    session = get_session()
    hotels_with_contacts = (
        session.query(Hotel)
        .options(joinedload(Hotel.contacts))
        .filter(Hotel.contacts.any())
        .order_by(Hotel.rating.desc(), Hotel.name)
        .all()
    )

    if view_mode == "🏢 Phân loại theo từng Khách sạn / Resort":
        # Bộ lọc tìm kiếm khách sạn
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        search_kw = col_f1.text_input("🔍 Tìm theo tên Khách sạn/Resort", placeholder="Nhập tên KS...")
        city_opts = sorted(list(set(h.city for h in hotels_with_contacts if h.city)))
        city_sel = col_f2.multiselect("📍 Lọc theo Thành phố", options=city_opts)
        status_sel = col_f3.selectbox("🛡️ Trạng thái Email", ["Tất cả", "Chỉ email Đã xác thực (VALID)", "Chưa scan"])

        # Lọc danh sách
        displayed_hotels = hotels_with_contacts
        if search_kw:
            displayed_hotels = [h for h in displayed_hotels if search_kw.lower() in h.name.lower()]
        if city_sel:
            displayed_hotels = [h for h in displayed_hotels if h.city in city_sel]

        st.markdown(f"**🏢 Hiển thị {len(displayed_hotels)} Khách sạn / Resort có liên hệ:**")

        for h in displayed_hotels[:40]:  # Phân trang hiển thị 40 KS mỗi lần
            contacts = h.contacts or []
            valid_count = sum(1 for c in contacts if c.verify_status == "VALID")
            
            with st.expander(f"🏨 {h.name.upper()}  ·  📍 {h.city or 'VN'}  ·  ⭐ {h.stars or 4}★  ({len(contacts)} Emails — {valid_count} Đã Verify)"):
                col_info1, col_info2 = st.columns([3, 1])
                with col_info1:
                    st.markdown(f"""
                    **Địa chỉ:** {h.address or 'Đang cập nhật'}  
                    **Website:** [{h.website or 'Chưa có website'}]({h.website if h.website and h.website.startswith('http') else 'https://' + (h.website or '')})  
                    **Hotline chính:** `{h.phone_main or '—'}`  ·  **Review:** {h.rating or '—'}⭐ ({h.review_count or 0} reviews)
                    """)
                
                with col_info2:
                    verify_single_btn = st.button(f"🔍 Scan Mail KS này", key=f"verify_h_{h.id}", help="Kiểm tra máy chủ mail và xác thực trạng thái sống của các email thuộc KS này")
                    if verify_single_btn:
                        from extractor.email_verifier import verify_email
                        v_count = 0
                        for c in contacts:
                            if c.email:
                                res = verify_email(c.email)
                                c.verify_status = res.status
                                c.confidence = res.confidence
                                if res.can_send:
                                    v_count += 1
                        session.commit()
                        st.success(f"✅ Đã scan {len(contacts)} email: {v_count} email hoạt động tốt!")
                        st.rerun()

                # Bảng chi tiết danh bạ các sếp của KS này
                contact_rows = []
                for c in contacts:
                    status_badge = "✅ VALID (Sống 100%)" if c.verify_status == "VALID" else ("⚠️ LIKELY" if c.verify_status == "LIKELY" else "❌ INVALID")
                    contact_rows.append({
                        "Chức danh / Vai trò": c.title or "—",
                        "Địa chỉ Email": c.email or "—",
                        "Số điện thoại": c.phone or h.phone_main or "—",
                        "Trạng thái Email": status_badge,
                        "Điểm ưu tiên": f"{c.confidence or 0}đ",
                    })
                if contact_rows:
                    st.table(contact_rows)

    else:
        # Chế độ xem bảng phẳng tổng hợp
        df_contacts = get_contacts_df()
        if df_contacts.empty:
            st.info("Chưa có contact trong kho.")
        else:
            fc1, fc2 = st.columns(2)
            city_filter = fc1.multiselect("Lọc thành phố", options=df_contacts["Thành phố"].unique().tolist())
            title_filter = fc2.text_input("Tìm chức vụ", placeholder="Marketing, GM, Sales...")

            filtered = df_contacts.copy()
            if city_filter:
                filtered = filtered[filtered["Thành phố"].isin(city_filter)]
            if title_filter:
                filtered = filtered[filtered["Chức vụ"].str.contains(title_filter, case=False, na=False)]

            st.markdown(f"**{len(filtered)}** contacts tìm thấy")
            st.dataframe(filtered.drop(columns=["ID"]), use_container_width=True, hide_index=True)

    session.close()

    # Thêm contact thủ công & Export
    st.markdown("---")
    col_exp1, col_exp2 = st.columns([1, 1])
    
    with col_exp1:
        with st.expander("➕ Thêm Contact Thủ Công"):
            session_h = get_session()
            hotel_list = session_h.query(Hotel).order_by(Hotel.name).all()
            hotel_map  = {f"{h.name} ({h.city})": h.id for h in hotel_list}
            session_h.close()

            with st.form("add_contact_form"):
                selected_hotel = st.selectbox("Khách sạn", options=list(hotel_map.keys()))
                cc1, cc2 = st.columns(2)
                c_name  = cc1.text_input("Tên người liên hệ")
                c_title = cc2.text_input("Chức vụ")
                cc3, cc4 = st.columns(2)
                c_email = cc3.text_input("Email *")
                c_phone = cc4.text_input("Số điện thoại")
                c_linkedin = st.text_input("LinkedIn URL")

                if st.form_submit_button("Thêm Contact", type="primary"):
                    if c_email:
                        session = get_session()
                        session.add(Contact(
                            hotel_id=hotel_map[selected_hotel],
                            name=c_name, title=c_title, email=c_email,
                            phone=c_phone, linkedin_url=c_linkedin,
                            source="manual", confidence=95, verify_status="LIKELY"
                        ))
                        session.commit()
                        session.close()
                        st.success(f"✅ Đã thêm: {c_email}")
                        st.rerun()
                    else:
                        st.error("Email là bắt buộc!")

    with col_exp2:
        df_contacts_all = get_contacts_df()
        if not df_contacts_all.empty:
            buf2 = io.BytesIO()
            df_contacts_all.to_excel(buf2, index=False, engine="openpyxl")
            st.download_button(
                "📥 Export Toàn Bộ Danh Bạ Ra Excel",
                data=buf2.getvalue(),
                file_name=f"danh_ba_khach_san_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )


# ─────────────────────────────────────────────────────────────
# TAB 3: EMAIL CAMPAIGN
# ─────────────────────────────────────────────────────────────
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
# TAB 4: ANALYTICS
# ─────────────────────────────────────────────────────────────
with tab4:
    st.markdown("## 📊 Analytics")
    import plotly.express as px
    import plotly.graph_objects as go

    session_a = get_session()

    # Phân bố theo thành phố
    hotels_by_city = {}
    for h in session_a.query(Hotel).all():
        hotels_by_city[h.city or "Unknown"] = hotels_by_city.get(h.city or "Unknown", 0) + 1

    # Phân bố theo trạng thái
    hotels_by_status = {}
    for h in session_a.query(Hotel).all():
        hotels_by_status[h.status or "Unknown"] = hotels_by_status.get(h.status or "Unknown", 0) + 1

    # Email logs timeline
    email_logs = session_a.query(EmailLog).filter(EmailLog.sent_at.isnot(None)).all()
    session_a.close()

    if not hotels_by_city:
        st.info("Chưa có dữ liệu. Hãy quét KS trước!")
    else:
        an1, an2 = st.columns(2)

        with an1:
            fig1 = px.bar(
                x=list(hotels_by_city.keys()),
                y=list(hotels_by_city.values()),
                title="KS theo thành phố",
                color=list(hotels_by_city.values()),
                color_continuous_scale="Oranges",
            )
            fig1.update_layout(showlegend=False, xaxis_title="", yaxis_title="Số KS")
            st.plotly_chart(fig1, use_container_width=True)

        with an2:
            fig2 = px.pie(
                names=list(hotels_by_status.keys()),
                values=list(hotels_by_status.values()),
                title="Trạng thái KS",
                color_discrete_sequence=px.colors.sequential.Oranges_r,
            )
            st.plotly_chart(fig2, use_container_width=True)

    if email_logs:
        df_logs = pd.DataFrame([{
            "Ngày": log.sent_at.date(),
            "Trạng thái": log.status,
        } for log in email_logs])

        daily = df_logs.groupby("Ngày").size().reset_index(name="Số email")
        fig3 = px.line(daily, x="Ngày", y="Số email", title="Email gửi theo ngày",
                       markers=True, line_shape="spline")
        fig3.update_traces(line_color="#c9a96e")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Chưa có lịch sử gửi email.")


# ─────────────────────────────────────────────────────────────
# TAB 5: SYSTEM LOGS
# ─────────────────────────────────────────────────────────────
with tab_logs:
    st.markdown("""
    <div style="background:#141414; border:1px solid #2a2a2a; border-left:3px solid #c9a96e; padding:16px 20px; border-radius:3px; margin-bottom:20px;">
      <div style="font-size:10px; letter-spacing:2.5px; color:#c9a96e; text-transform:uppercase; font-weight:600;">
        NHẬT KÝ VẬN HÀNH TOÀN HỆ THỐNG
      </div>
      <div style="font-size:13px; color:#aaa; margin-top:4px;">
        Theo dõi minh bạch 100% từng tiến trình: Quét khách sạn, Lọc verify email, Gửi chiến dịch và Thông báo Telegram.
      </div>
    </div>
    """, unsafe_allow_html=True)

    session_log = get_session()
    all_email_logs = (
        session_log.query(EmailLog)
        .options(joinedload(EmailLog.contact), joinedload(EmailLog.hotel))
        .order_by(EmailLog.sent_at.desc())
        .limit(150)
        .all()
    )
    all_scan_logs = session_log.query(ScanLog).order_by(ScanLog.scanned_at.desc()).limit(50).all()

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
            "Kích hoạt": s.triggered_by or "Thủ công",
        })

    session_log.close()

    # Thống kê nhanh
    log_c1, log_c2, log_c3, log_c4 = st.columns(4)
    log_c1.metric("TỔNG EMAIL ĐÃ GỬI", len(email_rows))
    log_c2.metric("LƯỢT SCAN ĐÃ CHẠY", len(scan_rows))
    log_c3.metric("TRẠNG THÁI SERVER", "🟢 ONLINE")
    log_c4.metric("CRON CHU KỲ", "09:00 AM Hàng Ngày")

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    log_sub1, log_sub2, log_sub3 = st.tabs([
        f"📬 Nhật Ký Gửi Email ({len(email_rows)})",
        f"🗺️ Lịch Sử Scan ({len(scan_rows)})",
        "🖥️ File Log Trực Tiếp (Live Stream)"
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
  <div style="font-family:'Cormorant Garamond',serif;font-size:16px;letter-spacing:4px;
              color:#333;text-transform:uppercase;margin-bottom:8px;">
    HÀ PHONG VISUALS
  </div>
  <div style="font-size:9px;letter-spacing:2px;color:#444;text-transform:uppercase;">
    Hotel Scout v1.0 · Architectural & Hotel Photography · Đà Nẵng, Việt Nam
  </div>
  <div style="font-size:9px;letter-spacing:1px;color:#333;margin-top:6px;">
    <a href="https://haphong.com" target="_blank"
       style="color:#c9a96e;text-decoration:none;">haphong.com</a>
    &nbsp;·&nbsp; +84 383 305 909
    &nbsp;·&nbsp; sales@haphong.com
  </div>
</div>
""", unsafe_allow_html=True)
