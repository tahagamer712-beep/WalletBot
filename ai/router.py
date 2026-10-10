"""
AI Router: يجرّب المزودات حسب الأولوية المخزّنة في قاعدة البيانات.
إذا فشل مزوّد (خطأ، timeout، حصة منتهية) ينتقل تلقائيًا للتالي.
إذا فشل الجميع يرجع None ليتولى Regex Parser المهمة (لا يوقف تسجيل العملية أبدًا).
"""
import asyncio
import logging

import database.db as db
from ai.providers import PROVIDER_CLASSES
from utils.security import decrypt_key

logger = logging.getLogger("ai.router")


async def parse_with_ai(text: str):
    ai_enabled = await db.get_setting("ai_enabled", "1")
    if ai_enabled != "1":
        return None, None

    providers = await db.list_providers(active_only=True)
    if not providers:
        return None, None

    for provider_row in providers:
        name = provider_row["name"]
        provider_class = PROVIDER_CLASSES.get(name)
        if not provider_class:
            continue

        key_row = await db.get_active_key_for_provider(name)
        if not key_row:
            continue

        try:
            raw_key = decrypt_key(key_row["encrypted_key"])
            provider = provider_class(raw_key)
            result = await asyncio.wait_for(provider.parse(text), timeout=15)
            return result, name
        except Exception as e:
            logger.warning("AI provider %s failed: %s", name, e)
            await db.add_ai_error_log(name, e, fell_back_to="next_provider_or_regex")
            continue

    return None, None
