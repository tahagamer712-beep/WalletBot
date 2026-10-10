"""
💸 سلفة — ميزة مالية حقيقية داخل البوت، مو مجرد تسجيل مبلغ.

كل سلفة محفوظة بجدول loans بقاعدة SQLite (تبقى بعد إعادة تشغيل Termux).
عند استلام أي عملية دخل بتصنيف "راتب"، تُطبَّق تلقائيًا استقطاعات كل السلف
النشطة لنفس المستخدم (كل سلفة مستقلة عن الثانية)، وتُسجَّل كـ loan_deductions
مربوطة بمعرّف عملية الراتب — الاستقطاع نفسه ليس عملية مالية منفصلة في جدول
transactions، فقط جزء من رسالة تأكيد الراتب.
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import re

import database.db as db
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from utils import dates

MAIN_BACK = back_row("main:home")


def _parse_amount(text: str) -> float:
    """
    يفهم '1,000,000' أو '1000000' أو '1.5 مليون' أو '500 الف' بشكل مرن —
    لكن يرفض (ValueError) أي نص فيه كلام إضافي غير متوقع بعد شيل الرقم
    والمضاعف المعروف. هذا يمنع مشكلة حقيقية: لو المستخدم بمنتصف تدفق سؤال
    (مثلًا "شكد مبلغ السلفة؟") وكتب رسالة عادية غير مرتبطة زي "500 اكل"،
    القديم كان يقتنص "500" بصمت ويكمل تدفق السلفة، فتضيع نية المستخدم الأصلية
    بدون أي تنبيه. هسه هذا يفشل بوضوح ويرجع لرسالة الخطأ الموجودة أصلًا.
    """
    text = text.strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    text = text.replace(",", "")
    multiplier = 1
    if "مليون" in text:
        multiplier = 1_000_000
        text = text.replace("مليون", "")
    elif "الف" in text or "ألف" in text:
        multiplier = 1000
        text = text.replace("الف", "").replace("ألف", "")
    leftover = re.sub(r"[\d.\s]", "", text)
    if leftover:
        raise ValueError(f"نص غير متوقع: {leftover}")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    if not digits:
        raise ValueError("ماكو رقم")
    return float(digits) * multiplier


# ---------------------------- القائمة الرئيسية للسلف ----------------------------

async def show_loans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    loans = await db.list_loans(user["id"], status="active")
    lines = ["💸 السلف"]
    rows = []
    if not loans:
        lines.append("\nماكو سلف نشطة حاليًا.")
    else:
        for loan in loans:
            remaining_deductions = _remaining_deductions_count(loan)
            lines.append(
                f"\n#{loan['id']} — متبقي {fmt_iqd(loan['remaining_amount'])} "
                f"(استقطاع {fmt_iqd(loan['deduction_per_salary'])}/راتب، "
                f"{remaining_deductions} استقطاعات متبقية)"
            )
            rows.append([InlineKeyboardButton(
                f"📋 سلفة #{loan['id']} — متبقي {loan['remaining_amount']:,.0f}",
                callback_data=f"loan:detail:{loan['id']}")])

    rows.append([InlineKeyboardButton("➕ إضافة سلفة", callback_data="loan:add")])
    rows.append(back_row("cmt:main"))
    await nav_render(update, context, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _remaining_deductions_count(loan: dict) -> int:
    if loan["deduction_per_salary"] <= 0:
        return 0
    import math
    return max(0, math.ceil(loan["remaining_amount"] / loan["deduction_per_salary"]))


# ---------------------------- تفاصيل سلفة واحدة ----------------------------

def _loan_detail_text(loan: dict) -> str:
    remaining_deductions = _remaining_deductions_count(loan)
    status_label = {"active": "🟢 نشطة", "completed": "✅ مسددة بالكامل", "cancelled": "❌ ملغاة"}.get(
        loan["status"], loan["status"])
    return (
        "💸 السلفة\n\n"
        f"• الحالة: {status_label}\n"
        f"• المبلغ الأصلي: {fmt_iqd(loan['original_amount'])}\n"
        f"• الاستقطاع لكل راتب: {fmt_iqd(loan['deduction_per_salary'])}\n"
        f"• المتبقي: {fmt_iqd(loan['remaining_amount'])}\n"
        f"• الاستقطاعات المتبقية: {remaining_deductions}"
    )


def _loan_detail_kb(loan_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([
            InlineKeyboardButton("✏️ تعديل الاستقطاع", callback_data=f"loan:edit_deduction:{loan_id}"),
            InlineKeyboardButton("📊 تفاصيل السلفة", callback_data=f"loan:history:{loan_id}"),
        ])
        rows.append([
            InlineKeyboardButton("💰 تسديد جزء", callback_data=f"loan:partial:{loan_id}"),
            InlineKeyboardButton("❌ إلغاء السلفة", callback_data=f"loan:cancel_confirm:{loan_id}"),
        ])
    else:
        rows.append([InlineKeyboardButton("📊 تفاصيل السلفة", callback_data=f"loan:history:{loan_id}")])
    rows.append(back_row("cmt:loans_list"))
    return InlineKeyboardMarkup(rows)


async def _show_loan_detail(update, context, user, loan_id):
    loan = await db.get_loan(loan_id, user["id"])
    if not loan:
        await nav_render(update, context, "السلفة غير موجودة.", reply_markup=InlineKeyboardMarkup([MAIN_BACK]))
        return
    await nav_render(update, context, _loan_detail_text(loan), reply_markup=_loan_detail_kb(loan_id, loan["status"]))


async def _show_loan_history(update, context, user, loan_id):
    loan = await db.get_loan(loan_id, user["id"])
    if not loan:
        await nav_render(update, context, "السلفة غير موجودة.", reply_markup=InlineKeyboardMarkup([MAIN_BACK]))
        return
    deductions = await db.list_loan_deductions(loan_id)
    lines = [f"📊 تفاصيل سلفة #{loan_id}"]
    if not deductions:
        lines.append("\nماكو استقطاعات مسجّلة بعد.")
    else:
        for d in deductions:
            kind_label = "راتب" if d["kind"] == "salary" else "تسديد يدوي"
            date_part = d["created_at"][:10]
            lines.append(f"{date_part} — {kind_label} — {fmt_iqd(d['amount'])}")
    kb = InlineKeyboardMarkup([back_row(f"loan:detail:{loan_id}", "🔙 رجوع لتفاصيل السلفة")])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


# ---------------------------- إضافة سلفة (تدفق سؤالين) ----------------------------

async def _start_add_loan(update, context):
    context.user_data["pending"] = {"action": "loan:await_amount"}
    kb = InlineKeyboardMarkup([back_row("cmt:loans_list")])
    await nav_render(update, context, "💸 إضافة سلفة\nشكد مبلغ السلفة؟", reply_markup=kb)


async def _start_edit_deduction(update, context, loan_id):
    context.user_data["pending"] = {"action": "loan:await_new_deduction", "loan_id": loan_id}
    kb = InlineKeyboardMarkup([back_row(f"loan:detail:{loan_id}")])
    await nav_render(update, context, "شكد تريد يصير الاستقطاع الجديد لكل راتب؟", reply_markup=kb)


async def _start_partial_payment(update, context, loan_id):
    context.user_data["pending"] = {"action": "loan:await_partial_payment", "loan_id": loan_id}
    kb = InlineKeyboardMarkup([back_row(f"loan:detail:{loan_id}")])
    await nav_render(update, context, "شكد المبلغ اللي تريد تسدده الحين؟", reply_markup=kb)


# ---------------------------- Callback router ----------------------------

async def handle_loan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "add":
        await _start_add_loan(update, context)
        return
    if action == "detail":
        await _show_loan_detail(update, context, user, int(parts[2]))
        return
    if action == "history":
        await _show_loan_history(update, context, user, int(parts[2]))
        return
    if action == "edit_deduction":
        await _start_edit_deduction(update, context, int(parts[2]))
        return
    if action == "partial":
        await _start_partial_payment(update, context, int(parts[2]))
        return
    if action == "cancel_confirm":
        loan_id = int(parts[2])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، الغِ السلفة", callback_data=f"loan:cancel_do:{loan_id}"),
             InlineKeyboardButton("↩️ تراجع", callback_data=f"loan:detail:{loan_id}")],
        ])
        await nav_render(update, context, "⚠️ هل تريد إلغاء هذه السلفة؟ ما تقدر تتراجع بعدين.",
                          reply_markup=kb)
        return
    if action == "cancel_do":
        loan_id = int(parts[2])
        await db.cancel_loan(loan_id, user["id"])
        await nav_render(update, context, "❌ تم إلغاء السلفة.",
                          reply_markup=InlineKeyboardMarkup([back_row("cmt:loans_list")]))
        return
    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending.get("action", "")

    if action == "loan:await_amount":
        try:
            amount = _parse_amount(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. أرسل مبلغ السلفة مرة ثانية، مثلًا: 1000000")
            return True
        context.user_data["pending"] = {"action": "loan:await_deduction", "amount": amount}
        await update.message.reply_text(
            f"💰 مبلغ السلفة: {fmt_iqd(amount)}\nشكد تريد ينخصم منك بعد كل راتب؟"
        )
        return True

    if action == "loan:await_deduction":
        try:
            deduction = _parse_amount(text)
            if deduction <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. أرسل مبلغ الاستقطاع مرة ثانية، مثلًا: 100000")
            return True
        amount = pending["amount"]
        loan_id = await db.create_loan(user["id"], amount, deduction)
        loan = await db.get_loan(loan_id, user["id"])
        context.user_data.pop("pending", None)
        kb = InlineKeyboardMarkup([back_row("cmt:loans_list")])
        await update.message.reply_text(
            "✅ تم إنشاء السلفة\n\n" + _loan_detail_text(loan), reply_markup=kb
        )
        return True

    if action == "loan:await_new_deduction":
        loan_id = pending["loan_id"]
        try:
            new_deduction = _parse_amount(text)
            if new_deduction <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        await db.update_loan_deduction(loan_id, user["id"], new_deduction)
        loan = await db.get_loan(loan_id, user["id"])
        context.user_data.pop("pending", None)
        kb = InlineKeyboardMarkup([back_row(f"loan:detail:{loan_id}")])
        await update.message.reply_text(
            f"✅ تم تحديث الاستقطاع إلى {fmt_iqd(new_deduction)} لكل راتب.", reply_markup=kb
        )
        return True

    if action == "loan:await_partial_payment":
        loan_id = pending["loan_id"]
        try:
            payment = _parse_amount(text)
            if payment <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        result = await db.apply_loan_deduction(loan_id, payment, transaction_id=None, kind="manual")
        context.user_data.pop("pending", None)
        if not result:
            await update.message.reply_text("السلفة غير موجودة.")
            return True
        loan = await db.get_loan(loan_id, user["id"])
        kb = InlineKeyboardMarkup([back_row(f"loan:detail:{loan_id}")])
        msg = f"✅ تم تسجيل تسديد {fmt_iqd(result['deducted'])}\nالمتبقي: {fmt_iqd(result['new_remaining'])}"
        if result["status"] == "completed":
            msg += "\n\n✅ تم تسديد السلفة بالكامل."
        await update.message.reply_text(msg, reply_markup=kb)
        return True

    return False


# ---------------------------- الربط التلقائي مع استلام الراتب ----------------------------

async def apply_salary_deductions(user_id: int, transaction_id: int) -> list:
    """
    تُستدعى بعد تسجيل أي عملية دخل بتصنيف 'راتب'. تطبّق استقطاع كل سلفة نشطة
    auto_deduct=1 لنفس المستخدم (كل سلفة مستقلة)، وترجع قائمة بنتيجة كل استقطاع حصل فعلًا.
    """
    active_loans = await db.list_loans(user_id, status="active")
    results = []
    for loan in active_loans:
        if not loan.get("auto_deduct", 1):
            continue
        if loan["deduction_per_salary"] <= 0 or loan["remaining_amount"] <= 0:
            continue
        result = await db.apply_loan_deduction(
            loan["id"], loan["deduction_per_salary"], transaction_id=transaction_id, kind="salary"
        )
        if result:
            result["loan_id"] = loan["id"]
            result["label"] = loan.get("name") or f"سلفة #{loan['id']}"
            results.append(result)
    return results
