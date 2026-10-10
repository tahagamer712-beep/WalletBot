"""⚙️ الإعدادات: سعر الصرف، تفعيل/تعطيل AI و Regex والنسخ التلقائي، وإدارة التصنيفات (أدمن فقط للتعديل)."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.security import is_admin
from utils.reply import send_reply, nav_render, back_row


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    rate = await db.get_exchange_rate()
    if not is_admin(update.effective_user.id):
        kb = InlineKeyboardMarkup([back_row("main:home")])
        await nav_render(update, context, f"💵 سعر الصرف الحالي: 1 USD = {rate:,.0f} IQD", reply_markup=kb)
        return

    ai_on = await db.get_setting("ai_enabled", "1") == "1"
    regex_on = await db.get_setting("regex_fallback_enabled", "1") == "1"
    backup_on = await db.get_setting("auto_backup_enabled", "1") == "1"
    keep = await db.get_setting("backup_keep_count", "7")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💵 سعر الصرف: {rate:,.0f}", callback_data="set:ask_rate")],
        [InlineKeyboardButton(f"🤖 AI: {'🟢 ON' if ai_on else '🔴 OFF'}", callback_data="set:toggle_ai")],
        [InlineKeyboardButton(f"🔄 Regex Fallback: {'🟢 ON' if regex_on else '🔴 OFF'}",
                               callback_data="set:toggle_regex")],
        [InlineKeyboardButton(f"💾 Auto Backup: {'🟢 ON' if backup_on else '🔴 OFF'}",
                               callback_data="set:toggle_backup")],
        [InlineKeyboardButton(f"📅 عدد نسخ Backup: {keep}", callback_data="set:ask_keep")],
        [InlineKeyboardButton("🏷️ إدارة التصنيفات", callback_data="set:cat_menu")],
        back_row("main:home"),
    ])
    await nav_render(update, context, "⚙️ الإعدادات", reply_markup=kb)


async def _show_categories(update, context):
    expense_cats = await db.list_categories("expense", active_only=False)
    income_cats = await db.list_categories("income", active_only=False)
    rows = []
    for c in expense_cats + income_cats:
        status = "🟢" if c["is_active"] else "🔴"
        rows.append([InlineKeyboardButton(f"{status} {c['name']} ({c['type']})",
                                           callback_data=f"set:cat_toggle:{c['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة تصنيف مصروف", callback_data="set:cat_add:expense")])
    rows.append([InlineKeyboardButton("➕ إضافة تصنيف دخل", callback_data="set:cat_add:income")])
    rows.append(back_row("main:settings"))
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🏷️ التصنيفات (اضغط للتفعيل/التعطيل):",
                                                    reply_markup=InlineKeyboardMarkup(rows))


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("للأدمن فقط.", show_alert=True)
        return

    parts = data.split(":")
    action = parts[1]

    if action == "ask_rate":
        context.user_data["pending"] = {"action": "settings:await_rate"}
        kb = InlineKeyboardMarkup([back_row("cancel:main:settings", "❌ إلغاء")])
        await query.message.reply_text("أرسل سعر الصرف الجديد (1 USD = ? IQD):", reply_markup=kb)
        await query.answer()
        return
    if action == "ask_keep":
        context.user_data["pending"] = {"action": "settings:await_keep"}
        kb = InlineKeyboardMarkup([back_row("cancel:main:settings", "❌ إلغاء")])
        await query.message.reply_text("أرسل عدد نسخ Backup المطلوب الاحتفاظ بها:", reply_markup=kb)
        await query.answer()
        return
    if action == "toggle_ai":
        cur = await db.get_setting("ai_enabled", "1")
        await db.set_setting("ai_enabled", "0" if cur == "1" else "1")
        await db.add_audit_log(user["telegram_id"], "toggle_ai_enabled")
        await show_settings_menu(update, context, user)  # nav_render يرد على الـ callback داخليًا
        return
    if action == "toggle_regex":
        cur = await db.get_setting("regex_fallback_enabled", "1")
        await db.set_setting("regex_fallback_enabled", "0" if cur == "1" else "1")
        await db.add_audit_log(user["telegram_id"], "toggle_regex_fallback")
        await show_settings_menu(update, context, user)
        return
    if action == "toggle_backup":
        cur = await db.get_setting("auto_backup_enabled", "1")
        await db.set_setting("auto_backup_enabled", "0" if cur == "1" else "1")
        await db.add_audit_log(user["telegram_id"], "toggle_auto_backup")
        await show_settings_menu(update, context, user)
        return
    if action == "cat_menu":
        await _show_categories(update, context)  # يرد على الـ callback داخليًا
        return
    if action == "cat_toggle":
        cat_id = int(parts[2])
        cats = await db.list_categories(active_only=False)
        target = next((c for c in cats if c["id"] == cat_id), None)
        if target:
            await db.set_category_active(cat_id, not target["is_active"])
        await _show_categories(update, context)
        return
    if action == "cat_add":
        cat_type = parts[2]
        context.user_data["pending"] = {"action": "settings:await_new_category", "type": cat_type}
        kb = InlineKeyboardMarkup([back_row("cancel:set:cat_menu", "❌ إلغاء")])
        await query.message.reply_text("أرسل اسم التصنيف الجديد:", reply_markup=kb)
        await query.answer()
        return
    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending["action"]
    if not is_admin(update.effective_user.id):
        context.user_data.pop("pending", None)
        return False

    if action == "settings:await_rate":
        try:
            rate = float(text.replace(",", "."))
            if rate <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مجددًا.")
            return True
        await db.set_setting("exchange_rate", rate)
        await db.add_audit_log(user["telegram_id"], "changed_exchange_rate", str(rate))
        await update.message.reply_text(f"✅ تم تحديث سعر الصرف إلى {rate:,.0f} IQD")
        context.user_data.pop("pending", None)
        return True

    if action == "settings:await_keep":
        try:
            keep = int(text)
            if keep <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مجددًا.")
            return True
        await db.set_setting("backup_keep_count", keep)
        await update.message.reply_text(f"✅ سيتم الاحتفاظ بآخر {keep} نسخة احتياطية.")
        context.user_data.pop("pending", None)
        return True

    if action == "settings:await_new_category":
        cat_type = pending["type"]
        await db.add_category(text.strip(), cat_type)
        kb = InlineKeyboardMarkup([back_row("set:cat_menu", "🔙 رجوع للتصنيفات")])
        await update.message.reply_text(f"✅ تمت إضافة التصنيف «{text.strip()}»", reply_markup=kb)
        context.user_data.pop("pending", None)
        return True

    return False
