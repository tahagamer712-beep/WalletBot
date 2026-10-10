"""استعادة قاعدة البيانات من ملف .db مرفوع، مع نسخة احتياطية تلقائية قبل الاستبدال ورجوع تلقائي عند الفشل."""
import shutil
import sqlite3
from pathlib import Path

import config
from backup.backup import create_backup

REQUIRED_TABLES = {"users", "transactions", "categories"}


def _validate_sync(path: str) -> tuple[bool, str]:
    try:
        conn = sqlite3.connect(path)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            conn.close()
            return False, "integrity_check فشل"
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        conn.close()
        if not REQUIRED_TABLES.issubset(tables):
            return False, "الملف لا يحتوي جداول محفظة الصحيحة"
        return True, "ok"
    except Exception as e:
        return False, str(e)


async def restore_from_file(uploaded_path: str):
    ok, msg = _validate_sync(uploaded_path)
    if not ok:
        return False, f"❌ الملف غير صالح: {msg}"

    # 1) نسخة احتياطية من القاعدة الحالية قبل أي استبدال
    pre_backup_path, pre_ok = await create_backup(kind="pre_restore")
    if not pre_ok:
        return False, "❌ فشل أخذ نسخة احتياطية قبل الاستعادة — تم إلغاء العملية لحمايتك."

    try:
        shutil.copy(uploaded_path, config.DB_PATH)
        ok2, msg2 = _validate_sync(config.DB_PATH)
        if not ok2:
            raise RuntimeError(msg2)
        return True, "✅ تمت استعادة قاعدة البيانات بنجاح."
    except Exception as e:
        # فشل الاستبدال → الرجوع للنسخة القديمة
        shutil.copy(pre_backup_path, config.DB_PATH)
        return False, f"❌ فشلت الاستعادة وتم الرجوع للنسخة القديمة تلقائيًا: {e}"
