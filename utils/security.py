"""
صلاحيات وأمان.

ملاحظة مهمة عن تخزين API Keys (trade-off صريح):
هذا المشروع محلي بالكامل — يعمل على هاتف المستخدم نفسه ضمن Termux، ولا يوجد
سيرفر خارجي أو مستخدمون متعددون يشاركون نفس الجهاز بشكل معتاد. حماية حقيقية
بمعنى تشفير معياري (AES/Fernet) تحتاج مكتبة `cryptography`، وهذه المكتبة على
Termux/ARM64 غالبًا لا يوجد لها wheel جاهز على PyPI لكل إصدارات Python، مما
يجبر pip على بناءها من المصدر ويتطلب Rust toolchain — بالضبط ما طلبت تجنبه.

البديل المستخدم هنا: تشويش (obfuscation) بسيط بـ XOR + Base64 باستخدام
`hashlib`/`secrets`/`base64` من المكتبة القياسية فقط (بدون أي تثبيت إضافي).
هذا **ليس تشفيرًا قويًا بالمعنى الأكاديمي** — أي شخص يملك SECRET_KEY (من ملف
.env) ويملك أيضًا نسخة قاعدة البيانات يقدر يعيد المفتاح الأصلي. لكنه يمنع:
- ظهور المفتاح كنص صريح لو انفتح ملف wallet.db بأداة عرض عادية.
- تسريبه صدفة لو شخص صوّر شاشة قاعدة بيانات أو شاركها بدون .env.

إذا احتجت حماية أقوى فعليًا (مثلاً تخزين نسخة من الـ DB على سيرفر مشترك)،
الحل الصحيح هو تشفير كامل القرص/الملف على مستوى نظام التشغيل، وليس تعقيد
هذا المشروع بمكتبة تشفير ثقيلة قد تفشل بالتثبيت على Termux.
"""
import base64
import hashlib

import config


def is_admin(telegram_id: int) -> bool:
    """كل Admin handler يجب أن يستدعي هذه الدالة قبل تنفيذ أي عملية."""
    return config.ADMIN_ID != 0 and telegram_id == config.ADMIN_ID


def _keystream(length: int) -> bytes:
    """يولّد stream بايتات بطول مطلوب من SECRET_KEY عبر SHA-256 متكرر (HKDF مبسّط يدويًا)."""
    if not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY غير موجود. تحقق من config.py (يُولَّد تلقائيًا عند أول تشغيل).")
    seed = config.SECRET_KEY.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes) -> bytes:
    stream = _keystream(len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


def encrypt_key(raw_key: str) -> str:
    """تشويش (وليس تشفيرًا قويًا) — راجع الشرح أعلى الملف."""
    data = raw_key.encode("utf-8")
    return base64.urlsafe_b64encode(_xor(data)).decode("ascii")


def decrypt_key(stored_value: str) -> str:
    data = base64.urlsafe_b64decode(stored_value.encode("ascii"))
    return _xor(data).decode("utf-8")


def mask_key(raw_key: str) -> str:
    suffix = raw_key[-4:] if len(raw_key) >= 4 else raw_key
    return "•" * 8 + suffix


def assert_user_owns(row_user_id: int, expected_user_id: int):
    """حارس إضافي: لا يسمح لأي استعلام بإرجاع بيانات مستخدم آخر."""
    if row_user_id != expected_user_id:
        raise PermissionError("محاولة وصول لبيانات مستخدم آخر مرفوضة.")
