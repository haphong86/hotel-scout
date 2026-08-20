"""
database/models.py — SQLAlchemy models cho Hotel Scout
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Text, Boolean, ForeignKey, Enum
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
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


def init_db():
    """Khởi tạo database và tạo các bảng"""
    os.makedirs("database", exist_ok=True)
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session():
    """Trả về session kết nối database"""
    engine = init_db()
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    print("🗄️ Khởi tạo database...")
    init_db()
    print("✅ Database đã được tạo tại database/hotel_scout.db")
