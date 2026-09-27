import re
from typing import Optional


PRICE_ERROR_FALLBACK = "AKShare 数据暂不可用，请稍后重试，或使用手动补录价格。"
PRICE_SEED_ERROR_FALLBACK = "初始化最近 {days} 个交易日行情失败：AKShare 数据暂不可用，请稍后重试，或先手动补录价格。"


TECHNICAL_ERROR_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"HTTPS?ConnectionPool",
        r"Max retries exceeded",
        r"ProxyError",
        r"RemoteDisconnected",
        r"Traceback",
        r"urllib3",
        r"requests",
        r"httpx",
        r"akshare response",
        r"host=.*port=",
        r"Caused by",
        r"SyntaxError",
        r"Unexpected token",
        r"<!doctype html>",
        r"<html",
        r"<anonymous>",
        r"/api/",
    ]
]


def sanitize_data_error_message(message: Optional[str]) -> Optional[str]:
    if not message:
        return message
    if not any(pattern.search(message) for pattern in TECHNICAL_ERROR_PATTERNS):
        return message
    match = re.search(r"初始化最近\s*(\d+)\s*个交易日", message)
    if match:
        return PRICE_SEED_ERROR_FALLBACK.format(days=match.group(1))
    return PRICE_ERROR_FALLBACK
