"""
scheduler/heartbeat_tracker.py — Theo dõi & ghi nhận hoạt động ngầm thời gian thực 24/7
Lưu TOÀN BỘ lịch sử vào file log riêng — không giới hạn số dòng.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List

os.environ["TZ"] = "Asia/Ho_Chi_Minh"
try:
    time.tzset()
except Exception:
    pass

VN_TZ = timezone(timedelta(hours=7))

def get_now_vn_str() -> str:
    return datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEARTBEAT_FILE = os.path.join(_BASE_DIR, "logs", "heartbeat.json")
ACTIVITY_LOG   = os.path.join(_BASE_DIR, "logs", "activity_full.log")  # Toàn bộ lịch sử


def log_activity(task_name: str, detail: str = ""):
    """Ghi nhận 1 hoạt động — lưu vào cả heartbeat (15 dòng) và full log (toàn bộ)"""
    os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
    now_str = get_now_vn_str()
    entry   = f"[{now_str}] {task_name}" + (f" — {detail}" if detail else "")

    # ── 1. Ghi vào full log (append — không bao giờ mất) ──────────────
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

    # ── 2. Cập nhật heartbeat.json (15 dòng gần nhất cho UI) ──────────
    data = get_heartbeat_status()
    data["last_heartbeat"] = now_str
    data["current_task"]   = task_name
    data["status"]         = "🟢 ĐANG CHẠY 24/7 (ACTIVE)"

    activities = data.get("recent_activities", [])
    activities.insert(0, entry)
    data["recent_activities"] = activities[:15]

    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_full_log(max_lines: int = 500) -> List[str]:
    """Đọc toàn bộ lịch sử hoạt động (mới nhất ở đầu)"""
    if not os.path.exists(ACTIVITY_LOG):
        return []
    try:
        with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Đảo ngược: mới nhất lên đầu
        return [l.rstrip() for l in reversed(lines) if l.strip()][:max_lines]
    except Exception:
        return []


def get_heartbeat_status() -> Dict:
    """Đọc trạng thái hiện tại"""
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "status": "🟢 ĐANG CHẠY 24/7 (ACTIVE)",
        "last_heartbeat": get_now_vn_str(),
        "current_task": "Đang giám sát và sẵn sàng quét chu kỳ tiếp theo",
        "recent_activities": [
            f"[{get_now_vn_str()}] 🚀 Hệ thống khởi động & kích hoạt tiến trình ngầm 24/7"
        ]
    }


if __name__ == "__main__":
    log_activity("🧪 Test", "Kiểm tra ghi log toàn bộ lịch sử")
    print(get_full_log(10))
