"""واجهة الـ AI Parser المستخدمة من parser_engine. التفاصيل الفعلية في ai/router.py."""
from ai.router import parse_with_ai


async def try_ai(text: str):
    """يرجع (payload_dict_or_None, provider_name_or_None)."""
    return await parse_with_ai(text)
