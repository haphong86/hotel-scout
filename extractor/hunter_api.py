"""
extractor/hunter_api.py — Tìm email bằng Hunter.io API
"""
import httpx
from typing import List, Dict
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import HUNTER_API_KEY, TARGET_JOB_TITLES


HUNTER_BASE = "https://api.hunter.io/v2"


def get_domain_from_url(url: str) -> str:
    """Trích domain từ URL: https://grandhotel.com → grandhotel.com"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    return domain.replace("www.", "").strip("/")


def hunt_by_domain(domain: str) -> List[Dict]:
    """
    Dùng Hunter.io Domain Search để tìm tất cả email của domain.
    Free plan: 25 request/tháng.
    """
    if not HUNTER_API_KEY:
        return []

    try:
        resp = httpx.get(
            f"{HUNTER_BASE}/domain-search",
            params={
                "domain": domain,
                "api_key": HUNTER_API_KEY,
                "limit": 10,
            },
            timeout=15,
        )
        data = resp.json()

        if data.get("errors"):
            print(f"    ⚠️ Hunter.io error: {data['errors']}")
            return []

        emails_found = []
        for email_data in data.get("data", {}).get("emails", []):
            title   = email_data.get("position", "")
            fname   = email_data.get("first_name", "")
            lname   = email_data.get("last_name", "")
            email   = email_data.get("value", "")
            conf    = email_data.get("confidence", 0)
            linkedin= email_data.get("linkedin", "")

            # Ưu tiên chức vụ liên quan đến hình ảnh/marketing
            is_target = any(
                t.lower() in title.lower()
                for t in TARGET_JOB_TITLES
            )

            emails_found.append({
                "name":         f"{fname} {lname}".strip(),
                "title":        title,
                "email":        email,
                "confidence":   conf,
                "linkedin_url": linkedin,
                "source":       "hunter.io",
                "is_target":    is_target,
            })

        # Sắp xếp: chức vụ liên quan lên đầu, sau đó theo confidence
        emails_found.sort(key=lambda x: (-x["is_target"], -x["confidence"]))
        return emails_found

    except Exception as e:
        print(f"    ❌ Hunter.io exception: {e}")
        return []


def verify_email(email: str) -> Dict:
    """
    Xác minh email còn hoạt động không.
    """
    if not HUNTER_API_KEY:
        return {"valid": True, "status": "unknown"}

    try:
        resp = httpx.get(
            f"{HUNTER_BASE}/email-verifier",
            params={"email": email, "api_key": HUNTER_API_KEY},
            timeout=15,
        )
        data = resp.json().get("data", {})
        return {
            "valid": data.get("result") in ["deliverable", "risky"],
            "status": data.get("result", "unknown"),
            "score": data.get("score", 0),
        }
    except Exception as e:
        return {"valid": True, "status": "unknown"}


def hunt_hotel(hotel_website: str) -> List[Dict]:
    """Tìm email cho 1 KS dựa vào website"""
    if not hotel_website:
        return []
    domain = get_domain_from_url(hotel_website)
    if not domain or '.' not in domain:
        return []
    print(f"    🎯 Hunter.io searching: {domain}")
    return hunt_by_domain(domain)
