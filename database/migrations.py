"""نظام تتبع نسخة قاعدة البيانات لدعم الترقية الآمنة لقواعد بيانات موجودة مسبقًا
(بدون فقدان بيانات) عند تحديث الكود على جهاز فيه wallet.db قديمة."""
from database.db import get_conn

CURRENT_VERSION = 2


async def ensure_version_table():
    async with get_conn() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        cur = await conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        if not row:
            # قاعدة جديدة تمامًا: init_db() أصلًا أنشأ كل الجداول بأحدث شكل، فلا حاجة لأي ترقية.
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (CURRENT_VERSION,))
        await conn.commit()


async def get_version():
    async with get_conn() as conn:
        cur = await conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cur.fetchone()
        return row["version"] if row else 0


async def _set_version(v):
    async with get_conn() as conn:
        await conn.execute("UPDATE schema_version SET version=?", (v,))
        await conn.commit()


async def _column_exists(conn, table, column):
    cur = await conn.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] async for r in cur]
    return column in cols


async def _migrate_v2_commitments():
    """
    ترقية جدول loans القديم (قبل ميزة الالتزامات الموحّدة) بإضافة الأعمدة
    الجديدة (name, auto_deduct, completed_at) وتوحيد قيمة status من 'paid'
    إلى 'completed' — بدون حذف أو فقدان أي سلفة أو استقطاع موجود مسبقًا.
    الجداول الجديدة كليًا (installments, recurring_commitments, savings_goals...)
    ينشئها init_db() تلقائيًا عبر SCHEMA (CREATE TABLE IF NOT EXISTS)، فلا حاجة
    لأي شيء هنا لها.
    """
    async with get_conn() as conn:
        if not await _column_exists(conn, "loans", "name"):
            await conn.execute("ALTER TABLE loans ADD COLUMN name TEXT")
        if not await _column_exists(conn, "loans", "auto_deduct"):
            await conn.execute("ALTER TABLE loans ADD COLUMN auto_deduct INTEGER NOT NULL DEFAULT 1")
        if not await _column_exists(conn, "loans", "completed_at"):
            await conn.execute("ALTER TABLE loans ADD COLUMN completed_at TEXT")
        await conn.commit()
        # توحيد مفردات الحالة القديمة 'paid' -> 'completed' (نفس المعنى بالضبط)
        await conn.execute("UPDATE loans SET status='completed' WHERE status='paid'")
        await conn.execute(
            "UPDATE loans SET completed_at=updated_at WHERE status='completed' AND completed_at IS NULL"
        )
        await conn.commit()


async def run_migrations():
    await ensure_version_table()
    version = await get_version()

    if version < 2:
        await _migrate_v2_commitments()
        await _set_version(2)
        version = 2

    return version
