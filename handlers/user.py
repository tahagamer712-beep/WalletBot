"""أوامر البداية والقائمة الرئيسية.

/start  -> للجميع: ترحيب + أزرار Inline بالشات (بدون أي ذكر للأدمن إطلاقًا).
/admin  -> للأدمن فقط: صمت تام (بدون أي رد) لغير الأدمن، ولوحة الأدمن كأزرار
           Inline بالشات للأدمن.
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
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
    await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")

    # يزيل أي قائمة أزرار قديمة كانت مثبتة تحت الشات بنسخة سابقة من البوت.
    await update.message.reply_text("👋", reply_markup=ReplyKeyboardRemove())

    name = tg_user.first_name or tg_user.full_name or "صديقي"
    text = (
        f"👋 هلا {name}!\n"
        f"معرفك: {tg_user.id}\n\n"
        "أني محفظة، بوت العائلة لتسجيل المصاريف والدخل.\n"
        "بس اكتب مصروفك أو دخلك بشكل طبيعي وأني أفهمه وأسجله تلقائيًا.\n\n"
        "مثال: «250 ببسي» أو «استلمت راتب 750 الف»"
    )
    await update.message.reply_text(text, reply_markup=MAIN_MENU_KB)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 كيف تستخدم محفظة:\n\n"
        "• لتسجيل مصروف أو دخل: بس اكتب المبلغ والشي، مثلًا «500 اكل» أو «راتب 750 الف»\n"
        "• للسؤال: «شكد صرفت اليوم؟» أو «شكد صرفت هذا الشهر؟»\n"
        "• لتعديل آخر عملية: «عدل آخر عملية وخليها 10000»\n"
        "• لحذف عملية: من 📋 السجل\n"
    )
    await update.message.reply_text(text)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /admin — صمت تام (بدون أي رد) لغير الأدمن، حتى لا يُكشف وجود صلاحية أدمن أصلًا."""
    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        return

    user = await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")
    from handlers.admin import show_admin_panel
    await show_admin_panel(update, context, user)
