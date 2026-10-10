"""🎯 أهداف الادخار — إنشاء هدف، إضافة مبلغ، متابعة التقدم بشريط تقدم نصي."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from utils.currency import fmt_iqd
from utils.reply import nav_render, back_row
from handlers.loans import _parse_amount


def _progress_bar(saved: float, target: float, width: int = 15) -> str:
    if target <= 0:
        return ""
    pct = min(1.0, saved / target)
    filled = round(pct * width)
    return "█" * filled + "░" * (width - filled) + f" {pct*100:.0f}%"


def _status_label(status: str) -> str:
    return {"active": "🟢 قيد التوفير", "completed": "✅ تم تحقيق الهدف", "cancelled": "❌ ملغى"}.get(status, status)


async def show_savings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    goals = await db.list_savings_goals(user["id"], status="active")
    lines = ["🎯 أهداف الادخار"]
    rows = []
    if not goals:
        lines.append("\nماكو أهداف ادخار حاليًا.")
    else:
        for g in goals:
            bar = _progress_bar(g["saved_amount"], g["target_amount"])
            lines.append(f"\n🎯 {g['name']}\n{fmt_iqd(g['saved_amount'])} / {fmt_iqd(g['target_amount'])}\n{bar}")
            rows.append([InlineKeyboardButton(f"🎯 {g['name']}", callback_data=f"sav:detail:{g['id']}")])
    rows.append([InlineKeyboardButton("➕ إضافة هدف", callback_data="sav:add")])
    rows.append(back_row("main:home"))
    await nav_render(update, context, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _detail_text(g: dict) -> str:
    remaining = max(0, g["target_amount"] - g["saved_amount"])
    bar = _progress_bar(g["saved_amount"], g["target_amount"])
    return (
        f"🎯 {g['name']}\n\n"
        f"• الحالة: {_status_label(g['status'])}\n"
        f"• الهدف: {fmt_iqd(g['target_amount'])}\n"
        f"• المدخر: {fmt_iqd(g['saved_amount'])}\n"
        f"• المتبقي: {fmt_iqd(remaining)}\n\n"
        f"{bar}"
    )


def _detail_kb(goal_id: int, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([
            InlineKeyboardButton("💰 إضافة مبلغ", callback_data=f"sav:deposit:{goal_id}"),
            InlineKeyboardButton("❌ إلغاء الهدف", callback_data=f"sav:cancel_confirm:{goal_id}"),
        ])
    rows.append(back_row("main:savings"))
    return InlineKeyboardMarkup(rows)


async def _show_detail(update, context, user, goal_id):
    g = await db.get_savings_goal(goal_id, user["id"])
    if not g:
        await nav_render(update, context, "الهدف غير موجود.", reply_markup=InlineKeyboardMarkup([back_row("main:savings")]))
        return
    await nav_render(update, context, _detail_text(g), reply_markup=_detail_kb(goal_id, g["status"]))


async def _start_add(update, context):
    context.user_data["pending"] = {"action": "sav:await_name"}
    kb = InlineKeyboardMarkup([back_row("main:savings")])
    await nav_render(update, context, "🎯 إضافة هدف ادخار\nشنو اسم الهدف؟ (مثلًا: سيارة)", reply_markup=kb)


async def _start_deposit(update, context, goal_id):
    context.user_data["pending"] = {"action": "sav:await_deposit", "goal_id": goal_id}
    kb = InlineKeyboardMarkup([back_row(f"sav:detail:{goal_id}")])
    await nav_render(update, context, "شكد المبلغ اللي تريد تضيفه؟", reply_markup=kb)


async def handle_savings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    parts = data.split(":")
    action = parts[1]

    if action == "add":
        await _start_add(update, context)
        return
    if action == "detail":
        await _show_detail(update, context, user, int(parts[2]))
        return
    if action == "deposit":
        await _start_deposit(update, context, int(parts[2]))
        return
    if action == "cancel_confirm":
        goal_id = int(parts[2])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ نعم، الغِ الهدف", callback_data=f"sav:cancel_do:{goal_id}"),
            InlineKeyboardButton("↩️ تراجع", callback_data=f"sav:detail:{goal_id}"),
        ]])
        await nav_render(update, context, "⚠️ هل تريد إلغاء هذا الهدف؟", reply_markup=kb)
        return
    if action == "cancel_do":
        goal_id = int(parts[2])
        await db.cancel_savings_goal(goal_id, user["id"])
        await nav_render(update, context, "❌ تم إلغاء الهدف.",
                          reply_markup=InlineKeyboardMarkup([back_row("main:savings")]))
        return
    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    action = pending.get("action", "")

    if action == "sav:await_name":
        name = text.strip()[:60]
        context.user_data["pending"] = {"action": "sav:await_target", "name": name}
        await update.message.reply_text(f"🎯 {name}\nشكد المبلغ المطلوب توفيره؟")
        return True

    if action == "sav:await_target":
        try:
            target = _parse_amount(text)
            if target <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        goal_id = await db.create_savings_goal(user["id"], pending["name"], target)
        g = await db.get_savings_goal(goal_id, user["id"])
        context.user_data.pop("pending", None)
        kb = InlineKeyboardMarkup([back_row("main:savings")])
        await update.message.reply_text("✅ تم إنشاء هدف الادخار\n\n" + _detail_text(g), reply_markup=kb)
        return True

    if action == "sav:await_deposit":
        goal_id = pending["goal_id"]
        try:
            amount = _parse_amount(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("رقم غير صالح. حاول مرة ثانية.")
            return True
        result = await db.add_savings_amount(goal_id, amount)
        context.user_data.pop("pending", None)
        if not result:
            await update.message.reply_text("الهدف غير موجود.")
            return True
        g = await db.get_savings_goal(goal_id, user["id"])
        kb = InlineKeyboardMarkup([back_row(f"sav:detail:{goal_id}")])
        msg = f"✅ تم إضافة {fmt_iqd(amount)}\n\n" + _detail_text(g)
        if result["status"] == "completed":
            msg += "\n\n🎉 مبروك! حققت هدفك بالكامل."
        await update.message.reply_text(msg, reply_markup=kb)
        return True

    return False
