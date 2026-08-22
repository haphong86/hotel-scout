"""
database/models.py — SQLAlchemy models cho Hotel Scout
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, Boolean, ForeignKey, Enum
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime, timezone, timedelta
import enum
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DATABASE_URL

Base = declarative_base()


class HotelStatus(enum.Enum):
    NEW        = "Mới tìm thấy"
    CONTACTED  = "Đã liên hệ"
    REPLIED    = "Đã reply"
    INTERESTED = "Quan tâm"
    CONVERTED  = "Chốt được"
    NOT_INTERESTED = "Không quan tâm"


class EmailStatus(enum.Enum):
    PENDING   = "Chờ gửi"
    SENT      = "Đã gửi"
    OPENED    = "Đã mở"
    CLICKED   = "Đã click"
    REPLIED   = "Đã reply"
    BOUNCED   = "Lỗi gửi"
    UNSUBSCRIBED = "Unsubscribe"


class Hotel(Base):
    __tablename__ = "hotels"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(255), nullable=False)
    name_en       = Column(String(255))
    city          = Column(String(100))
    province      = Column(String(100))
    address       = Column(Text)
    stars         = Column(Integer)            # Số sao (1-5)
    website       = Column(String(500))
    phone_main    = Column(String(50))         # Hotline chính
    google_maps_id= Column(String(200))        # Place ID từ Google Maps
    booking_id    = Column(String(200))        # ID trên Booking.com
    rating        = Column(Float)              # Điểm đánh giá
    review_count  = Column(Integer)
    opening_date  = Column(DateTime)           # Ngày khai trương
    source        = Column(String(100))        # Nguồn: google_maps/booking/news
    status        = Column(String(50), default=HotelStatus.NEW.value)
    notes         = Column(Text)
    created_at    = Column(DateTime, default=datetime.now)
    updated_at    = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    contacts      = relationship("Contact", back_populates="hotel", cascade="all, delete-orphan")
    email_logs    = relationship("EmailLog", back_populates="hotel")

    def __repr__(self):
        return f"<Hotel {self.name} ({self.city}) {self.stars}⭐>"


class Contact(Base):
    __tablename__ = "contacts"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    hotel_id      = Column(Integer, ForeignKey("hotels.id"), nullable=False)
    name          = Column(String(200))        # Tên người liên hệ
    title         = Column(String(200))        # Chức vụ
    email         = Column(String(300))        # Email cá nhân / công ty
    phone         = Column(String(50))         # SĐT cá nhân
    linkedin_url  = Column(String(500))
    confidence    = Column(Integer, default=50)  # Độ tin cậy 0-100
    is_primary    = Column(Boolean, default=False)  # Liên hệ chính
    source        = Column(String(100))        # Nguồn: website/hunter/linkedin
    is_valid      = Column(Boolean, default=True)
    verify_status = Column(String(20), default="UNVERIFIED")  # VALID/LIKELY/RISKY/INVALID
    created_at    = Column(DateTime, default=datetime.now)

    hotel         = relationship("Hotel", back_populates="contacts")
    email_logs    = relationship("EmailLog", back_populates="contact")

    def __repr__(self):
        return f"<Contact {self.name} ({self.title}) at Hotel {self.hotel_id}>"


class Campaign(Base):
    __tablename__ = "campaigns"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(200), nullable=False)
    description   = Column(Text)
    status        = Column(String(50), default="active")  # active/paused/completed
    emails_per_day= Column(Integer, default=20)
    regions       = Column(Text)               # JSON string danh sách khu vực
    min_stars     = Column(Integer, default=3)
    created_at    = Column(DateTime, default=datetime.now)

    email_logs    = relationship("EmailLog", back_populates="campaign")

    def __repr__(self):
        return f"<Campaign {self.name}>"


class EmailLog(Base):
    __tablename__ = "email_logs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    hotel_id      = Column(Integer, ForeignKey("hotels.id"))
    contact_id    = Column(Integer, ForeignKey("contacts.id"))
    campaign_id   = Column(Integer, ForeignKey("campaigns.id"), nullable=True)
    sequence_num  = Column(Integer, default=1)  # Email 1, 2, 3
    subject       = Column(String(500))
    body_preview  = Column(Text)               # 200 ký tự đầu
    status        = Column(String(50), default=EmailStatus.PENDING.value)
    sent_at       = Column(DateTime)
    opened_at     = Column(DateTime)
    clicked_at    = Column(DateTime)
    replied_at    = Column(DateTime)
    error_msg     = Column(Text)
    created_at    = Column(DateTime, default=datetime.now)

    hotel         = relationship("Hotel", back_populates="email_logs")
    contact       = relationship("Contact", back_populates="email_logs")
    campaign      = relationship("Campaign", back_populates="email_logs")


class ScanLog(Base):
    """Lịch sử mỗi lần quét — để hiển thị trên UI"""
    __tablename__ = "scan_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    cities      = Column(String(500))   # "Đà Nẵng, Hội An"
    source      = Column(String(100))   # openstreetmap / booking.com
    total_found = Column(Integer, default=0)
    new_saved   = Column(Integer, default=0)
    skipped     = Column(Integer, default=0)
    duration_s  = Column(Integer, default=0)  # Giây chạy
    triggered_by= Column(String(50), default="manual")  # manual / cron
    scanned_at  = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ScanLog {self.cities} +{self.new_saved} new>"


class PreOpeningProject(Base):
    """Radar phát hiện Khách sạn & Resort sắp khai trương trước 3-6 tháng"""
    __tablename__ = "pre_opening_projects"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(255), nullable=False)
    brand_chain    = Column(String(100))        # Marriott, Accor, Hilton, Fusion, Boutique...
    city           = Column(String(100), nullable=False)
    province       = Column(String(100))
    address        = Column(Text)
    est_opening    = Column(String(100))        # "Q4/2026", "Tháng 12/2026", "Cuối năm 2026"
    stage          = Column(String(100))        # "Hoàn thiện nội thất", "Pre-Opening Tuyển GM", "Sắp mở bán", "Cất nóc"
    priority       = Column(String(50), default="🔴 RẤT NÓNG - CẦN CHỤP NGAY")  # 🔴 RẤT NÓNG, 🟠 TIỀM NĂNG 3T, 🟡 TIỀM NĂNG 6T
    source         = Column(String(100))        # "Hoteljob Pre-Opening", "Booking Opening Soon", "Báo Xây Dựng", "LinkedIn"
    source_url     = Column(String(500))
    contact_name   = Column(String(200))        # GM / DOSM / Chủ Đầu Tư
    contact_role   = Column(String(200))
    contact_email  = Column(String(300))
    contact_phone  = Column(String(50))
    notes          = Column(Text)
    status         = Column(String(50), default="Chưa tiếp cận")  # "Chưa tiếp cận", "Đã gửi Email Launching", "Đang đàm phán", "Đã chốt hợp đồng"
    scanned_at     = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<PreOpeningProject {self.name} ({self.city}) - {self.est_opening}>"


from sqlalchemy import event

_engine = None
_SessionFactory = None

VN_TZ = timezone(timedelta(hours=7))


def get_now_vn() -> datetime:
    """Lấy thời gian chuẩn Việt Nam UTC+7"""
    return datetime.now(VN_TZ)


def init_db():
    """Khởi tạo database — tự động nhận diện PostgreSQL (Railway) hoặc SQLite (local)."""
    global _engine, _SessionFactory
    if _engine is not None:
        return _engine

    db_url = DATABASE_URL or ""

    # ── PostgreSQL (Railway production) ──────────────────────────
    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        # Railway dùng postgres:// nhưng SQLAlchemy cần postgresql://
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,       # Tự reconnect nếu connection bị drop
            pool_size=5,
            max_overflow=10,
            echo=False
        )
        print("🐘 Dùng PostgreSQL (Railway)")

    # ── SQLite (local / fallback) ─────────────────────────────────
    else:
        sqlite_path = db_url.replace("sqlite:///", "")
        if sqlite_path:
            os.makedirs(os.path.dirname(sqlite_path) or "database", exist_ok=True)
        _engine = create_engine(
            db_url,
            connect_args={"timeout": 60, "check_same_thread": False},
            echo=False
        )

        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.close()

        print("🗄️  Dùng SQLite (local)")

    Base.metadata.create_all(_engine)
    # autoflush=False: tránh lỗi "Query-invoked autoflush" khi session có pending changes
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False)
    return _engine



def get_session():
    """Trả về session kết nối database từ pool an toàn"""
    global _SessionFactory
    if _SessionFactory is None:
        init_db()
    return _SessionFactory()


def safe_commit(session, max_retries: int = 5, delay: float = 0.5) -> bool:
    """Commit an toàn tuyệt đối chống SQLite database is locked với cơ chế auto-retry"""
    import time
    for attempt in range(max_retries):
        try:
            session.commit()
            return True
        except Exception as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            session.rollback()
            raise e
    return False


if __name__ == "__main__":
    print("🗄️ Khởi tạo database với chế độ WAL...")
    init_db()
    print("✅ Database đã được tạo tại database/hotel_scout.db (WAL Mode: ACTIVE)")
