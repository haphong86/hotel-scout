"""
pipeline.py — Pipeline tự động hoàn chỉnh
Scan KS → Tìm domain → Đoán 61 email → Verify (DNS+Disify) → Lưu email sạch

Chỉ lưu email đã verify → KHÔNG bao giờ gửi vào địa chỉ không hoạt động
"""
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from typing import List, Dict, Callable, Optional, Tuple, Set
from sqlalchemy.orm import joinedload
from database.models import get_session, Hotel, Contact, init_db
from extractor.free_email_finder import (
    find_emails_free, guess_emails_by_pattern,
    get_domain_from_website, is_blacklisted_domain, EMAIL_PATTERNS_RANKED
)
from extractor.email_verifier import verify_email, check_mx, VerifyResult


# ═══════════════════════════════════════════════════════════════
# BƯỚC 1: Chọn KS cần xử lý
# ═══════════════════════════════════════════════════════════════

def get_hotels_to_process(
    cities: List[str] = None,
    limit: int = 50,
    only_without_contact: bool = True,
) -> List[Hotel]:
    """Lấy danh sách KS cần tìm email"""
    session = get_session()
    try:
        q = session.query(Hotel).options(joinedload(Hotel.contacts))

        if cities:
            q = q.filter(Hotel.city.in_(cities))

        if only_without_contact:
            q = q.filter(~Hotel.contacts.any())

        # Ưu tiên KS có website (dễ tìm email hơn)
        q = q.order_by(
            Hotel.website.desc(),
            Hotel.rating.desc(),
        )

        hotels = q.limit(limit).all()
        session.expunge_all()
        return hotels
    finally:
        session.close()


def generate_candidates(hotel: Hotel) -> List[Dict]:
    """
    Sinh danh sách email ứng viên cho 1 KS.
    Ưu tiên: crawl website → đoán pattern từ domain CHÍNH HÃNG (đã qua check MX) → google search
    """
    candidates = []

    # Có website → lấy domain và generate patterns
    if hotel.website:
        domain = get_domain_from_website(hotel.website)

        # Crawl website tìm email hiện trên trang (nếu không phải trang MXH)
        if domain and not is_blacklisted_domain(domain):
            try:
                from extractor.free_email_finder import crawl_website_emails
                found = crawl_website_emails(hotel.website)
                candidates.extend(found)
            except Exception:
                pass

            # BẮT BUỘC: Kiểm tra domain có mail server (MX) thực tế không mới đoán 61 pattern
            if check_mx(domain):
                patterns = guess_emails_by_pattern(domain)
                existing_emails = {c["email"] for c in candidates}
                for p in patterns:
                    if p["email"] not in existing_emails:
                        candidates.append(p)
    else:
        # Không có website → dùng Google search để tìm email thực tế
        try:
            from extractor.free_email_finder import google_search_email
            found = google_search_email(hotel.name)
            for f in found:
                f_dom = f.get("email", "").split("@")[-1].lower()
                if not is_blacklisted_domain(f_dom):
                    candidates.append(f)
        except Exception:
            pass

    # Lọc lại một lần nữa: tuyệt đối không chứa domain MXH hoặc rác
    clean_candidates = []
    for c in candidates:
        dom = c.get("email", "").split("@")[-1].lower()
        if not is_blacklisted_domain(dom):
            clean_candidates.append(c)

    # Sắp xếp theo confidence cao nhất trước
    clean_candidates.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return clean_candidates


# ═══════════════════════════════════════════════════════════════
# BƯỚC 3: Verify từng email
# ═══════════════════════════════════════════════════════════════

def verify_candidates(
    candidates: List[Dict],
    max_verify: int = 8,
    log_fn: Optional[Callable] = None,
) -> List[Dict]:
    """
    Verify từng email ứng viên.
    Dừng sớm khi đã có đủ email VALID/LIKELY.
    max_verify: số email tối đa kiểm tra (tiết kiệm thời gian)
    """
    verified = []
    valid_count = 0

    # Chỉ verify Tier 1 & 2 (confidence ≥ 60) trước
    priority = [c for c in candidates if c.get("confidence", 0) >= 60]
    fallback = [c for c in candidates if c.get("confidence", 0) < 60]

    for candidate in (priority + fallback)[:max_verify]:
        email = candidate.get("email", "")
        if not email:
            continue

        result: VerifyResult = verify_email(email)

        enriched = {
            **candidate,
            "verify_status":     result.status,
            "verify_confidence": result.confidence,
            "verify_reason":     result.reason,
            "can_send":          result.can_send,
        }
        verified.append(enriched)

        if log_fn:
            icon = {"VALID": "✅", "LIKELY": "🟢", "NO_MX": "❌",
                    "INVALID": "❌", "RISKY": "⚠️"}.get(result.status, "?")
            log_fn(f"  {icon} {email:<45} [{result.confidence}%] {result.status}")

        # Dừng sớm nếu đã có đủ email tốt (tiết kiệm API calls)
        if result.status in ("VALID", "LIKELY") and result.can_send:
            valid_count += 1
            if valid_count >= 3:  # Có 3 email tốt là đủ cho 1 KS
                break

        time.sleep(0.3)  # Tránh rate limit Disify

    # Sắp xếp: email tốt nhất trước
    verified.sort(
        key=lambda x: (
            0 if x["verify_status"] == "VALID" else
            1 if x["verify_status"] == "LIKELY" else
            2 if x["verify_status"] == "RISKY" else 3,
            -x.get("verify_confidence", 0)
        )
    )
    return verified


# ═══════════════════════════════════════════════════════════════
# BƯỚC 4: Lưu email đã verify vào DB
# ═══════════════════════════════════════════════════════════════

def save_verified_contacts(hotel_id: int, verified: List[Dict]) -> int:
    """
    Lưu email đã qua verify vào bảng Contact.
    Chỉ lưu email có can_send=True.
    Không lưu email trùng.
    Trả về số email mới lưu.
    """
    session = get_session()
    saved = 0
    try:
        for e in verified:
            if not e.get("can_send", False):
                continue  # Bỏ qua email INVALID/NO_MX

            email = e.get("email", "").strip().lower()
            if not email:
                continue

            # Không thêm trùng
            exists = session.query(Contact).filter(
                Contact.hotel_id == hotel_id,
                Contact.email    == email,
            ).first()

            if not exists:
                contact = Contact(
                    hotel_id      = hotel_id,
                    email         = email,
                    title         = e.get("title", ""),
                    confidence    = e.get("verify_confidence",
                                          e.get("confidence", 50)),
                    source        = e.get("method", "pipeline"),
                    verify_status = e.get("verify_status", "UNVERIFIED"),
                    is_valid      = e.get("can_send", True),
                )
                session.add(contact)
                saved += 1

        session.commit()
    finally:
        session.close()

    return saved


# ═══════════════════════════════════════════════════════════════
# PIPELINE CHÍNH — Chạy toàn bộ
# ═══════════════════════════════════════════════════════════════

def run_pipeline(
    cities: List[str] = None,
    limit: int = 20,
    log_fn: Optional[Callable] = None,
    progress_fn: Optional[Callable] = None,
) -> Dict:
    """
    Chạy toàn bộ pipeline:
    1. Lấy KS chưa có contact
    2. Generate email candidates
    3. Verify từng email
    4. Lưu email sạch vào DB

    Args:
        cities: Danh sách thành phố cần xử lý
        limit: Số KS tối đa mỗi lần chạy
        log_fn: Callback để in log (dùng trong Streamlit)
        progress_fn: Callback cập nhật progress bar

    Returns:
        {hotels_processed, emails_found, emails_saved, skipped}
    """
    def log(msg: str):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    hotels = get_hotels_to_process(cities=cities, limit=limit)

    if not hotels:
        log("⚠️ Không có KS nào cần xử lý!")
        return {"hotels_processed": 0, "emails_found": 0,
                "emails_saved": 0, "skipped": 0}

    log(f"📋 Bắt đầu pipeline: {len(hotels)} KS")
    log("─" * 60)

    total_found = 0
    total_saved = 0
    skipped     = 0

    for i, hotel in enumerate(hotels):
        pct = (i + 1) / len(hotels)
        if progress_fn:
            progress_fn(pct, f"[{i+1}/{len(hotels)}] {hotel.name[:45]}...")

        log(f"\n▶ [{i+1}/{len(hotels)}] {hotel.name} | {hotel.city}")
        log(f"  Website: {hotel.website or '(không có)'}")

        # Bước 2: Generate candidates
        candidates = generate_candidates(hotel)
        log(f"  → {len(candidates)} email ứng viên")

        if not candidates:
            log("  ⚪ Không tìm thấy ứng viên nào — bỏ qua")
            skipped += 1
            continue

        # Bước 3: Verify
        log("  🔍 Đang verify...")
        verified = verify_candidates(
            candidates, max_verify=8, log_fn=log
        )

        sendable = [v for v in verified if v.get("can_send")]
        total_found += len(verified)
        log(f"  → {len(sendable)}/{len(verified)} email có thể gửi")

        # Bước 4: Lưu
        if sendable:
            saved = save_verified_contacts(hotel.id, sendable)
            total_saved += saved
            log(f"  💾 Đã lưu {saved} email mới vào DB")
        else:
            log("  ⚪ Không có email nào pass verify")
            skipped += 1

        time.sleep(0.5)  # Nghỉ giữa các KS

    log("\n" + "═" * 60)
    log(f"✅ PIPELINE HOÀN TẤT")
    log(f"   KS xử lý:    {len(hotels)}")
    log(f"   Email tìm:   {total_found}")
    log(f"   Email lưu:   {total_saved} (đã verify)")
    log(f"   Bỏ qua:      {skipped}")
    log("═" * 60)

    return {
        "hotels_processed": len(hotels),
        "emails_found":     total_found,
        "emails_saved":     total_saved,
        "skipped":          skipped,
    }


# ═══════════════════════════════════════════════════════════════
# CLI: Chạy trực tiếp từ Terminal
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hotel Scout Email Pipeline")
    parser.add_argument("--cities", nargs="+", default=["Đà Nẵng"],
                        help="Danh sách thành phố")
    parser.add_argument("--limit", type=int, default=10,
                        help="Số KS tối đa")
    args = parser.parse_args()

    init_db()
    print(f"🚀 Chạy pipeline: {args.cities}, limit={args.limit}\n")
    result = run_pipeline(cities=args.cities, limit=args.limit)
    print(f"\n📊 Kết quả: {result}")
