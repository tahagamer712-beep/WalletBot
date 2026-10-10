"""نسخ احتياطي آمن لقاعدة SQLite أثناء التشغيل (sqlite3 backup API) + integrity check + تنظيف النسخ القديمة."""
import asyncio
import sqlite3
from pathlib import Path

import config
import database.db as db
from utils import dates


def _do_backup_sync():
    ts = dates.now().strftime("%Y-%m-%d_%H%M")
    filename = f"wallet_backup_{ts}.db"
    path = config.BACKUPS_DIR / filename

    src = sqlite3.connect(config.DB_PATH)
    dst = sqlite3.connect(str(path))
    with dst:
        src.backup(dst)  # طريقة آمنة تمنع نسخة تالفة أثناء الكتابة المتزامنة
    src.close()
    dst.close()

    check_conn = sqlite3.connect(str(path))
    result = check_conn.execute("PRAGMA integrity_check").fetchone()[0]
    check_conn.close()
    ok = result == "ok"
    return path, ok


async def create_backup(kind="manual"):
    path, ok = await asyncio.to_thread(_do_backup_sync)
    size = path.stat().st_size if path.exists() else 0
    await db.record_backup(path.name, size, "ok" if ok else "failed", kind)
    if ok:
        await cleanup_old_backups()
    return path, ok


async def cleanup_old_backups():
    keep_str = await db.get_setting("backup_keep_count", str(config.DEFAULT_BACKUP_KEEP))
    keep = int(keep_str)
    files = sorted(Path(config.BACKUPS_DIR).glob("wallet_backup_*.db"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[keep:]:
        f.unlink(missing_ok=True)


async def auto_backup_job():
    enabled = await db.get_setting("auto_backup_enabled", "1")
    if enabled != "1":
        return
    await create_backup(kind="auto")
