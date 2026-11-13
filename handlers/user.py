"""أوامر البداية والقائمة الرئيسية.

/start  -> للجميع: ترحيب + أزرار Inline بالشات (بدون أي ذكر للأدمن إطلاقًا).
للأدمن فقط: تُعرض لوحة الأدمن أيضًا بنفس أمر /start مباشرة بعد لوحة
           المستخدم. أمر /admin أُلغي نهائيًا.
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.security import is_admin

MAIN_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 الملخص", callback_data="main:summary"),
     InlineKeyboardButton("📋 السجل", callback_data="main:history")],
    [InlineKeyboardButton("📈 التقارير", callback_data="main:reports"),
     InlineKeyboardButton("💵 الرصيد", callback_data="main:balance")],
    [InlineKeyboardButton("📌 الالتزامات المالية", callback_data="cmt:main"),
     InlineKeyboardButton("🎯 أهداف الادخار", callback_data="main:savings")],
    [InlineKeyboardButton("📁 Excel", callback_data="main:excel"),
     InlineKeyboardButton("⚙️ الإعدادات", callback_data="main:settings")],
])

HOME_TEXT = "🏠 القائمة الرئيسية"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    # Check if new user
    _is_new = await db.get_user_by_telegram_id(tg_user.id) is None
    user = await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")
    # New user notification to admin (Taha)
    if _is_new:
        try:
            from database.db import get_conn
            async with get_conn() as _conn:
                _cur = await _conn.execute("SELECT COUNT(*) FROM users")
                _total = (await _cur.fetchone())[0]
            _uname = f"@{tg_user.username}" if tg_user.username else "بدون معرف"
            _fname = tg_user.first_name or ""
            if tg_user.last_name:
                _fname += f" {tg_user.last_name}"
            _lang = tg_user.language_code or "unknown"
            _notif = (
                "👾 شخص جديد دخل البوت\n"
                "\n"
                "👤 معلومات العضو الجديد:\n"
                f"• الاسم: {_fname}\n"
                f"• المعرف: {_uname}\n"
                f"• الآيدي: {tg_user.id}\n"
                f"• 🌐 اللغة: {_lang}\n"
                "\n"
                f"📊 إجمالي المستخدمين: {_total}"
            )
            await context.bot.send_message(chat_id=5149213983, text=_notif)
        except Exception:
            pass

    name = tg_user.first_name or tg_user.full_name or "صديقي"
    text = (
        f"👋 هلا {name}!\n"
        f"معرفك: {tg_user.id}\n\n"
        "أني «محفظة» — مساعدك الذكي لمتابعة مصاريفك ودخلك.\n"
        "اكتب أي مصروف أو دخل بلغة طبيعية وأني أفهمه وأسجله تلقائيًا.\n\n"
        "مثال: «250 ببسي» أو «استلمت راتب 750 الف»"
    )
    await update.message.reply_text(text, reply_markup=MAIN_MENU_KB)

    # لوحة الأدمن تظهر فقط للأدمن ضمن نفس أمر /start — ولا يُذكر وجودها
    # إطلاقًا لغير الأدمن.
    if is_admin(tg_user.id):
        from handlers.admin import show_admin_panel
        await show_admin_panel(update, context, user)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 كيف تستخدم محفظة:\n\n"
        "• لتسجيل مصروف أو دخل: بس اكتب المبلغ والشي، مثلًا «500 اكل» أو «راتب 750 الف»\n"
        "• للسؤال: «شكد صرفت اليوم؟» أو «شكد صرفت هذا الشهر؟»\n"
        "• لتعديل آخر عملية: «عدل آخر عملية وخليها 10000»\n"
        "• لحذف عملية: من 📋 السجل\n"
    )
    await update.message.reply_text(text)

