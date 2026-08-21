"""
scheduler/heartbeat_tracker.py — Theo dõi & ghi nhận hoạt động ngầm thời gian thực 24/7
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, List

HEARTBEAT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "heartbeat.json")


def log_activity(task_name: str, detail: str = ""):
    """Ghi nhận 1 hoạt động thời gian thực của hệ thống ngầm"""
    os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    data = get_heartbeat_status()
    data["last_heartbeat"] = now_str
    data["current_task"] = task_name
    data["status"] = "🟢 ĐANG CHẠY 24/7 (ACTIVE)"
    
    # Lưu danh sách 15 hoạt động gần nhất
    activity_entry = f"[{now_str}] {task_name} {f'— {detail}' if detail else ''}"
    activities = data.get("recent_activities", [])
    activities.insert(0, activity_entry)
    data["recent_activities"] = activities[:15]

    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_heartbeat_status() -> Dict:
    """Đọc trạng thái hiện tại của hệ thống"""
    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "status": "🟢 ĐANG CHẠY 24/7 (ACTIVE)",
        "last_heartbeat": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "current_task": "Đang giám sát và sẵn sàng quét chu kỳ tiếp theo",
        "recent_activities": [
            f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] 🚀 Hệ thống khởi động & kích hoạt tiến trình ngầm 24/7"
        ]
    }


if __name__ == "__main__":
    log_activity("Kiểm tra máy chủ mail", "Đã scan 20 email của KS Đà Nẵng")
    print(get_heartbeat_status())
