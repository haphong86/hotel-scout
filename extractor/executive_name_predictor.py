"""
extractor/executive_name_predictor.py — BỘ NÃO DỰ ĐOÁN EMAIL THEO TÊN RIÊNG CỦA LÃNH ĐẠO
1. Bóc tách HỌ TÊN của Ban Giám Đốc, DOSM, Marcom từ Web & Báo chí
2. Sinh 12 cấu trúc email Họ Tên phổ biến nhất tại các khách sạn quốc tế
"""
import re
import unicodedata
from typing import List, Dict, Set


def remove_vietnamese_accents(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    clean_text = ''.join([c for c in text if not unicodedata.combining(c)])
    clean_text = clean_text.replace('đ', 'd').replace('Đ', 'd')
    return clean_text.strip().lower()


def generate_named_email_patterns(full_name: str, domain: str) -> List[Dict]:
    if not full_name or not domain:
        return []

    clean_name = remove_vietnamese_accents(full_name)
    clean_name = re.sub(r'^(mr|ms|mrs|ong|ba)\.?\s+', '', clean_name, flags=re.IGNORECASE)
    parts = re.split(r'\s+', clean_name.strip())
    
    if len(parts) < 2:
        first_only = parts[0]
        return [{
            'email': f'{first_only}@{domain}'.lower(),
            'pattern_type': 'Tên đơn (first@)',
            'person_name': full_name
        }]

    first = parts[-1]
    last = parts[0]
    middle = parts[1:-1]
    mid_initials = ''.join(m[0] for m in middle) if middle else ''

    patterns = [
        (f'{first}.{last}@{domain}', 'Tên.Họ (first.last@) — Chuẩn Quốc Tế'),
        (f'{last}.{first}@{domain}', 'Họ.Tên (last.first@) — Chuẩn Việt Nam'),
        (f'{last[0]}{first}@{domain}', 'Viết tắt Họ + Tên (lfirst@)'),
        (f'{first}{last[0]}@{domain}', 'Tên + Viết tắt Họ (firstl@)'),
        (f'{first}.{last[0]}@{domain}', 'Tên.Viết tắt Họ (first.l@)'),
        (f'{last[0]}.{first}@{domain}', 'Viết tắt Họ.Tên (l.first@)'),
        (f'{first}_{last}@{domain}', 'Tên_Họ (first_last@)'),
        (f'{last}_{first}@{domain}', 'Họ_Tên (last_first@)'),
        (f'{first}{last}@{domain}', 'TênHọ viết liền (firstlast@)'),
        (f'{last}{first}@{domain}', 'HọTên viết liền (lastfirst@)'),
        (f'{first}@{domain}', 'Tên chính (first@)'),
    ]

    if middle:
        patterns.append((f'{first}.{last[0]}{mid_initials}@{domain}', 'Tên.HọĐệm viết tắt (first.lmid@)'))
        patterns.append((f'{last[0]}{mid_initials}{first}@{domain}', 'Viết tắt HọĐệm + Tên (lmidfirst@)'))

    seen = set()
    result = []
    for em, p_name in patterns:
        em_clean = em.lower().strip()
        if em_clean not in seen:
            seen.add(em_clean)
            result.append({
                'email': em_clean,
                'pattern_type': p_name,
                'person_name': full_name
            })

    return result
