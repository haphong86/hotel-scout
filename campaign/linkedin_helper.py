"""
campaign/linkedin_helper.py — Hỗ trợ kết nối & soạn tin nhắn tiếp cận LinkedIn cho Lãnh đạo Khách sạn
"""
from urllib.parse import quote
from typing import Dict


def generate_linkedin_search_url(hotel_name: str, target_role: str = "General Manager") -> str:
    """Tạo link tìm kiếm chính xác profile LinkedIn của sếp KS"""
    query = f"{target_role} {hotel_name}"
    return f"https://www.linkedin.com/search/results/people/?keywords={quote(query)}"


def generate_linkedin_connect_note(hotel_name: str, role_or_name: str = "Anh/Chị", city: str = "Việt Nam") -> str:
    """
    Tạo tin nhắn kết nối LinkedIn (Note < 300 ký tự chuẩn LinkedIn)
    """
    note = (
        f"Chào {role_or_name}, em là Phong từ Hà Phong Visuals. "
        f"Xin chúc mừng dự án {hotel_name} tại {city}! "
        f"Em rất ấn tượng với kiến trúc của dự án và mong muốn được kết nối, chia sẻ một số góc chụp ảnh/video định vị cho khách sạn mình ạ."
    )
    if len(note) > 295:
        note = f"Chào {role_or_name}, em là Phong từ Hà Phong Visuals. Xin chúc mừng dự án {hotel_name}! Rất mong được kết nối và chia sẻ một số góc chụp kiến trúc định vị cho khách sạn mình ạ."
    return note


if __name__ == "__main__":
    print(generate_linkedin_search_url("Komorebi Retreat Da Lat", "General Manager"))
    print(generate_linkedin_connect_note("Komorebi Retreat", "GM", "Đà Lạt"))
