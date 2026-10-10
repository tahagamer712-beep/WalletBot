"""المعالج الأساسي للرسائل النصية: تسجيل عمليات، استعلامات طبيعية، تعديل/حذف، وموجّه أزرار الـ Inline."""
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
import config
from parser.parser_engine import parse_message
from utils import dates, categories as cat_utils
from utils.currency import to_iqd, fmt_amount, fmt_iqd
from utils.security import is_admin
from utils.reply import nav_render, back_row
from handlers import (
    reports, excel as excel_handler, admin as admin_handler, settings as settings_handler,
    loans as loans_handler, installments as inst_handler, recurring as rec_handler,
    commitments as cmt_handler, savings as savings_handler,
)
from handlers.user import MAIN_MENU_KB, HOME_TEXT

# أزرار القائمة الرئيسية (main:*) — تُعرض فقط كأزرار Inline مرفقة برسالة /start،
# ولا تظهر فيها أي إشارة للأدمن إطلاقًا (لوحة الأدمن مخصصة حصرًا لأمر /admin).
MAIN_MENU_HANDLERS = {
    "summary": reports.show_today_summary,
    "reports": reports.show_reports_menu,
    "balance": reports.show_balance,
    "excel": excel_handler.show_excel_menu,
    "settings": settings_handler.show_settings_menu,
    "savings": savings_handler.show_savings_menu,
}

EDIT_LAST_RE = re.compile(r"(عدل|غير|صحح).*(اخر|آخر) عملية.*?(\d+(?:[.,]\d+)?)")
NON_FINANCE_REPLY = (
    "ما فهمت أنها عملية مالية 🤔\n"
    "حاول مثلًا: «500 اكل» أو «راتب 750 الف»"
)


HOME_KB = InlineKeyboardMarkup([back_row("main:home")])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    tg_user = update.effective_user
    user = await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")

    # 0) هل هناك إجراء معلّق ينتظر رد المستخدم؟ (تُدار من admin/settings handlers)
    pending = context.user_data.get("pending")
    if pending:
        handled = await _dispatch_pending(update, context, pending, text, user)
        if handled:
            return

    # 1) تعديل آخر عملية
    m = EDIT_LAST_RE.search(text)
    if m:
        await _edit_last_transaction(update, user, float(m.group(3).replace(",", ".")))
        return

    # 2) استعلامات طبيعية (شكد صرفت...)
    query_reply = await reports.try_natural_query(text, user)
    if query_reply:
        await update.message.reply_text(query_reply, reply_markup=HOME_KB)
        return

    # 3) تسجيل عملية عبر AI/Regex
    result = await parse_message(text)
    if result is None:
        await update.message.reply_text(NON_FINANCE_REPLY, reply_markup=HOME_KB)
        return
    if result.get("ambiguous"):
        await update.message.reply_text(
            "المبلغ أو التصنيف مو واضح تمامًا 🤔\nمثال: «50 دولار اكل»\nحاول تكتبها بشكل أوضح.",
            reply_markup=HOME_KB,
        )
        return

    await _register_transactions(update, user, result)


async def _register_transactions(update: Update, user: dict, result: dict):
    exchange_rate = await db.get_exchange_rate()
    now_date = dates.now_date_str()
    now_time = dates.now_time_str()
    saved = []
    for tx in result["transactions"]:
        amount_iqd = to_iqd(tx["amount"], tx["currency"], exchange_rate)
        tx_id = await db.insert_transaction(
            user_id=user["id"], type_=tx["type"], category=tx["category"], amount=tx["amount"],
            currency=tx["currency"], exchange_rate=exchange_rate, amount_iqd=amount_iqd,
            note=tx.get("note"), transaction_date=now_date, transaction_time=now_time,
            source=result["source"], ai_provider=result.get("ai_provider"),
        )
        saved.append((tx_id, tx, amount_iqd))

    # لو كانت العملية دخل براتب، طبّق استقطاعات كل الالتزامات النشطة (سلف/أقساط/متكررة) تلقائيًا.
    deduction_lines = []
    total_deducted_iqd = 0.0
    for tx_id, tx, amount_iqd in saved:
        if tx["type"] == "income" and tx["category"] == "راتب":
            deductions = await cmt_handler.apply_all_salary_deductions(user["id"], tx_id)
            for d in deductions:
                deduction_lines.append(f"💸 استقطاع {d['label']}: -{fmt_iqd(d['deducted'])}")
                total_deducted_iqd += d["deducted"]
                if d.get("status") == "completed":
                    deduction_lines.append(f"✅ تم تسديد {d['label']} بالكامل.")

    if len(saved) == 1:
        tx_id, tx, amount_iqd = saved[0]
        text = _confirmation_text(tx, amount_iqd, now_date, now_time)
        if deduction_lines:
            net = amount_iqd - total_deducted_iqd
            text += "\n" + "\n".join(deduction_lines)
            text += f"\n━━━━━━━━━━━━\n💵 الصافي: {fmt_iqd(net)}"
        await update.message.reply_text(text, reply_markup=HOME_KB)
    else:
        lines = ["✅ تم تسجيل عدة عمليات:\n"]
        total_iqd = 0
        for _, tx, amount_iqd in saved:
            icon = cat_utils.icon(tx["category"])
            lines.append(f"{icon} {tx['category']} — {fmt_amount(tx['amount'], tx['currency'])}")
            total_iqd += amount_iqd
        lines.append(f"\n💸 المجموع: {fmt_iqd(total_iqd)}")
        if deduction_lines:
            lines.extend(deduction_lines)
            lines.append(f"━━━━━━━━━━━━\n💵 الصافي: {fmt_iqd(total_iqd - total_deducted_iqd)}")
        lines.append(f"📅 {dates.display_date(now_date)}  🕐 {dates.display_time(now_time)}")
        await update.message.reply_text("\n".join(lines), reply_markup=HOME_KB)


def _confirmation_text(tx: dict, amount_iqd: float, date_str: str, time_str: str) -> str:
    icon = cat_utils.icon(tx["category"])
    kind = "المصروف" if tx["type"] == "expense" else "الدخل"
    lines = [f"✅ تم تسجيل {kind}", f"{icon} {tx['category']}", fmt_amount(tx["amount"], tx["currency"])]
    if tx["currency"] == "USD":
        lines.append(fmt_iqd(amount_iqd))
    lines.append(f"📅 {dates.display_date(date_str)}")
    lines.append(f"🕐 {dates.display_time(time_str)}")
    return "\n".join(lines)


async def _edit_last_transaction(update: Update, user: dict, new_amount: float):
    last = await db.get_last_transaction(user["id"])
    if not last:
        await update.message.reply_text("ماكو عمليات لتعديلها.", reply_markup=HOME_KB)
        return
    exchange_rate = last["exchange_rate"]
    new_amount_iqd = to_iqd(new_amount, last["currency"], exchange_rate)
    await db.update_transaction_amount(last["id"], user["id"], new_amount, new_amount_iqd)
    icon = cat_utils.icon(last["category"])
    await update.message.reply_text(
        f"✏️ تم تعديل آخر عملية\n{icon} {last['category']}\n"
        f"المبلغ الجديد: {fmt_amount(new_amount, last['currency'])}",
        reply_markup=HOME_KB,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """موجّه مركزي لكل أزرار الـ Inline. كل قسم يتعامل مع بادئة الـ callback_data الخاصة به."""
    query = update.callback_query
    data = query.data
    tg_user = update.effective_user
    user = await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")

    # حماية من مشكلة حقيقية: لو المستخدم بمنتصف تدفق سؤال (مثلًا "شكد مبلغ
    # السلفة؟") وضغط أي زر تنقّل آخر (رجوع، أو حتى زر قديم برسالة سابقة)
    # بدون هذا، تبقى حالة "pending" عالقة وتخرّب أول رسالة نصية عادية يكتبها
    # بعدين. نمسحها تلقائيًا على أي ضغطة زر إلا أزرار استمرار نفس التدفق تحديدًا.
    FLOW_CONTINUATION_PREFIXES = ("inst:autoded:", "rec:autoded:")
    if data.startswith("cancel:"):
        context.user_data.pop("pending", None)
        data = data.split(":", 1)[1]  # يتحول لزر تنقّل عادي بعد مسح الـ pending
    elif not data.startswith(FLOW_CONTINUATION_PREFIXES):
        context.user_data.pop("pending", None)

    if data.startswith("adm:"):
        if not is_admin(tg_user.id):
            await query.answer("غير مصرح.", show_alert=True)
            return
        await admin_handler.handle_admin_callback(update, context, data, user)
        return
    if data.startswith("main:"):
        await _handle_main_menu_callback(update, context, data, user)
        return
    if data.startswith("loan:"):
        await loans_handler.handle_loan_callback(update, context, data, user)
        return
    if data.startswith("inst:"):
        await inst_handler.handle_installment_callback(update, context, data, user)
        return
    if data.startswith("rec:"):
        await rec_handler.handle_recurring_callback(update, context, data, user)
        return
    if data.startswith("cmt:"):
        await cmt_handler.handle_commitments_callback(update, context, data, user)
        return
    if data.startswith("sav:"):
        await savings_handler.handle_savings_callback(update, context, data, user)
        return
    if data.startswith("rep:"):
        await reports.handle_reports_callback(update, context, data, user)
        return
    if data.startswith("xls:"):
        await excel_handler.handle_excel_callback(update, context, data, user)
        return
    if data.startswith("set:"):
        await settings_handler.handle_settings_callback(update, context, data, user)
        return
    if data.startswith("tx:"):
        await _handle_tx_callback(update, context, data, user)
        return
    await query.answer()


async def _handle_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    action = data.split(":")[1]
    if action == "home":
        await nav_render(update, context, HOME_TEXT, reply_markup=MAIN_MENU_KB)
        return
    if action == "history":
        await reports.handle_reports_callback(update, context, "rep:hist:0", user)
        return
    handler = MAIN_MENU_HANDLERS.get(action)
    if not handler:
        await update.callback_query.answer()
        return
    await handler(update, context, user)


async def _handle_tx_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]
    if action == "del_confirm":
        tx_id = int(parts[2])
        tx = await db.get_transaction(tx_id, user["id"])
        if not tx:
            await query.answer("العملية غير موجودة (ممكن تكون انحذفت مسبقًا).", show_alert=True)
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، احذفها", callback_data=f"tx:del_do:{tx_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data="tx:del_cancel"),
        ]])
        icon = cat_utils.icon(tx["category"])
        text = (
            "⚠️ تأكيد الحذف\n\n"
            f"{icon} {tx['category']} — {fmt_amount(tx['amount'], tx['currency'])}\n"
            f"📅 {dates.display_date(tx['transaction_date'])}  🕐 {dates.display_time(tx['transaction_time'])}\n"
            + (f"📝 {tx['note']}\n" if tx.get("note") else "")
            + "\nهل تريد حذف هذي العملية؟"
        )
        await query.edit_message_text(text, reply_markup=kb)
    elif action == "del_do":
        tx_id = int(parts[2])
        await db.soft_delete_transaction(tx_id, user["id"])
        kb = InlineKeyboardMarkup([back_row("main:history", "🔙 رجوع للسجل")])
        await query.edit_message_text("🗑️ تم حذف العملية.", reply_markup=kb)
    elif action == "del_cancel":
        kb = InlineKeyboardMarkup([back_row("main:history", "🔙 رجوع للسجل")])
        await query.edit_message_text("تم الإلغاء.", reply_markup=kb)
    await query.answer()


async def _dispatch_pending(update, context, pending, text, user) -> bool:
    action = pending.get("action")
    if action and action.startswith("admin:"):
        return await admin_handler.handle_pending_text(update, context, pending, text, user)
    if action and action.startswith("settings:"):
        return await settings_handler.handle_pending_text(update, context, pending, text, user)
    if action and action.startswith("loan:"):
        return await loans_handler.handle_pending_text(update, context, pending, text, user)
    if action and action.startswith("inst:"):
        return await inst_handler.handle_pending_text(update, context, pending, text, user)
    if action and action.startswith("rec:"):
        return await rec_handler.handle_pending_text(update, context, pending, text, user)
    if action and action.startswith("sav:"):
        return await savings_handler.handle_pending_text(update, context, pending, text, user)
    return False
