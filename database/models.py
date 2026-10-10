"""تعريف جداول قاعدة البيانات (DDL) لـ SQLite."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    username TEXT,
    role TEXT NOT NULL DEFAULT 'user',       -- 'user' | 'admin'
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,                      -- 'expense' | 'income'
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,                  -- 'IQD' | 'USD'
    exchange_rate REAL NOT NULL,
    amount_iqd REAL NOT NULL,
    note TEXT,
    transaction_date TEXT NOT NULL,          -- YYYY-MM-DD (Asia/Baghdad)
    transaction_time TEXT NOT NULL,          -- HH:MM:SS
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,                    -- 'ai' | 'regex' | 'manual'
    ai_provider TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                      -- 'expense' | 'income'
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(name, type)
);

CREATE TABLE IF NOT EXISTS ai_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    key_suffix TEXT NOT NULL,                -- آخر 4 خانات للعرض فقط
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    size_bytes INTEGER,
    status TEXT NOT NULL,                    -- 'ok' | 'failed'
    kind TEXT NOT NULL DEFAULT 'manual'      -- 'manual' | 'auto'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_error_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT,
    error TEXT,
    fell_back_to TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER,
    message_text TEXT,
    old_category TEXT,
    new_category TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ============================== الالتزامات المالية ==============================
-- سلفة / قسط / التزام متكرر — كل نوع جدول مستقل، لكن كلها تشترك بمفهوم auto_deduct
-- (يُستقطع تلقائيًا عند تسجيل أي دخل بتصنيف "راتب") وبمفردات status موحّدة:
-- 'active' | 'completed' | 'cancelled'

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT,
    original_amount REAL NOT NULL,
    deduction_per_salary REAL NOT NULL,
    remaining_amount REAL NOT NULL,
    auto_deduct INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS loan_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    transaction_id INTEGER,          -- ربط بعملية الراتب المرتبطة، إن وُجدت (NULL لتسديد يدوي)
    amount REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'salary',  -- 'salary' (استقطاع تلقائي) | 'manual' (تسديد جزء يدوي)
    created_at TEXT NOT NULL,
    FOREIGN KEY(loan_id) REFERENCES loans(id)
);

CREATE TABLE IF NOT EXISTS installments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT,
    original_amount REAL NOT NULL,
    installment_amount REAL NOT NULL,
    remaining_amount REAL NOT NULL,
    remaining_payments INTEGER NOT NULL,
    auto_deduct INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS installment_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    installment_id INTEGER NOT NULL,
    transaction_id INTEGER,
    amount REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'salary',
    created_at TEXT NOT NULL,
    FOREIGN KEY(installment_id) REFERENCES installments(id)
);

CREATE TABLE IF NOT EXISTS recurring_commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT,
    frequency TEXT NOT NULL DEFAULT 'monthly',
    auto_deduct INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS recurring_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recurring_id INTEGER NOT NULL,
    transaction_id INTEGER,
    amount REAL NOT NULL,
    kind TEXT NOT NULL DEFAULT 'salary',
    created_at TEXT NOT NULL,
    FOREIGN KEY(recurring_id) REFERENCES recurring_commitments(id)
);

-- ============================== أهداف الادخار ==============================

CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    saved_amount REAL NOT NULL DEFAULT 0,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS savings_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(goal_id) REFERENCES savings_goals(id)
);

CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_loans_user_status ON loans(user_id, status);
"""

DEFAULT_EXPENSE_CATEGORIES = [
    "أكل", "مطاعم", "مشروبات", "مواصلات", "وقود", "صيانة سيارة", "تسوق",
    "أدوية", "صحة", "منزل", "صيانة منزل", "أثاث", "فواتير", "اتصالات",
    "ترفيه", "ألعاب", "تعليم", "هدايا", "عناية شخصية", "صالون", "رياضة",
    "إلكترونيات", "سفر", "حيوانات أليفة", "قرطاسية", "تدخين", "مناسبات",
    "تبرعات", "تأمين", "ضرائب ورسوم", "أخرى",
]

DEFAULT_INCOME_CATEGORIES = [
    "راتب", "عمل إضافي", "تحويل", "هدية", "استثمار", "إيجار", "مكافأة",
    "بيع", "دخل آخر",
]

# تصنيفات "الالتزامات" — نوع ثالث مستقل عن expense/income، تُستخدم لتسمية نوع
# الالتزام في التقارير والـ Excel. قابلة للتعديل والإضافة متل باقي التصنيفات.
DEFAULT_COMMITMENT_CATEGORIES = [
    "سلفة", "قسط", "إيجار", "اشتراك", "فاتورة", "تأمين", "التزام آخر",
]

DEFAULT_SETTINGS = {
    "exchange_rate": "1500",
    "ai_enabled": "1",
    "regex_fallback_enabled": "1",
    "auto_backup_enabled": "1",
    "backup_keep_count": "7",
    "timezone": "Asia/Baghdad",
}
