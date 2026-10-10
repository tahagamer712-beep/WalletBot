"""
💳 قسط — نفس فكرة السلفة لكن محسوبة بعدد أقساط بدل مبلغ استقطاع حر.
محفوظة بجدول installments (تبقى بعد إعادة تشغيل Termux)، وتُستقطع تلقائيًا
عند استلام راتب لو auto_deduct=1، بنفس آلية السلفة تمامًا.
"""
import math
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from handlers.loans import _parse_amount  # نفس دالة تحليل المبالغ المرنة (1 مليون / 500 الف...)


def _remaining_count(inst: dict) -> int:
    if inst["installment_amount"] <= 0:
        return 0
    return max(0, math.ceil(inst["remaining_amount"] / inst["installment_amount"]))


def _status_label(status: str) -> str:
    return {"active": "🟢 نشط", "completed": "✅ مسدد بالكامل", "cancelled": "❌ ملغى"}.get(status, status)


async def show_installments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    items = await db.list_installments(user["id"], status="active")
    lines = ["💳 الأقساط"]
    rows = []
    if not items:
        lines.append("\nماكو أقساط نشطة حاليًا.")
    else:
        for inst in items:
            rows.append([InlineKeyboardButton(
                f"💳 {inst['name'] or ('قسط #' + str(inst['id']))} — متبقي {inst['remaining_amount']:,.0f}",
                callback_data=f"inst:detail:{inst['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة قسط", callback_data="inst:add")])
    rows.append(back_row("cmt:main"))
    await nav_render(update, context, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _detail_text(inst: dict) -> str:
    return (
        "💳 القسط\n\n"
        f"• الاسم: {inst['name'] or '—'}\n"
        f"• الحالة: {_status_label(inst['status'])}\n"
        f"• السعر الأصلي: {fmt_iqd(inst['original_amount'])}\n"
        f"• قيمة القسط: {fmt_iqd(inst['installment_amount'])}\n"
        f"• المتبقي: {fmt_iqd(inst['remaining_amount'])}\n"
        f"• الأقساط المتبقية: {inst['remaining_payments']}\n"
        f"• استقطاع تلقائي عند الراتب: {'✅ نعم' if inst['auto_deduct'] else '❌ لا'}"
    )


def _detail_kb(inst_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([
            InlineKeyboardButton("📊 سجل الدفعات", callback_data=f"inst:history:{inst_id}"),
            InlineKeyboardButton("💰 تسديد جزء", callback_data=f"inst:partial:{inst_id}"),
        ])
        rows.append([InlineKeyboardButton("❌ إلغاء القسط", callback_data=f"inst:cancel_confirm:{inst_id}")])
    else:
        rows.append([InlineKeyboardButton("📊 سجل الدفعات", callback_data=f"inst:history:{inst_id}")])
    rows.append(back_row("inst:list"))
    return InlineKeyboardMarkup(rows)


async def _show_detail(update, context, user, inst_id):
    inst = await db.get_installment(inst_id, user["id"])
    if not inst:
        await nav_render(update, context, "القسط غير موجود.", reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    await nav_render(update, context, _detail_text(inst), reply_markup=_detail_kb(inst_id, inst["status"]))


async def _show_history(update, context, user, inst_id):
    inst = await db.get_installment(inst_id, user["id"])
    if not inst:
        await nav_render(update, context, "القسط غير موجود.", reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    payments = await db.list_installment_payments(inst_id)
    lines = [f"📊 سجل دفعات: {inst['name'] or ('#' + str(inst_id))}"]
    if not payments:
        lines.append("\nماكو دفعات مسجّلة بعد.")
    else:
        for p in payments:
            kind_label = "راتب" if p["kind"] == "salary" else "تسديد يدوي"
            lines.append(f"{p['created_at'][:10]} — {kind_label} — {fmt_iqd(p['amount'])}")
    kb = InlineKeyboardMarkup([back_row(f"inst:detail:{inst_id}", "🔙 رجوع للتفاصيل")])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


async def _start_add(update, context):
    context.user_data["pending"] = {"action": "inst:await_name"}
    kb = InlineKeyboardMarkup([back_row("cmt:main")])
    await nav_render(update, context, "💳 إضافة قسط\nشنو اسم القسط؟ (مثلًا: آيفون)", reply_markup=kb)


async def _start_partial(update, context, inst_id):
    context.user_data["pending"] = {"action": "inst:await_partial", "inst_id": inst_id}
    kb = InlineKeyboardMarkup([back_row(f"inst:detail:{inst_id}")])
    await nav_render(update, context, "شكد المبلغ اللي تريد تسدده الحين؟", reply_markup=kb)


async def handle_installment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "list":
        await show_installments_menu(update, context, user)
        return
    if action == "add":
        await _start_add(update, context)
        return
    if action == "detail":
        await _show_detail(update, context, user, int(parts[2]))
        return
    if action == "history":
        await _show_history(update, context, user, int(parts[2]))
        return
    if action == "partial":
        await _start_partial(update, context, int(parts[2]))
        return
    if action == "cancel_confirm":
        inst_id = int(parts[2])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، الغِ القسط", callback_data=f"inst:cancel_do:{inst_id}"),
            InlineKeyboardButton("↩️ تراجع", callback_data=f"inst:detail:{inst_id}"),
        ]])
        await nav_render(update, context, "⚠️ هل تريد إلغاء هذا القسط؟ ما تقدر تتراجع بعدين.", reply_markup=kb)
        return
    if action == "cancel_do":
        inst_id = int(parts[2])
        await db.cancel_installment(inst_id, user["id"])
        await nav_render(update, context, "❌ تم إلغاء القسط.",
                          reply_markup=InlineKeyboardMarkup([back_row("cmt:main")]))
        return
    # خطوة اختيار "استقطاع تلقائي؟" أثناء إضافة قسط جديد
    if action == "autoded":
        pending = context.user_data.get("pending", {})
        if pending.get("action") != "inst:await_autoded":
            await query.answer()
            return
        auto_deduct = parts[2] == "yes"
        name = pending["name"]
        price = pending["price"]
        amount = pending["amount"]
        inst_id = await db.create_installment(user["id"], name, price, amount, auto_deduct=auto_deduct)
        inst = await db.get_installment(inst_id, user["id"])
        context.user_data.pop("pending", None)
        kb = InlineKeyboardMarkup([back_row("cmt:main")])
        await query.answer()
        await query.edit_message_text("✅ تم إنشاء القسط\n\n" + _detail_text(inst), reply_markup=kb)
        return
    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending.get("action", "")

    if action == "inst:await_name":
        name = text.strip()[:60]
        context.user_data["pending"] = {"action": "inst:await_price", "name": name}
        await update.message.reply_text(f"💳 {name}\nشكد السعر الكلي؟")
        return True

    if action == "inst:await_price":
        try:
            price = _parse_amount(text)
            if price <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        context.user_data["pending"] = {"action": "inst:await_amount", "name": pending["name"], "price": price}
        await update.message.reply_text("شكد قيمة القسط الواحد (شهريًا)؟")
        return True

    if action == "inst:await_amount":
        try:
            amount = _parse_amount(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        count = max(1, math.ceil(pending["price"] / amount))
        context.user_data["pending"] = {
            "action": "inst:await_autoded", "name": pending["name"], "price": pending["price"], "amount": amount,
        }
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم", callback_data="inst:autoded:yes"),
            InlineKeyboardButton("❌ لا", callback_data="inst:autoded:no"),
        ]])
        await update.message.reply_text(
            f"عدد الأقساط سيكون: {count}\nهل تريد استقطاعه تلقائيًا عند تسجيل الراتب؟",
            reply_markup=kb,
        )
        return True

    if action == "inst:await_partial":
        inst_id = pending["inst_id"]
        try:
            payment = _parse_amount(text)
            if payment <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        result = await db.apply_installment_payment(inst_id, payment, transaction_id=None, kind="manual")
        context.user_data.pop("pending", None)
        if not result:
            await update.message.reply_text("القسط غير موجود.")
            return True
        kb = InlineKeyboardMarkup([back_row(f"inst:detail:{inst_id}")])
        msg = f"✅ تم تسجيل تسديد {fmt_iqd(result['deducted'])}\nالمتبقي: {fmt_iqd(result['new_remaining'])}"
        if result["status"] == "completed":
            msg += "\n\n✅ تم تسديد القسط بالكامل."
        await update.message.reply_text(msg, reply_markup=kb)
        return True

    return False


async def apply_salary_deductions(user_id: int, transaction_id: int) -> list:
    """تُستدعى بعد أي دخل بتصنيف 'راتب' — تستقطع كل قسط نشط auto_deduct=1."""
    active = await db.list_installments(user_id, status="active")
    results = []
    for inst in active:
        if not inst.get("auto_deduct", 1):
            continue
        if inst["installment_amount"] <= 0 or inst["remaining_amount"] <= 0:
            continue
        result = await db.apply_installment_payment(
            inst["id"], inst["installment_amount"], transaction_id=transaction_id, kind="salary"
        )
        if result:
            result["installment_id"] = inst["id"]
            result["label"] = inst.get("name") or f"قسط #{inst['id']}"
            results.append(result)
    return results
