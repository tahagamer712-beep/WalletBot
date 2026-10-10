"""
🔄 الالتزامات المتكررة — إيجار، اشتراكات، فواتير دورية. وأيضًا "📄 التزام آخر"
كنوع بسيط لأي التزام لا يندرج تحت سلفة أو قسط.

محفوظة بجدول recurring_commitments. auto_deduct=1 تعني تُستقطع تلقائيًا عند
كل استلام راتب (بدون مفهوم "متبقي" — هي مبلغ ثابت متكرر، عكس السلفة والقسط).
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from handlers.loans import _parse_amount


def _status_label(status: str) -> str:
    return {"active": "🟢 فعّال", "cancelled": "❌ ملغى"}.get(status, status)


async def show_recurring_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    items = await db.list_recurring(user["id"], status="active")
    lines = ["🔄 الالتزامات المتكررة"]
    rows = []
    if not items:
        lines.append("\nماكو التزامات متكررة مسجّلة حاليًا.")
    else:
        for r in items:
            freq_label = "لمرة وحدة" if r["frequency"] == "once" else "شهريًا"
            rows.append([InlineKeyboardButton(
                f"🔄 {r['name']} — {r['amount']:,.0f} ({freq_label})",
                callback_data=f"rec:detail:{r['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة التزام متكرر", callback_data="rec:add")])
    rows.append(back_row("cmt:main"))
    await nav_render(update, context, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _detail_text(r: dict) -> str:
    freq_label = "لمرة وحدة" if r["frequency"] == "once" else "شهريًا"
    return (
        "🔄 الالتزام المتكرر\n\n"
        f"• الاسم: {r['name']}\n"
        f"• الحالة: {_status_label(r['status'])}\n"
        f"• المبلغ: {fmt_iqd(r['amount'])}\n"
        f"• التكرار: {freq_label}\n"
        f"• استقطاع تلقائي عند الراتب: {'✅ نعم' if r['auto_deduct'] else '❌ لا'}"
    )


def _detail_kb(rec_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([
            InlineKeyboardButton("📊 سجل الدفعات", callback_data=f"rec:history:{rec_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"rec:cancel_confirm:{rec_id}"),
        ])
    else:
        rows.append([InlineKeyboardButton("📊 سجل الدفعات", callback_data=f"rec:history:{rec_id}")])
    rows.append(back_row("rec:list"))
    return InlineKeyboardMarkup(rows)


async def _show_detail(update, context, user, rec_id):
    r = await db.get_recurring(rec_id, user["id"])
    if not r:
        await nav_render(update, context, "الالتزام غير موجود.", reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    await nav_render(update, context, _detail_text(r), reply_markup=_detail_kb(rec_id, r["status"]))


async def _show_history(update, context, user, rec_id):
    r = await db.get_recurring(rec_id, user["id"])
    if not r:
        await nav_render(update, context, "الالتزام غير موجود.", reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    payments = await db.list_recurring_payments(rec_id)
    lines = [f"📊 سجل دفعات: {r['name']}"]
    if not payments:
        lines.append("\nماكو دفعات مسجّلة بعد.")
    else:
        for p in payments:
            kind_label = "راتب" if p["kind"] == "salary" else "يدوي"
            lines.append(f"{p['created_at'][:10]} — {kind_label} — {fmt_iqd(p['amount'])}")
    kb = InlineKeyboardMarkup([back_row(f"rec:detail:{rec_id}", "🔙 رجوع للتفاصيل")])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


async def _start_add(update, context, once=False):
    action = "rec:await_name_once" if once else "rec:await_name"
    context.user_data["pending"] = {"action": action}
    title = "📄 إضافة التزام آخر" if once else "🔄 إضافة التزام متكرر"
    kb = InlineKeyboardMarkup([back_row("cmt:main")])
    await nav_render(update, context, f"{title}\nشنو اسم الالتزام؟", reply_markup=kb)


async def handle_recurring_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "list":
        await show_recurring_menu(update, context, user)
        return
    if action == "add":
        await _start_add(update, context, once=False)
        return
    if action == "add_once":
        await _start_add(update, context, once=True)
        return
    if action == "detail":
        await _show_detail(update, context, user, int(parts[2]))
        return
    if action == "history":
        await _show_history(update, context, user, int(parts[2]))
        return
    if action == "cancel_confirm":
        rec_id = int(parts[2])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، الغِ", callback_data=f"rec:cancel_do:{rec_id}"),
            InlineKeyboardButton("↩️ تراجع", callback_data=f"rec:detail:{rec_id}"),
        ]])
        await nav_render(update, context, "⚠️ هل تريد إلغاء هذا الالتزام؟", reply_markup=kb)
        return
    if action == "cancel_do":
        rec_id = int(parts[2])
        await db.cancel_recurring(rec_id, user["id"])
        await nav_render(update, context, "❌ تم إلغاء الالتزام.",
                          reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    if action == "autoded":
        pending = context.user_data.get("pending", {})
        if pending.get("action") != "rec:await_autoded":
            await query.answer()
            return
        auto_deduct = parts[2] == "yes"
        name = pending["name"]
        amount = pending["amount"]
        frequency = pending.get("frequency", "monthly")
        rec_id = await db.create_recurring(user["id"], name, amount, category=None,
                                            frequency=frequency, auto_deduct=auto_deduct)
        r = await db.get_recurring(rec_id, user["id"])
        context.user_data.pop("pending", None)
        kb = InlineKeyboardMarkup([back_row("cmt:main")])
        await query.answer()
        await query.edit_message_text("✅ تم إنشاء الالتزام\n\n" + _detail_text(r), reply_markup=kb)
        return
    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending.get("action", "")

    if action in ("rec:await_name", "rec:await_name_once"):
        name = text.strip()[:60]
        once = action == "rec:await_name_once"
        next_action = "rec:await_amount_once" if once else "rec:await_amount"
        context.user_data["pending"] = {"action": next_action, "name": name}
        await update.message.reply_text(f"🔄 {name}\nشكد المبلغ؟")
        return True

    if action in ("rec:await_amount", "rec:await_amount_once"):
        try:
            amount = _parse_amount(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        once = action == "rec:await_amount_once"
        frequency = "once" if once else "monthly"
        context.user_data["pending"] = {
            "action": "rec:await_autoded", "name": pending["name"], "amount": amount, "frequency": frequency,
        }
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم", callback_data="rec:autoded:yes"),
            InlineKeyboardButton("❌ لا", callback_data="rec:autoded:no"),
        ]])
        await update.message.reply_text(
            "هل يتم استقطاعه تلقائيًا عند تسجيل الراتب؟", reply_markup=kb
        )
        return True

    return False


async def apply_salary_deductions(user_id: int, transaction_id: int) -> list:
    """تُستدعى بعد أي دخل بتصنيف 'راتب' — تسجّل دفعة لكل التزام متكرر auto_deduct=1 (بدون مفهوم 'متبقي')."""
    active = await db.list_recurring(user_id, status="active")
    results = []
    for r in active:
        if not r.get("auto_deduct", 0):
            continue
        await db.record_recurring_payment(r["id"], r["amount"], transaction_id=transaction_id, kind="salary")
        results.append({"recurring_id": r["id"], "deducted": r["amount"], "label": r["name"]})
        if r["frequency"] == "once":
            # التزام "لمرة وحدة" يُلغى تلقائيًا بعد أول استقطاع حتى لا يتكرر كل راتب
            await db.cancel_recurring(r["id"], user_id)
    return results
