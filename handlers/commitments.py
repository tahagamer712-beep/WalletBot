"""📌 الالتزامات المالية — المحور الموحّد للسلف والأقساط والالتزامات المتكررة."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from handlers import loans as loans_handler, installments as inst_handler, recurring as rec_handler


async def show_commitments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    loans = await db.list_loans(user["id"], status="active")
    insts = await db.list_installments(user["id"], status="active")
    recs = await db.list_recurring(user["id"], status="active")

    loans_remaining = sum(l["remaining_amount"] for l in loans)
    insts_remaining = sum(i["remaining_amount"] for i in insts)
    recs_monthly = sum(r["amount"] for r in recs if r["frequency"] == "monthly")

    total_remaining = loans_remaining + insts_remaining
    monthly_total = (
        sum(l["deduction_per_salary"] for l in loans)
        + sum(i["installment_amount"] for i in insts)
        + recs_monthly
    )

    lines = [
        "📌 الالتزامات المالية\n",
        f"💸 السلف\n{fmt_iqd(loans_remaining)} متبقي\n",
        f"💳 الأقساط\n{fmt_iqd(insts_remaining)} متبقي\n",
        f"🔄 الالتزامات المتكررة\n{fmt_iqd(recs_monthly)} شهريًا\n",
        "━━━━━━━━━━━━━━━━",
        f"💰 إجمالي المتبقي\n{fmt_iqd(total_remaining)}\n",
        f"📅 الالتزامات الشهرية\n{fmt_iqd(monthly_total)}",
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة التزام", callback_data="cmt:add_type")],
        [InlineKeyboardButton("📋 التزاماتي", callback_data="cmt:list")],
        [InlineKeyboardButton("📊 ملخص الالتزامات", callback_data="cmt:summary")],
        back_row("main:home"),
    ])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


async def _show_add_type_picker(update, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 سلفة", callback_data="loan:add")],
        [InlineKeyboardButton("💳 قسط", callback_data="inst:add")],
        [InlineKeyboardButton("🔄 التزام متكرر", callback_data="rec:add")],
        [InlineKeyboardButton("📄 التزام آخر", callback_data="rec:add_once")],
        back_row("cmt:main"),
    ])
    await nav_render(update, context, "شنو نوع الالتزام؟", reply_markup=kb)


async def _show_my_commitments(update, context, user):
    loans = await db.list_loans(user["id"], status="active")
    insts = await db.list_installments(user["id"], status="active")
    recs = await db.list_recurring(user["id"], status="active")

    rows = []
    if loans:
        rows.append([InlineKeyboardButton(f"💸 السلف ({len(loans)})", callback_data="cmt:loans_list")])
    if insts:
        rows.append([InlineKeyboardButton(f"💳 الأقساط ({len(insts)})", callback_data="inst:list")])
    if recs:
        rows.append([InlineKeyboardButton(f"🔄 الالتزامات المتكررة ({len(recs)})", callback_data="rec:list")])
    if not rows:
        text = "📋 التزاماتي\n\nماكو التزامات مسجّلة حاليًا."
    else:
        text = "📋 التزاماتي\nاختر القسم:"
    rows.append(back_row("cmt:main"))
    await nav_render(update, context, text, reply_markup=InlineKeyboardMarkup(rows))


async def _show_summary(update, context, user):
    loans = await db.list_loans(user["id"], status="active")
    insts = await db.list_installments(user["id"], status="active")
    recs = await db.list_recurring(user["id"], status="active")

    lines = ["📊 ملخص الالتزامات"]
    if loans:
        lines.append("\n💸 السلف:")
        for l in loans:
            label = l["name"] or f"#{l['id']}"
            lines.append(f"  • {label}: متبقي {fmt_iqd(l['remaining_amount'])} "
                         f"(استقطاع {fmt_iqd(l['deduction_per_salary'])}/راتب)")
    if insts:
        lines.append("\n💳 الأقساط:")
        for i in insts:
            label = i["name"] or f"#{i['id']}"
            lines.append(f"  • {label}: متبقي {fmt_iqd(i['remaining_amount'])} "
                         f"({i['remaining_payments']} قسط متبقي)")
    if recs:
        lines.append("\n🔄 الالتزامات المتكررة:")
        for r in recs:
            lines.append(f"  • {r['name']}: {fmt_iqd(r['amount'])} "
                         f"({'شهريًا' if r['frequency']=='monthly' else 'لمرة وحدة'})")
    if not (loans or insts or recs):
        lines.append("\nماكو التزامات نشطة حاليًا.")

    kb = InlineKeyboardMarkup([back_row("cmt:main")])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


async def handle_commitments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "main":
        await show_commitments_menu(update, context, user)
        return
    if action == "add_type":
        await _show_add_type_picker(update, context)
        return
    if action == "list":
        await _show_my_commitments(update, context, user)
        return
    if action == "summary":
        await _show_summary(update, context, user)
        return
    if action == "loans_list":
        await loans_handler.show_loans_menu(update, context, user)
        return
    await query.answer()


async def apply_all_salary_deductions(user_id: int, transaction_id: int) -> list:
    """
    يُستدعى بعد أي دخل بتصنيف 'راتب' — يطبّق استقطاعات كل الالتزامات (سلف +
    أقساط + متكررة) اللي عندها auto_deduct=1 لنفس المستخدم، كل التزام مستقل.
    """
    results = []
    results.extend(await loans_handler.apply_salary_deductions(user_id, transaction_id))
    results.extend(await inst_handler.apply_salary_deductions(user_id, transaction_id))
    results.extend(await rec_handler.apply_salary_deductions(user_id, transaction_id))
    return results
