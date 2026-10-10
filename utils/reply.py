"""
مساعدات موحّدة للرد والتنقّل بين قوائم الـ Inline:
- send_reply: يرسل رسالة جديدة دائمًا (لأول فتح لقائمة من أمر مباشر مثل /admin).
- nav_render: يعدّل نفس الرسالة مكانها عند التنقّل بضغط الأزرار (تجربة أنعم،
  ما تتكدس رسائل)، ويرسل رسالة جديدة فقط لو الاستدعاء من رسالة نصية مباشرة.
- back_row: صف جاهز لزر "🔙 رجوع" يُضاف لأي InlineKeyboardMarkup.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest


async def send_reply(update, context, text: str, reply_markup: InlineKeyboardMarkup = None):
    if update.callback_query:
        await update.callback_query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def nav_render(update, context, text: str, reply_markup: InlineKeyboardMarkup = None):
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        except BadRequest:
            # مثلًا "Message is not modified" لو نفس النص بالضبط — نتجاهلها بأمان.
            pass
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


def back_row(callback_data: str, label: str = "🔙 رجوع"):
    return [InlineKeyboardButton(label, callback_data=callback_data)]
