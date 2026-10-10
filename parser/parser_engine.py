"""
الترتيب الإجباري:
User Message -> AI Parser -> نجح؟ -> Validation -> SQLite
                    لا -> Regex Parser -> Validation -> SQLite
فشل AI أو انقطاعه لا يوقف تسجيل العملية أبدًا طالما Regex يستطيع الفهم.
"""
import database.db as db
from parser.ai_parser import try_ai
from parser.regex_parser import parse as regex_parse
from parser.validator import validate_payload, ValidationError


async def parse_message(text: str):
    exchange_rate = await db.get_exchange_rate()

    # 1) AI أولاً
    ai_payload, provider_name = await try_ai(text)
    if ai_payload is not None:
        try:
            valid_txs = validate_payload(ai_payload)
            if valid_txs:
                return {"transactions": valid_txs, "source": "ai", "ai_provider": provider_name}
        except ValidationError:
            pass  # ينتقل إلى Regex

    # 2) Regex كـ fallback
    regex_enabled = await db.get_setting("regex_fallback_enabled", "1")
    if regex_enabled == "1":
        regex_payload = regex_parse(text, exchange_rate)
        if regex_payload is None:
            return None  # لا علاقة له بالمال إطلاقًا
        if regex_payload.get("ambiguous"):
            return {"ambiguous": True}
        try:
            valid_txs = validate_payload(regex_payload)
            if valid_txs:
                return {"transactions": valid_txs, "source": "regex", "ai_provider": None}
        except ValidationError:
            return {"ambiguous": True}

    return None
