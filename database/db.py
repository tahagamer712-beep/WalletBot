"""طبقة الوصول لقاعدة البيانات SQLite (aiosqlite). كل الاستعلامات الحساسة لمستخدم تُفلتَر بـ user_id."""
import aiosqlite
import datetime
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

import config
from database.models import (
    SCHEMA, DEFAULT_EXPENSE_CATEGORIES, DEFAULT_INCOME_CATEGORIES,
    DEFAULT_COMMITMENT_CATEGORIES, DEFAULT_SETTINGS,
)

TZ = ZoneInfo(config.TIMEZONE)


def now_str():
    return datetime.datetime.now(TZ).isoformat()


@asynccontextmanager
async def get_conn():
    conn = await aiosqlite.connect(config.DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        await conn.close()


async def init_db():
    async with get_conn() as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()
        # تصنيفات افتراضية
        for name in DEFAULT_EXPENSE_CATEGORIES:
            await conn.execute(
                "INSERT OR IGNORE INTO categories (name, type, is_active, created_at) VALUES (?,?,1,?)",
                (name, "expense", now_str()),
            )
        for name in DEFAULT_INCOME_CATEGORIES:
            await conn.execute(
                "INSERT OR IGNORE INTO categories (name, type, is_active, created_at) VALUES (?,?,1,?)",
                (name, "income", now_str()),
            )
        for name in DEFAULT_COMMITMENT_CATEGORIES:
            await conn.execute(
                "INSERT OR IGNORE INTO categories (name, type, is_active, created_at) VALUES (?,?,1,?)",
                (name, "commitment", now_str()),
            )
        for k, v in DEFAULT_SETTINGS.items():
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
        await conn.commit()


# ---------------------------- users ----------------------------

async def get_or_create_user(telegram_id: int, name: str, username: str):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                "UPDATE users SET last_seen=?, name=?, username=? WHERE telegram_id=?",
                (now_str(), name, username, telegram_id),
            )
            await conn.commit()
            return dict(row)
        role = "admin" if telegram_id == config.ADMIN_ID else "user"
        await conn.execute(
            "INSERT INTO users (telegram_id, name, username, role, is_active, created_at, last_seen) "
            "VALUES (?,?,?,?,1,?,?)",
            (telegram_id, name, username, role, now_str(), now_str()),
        )
        await conn.commit()
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row)


async def get_user_by_telegram_id(telegram_id: int):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_users():
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM users ORDER BY created_at")
        return [dict(r) for r in await cur.fetchall()]


# ------------------------- transactions -------------------------

async def insert_transaction(user_id, type_, category, amount, currency, exchange_rate,
                              amount_iqd, note, transaction_date, transaction_time, source, ai_provider):
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO transactions (user_id,type,category,amount,currency,exchange_rate,amount_iqd,"
            "note,transaction_date,transaction_time,created_at,source,ai_provider) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, type_, category, amount, currency, exchange_rate, amount_iqd, note,
             transaction_date, transaction_time, now_str(), source, ai_provider),
        )
        await conn.commit()
        return cur.lastrowid


async def get_last_transaction(user_id):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM transactions WHERE user_id=? AND is_deleted=0 ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_transaction(tx_id, user_id):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM transactions WHERE id=? AND user_id=? AND is_deleted=0", (tx_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_transaction_amount(tx_id, user_id, new_amount, new_amount_iqd):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE transactions SET amount=?, amount_iqd=? WHERE id=? AND user_id=?",
            (new_amount, new_amount_iqd, tx_id, user_id),
        )
        await conn.commit()


async def update_transaction_category(tx_id, user_id, new_category):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT category FROM transactions WHERE id=? AND user_id=?", (tx_id, user_id))
        row = await cur.fetchone()
        old_category = row["category"] if row else None
        await conn.execute(
            "UPDATE transactions SET category=? WHERE id=? AND user_id=?", (new_category, tx_id, user_id)
        )
        await conn.commit()
        return old_category


async def soft_delete_transaction(tx_id, user_id):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE transactions SET is_deleted=1 WHERE id=? AND user_id=?", (tx_id, user_id)
        )
        await conn.commit()


async def clear_user_transactions(user_id):
    """يمسح كل سجل عمليات مستخدم محدد (soft delete — نفس منطق حذف عملية وحدة)."""
    async with get_conn() as conn:
        cur = await conn.execute(
            "UPDATE transactions SET is_deleted=1 WHERE user_id=? AND is_deleted=0", (user_id,)
        )
        await conn.commit()
        return cur.rowcount


async def list_transactions(user_id, limit=10, offset=0):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM transactions WHERE user_id=? AND is_deleted=0 "
            "ORDER BY transaction_date DESC, transaction_time DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]


async def transactions_in_range(user_id, date_from, date_to, category=None, type_=None):
    q = ("SELECT * FROM transactions WHERE user_id=? AND is_deleted=0 "
         "AND transaction_date BETWEEN ? AND ?")
    params = [user_id, date_from, date_to]
    if category:
        q += " AND category=?"
        params.append(category)
    if type_:
        q += " AND type=?"
        params.append(type_)
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def sum_by_type(user_id, date_from, date_to, type_):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT COALESCE(SUM(amount_iqd),0) as total_iqd, "
            "COALESCE(SUM(CASE WHEN currency='USD' THEN amount ELSE 0 END),0) as total_usd "
            "FROM transactions WHERE user_id=? AND is_deleted=0 AND type=? "
            "AND transaction_date BETWEEN ? AND ?",
            (user_id, type_, date_from, date_to),
        )
        row = await cur.fetchone()
        return dict(row)


async def sum_by_category(user_id, date_from, date_to, type_):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT category, COUNT(*) as count, COALESCE(SUM(amount_iqd),0) as total FROM transactions "
            "WHERE user_id=? AND is_deleted=0 AND type=? AND transaction_date BETWEEN ? AND ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, type_, date_from, date_to),
        )
        return [dict(r) for r in await cur.fetchall()]


async def overall_balance(user_id):
    income = await sum_by_type(user_id, "0000-01-01", "9999-12-31", "income")
    expense = await sum_by_type(user_id, "0000-01-01", "9999-12-31", "expense")
    return income, expense


# --------------------------- categories ---------------------------

async def list_categories(type_=None, active_only=True):
    q = "SELECT * FROM categories"
    conds, params = [], []
    if type_:
        conds.append("type=?")
        params.append(type_)
    if active_only:
        conds.append("is_active=1")
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY name"
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def add_category(name, type_):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO categories (name,type,is_active,created_at) VALUES (?,?,1,?)",
            (name, type_, now_str()),
        )
        await conn.commit()


async def set_category_active(cat_id, active: bool):
    async with get_conn() as conn:
        await conn.execute("UPDATE categories SET is_active=? WHERE id=?", (1 if active else 0, cat_id))
        await conn.commit()


# ---------------------------- settings ----------------------------

async def get_setting(key, default=None):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default


async def set_setting(key, value):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        await conn.commit()


async def get_exchange_rate():
    val = await get_setting("exchange_rate", str(config.DEFAULT_EXCHANGE_RATE))
    return float(val)


# ---------------------------- api_keys ----------------------------

async def add_api_key(provider_name, encrypted_key, key_suffix):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO api_keys (provider_name, encrypted_key, key_suffix, is_active, created_at) "
            "VALUES (?,?,?,1,?)",
            (provider_name, encrypted_key, key_suffix, now_str()),
        )
        await conn.commit()


async def list_api_keys(active_only=False):
    q = "SELECT * FROM api_keys"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY provider_name"
    async with get_conn() as conn:
        cur = await conn.execute(q)
        return [dict(r) for r in await cur.fetchall()]


async def get_active_key_for_provider(provider_name):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM api_keys WHERE provider_name=? AND is_active=1 ORDER BY id DESC LIMIT 1",
            (provider_name,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_api_key_active(key_id, active: bool):
    async with get_conn() as conn:
        await conn.execute("UPDATE api_keys SET is_active=? WHERE id=?", (1 if active else 0, key_id))
        await conn.commit()


async def delete_api_key(key_id):
    async with get_conn() as conn:
        await conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
        await conn.commit()


# --------------------------- ai_providers ---------------------------

async def upsert_provider(name, priority=100, is_active=True):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT id FROM ai_providers WHERE name=?", (name,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                "UPDATE ai_providers SET priority=?, is_active=? WHERE name=?",
                (priority, 1 if is_active else 0, name),
            )
        else:
            await conn.execute(
                "INSERT INTO ai_providers (name, priority, is_active, created_at) VALUES (?,?,?,?)",
                (name, priority, 1 if is_active else 0, now_str()),
            )
        await conn.commit()


async def list_providers(active_only=False):
    q = "SELECT * FROM ai_providers"
    if active_only:
        q += " WHERE is_active=1"
    q += " ORDER BY priority ASC"
    async with get_conn() as conn:
        cur = await conn.execute(q)
        return [dict(r) for r in await cur.fetchall()]


async def set_provider_priority(name, priority):
    async with get_conn() as conn:
        await conn.execute("UPDATE ai_providers SET priority=? WHERE name=?", (priority, name))
        await conn.commit()


async def set_provider_active(name, active: bool):
    async with get_conn() as conn:
        await conn.execute("UPDATE ai_providers SET is_active=? WHERE name=?", (1 if active else 0, name))
        await conn.commit()


# ----------------------------- backups -----------------------------

async def record_backup(filename, size_bytes, status, kind="manual"):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO backups (filename, created_at, size_bytes, status, kind) VALUES (?,?,?,?,?)",
            (filename, now_str(), size_bytes, status, kind),
        )
        await conn.commit()


async def list_backups(limit=20):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM backups ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


# --------------------------- audit / ai logs ---------------------------

async def add_audit_log(admin_id, action, details=""):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO audit_logs (admin_id, action, details, created_at) VALUES (?,?,?,?)",
            (admin_id, action, details, now_str()),
        )
        await conn.commit()


async def list_audit_logs(limit=50):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def clear_audit_logs():
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM audit_logs")
        await conn.commit()
        return cur.rowcount


async def add_ai_error_log(provider_name, error, fell_back_to):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO ai_error_logs (provider_name, error, fell_back_to, created_at) VALUES (?,?,?,?)",
            (provider_name, str(error)[:500], fell_back_to, now_str()),
        )
        await conn.commit()


async def list_ai_error_logs(limit=30):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM ai_error_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def clear_ai_error_logs():
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM ai_error_logs")
        await conn.commit()
        return cur.rowcount


async def add_correction(transaction_id, message_text, old_category, new_category):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO corrections (transaction_id, message_text, old_category, new_category, created_at) "
            "VALUES (?,?,?,?,?)",
            (transaction_id, message_text, old_category, new_category, now_str()),
        )
        await conn.commit()


# ============================== الالتزامات المالية ==============================
# سلفة (loans) / قسط (installments) / التزام متكرر (recurring_commitments)
# كل نوع جدول مستقل، لكن الثلاثة تشترك بمفهوم auto_deduct وحالة موحّدة:
# 'active' | 'completed' | 'cancelled'

# ------------------------------ سلفة (loans) ------------------------------

async def create_loan(user_id, original_amount, deduction_per_salary, name=None, auto_deduct=True, note=None):
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO loans (user_id, name, original_amount, deduction_per_salary, remaining_amount, "
            "auto_deduct, status, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, name, original_amount, deduction_per_salary, original_amount,
             1 if auto_deduct else 0, "active", note, now_str(), now_str()),
        )
        await conn.commit()
        return cur.lastrowid


async def list_loans(user_id, status=None):
    q = "SELECT * FROM loans WHERE user_id=?"
    params = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_loan(loan_id, user_id):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM loans WHERE id=? AND user_id=?", (loan_id, user_id))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_loan_deduction(loan_id, user_id, new_deduction):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE loans SET deduction_per_salary=?, updated_at=? WHERE id=? AND user_id=?",
            (new_deduction, now_str(), loan_id, user_id),
        )
        await conn.commit()


async def apply_loan_deduction(loan_id, amount, transaction_id=None, kind="salary"):
    """يخصم amount من رصيد سلفة، يسجّل الاستقطاع، ويحدّث حالتها لو تسددت بالكامل. يرجع None لو السلفة غير موجودة."""
    async with get_conn() as conn:
        cur = await conn.execute("SELECT remaining_amount FROM loans WHERE id=?", (loan_id,))
        row = await cur.fetchone()
        if not row:
            return None
        actual_deducted = min(amount, row["remaining_amount"])
        new_remaining = round(row["remaining_amount"] - actual_deducted, 2)
        status = "completed" if new_remaining <= 0 else "active"
        completed_at = now_str() if status == "completed" else None
        await conn.execute(
            "UPDATE loans SET remaining_amount=?, status=?, updated_at=?, "
            "completed_at=COALESCE(completed_at, ?) WHERE id=?",
            (new_remaining, status, now_str(), completed_at, loan_id),
        )
        await conn.execute(
            "INSERT INTO loan_deductions (loan_id, transaction_id, amount, kind, created_at) VALUES (?,?,?,?,?)",
            (loan_id, transaction_id, actual_deducted, kind, now_str()),
        )
        await conn.commit()
        return {"deducted": actual_deducted, "new_remaining": new_remaining, "status": status}


async def cancel_loan(loan_id, user_id):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE loans SET status='cancelled', updated_at=? WHERE id=? AND user_id=?",
            (now_str(), loan_id, user_id),
        )
        await conn.commit()


async def list_loan_deductions(loan_id, limit=20):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM loan_deductions WHERE loan_id=? ORDER BY id DESC LIMIT ?", (loan_id, limit)
        )
        return [dict(r) for r in await cur.fetchall()]


# ------------------------------ قسط (installments) ------------------------------

async def create_installment(user_id, name, original_amount, installment_amount, auto_deduct=True):
    import math
    remaining_payments = max(1, math.ceil(original_amount / installment_amount))
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO installments (user_id, name, original_amount, installment_amount, remaining_amount, "
            "remaining_payments, auto_deduct, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, name, original_amount, installment_amount, original_amount, remaining_payments,
             1 if auto_deduct else 0, "active", now_str(), now_str()),
        )
        await conn.commit()
        return cur.lastrowid


async def list_installments(user_id, status=None):
    q = "SELECT * FROM installments WHERE user_id=?"
    params = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_installment(installment_id, user_id):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM installments WHERE id=? AND user_id=?", (installment_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def apply_installment_payment(installment_id, amount, transaction_id=None, kind="salary"):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT remaining_amount, installment_amount FROM installments WHERE id=?", (installment_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        actual = min(amount, row["remaining_amount"])
        new_remaining = round(row["remaining_amount"] - actual, 2)
        import math
        new_remaining_payments = (
            math.ceil(new_remaining / row["installment_amount"]) if row["installment_amount"] > 0 else 0
        )
        status = "completed" if new_remaining <= 0 else "active"
        completed_at = now_str() if status == "completed" else None
        await conn.execute(
            "UPDATE installments SET remaining_amount=?, remaining_payments=?, status=?, updated_at=?, "
            "completed_at=COALESCE(completed_at, ?) WHERE id=?",
            (new_remaining, new_remaining_payments, status, now_str(), completed_at, installment_id),
        )
        await conn.execute(
            "INSERT INTO installment_payments (installment_id, transaction_id, amount, kind, created_at) "
            "VALUES (?,?,?,?,?)",
            (installment_id, transaction_id, actual, kind, now_str()),
        )
        await conn.commit()
        return {"deducted": actual, "new_remaining": new_remaining, "status": status}


async def cancel_installment(installment_id, user_id):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE installments SET status='cancelled', updated_at=? WHERE id=? AND user_id=?",
            (now_str(), installment_id, user_id),
        )
        await conn.commit()


async def list_installment_payments(installment_id, limit=20):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM installment_payments WHERE installment_id=? ORDER BY id DESC LIMIT ?",
            (installment_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


# ------------------------------ التزام متكرر (recurring) ------------------------------

async def create_recurring(user_id, name, amount, category=None, frequency="monthly", auto_deduct=False):
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO recurring_commitments (user_id, name, amount, category, frequency, auto_deduct, "
            "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, name, amount, category, frequency, 1 if auto_deduct else 0, "active",
             now_str(), now_str()),
        )
        await conn.commit()
        return cur.lastrowid


async def list_recurring(user_id, status=None):
    q = "SELECT * FROM recurring_commitments WHERE user_id=?"
    params = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_recurring(recurring_id, user_id):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM recurring_commitments WHERE id=? AND user_id=?", (recurring_id, user_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def record_recurring_payment(recurring_id, amount, transaction_id=None, kind="salary"):
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO recurring_payments (recurring_id, transaction_id, amount, kind, created_at) "
            "VALUES (?,?,?,?,?)",
            (recurring_id, transaction_id, amount, kind, now_str()),
        )
        await conn.commit()


async def cancel_recurring(recurring_id, user_id):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE recurring_commitments SET status='cancelled', updated_at=? WHERE id=? AND user_id=?",
            (now_str(), recurring_id, user_id),
        )
        await conn.commit()


async def list_recurring_payments(recurring_id, limit=20):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM recurring_payments WHERE recurring_id=? ORDER BY id DESC LIMIT ?",
            (recurring_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


# ------------------------------ أهداف الادخار (savings) ------------------------------

async def create_savings_goal(user_id, name, target_amount, target_date=None):
    async with get_conn() as conn:
        cur = await conn.execute(
            "INSERT INTO savings_goals (user_id, name, target_amount, saved_amount, target_date, status, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, name, target_amount, 0, target_date, "active", now_str(), now_str()),
        )
        await conn.commit()
        return cur.lastrowid


async def list_savings_goals(user_id, status=None):
    q = "SELECT * FROM savings_goals WHERE user_id=?"
    params = [user_id]
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_savings_goal(goal_id, user_id):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM savings_goals WHERE id=? AND user_id=?", (goal_id, user_id))
        row = await cur.fetchone()
        return dict(row) if row else None


async def add_savings_amount(goal_id, amount):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT saved_amount, target_amount FROM savings_goals WHERE id=?", (goal_id,))
        row = await cur.fetchone()
        if not row:
            return None
        new_saved = round(row["saved_amount"] + amount, 2)
        status = "completed" if new_saved >= row["target_amount"] else "active"
        completed_at = now_str() if status == "completed" else None
        await conn.execute(
            "UPDATE savings_goals SET saved_amount=?, status=?, updated_at=?, "
            "completed_at=COALESCE(completed_at, ?) WHERE id=?",
            (new_saved, status, now_str(), completed_at, goal_id),
        )
        await conn.execute(
            "INSERT INTO savings_transactions (goal_id, amount, created_at) VALUES (?,?,?)",
            (goal_id, amount, now_str()),
        )
        await conn.commit()
        return {"new_saved": new_saved, "status": status}


async def cancel_savings_goal(goal_id, user_id):
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE savings_goals SET status='cancelled', updated_at=? WHERE id=? AND user_id=?",
            (now_str(), goal_id, user_id),
        )
        await conn.commit()


async def list_savings_transactions(goal_id, limit=20):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM savings_transactions WHERE goal_id=? ORDER BY id DESC LIMIT ?", (goal_id, limit)
        )
        return [dict(r) for r in await cur.fetchall()]
