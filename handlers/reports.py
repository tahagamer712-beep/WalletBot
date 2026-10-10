"""الملخص اليومي، الاستعلامات الطبيعية، سجل العمليات (Pagination)، الرصيد، التقارير الشهرية والمقارنات."""
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from reports.balance import wallet_balance, month_statement
from utils import dates, categories as cat_utils
from utils.currency import fmt_iqd, fmt_amount
from utils.reply import send_reply, nav_render, back_row

PAGE_SIZE = 8


# ---------------------------- ملخص اليوم ----------------------------

async def show_today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    d_from, d_to = dates.today_range()
    text = await _spend_breakdown_text(user["id"], d_from, d_to, "📅 مصاريف اليوم")
    kb = InlineKeyboardMarkup([back_row("main:home")])
    await nav_render(update, context, text, reply_markup=kb)


async def _spend_breakdown_text(user_id, d_from, d_to, title, type_="expense"):
    rows = await db.sum_by_category(user_id, d_from, d_to, type_)
    if not rows:
        return f"{title}\nماكو عمليات بهذي الفترة."
    lines = [title]
    total = 0
    for r in rows:
        icon = cat_utils.icon(r["category"])
        lines.append(f"{icon} {r['category']}: {r['total']:,.0f}")
        total += r["total"]
    label = "المجموع" if type_ == "expense" else "الإجمالي"
    lines.append(f"💸 {label}: {fmt_iqd(total)}")
    return "\n".join(lines)


# ---------------------------- استعلامات طبيعية ----------------------------

QUERY_TRIGGER = re.compile(r"شكد|كم صرفت|كم استلمت|شنو صرفت")


async def try_natural_query(text: str, user: dict):
    if not QUERY_TRIGGER.search(text):
        return None

    type_ = "income" if any(w in text for w in ["استلمت", "راتب", "دخل"]) else "expense"

    if "اليوم" in text:
        d_from, d_to = dates.today_range()
        period_label = "اليوم"
    elif "الشهر الماضي" in text or "الماضي" in text:
        d_from, d_to = dates.previous_month_range(1)
        period_label = "الشهر الماضي"
    elif "الشهر" in text or "هذا الشهر" in text:
        d_from, d_to = dates.current_month_range()
        period_label = "هذا الشهر"
    elif "السنة" in text or "هاي السنة" in text:
        d_from, d_to = dates.year_range()
        period_label = "هذه السنة"
    else:
        d_from, d_to = dates.current_month_range()
        period_label = "هذا الشهر"

    category = None
    for word, cat in _CATEGORY_HINTS.items():
        if word in text:
            category = cat
            break

    if category:
        rows = await db.transactions_in_range(user["id"], d_from, d_to, category=category, type_=type_)
        total = sum(r["amount_iqd"] for r in rows)
        icon = cat_utils.icon(category)
        return f"{icon} {category} ({period_label})\n💸 {fmt_iqd(total)}"

    title = f"📅 {'دخل' if type_=='income' else 'مصاريف'} {period_label}"
    return await _spend_breakdown_text(user["id"], d_from, d_to, title, type_)


_CATEGORY_HINTS = {
    "اكل": "أكل", "أكل": "أكل", "مواصلات": "مواصلات", "بنزين": "وقود", "وقود": "وقود",
    "تسوق": "تسوق", "ملابس": "تسوق", "أدوية": "أدوية", "فواتير": "فواتير",
    "اتصالات": "اتصالات", "ترفيه": "ترفيه", "تعليم": "تعليم", "راتب": "راتب",
}


# ---------------------------- سجل العمليات ----------------------------

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict, offset=0):
    txs = await db.list_transactions(user["id"], limit=PAGE_SIZE, offset=offset)
    if not txs:
        msg = "📋 ماكو عمليات بعد."
        kb = InlineKeyboardMarkup([back_row("main:home")])
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg, reply_markup=kb)
        else:
            await update.message.reply_text(msg, reply_markup=kb)
        return

    lines = ["📋 آخر العمليات"]
    kb_rows = []
    last_date = None
    for tx in txs:
        d = dates.display_date(tx["transaction_date"])
        t = dates.display_time(tx["transaction_time"])
        if d != last_date:
            lines.append(f"\n{d}")
            last_date = d
        icon = cat_utils.icon(tx["category"])
        lines.append(f"{icon} {tx['category']} — {fmt_amount(tx['amount'], tx['currency'])} — {t}")
        kb_rows.append([InlineKeyboardButton(
            f"🗑️ حذف {tx['category']} {tx['amount']:.0f} ({t})",
            callback_data=f"tx:del_confirm:{tx['id']}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"rep:hist:{max(0, offset-PAGE_SIZE)}"))
    if len(txs) == PAGE_SIZE:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"rep:hist:{offset+PAGE_SIZE}"))
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton("🗑️ مسح كل السجل", callback_data="rep:clear_confirm")])
    kb_rows.append(back_row("main:home"))

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


# ---------------------------- الرصيد ----------------------------

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    bal = await wallet_balance(user["id"])
    n = dates.now()
    stmt = await month_statement(user["id"], n.year, n.month)
    text = (
        "💰 الرصيد الحالي للمحفظة (تراكمي)\n"
        f"💵 الدخل الكلي: {bal['income_iqd']:,.0f} د.ع\n"
        f"💸 المصروف الكلي: {bal['expense_iqd']:,.0f} د.ع\n"
        f"✅ الرصيد: {bal['net_iqd']:,.0f} د.ع\n"
        "─────────────\n"
        f"📊 ملخص {stmt['label']}\n"
        f"🔄 المرحّل من الشهر السابق: {stmt['opening_iqd']:,.0f} د.ع\n"
        f"💵 دخل الشهر: {stmt['income_iqd']:,.0f} د.ع\n"
        f"💸 مصروف الشهر: {stmt['expense_iqd']:,.0f} د.ع\n"
        f"📌 صافي الشهر: {stmt['net_iqd']:,.0f} د.ع"
    )
    kb = InlineKeyboardMarkup([back_row("main:home")])
    await nav_render(update, context, text, reply_markup=kb)


# ---------------------------- قائمة التقارير ----------------------------

async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تقرير هذا الشهر", callback_data="rep:monthly:0")],
        [InlineKeyboardButton("📊 الشهر الماضي", callback_data="rep:monthly:1")],
        [InlineKeyboardButton("📈 مقارنة آخر 3 أشهر", callback_data="rep:compare")],
        back_row("main:home"),
    ])
    await nav_render(update, context, "📈 اختر التقرير:", reply_markup=kb)


async def _monthly_report_text(user_id, months_ago: int):
    n = dates.now()
    month = n.month - months_ago
    year = n.year
    while month <= 0:
        month += 12
        year -= 1
    stmt = await month_statement(user_id, year, month)
    cats = await db.sum_by_category(user_id, stmt["date_from"], stmt["date_to"], "expense")
    lines = [
        f"📊 تقرير {stmt['label']}",
        f"🔄 الرصيد المرحّل (بداية الشهر)\n{stmt['opening_iqd']:,.0f} د.ع",
        f"💵 الدخل\n{stmt['income_iqd']:,.0f} د.ع",
        f"💸 المصروف\n{stmt['expense_iqd']:,.0f} د.ع",
        f"📌 صافي الشهر\n{stmt['net_iqd']:,.0f} د.ع",
        f"✅ رصيد نهاية الشهر\n{stmt['closing_iqd']:,.0f} د.ع",
    ]
    if cats:
        lines.append("أكثر التصنيفات صرفًا:")
        for r in cats[:5]:
            icon = cat_utils.icon(r["category"])
            lines.append(f"{icon} {r['category']} — {r['total']:,.0f}")
    return "\n".join(lines)


async def _compare_months_text(user_id):
    lines = ["📈 مقارنة الأشهر"]
    for months_ago in (2, 1, 0):
        n = dates.now()
        month = n.month - months_ago
        year = n.year
        while month <= 0:
            month += 12
            year -= 1
        stmt = await month_statement(user_id, year, month)
        lines.append(f"\n{stmt['label']}:")
        lines.append(f"الدخل {stmt['income_iqd']:,.0f}")
        lines.append(f"المصروف {stmt['expense_iqd']:,.0f}")
        lines.append(f"رصيد النهاية {stmt['closing_iqd']:,.0f}")
    return "\n".join(lines)


async def handle_reports_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]
    if action == "hist":
        offset = int(parts[2])
        await show_history(update, context, user, offset=offset)
        await query.answer()
        return
    if action == "monthly":
        months_ago = int(parts[2])
        text = await _monthly_report_text(user["id"], months_ago)
        kb = InlineKeyboardMarkup([back_row("main:reports")])
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
        return
    if action == "compare":
        text = await _compare_months_text(user["id"])
        kb = InlineKeyboardMarkup([back_row("main:reports")])
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb)
        return
    if action == "clear_confirm":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، مسح الكل", callback_data="rep:clear_do"),
            InlineKeyboardButton("↩️ تراجع", callback_data="rep:hist:0"),
        ]])
        await query.answer()
        await query.edit_message_text(
            "⚠️ هل تريد مسح كل سجل عملياتك؟ ما تقدر تتراجع بعدين.", reply_markup=kb
        )
        return
    if action == "clear_do":
        count = await db.clear_user_transactions(user["id"])
        kb = InlineKeyboardMarkup([back_row("main:home")])
        await query.answer()
        await query.edit_message_text(f"🗑️ تم مسح كل السجل ({count} عملية).", reply_markup=kb)
        return
    await query.answer()
