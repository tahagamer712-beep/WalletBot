"""إعدادات المشروع - تحمّل من .env ولا تحتوي على أي secrets مباشرة."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_PATH = str(BASE_DIR / "wallet.db")
EXPORTS_DIR = BASE_DIR / "exports"
BACKUPS_DIR = BASE_DIR / "backups"
EXPORTS_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)

TIMEZONE = os.getenv("TIMEZONE", "Asia/Baghdad")

DEFAULT_EXCHANGE_RATE = float(os.getenv("DEFAULT_EXCHANGE_RATE", "1500"))

DEFAULT_BACKUP_KEEP = int(os.getenv("BACKUP_KEEP_COUNT", "7"))
AUTO_BACKUP_HOUR = int(os.getenv("AUTO_BACKUP_HOUR", "3"))  # 3 AM local time

# لا تضع أي API key هنا. المفاتيح تُدار من لوحة الأدمن وتُخزَّن في جدول api_keys.

# SECRET_KEY: يُستخدم فقط لتشويش (obfuscate) مفاتيح AI قبل حفظها في SQLite —
# حل بسيط بدون أي مكتبة خارجية (لا cryptography ولا Rust). راجع utils/security.py
# لتفاصيل الـ trade-off. يُولَّد تلقائيًا أول مرة ويُحفظ في .env حتى لا يتغيّر بين التشغيلات.
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    import secrets as _secrets
    SECRET_KEY = _secrets.token_hex(32)
    try:
        env_path = BASE_DIR / ".env"
        with open(env_path, "a", encoding="utf-8") as _f:
            _f.write(f"\nSECRET_KEY={SECRET_KEY}\n")
    except OSError:
        # إذا تعذّرت الكتابة (صلاحيات مثلاً)، يستمر التشغيل لكن المفتاح لن يثبت بين
        # عمليات إعادة التشغيل — يُفضّل ضبط SECRET_KEY يدويًا في .env في هذه الحالة.
        pass
