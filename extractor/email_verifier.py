"""
extractor/email_verifier.py
Xác minh email 3 lớp — KHÔNG gửi email thật, không cần API key trả phí

Lớp 1: DNS MX Check   — domain có mail server không? (luôn hoạt động)
Lớp 2: Disify API     — API miễn phí, không cần đăng ký
Lớp 3: Pattern Score  — chấm điểm dựa trên pattern phổ biến của KS VN

Lý do bỏ SMTP port 25:
  → ISP Việt Nam (VNPT, Viettel, FPT) chặn port 25 outbound
  → Chỉ VPS/server mới dùng được — máy tính cá nhân không dùng được
"""
import re
import time
import httpx
from dataclasses import dataclass
from typing import Dict, Optional

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False

# ── Cache ────────────────────────────────────────────────────
_cache: Dict[str, "VerifyResult"] = {}
_mx_cache: Dict[str, Optional[str]] = {}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "mail.com", "protonmail.com",
    "ymail.com", "yahoo.com.vn",
}

STATUS_ICON = {
    "VALID":     "✅",
    "LIKELY":    "🟢",
    "CATCH_ALL": "🟡",
    "RISKY":     "⚠️",
    "NO_MX":     "❌",
    "INVALID":   "❌",
}

STATUS_LABEL = {
    "VALID":     "Xác nhận hoạt động",
    "LIKELY":    "Có thể hoạt động (domain OK)",
    "CATCH_ALL": "Domain nhận tất cả email",
    "RISKY":     "Không chắc chắn",
    "NO_MX":     "Domain không có mail server",
    "INVALID":   "Email không hợp lệ",
}


@dataclass
class VerifyResult:
    email:      str
    status:     str    # VALID / LIKELY / CATCH_ALL / RISKY / NO_MX / INVALID
    confidence: int    # 0-100
    reason:     str
    can_send:   bool = True
    is_free:    bool = False


# ═══════════════════════════════════════════════════════════════
# LỚP 1: DNS MX CHECK
# Hỏi: "Domain này có mail server không?"
# Luôn hoạt động, không bị block
# ═══════════════════════════════════════════════════════════════

def check_mx(domain: str) -> Optional[str]:
    """
    Kiểm tra NGHIÊM NGẶT máy chủ MX của domain bằng Cloudflare/Google DNS.
    Trả về tên mail server nếu domain có MX record hoạt động thật, None nếu không.
    """
    if not domain or "." not in domain:
        return None

    domain = domain.lower().strip()
    if domain in _mx_cache:
        return _mx_cache[domain]

    mx = None
    if HAS_DNS:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ["1.1.1.1", "8.8.8.8", "8.8.4.4"]  # Dùng DNS quốc tế siêu nhanh
        resolver.timeout = 3.0
        resolver.lifetime = 4.0

        try:
            records = resolver.resolve(domain, "MX")
            if records:
                sorted_records = sorted(records, key=lambda r: r.preference)
                mx = str(sorted_records[0].exchange).rstrip(".").lower()
        except Exception:
            mx = None
    else:
        import socket
        try:
            socket.getaddrinfo(domain, 25)
            mx = domain
        except Exception:
            mx = None

    _mx_cache[domain] = mx
    return mx


# ═══════════════════════════════════════════════════════════════
# LỚP 2: DISIFY API — Miễn phí, không cần key
# Kiểm tra: format, DNS, disposable email
# ═══════════════════════════════════════════════════════════════

def disify_check(email: str) -> dict:
    """
    Gọi Disify API miễn phí.
    https://www.disify.com — không cần API key, không cần đăng ký
    Trả về: {format, domain, dns, disposable, whitelist}
    """
    try:
        url = f"https://www.disify.com/api/email/{email}"
        resp = httpx.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


# ═══════════════════════════════════════════════════════════════
# LỚP 3: PATTERN SCORE
# Chấm điểm dựa trên pattern phổ biến của KS VN
# ═══════════════════════════════════════════════════════════════

# Pattern cao điểm = KS VN hay dùng
HIGH_CONFIDENCE_PATTERNS = [
    "marketing", "sales", "gm", "info", "reservation",
    "booking", "director", "manager", "contact", "pr",
]

def pattern_score(email: str) -> int:
    """Chấm điểm 0-100 dựa trên pattern email"""
    local = email.split("@")[0].lower()
    domain = email.split("@")[1].lower() if "@" in email else ""

    score = 40  # Base

    # +20: Email domain riêng (không phải gmail/yahoo)
    if domain and domain not in FREE_EMAIL_DOMAINS:
        score += 20

    # +20: Pattern phổ biến KS
    if any(p in local for p in HIGH_CONFIDENCE_PATTERNS):
        score += 20

    # +10: Format gọn (không quá dài)
    if len(local) <= 15:
        score += 10

    # -10: Pattern lạ (quá dài hoặc có số)
    if len(local) > 20 or re.search(r'\d{3,}', local):
        score -= 10

    return min(100, max(0, score))


# ═══════════════════════════════════════════════════════════════
# MAIN: Xác minh 1 email (3 lớp)
# ═══════════════════════════════════════════════════════════════

def check_smtp_mailbox_exists(email: str, mx_host: str) -> Optional[bool]:
    """
    Thực hiện SMTP Handshake kiểm tra hòm thư có thực sự tồn tại trên máy chủ không.
    Trả về:
      True: Server trả về 250 (Hòm thư tồn tại thật 100%)
      False: Server trả về 550 / 551 / 553 / User not found (Hòm thư không tồn tại -> LOẠI BỎ)
      None: Server từ chối probe hoặc timeout -> Giữ lại theo DNS
    """
    if not email or not mx_host:
        return None
    try:
        import smtplib
        server = smtplib.SMTP(timeout=3.0)
        server.connect(mx_host, 25)
        server.helo("haphong.com")
        server.mail("probe@haphong.com")
        code, msg = server.rcpt(email)
        try:
            server.quit()
        except Exception:
            pass
        if code == 250:
            return True
        elif code >= 500:
            return False
    except Exception:
        return None
    return None


# ═══════════════════════════════════════════════════════════════
# MAIN: Xác minh 1 email (4 lớp)
# ═══════════════════════════════════════════════════════════════

def verify_email(email: str) -> VerifyResult:
    """
    Xác minh email dùng 4 lớp:
    1. DNS MX — domain có nhận email không?
    2. SMTP Mailbox Probe — hòm thư có tồn tại thực sự trên server không?
    3. Disify API — kiểm tra disposable, format
    4. Pattern score — ưu tiên GM, DOSM, SM, Marketing, Sales
    """
    email = email.lower().strip()

    if email in _cache:
        return _cache[email]

    # ── Kiểm tra format ──────────────────────────────────────
    if not re.match(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$', email):
        r = VerifyResult(email, "INVALID", 0, "Sai format email", can_send=False)
        _cache[email] = r
        return r

    domain = email.split("@")[1]

    # ── Email cá nhân — không verify được nhưng vẫn gửi được ─
    if domain in FREE_EMAIL_DOMAINS:
        r = VerifyResult(
            email, "RISKY", 50,
            "Gmail/Yahoo cá nhân — không verify được, vẫn gửi được",
            is_free=True, can_send=True
        )
        _cache[email] = r
        return r

    # ── LỚP 1: DNS MX Check ──────────────────────────────────
    mx = check_mx(domain)
    if not mx:
        r = VerifyResult(
            email, "NO_MX", 0,
            f"Domain '{domain}' không có mail server — email sẽ bounce",
            can_send=False
        )
        _cache[email] = r
        return r

    # ── LỚP 2: SMTP Mailbox Probe (Bắt lỗi 550 No Such User) ──
    smtp_exists = check_smtp_mailbox_exists(email, mx)
    if smtp_exists is False:
        r = VerifyResult(
            email, "NO_USER", 0,
            f"Máy chủ {mx} báo lỗi 550: Hòm thư '{email}' không tồn tại",
            can_send=False
        )
        _cache[email] = r
        return r

    # ── LỚP 3: Disify API ────────────────────────────────────
    disify = disify_check(email)
    confidence = pattern_score(email)  # Base từ pattern theo thứ bậc quyết định

    if disify:
        fmt      = disify.get("format", True)
        dns_ok   = disify.get("dns", True)
        disposable = disify.get("disposable", False)

        if not fmt or not dns_ok or disposable:
            r = VerifyResult(email, "INVALID", 0, "Disify: không hợp lệ", can_send=False)
            _cache[email] = r
            return r

        confidence = min(100, confidence + 10)

    if smtp_exists is True:
        confidence = 100
        status = "VALID"
        reason = f"✅ Xác thực 100% (SMTP 250 OK) · MX: {mx}"
    else:
        status = "LIKELY"
        reason = f"DNS MX OK ({mx}) · Pattern Score: {confidence}"

    r = VerifyResult(email, status, confidence, reason, can_send=True)
    _cache[email] = r
    return r


# ═══════════════════════════════════════════════════════════════
# BATCH VERIFY
# ═══════════════════════════════════════════════════════════════

def verify_batch(emails: list, delay: float = 0.5) -> list:
    """Verify danh sách email, sắp xếp confidence cao → thấp"""
    results = []
    for email in emails:
        r = verify_email(email)
        results.append(r)
        time.sleep(delay)

    priority = {"VALID": 0, "LIKELY": 1, "CATCH_ALL": 2,
                "RISKY": 3, "NO_MX": 4, "INVALID": 5}
    results.sort(key=lambda x: (-x.confidence, priority.get(x.status, 9)))
    return results


def format_result(r: VerifyResult) -> str:
    icon  = STATUS_ICON.get(r.status, "?")
    label = STATUS_LABEL.get(r.status, r.status)
    return f"{icon} {r.email:<42} [{r.confidence:3d}%] {label}"
