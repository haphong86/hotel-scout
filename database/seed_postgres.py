"""
database/seed_postgres.py — Tự động seed data lên PostgreSQL lần đầu tiên.
Chạy khi Railway start nếu PostgreSQL trống.
"""
import os, json, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def seed_if_empty():
    """Chỉ seed khi PostgreSQL đang trống hoàn toàn."""
    db_url = os.getenv("DATABASE_URL", "")
    if not (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
        return  # Không chạy trên SQLite local

    from database.models import get_session, Hotel, Contact, EmailLog, init_db
    init_db()
    s = get_session()

    hotel_count = s.query(Hotel).count()
    if hotel_count > 0:
        print(f"✅ PostgreSQL đã có {hotel_count} hotels — bỏ qua seed.")
        s.close()
        return

    # Load seed file
    seed_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
    if not os.path.exists(seed_path):
        print("⚠️  Không tìm thấy seed_data.json")
        s.close()
        return

    print("🌱 PostgreSQL trống — đang seed data...")
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import datetime

    def parse_dt(v):
        if v and isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except Exception:
                return None
        return v

    # Seed Hotels
    hotel_count = 0
    for row in data.get("hotels", []):
        for k in ["created_at", "updated_at", "opening_date"]:
            if k in row:
                row[k] = parse_dt(row[k])
        exists = s.query(Hotel).filter_by(id=row["id"]).first()
        if not exists:
            s.add(Hotel(**row))
            hotel_count += 1
    s.commit()
    print(f"  ✅ Hotels: +{hotel_count}")

    # Seed Contacts
    contact_count = 0
    for row in data.get("contacts", []):
        for k in ["created_at"]:
            if k in row:
                row[k] = parse_dt(row[k])
        exists = s.query(Contact).filter_by(id=row["id"]).first()
        if not exists:
            s.add(Contact(**row))
            contact_count += 1
    s.commit()
    print(f"  ✅ Contacts: +{contact_count}")

    # Seed EmailLogs
    elog_count = 0
    for row in data.get("email_logs", []):
        for k in ["sent_at", "opened_at", "clicked_at", "replied_at", "created_at"]:
            if k in row:
                row[k] = parse_dt(row[k])
        exists = s.query(EmailLog).filter_by(id=row["id"]).first()
        if not exists:
            s.add(EmailLog(**row))
            elog_count += 1
    s.commit()
    print(f"  ✅ EmailLogs: +{elog_count}")

    s.close()
    print("🎉 Seed hoàn tất! PostgreSQL đã có đầy đủ data.")


if __name__ == "__main__":
    seed_if_empty()
