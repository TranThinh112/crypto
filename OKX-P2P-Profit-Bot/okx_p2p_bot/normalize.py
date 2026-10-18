from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


def strip_accents(value: str) -> str:
    value = (value or "").replace("Đ", "D").replace("đ", "d")
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_side(value: str) -> str:
    text = strip_accents(value).lower()
    if re.search(r"\b(mua|mua)\b", text) or "mưa" in value.lower():
        return "Mua"
    if re.search(r"\b(ban|bán)\b", text):
        return "Bán"
    return ""


def normalize_status(value: str) -> str:
    text = strip_accents(value).lower()
    text = re.sub(r"\s+", " ", text)
    compact = re.sub(r"[^a-z0-9]", "", text)
    if re.search(r"\b(huy|cancel|cancelled|canceled)\b", text):
        return "Đã hủy"
    completed_patterns = [
        r"th[uuv]c\s*h[i1l]e[nm]",
        r"th[uuv]c.*h[i1l]e[nm]",
        r"da\s*th",
        r"d[a4]\s*th",
    ]
    if (
        "thuchien" in compact
        or "dathuchien" in compact
        or "dathuc" in compact
        or "dath" in compact
        or "hoantat" in compact
        or "completed" in text
        or "success" in text
        or any(re.search(pattern, text) for pattern in completed_patterns)
    ):
        return "Đã thực hiện"
    return ""


def parse_vietnam_number(value: object, decimal_hint: bool = False) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text or text in {"-", ".", ","}:
        return None

    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        text = text.replace(",", ".")
    elif has_dot and not decimal_hint:
        pieces = text.split(".")
        if len(pieces[-1]) == 3 and all(piece.isdigit() for piece in pieces):
            text = "".join(pieces)
    try:
        return float(text)
    except ValueError:
        return None


def parse_datetime(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    for fmt in ("%H:%M:%S %d/%m/%Y", "%H:%M %d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s+(\d{1,2}/\d{1,2}/\d{4})", text)
    if match:
        time_part = match.group(1)
        if time_part.count(":") == 1:
            time_part += ":00"
        return parse_datetime(f"{time_part} {match.group(2)}")
    return None
