"""نقطة تشغيل بوت «محفظة». تشغيل: python bot.py

لا نستخدم APScheduler (dependency إضافية غير ضرورية). الـ Auto Backup يعمل
عبر asyncio task بسيط يحسب الوقت المتبقي حتى الساعة المحددة وينام حتى ذلك
الوقت، بدون أي مكتبة خارجية.
"""
import asyncio
import logging
import datetime
from zoneinfo import ZoneInfo

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)

import config
import database.db as db
from database.migrations import run_migrations
from handlers.user import start, help_cmd
from handlers.messages import handle_text, handle_callback
from handlers.backup import handle_document
from backup.backup import auto_backup_job

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("wallet.bot")


async def _seed_default_providers():
    # يضيف المزودات المعروفة بأولوية افتراضية إن لم تكن موجودة، بدون تفعيلها بدون مفتاح فعلي.
    defaults = [("gemini", 1), ("groq", 2), ("openrouter", 3)]
    existing = {p["name"] for p in await db.list_providers()}
    for name, priority in defaults:
        if name not in existing:
            await db.upsert_provider(name, priority=priority, is_active=True)


async def _daily_backup_loop():
    """ينام حتى الساعة AUTO_BACKUP_HOUR كل يوم بتوقيت TIMEZONE، ثم يشغّل auto_backup_job()."""
    tz = ZoneInfo(config.TIMEZONE)
    while True:
        now = datetime.datetime.now(tz)
        target = now.replace(hour=config.AUTO_BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info("Auto backup scheduled in %.0f minutes.", wait_seconds / 60)
        await asyncio.sleep(wait_seconds)
        try:
            await auto_backup_job()
            logger.info("Auto backup finished.")
        except Exception:
            logger.exception("Auto backup failed.")


async def _post_init(application: Application):
    await db.init_db()
    await run_migrations()
    await _seed_default_providers()
    logger.info("Database initialized.")

    task = asyncio.create_task(_daily_backup_loop())
    application.bot_data["backup_task"] = task  # نحتفظ بمرجع لمنع garbage collection
    logger.info("Auto-backup loop started (daily at %02d:00 %s).",
                config.AUTO_BACKUP_HOUR, config.TIMEZONE)

    # قائمة أوامر البوت (زر Menu): /start فقط — أمر /admin أُلغي نهائيًا
    # ولوحة الأدمن تُعرض ضمن /start للأدمن فقط.
    await application.bot.set_my_commands([
        BotCommand("start", "القائمة الرئيسية 🏠"),
    ])
    logger.info("Bot commands menu updated.")


def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود في .env")
    if not config.ADMIN_ID:
        logger.warning("ADMIN_ID غير مضبوط — لن يكون هناك أدمن للبوت.")

    application = Application.builder().token(config.BOT_TOKEN).post_init(_post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot starting (polling)...")
    # Python 3.14 compat: PTB 21.x calls asyncio.get_event_loop() which raises
    # RuntimeError when no current loop exists in the main thread.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
