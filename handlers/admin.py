"""🔐 لوحة الأدمن: المستخدمين، الإحصائيات، السجلات. كل عملية تتحقق من is_admin أولاً."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils import dates
from utils.security import is_admin
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from handlers import ai_admin, backup as backup_handler, settings as settings_handler

ADMIN_HOME_TEXT = "🔐 لوحة الأدمن"
ADMIN_HOME_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("👥 المستخدمين", callback_data="adm:users"),
     InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats")],
    [InlineKeyboardButton("🤖 الذكاء الاصطناعي", callback_data="adm:ai"),
     InlineKeyboardButton("💾 Backup", callback_data="adm:backup")],
    [InlineKeyboardButton("♻️ Restore", callback_data="adm:restore_info"),
     InlineKeyboardButton("🏷️ التصنيفات", callback_data="set:cat_menu")],
    [InlineKeyboardButton("💵 العملة", callback_data="set:ask_rate"),
     InlineKeyboardButton("📝 Logs", callback_data="adm:logs")],
    [InlineKeyboardButton("⚠️ Errors", callback_data="adm:errors"),
     InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="adm:settings")],
])


async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا القسم للأدمن فقط.")
        return
    await nav_render(update, context, ADMIN_HOME_TEXT, reply_markup=ADMIN_HOME_KB)


async def _users_list_kb():
    users = await db.list_users()
    rows = [[InlineKeyboardButton(f"👤 {u['name'] or u['username'] or u['telegram_id']}",
                                   callback_data=f"adm:user:{u['id']}")] for u in users]
    rows.append(back_row("adm:main"))
    return InlineKeyboardMarkup(rows)


async def _user_detail_text_kb(user_row):
    d_from, d_to = dates.current_month_range()
    income = await db.sum_by_type(user_row["id"], d_from, d_to, "income")
    expense = await db.sum_by_type(user_row["id"], d_from, d_to, "expense")
    txs = await db.list_transactions(user_row["id"], limit=1000)
    net = income["total_iqd"] - expense["total_iqd"]
    text = (
        f"👤 {user_row['name'] or user_row['username']}\n"
        f"💵 الدخل هذا الشهر:\n{fmt_iqd(income['total_iqd'])}\n"
        f"💸 المصروف هذا الشهر:\n{fmt_iqd(expense['total_iqd'])}\n"
        f"💰 الصافي:\n{fmt_iqd(net)}\n"
        f"📊 العمليات: {len(txs)}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 سجل العمليات", callback_data=f"adm:user_hist:{user_row['id']}:0"),
         InlineKeyboardButton("📊 التقرير الشهري", callback_data=f"adm:user_report:{user_row['id']}")],
        [InlineKeyboardButton("📁 Excel", callback_data=f"adm:user_excel:{user_row['id']}")],
        back_row("adm:users"),
    ])
    return text, kb


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "main":
        await query.answer()
        await query.edit_message_text(ADMIN_HOME_TEXT, reply_markup=ADMIN_HOME_KB)
        return

    if action == "users":
        kb = await _users_list_kb()
        await query.answer()
        await query.edit_message_text("👥 المستخدمين", reply_markup=kb)
        return

    if action == "user":
        target_id = int(parts[2])
        target = next((u for u in await db.list_users() if u["id"] == target_id), None)
        if not target:
            await query.answer("غير موجود.", show_alert=True)
            return
        await db.add_audit_log(user["telegram_id"], "admin_viewed_user_data", str(target_id))
        text, kb = await _user_detail_text_kb(target)
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if action == "user_hist":
        target_id = int(parts[2])
        offset = int(parts[3])
        txs = await db.list_transactions(target_id, limit=10, offset=offset)
        kb_rows = []
        if txs:
            lines = ["📋 سجل العمليات"]
            for tx in txs:
                lines.append(f"{dates.display_date(tx['transaction_date'])} — {tx['category']} — "
                              f"{tx['amount']:.0f} {tx['currency']}")
            if len(txs) == 10:
                kb_rows.append([InlineKeyboardButton(
                    "التالي ➡️", callback_data=f"adm:user_hist:{target_id}:{offset+10}")])
        else:
            lines = ["ماكو عمليات."]
        kb_rows.append(back_row(f"adm:user:{target_id}"))
        await query.answer()
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))
        return

    if action == "user_report":
        target_id = int(parts[2])
        from reports.monthly import build_monthly_report
        n = dates.now()
        rep = await build_monthly_report(target_id, n.year, n.month)
        text = (f"📊 تقرير {rep['label']}\nالدخل: {fmt_iqd(rep['income_iqd'])}\n"
                f"المصروف: {fmt_iqd(rep['expense_iqd'])}\nالصافي: {fmt_iqd(rep['net_iqd'])}")
        kb = InlineKeyboardMarkup([back_row(f"adm:user:{target_id}")])
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if action == "user_excel":
        target_id = int(parts[2])
        target = next((u for u in await db.list_users() if u["id"] == target_id), None)
        if not target:
            await query.answer("غير موجود.", show_alert=True)
            return
        label = target["name"] or target["username"] or str(target_id)
        await query.answer("جاري إنشاء الملف...")
        from handlers.excel import send_excel_for_user
        await send_excel_for_user(context, update.effective_chat.id, target_id, label)
        await db.add_audit_log(user["telegram_id"], "admin_exported_user_excel", str(target_id))
        return

    if action == "stats":
        users = await db.list_users()
        d_from, d_to = dates.current_month_range()
        total_income = total_expense = 0.0
        for u in users:
            inc = await db.sum_by_type(u["id"], d_from, d_to, "income")
            exp = await db.sum_by_type(u["id"], d_from, d_to, "expense")
            total_income += inc["total_iqd"]
            total_expense += exp["total_iqd"]
        text = (f"📊 إحصائيات عامة (هذا الشهر)\n👥 عدد المستخدمين: {len(users)}\n"
                f"💵 إجمالي الدخل: {fmt_iqd(total_income)}\n💸 إجمالي المصروف: {fmt_iqd(total_expense)}")
        kb = InlineKeyboardMarkup([back_row("adm:main")])
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
        return

    if action == "logs":
        logs = await db.list_audit_logs(limit=20)
        lines = ["📝 آخر العمليات الحساسة:"] + [
            f"{l['created_at'][:16]} — {l['action']} {l['details'] or ''}" for l in logs
        ]
        kb_rows = []
        if logs:
            kb_rows.append([InlineKeyboardButton("🗑️ مسح السجلات", callback_data="adm:logs_clear_confirm")])
        kb_rows.append(back_row("adm:main"))
        await query.answer()
        await query.edit_message_text("\n".join(lines) or "ماكو سجلات.", reply_markup=InlineKeyboardMarkup(kb_rows))
        return

    if action == "logs_clear_confirm":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، مسح الكل", callback_data="adm:logs_clear_do"),
            InlineKeyboardButton("↩️ تراجع", callback_data="adm:logs"),
        ]])
        await query.answer()
        await query.edit_message_text("⚠️ هل تريد مسح كل سجلات العمليات الحساسة؟", reply_markup=kb)
        return

    if action == "logs_clear_do":
        count = await db.clear_audit_logs()
        await db.add_audit_log(user["telegram_id"], "cleared_audit_logs", str(count))
        kb = InlineKeyboardMarkup([back_row("adm:main")])
        await query.answer()
        await query.edit_message_text(f"🗑️ تم مسح السجلات ({count}).", reply_markup=kb)
        return

    if action == "errors":
        errors = await db.list_ai_error_logs(limit=20)
        if not errors:
            text = "✅ ماكو أخطاء AI مسجلة."
        else:
            lines = ["⚠️ آخر أخطاء AI:"] + [
                f"{e['created_at'][:16]} — {e['provider_name']}: {e['error'][:60]}" for e in errors
            ]
            text = "\n".join(lines)
        kb_rows = []
        if errors:
            kb_rows.append([InlineKeyboardButton("🗑️ مسح السجلات", callback_data="adm:errors_clear_confirm")])
        kb_rows.append(back_row("adm:main"))
        await query.answer()
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))
        return

    if action == "errors_clear_confirm":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، مسح الكل", callback_data="adm:errors_clear_do"),
            InlineKeyboardButton("↩️ تراجع", callback_data="adm:errors"),
        ]])
        await query.answer()
        await query.edit_message_text("⚠️ هل تريد مسح كل سجلات أخطاء AI؟", reply_markup=kb)
        return

    if action == "errors_clear_do":
        count = await db.clear_ai_error_logs()
        kb = InlineKeyboardMarkup([back_row("adm:main")])
        await query.answer()
        await query.edit_message_text(f"🗑️ تم مسح السجلات ({count}).", reply_markup=kb)
        return

    if action == "settings":
        await settings_handler.show_settings_menu(update, context, user)  # nav_render يرد داخليًا
        return

    if action == "ai":
        await ai_admin.show_ai_menu(update, context, user)
        return

    if action.startswith("ai"):
        await ai_admin.handle_ai_callback(update, context, data, user)
        return

    if action == "backup":
        await backup_handler.show_backup_menu(update, context, user)
        return

    if action.startswith("backup"):
        await backup_handler.handle_backup_callback(update, context, data, user)
        return

    if action == "restore_info":
        kb = InlineKeyboardMarkup([back_row("adm:main")])
        await query.answer()
        await query.edit_message_text(
            "♻️ لاستعادة نسخة احتياطية: أرسل ملف .db مباشرة إلى المحادثة (كمستند).",
            reply_markup=kb,
        )
        return

    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending.get("action", "")
    if action.startswith("admin:ai:"):
        return await ai_admin.handle_pending_text(update, context, pending, text, user)
    return False
