"""🤖 لوحة إدارة الذكاء الاصطناعي: API Keys، ترتيب Providers، AI Status، اختيار موديل OpenRouter المجاني. أدمن فقط."""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database.db as db
from ai.providers import PROVIDER_CLASSES, OpenRouterProvider, fetch_openrouter_free_models
from utils.security import encrypt_key, decrypt_key, mask_key, is_admin
from utils.reply import nav_render, back_row

OR_PAGE_SIZE = 8


async def show_ai_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗝️ API Keys", callback_data="adm:ai_keys"),
         InlineKeyboardButton("🔄 ترتيب Providers", callback_data="adm:ai_priority")],
        [InlineKeyboardButton("📡 AI Status", callback_data="adm:ai_status"),
         InlineKeyboardButton("🆓 موديل OpenRouter", callback_data="adm:ai_or_models:0")],
        back_row("adm:main"),
    ])
    await nav_render(update, context, "🤖 الذكاء الاصطناعي", reply_markup=kb)


async def _keys_menu_kb():
    keys = await db.list_api_keys()
    rows = []
    for k in keys:
        status = "🟢" if k["is_active"] else "🔴"
        rows.append([InlineKeyboardButton(
            f"{status} {k['provider_name']} ••••{k['key_suffix']}",
            callback_data=f"adm:ai_key_toggle:{k['id']}")])
        rows.append([
            InlineKeyboardButton("🧪 اختبار", callback_data=f"adm:ai_key_test:{k['id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"adm:ai_key_del:{k['id']}"),
        ])
    rows.append([InlineKeyboardButton("➕ إضافة مفتاح", callback_data="adm:ai_key_add")])
    rows.append(back_row("adm:ai"))
    return InlineKeyboardMarkup(rows)


async def _priority_kb():
    providers = await db.list_providers()
    rows = []
    for i, p in enumerate(providers):
        status = "🟢" if p["is_active"] else "🔴"
        label = f"{i+1}️⃣ {p['name']} {status}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"adm:ai_p_toggle:{p['name']}"),
            InlineKeyboardButton("⬆️", callback_data=f"adm:ai_p_up:{p['name']}"),
            InlineKeyboardButton("⬇️", callback_data=f"adm:ai_p_down:{p['name']}"),
        ])
    rows.append(back_row("adm:ai"))
    return InlineKeyboardMarkup(rows)


async def _status_text():
    providers = await db.list_providers()
    lines = ["🤖 AI Status"]
    for p in providers:
        key = await db.get_active_key_for_provider(p["name"])
        dot = "🟢" if (p["is_active"] and key) else "🔴"
        lines.append(f"{p['name']} {dot}")
    regex_on = await db.get_setting("regex_fallback_enabled", "1") == "1"
    lines.append(f"Regex {'🟢' if regex_on else '🔴'}")
    lines.append("\nCurrent Priority:")
    active = [p["name"] for p in providers if p["is_active"]]
    for i, name in enumerate(active, 1):
        lines.append(f"{i}. {name}")
    lines.append(f"{len(active)+1}. Regex")
    return "\n".join(lines)


async def _show_or_models(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, refresh: bool = False):
    """
    يعرض قائمة موديلات OpenRouter المجانية حصرًا (تُجلب حيًا وتُفلتَر). القائمة
    الكاملة تُخزَّن بـ context.user_data لهذا التبويب فقط، والأزرار تستخدم
    index بدل الـ model id الكامل (بعض الـ ids طويلة وتتجاوز حد callback_data
    البالغ 64 بايت بتيليجرام لو دمجناها مباشرة بالبيانات).
    """
    query = update.callback_query
    if refresh or "or_models_cache" not in context.user_data:
        await query.answer("جاري الجلب من OpenRouter...")
        key_row = await db.get_active_key_for_provider("openrouter")
        api_key = None
        if key_row:
            try:
                api_key = decrypt_key(key_row["encrypted_key"])
            except Exception:
                api_key = None
        try:
            models = await fetch_openrouter_free_models(api_key=api_key)
        except Exception as e:
            kb = InlineKeyboardMarkup([back_row("adm:ai")])
            await query.edit_message_text(f"❌ فشل جلب قائمة الموديلات من OpenRouter: {e}", reply_markup=kb)
            return
        if not models:
            kb = InlineKeyboardMarkup([back_row("adm:ai")])
            await query.edit_message_text("ماكو موديلات مجانية متوفرة حاليًا من OpenRouter.", reply_markup=kb)
            return
        context.user_data["or_models_cache"] = models
    else:
        await query.answer()

    models = context.user_data["or_models_cache"]
    current_model = await db.get_setting("openrouter_model", OpenRouterProvider.DEFAULT_MODEL)

    page = models[offset:offset + OR_PAGE_SIZE]
    rows = []
    for i, m in enumerate(page, start=offset):
        mark = "✅ " if m["id"] == current_model else ""
        rows.append([InlineKeyboardButton(f"{mark}{m['name'][:45]}", callback_data=f"adm:ai_or_pick:{i}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"adm:ai_or_models:{max(0, offset-OR_PAGE_SIZE)}"))
    if offset + OR_PAGE_SIZE < len(models):
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"adm:ai_or_models:{offset+OR_PAGE_SIZE}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data="adm:ai_or_refresh")])
    rows.append(back_row("adm:ai"))

    text = (
        f"🆓 موديلات OpenRouter المجانية ({len(models)})\n"
        f"الحالي: {current_model}\n\n"
        "اختر موديل:"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def handle_ai_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user: dict):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("للأدمن فقط.", show_alert=True)
        return
    parts = data.split(":")
    action = parts[1]

    if action == "ai_keys":
        await query.edit_message_text("🗝️ API Keys", reply_markup=await _keys_menu_kb())
        await query.answer()
        return

    if action == "ai_key_add":
        rows = [[InlineKeyboardButton(name, callback_data=f"adm:ai_key_provider:{name}")]
                for name in PROVIDER_CLASSES.keys()]
        rows.append(back_row("adm:ai_keys"))
        await query.edit_message_text("اختر المزوّد:", reply_markup=InlineKeyboardMarkup(rows))
        await query.answer()
        return

    if action == "ai_key_provider":
        provider_name = parts[2]
        context.user_data["pending"] = {"action": "admin:ai:await_key", "provider": provider_name}
        kb = InlineKeyboardMarkup([back_row("cancel:adm:ai_keys", "❌ إلغاء")])
        await query.message.reply_text(f"أرسل مفتاح API الخاص بـ {provider_name}:", reply_markup=kb)
        await query.answer()
        return

    if action == "ai_key_toggle":
        key_id = int(parts[2])
        keys = await db.list_api_keys()
        target = next((k for k in keys if k["id"] == key_id), None)
        if target:
            await db.set_api_key_active(key_id, not target["is_active"])
        await query.edit_message_text("🗝️ API Keys", reply_markup=await _keys_menu_kb())
        await query.answer()
        return

    if action == "ai_key_del":
        key_id = int(parts[2])
        await db.delete_api_key(key_id)
        await db.add_audit_log(user["telegram_id"], "deleted_api_key", str(key_id))
        await query.edit_message_text("🗝️ API Keys", reply_markup=await _keys_menu_kb())
        await query.answer()
        return

    if action == "ai_key_test":
        key_id = int(parts[2])
        keys = await db.list_api_keys()
        target = next((k for k in keys if k["id"] == key_id), None)
        if not target:
            await query.answer("غير موجود.", show_alert=True)
            return
        await query.answer("جاري الاختبار...")
        provider_class = PROVIDER_CLASSES.get(target["provider_name"])
        try:
            raw_key = decrypt_key(target["encrypted_key"])
            provider = provider_class(raw_key)
            result = await provider.parse("صرفت 1000 اكل")
            ok = "transactions" in result
            msg = "✅ المفتاح يعمل بنجاح." if ok else "⚠️ رد غير متوقع من المزوّد."
        except Exception as e:
            msg = f"❌ فشل الاختبار: {e}"
        kb = InlineKeyboardMarkup([back_row("adm:ai_keys")])
        await query.message.reply_text(msg, reply_markup=kb)
        return

    if action == "ai_priority":
        await query.edit_message_text("🔄 ترتيب Providers", reply_markup=await _priority_kb())
        await query.answer()
        return

    if action == "ai_p_toggle":
        name = parts[2]
        providers = await db.list_providers()
        target = next((p for p in providers if p["name"] == name), None)
        if target:
            await db.set_provider_active(name, not target["is_active"])
        await query.edit_message_text("🔄 ترتيب Providers", reply_markup=await _priority_kb())
        await query.answer()
        return

    if action in ("ai_p_up", "ai_p_down"):
        name = parts[2]
        providers = await db.list_providers()
        idx = next((i for i, p in enumerate(providers) if p["name"] == name), None)
        if idx is not None:
            swap_idx = idx - 1 if action == "ai_p_up" else idx + 1
            if 0 <= swap_idx < len(providers):
                a, b = providers[idx], providers[swap_idx]
                await db.set_provider_priority(a["name"], b["priority"])
                await db.set_provider_priority(b["name"], a["priority"])
        await query.edit_message_text("🔄 ترتيب Providers", reply_markup=await _priority_kb())
        await query.answer()
        return

    if action == "ai_status":
        kb = InlineKeyboardMarkup([back_row("adm:ai")])
        await query.edit_message_text(await _status_text(), reply_markup=kb)
        await query.answer()
        return

    if action == "ai_or_models":
        offset = int(parts[2])
        await _show_or_models(update, context, offset=offset)
        return

    if action == "ai_or_refresh":
        context.user_data.pop("or_models_cache", None)
        await _show_or_models(update, context, offset=0, refresh=True)
        return

    if action == "ai_or_pick":
        idx = int(parts[2])
        models = context.user_data.get("or_models_cache", [])
        if idx >= len(models):
            await query.answer("انتهت صلاحية القائمة، اضغط 🔄 تحديث القائمة.", show_alert=True)
            return
        model = models[idx]
        await db.set_setting("openrouter_model", model["id"])
        await db.add_audit_log(user["telegram_id"], "changed_openrouter_model", model["id"])
        kb = InlineKeyboardMarkup([back_row("adm:ai")])
        await query.answer("✅ تم الحفظ")
        await query.edit_message_text(
            f"✅ تم اختيار موديل OpenRouter:\n{model['name']}\n({model['id']})", reply_markup=kb
        )
        return

    await query.answer()


async def handle_pending_text(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict, text: str, user: dict) -> bool:
    if pending.get("action") != "admin:ai:await_key":
        return False
    provider_name = pending["provider"]
    raw_key = text.strip()
    encrypted = encrypt_key(raw_key)
    suffix = raw_key[-4:] if len(raw_key) >= 4 else raw_key
    await db.add_api_key(provider_name, encrypted, suffix)

    providers = await db.list_providers()
    if not any(p["name"] == provider_name for p in providers):
        next_priority = (max((p["priority"] for p in providers), default=0) + 1)
        await db.upsert_provider(provider_name, priority=next_priority, is_active=True)

    await db.add_audit_log(user["telegram_id"], "added_api_key", provider_name)
    kb = InlineKeyboardMarkup([back_row("adm:ai_keys")])
    await update.message.reply_text(f"✅ تم حفظ مفتاح {provider_name}\n{mask_key(raw_key)}", reply_markup=kb)
    context.user_data.pop("pending", None)
    return True
