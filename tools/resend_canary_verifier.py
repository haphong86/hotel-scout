"""
tools/resend_canary_verifier.py — HỆ THỐNG KIỂM THỬ BOUNCE TỰ ĐỘNG QUA RESEND API
"""
import os, sys, time, requests
from typing import Dict

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_API_URL = "https://api.resend.com/emails"

def verify_email_via_resend(target_email: str, sender_from: str = "onboarding@resend.dev") -> Dict:
    api_key = RESEND_API_KEY or os.getenv("RESEND_API_KEY", "")
    if not api_key:
        return {"valid": False, "status": "NO_API_KEY"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"from": sender_from, "to": [target_email], "subject": "Inquiry", "html": "<p>Testing</p>"}
    try:
        r = requests.post(RESEND_API_URL, headers=headers, json=payload, timeout=10)
        return {"valid": r.status_code == 200, "data": r.json()}
    except Exception as e:
        return {"valid": False, "error": str(e)}
