"""💾 Backup / ♻️ Restore — أدمن فقط."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import config
import database.db as db
from backup.backup import create_backup
from backup.restore import restore_from_file
from utils.security import is_admin
from utils.reply import nav_render, back_row


async def show_backup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    backups = await db.list_backups(limit=5)
    lines = ["💾 النسخ الاحتياطية"]
    for b in backups:
        icon = "✅" if b["status"] == "ok" else "❌"
        lines.append(f"{icon} {b['filename']} ({b['kind']})")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 إنشاء نسخة الآن", callback_data="adm:backup_now")],
        back_row("adm:main"),
    ])
    await nav_render(update, context, "\n".join(lines), reply_markup=kb)


async def handle_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("للأدمن فقط.", show_alert=True)
        return
    action = data.split(":")[1]
    if action == "backup_now":
        await query.answer("جاري إنشاء النسخة الاحتياطية...")
        path, ok = await create_backup(kind="manual")
        await db.add_audit_log(user["telegram_id"], "created_backup", path.name)
        kb = InlineKeyboardMarkup([back_row("adm:backup")])
        if ok:
            await context.bot.send_document(chat_id=update.effective_chat.id,
                                             document=open(path, "rb"), filename=path.name,
                                             caption="✅ تم إنشاء النسخة الاحتياطية بنجاح.")
            await query.message.reply_text("↩️ ارجع لقائمة Backup:", reply_markup=kb)
        else:
            await query.message.reply_text("❌ فشل إنشاء نسخة احتياطية سليمة.", reply_markup=kb)
        return
    await query.answer()


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أي أدمن يرسل ملف .db يُعامل كطلب استعادة (Restore)."""
    tg_user = update.effective_user
    if not is_admin(tg_user.id):
        return
    doc = update.message.document
    if not doc.file_name.endswith(".db"):
        return

    await update.message.reply_text("⏳ جاري التحقق من الملف واستعادته...")
    file = await context.bot.get_file(doc.file_id)
    tmp_path = str(config.BASE_DIR / "exports" / f"_restore_upload_{doc.file_unique_id}.db")
    await file.download_to_drive(tmp_path)

    ok, msg = await restore_from_file(tmp_path)
    user = await db.get_or_create_user(tg_user.id, tg_user.full_name, tg_user.username or "")
    await db.add_audit_log(user["telegram_id"], "restored_backup" if ok else "restore_failed", msg)
    kb = InlineKeyboardMarkup([back_row("adm:main")])
    await update.message.reply_text(msg, reply_markup=kb)
