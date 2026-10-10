"""اختبارات الرصيد التراكمي الدائم (Carry Forward).

تستخدم تواريخ ثابتة تمامًا — لا تعتمد على تاريخ اليوم — حتى تكون النتائج
قابلة لإعادة التشغيل في أي وقت.

السيناريو (من متطلبات المستخدم):
  الشهر 1: راتب 750,000 / مصاريف 450,000 → صافي 300,000
  الشهر 2: مرحّل 300,000 + راتب 750,000 − مصاريف 500,000 → نهائي 550,000
  الشهر 3: مرحّل 550,000 + راتب 750,000 − مصاريف 600,000 → نهائي 700,000

التشغيل:
    python tests/test_carry_forward.py
"""
import asyncio
import sys
import tempfile
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config

_tmp = tempfile.mkdtemp(prefix="wallet_test_")
config.DB_PATH = str(Path(_tmp) / "test_wallet.db")

import database.db as db
from reports.balance import wallet_balance, balance_before, month_statement
from utils.currency import to_iqd

RATE = 1500.0
PASSED = []
FAILED = []


def check(name, actual, expected):
    ok = abs(actual - expected) < 0.01
    (PASSED if ok else FAILED).append(name)
    print(f"{'✅' if ok else '❌'} {name}: got {actual:,.0f}, expected {expected:,.0f}")


async def add_tx(user_id, type_, amount, currency, date, category=None):
    category = category or ("راتب" if type_ == "income" else "أكل")
    rate = RATE if currency == "USD" else 1.0
    amount_iqd = to_iqd(amount, currency, rate)
    await db.insert_transaction(
        user_id, type_, category, amount, currency, rate, amount_iqd,
        "", date, "12:00:00", "manual", None,
    )


async def seed_user1(uid):
    # الشهر 1 — 2026-01
    await add_tx(uid, "income", 750000, "IQD", "2026-01-05")
    await add_tx(uid, "expense", 200000, "IQD", "2026-01-10")
    await add_tx(uid, "expense", 250000, "IQD", "2026-01-20")
    # الشهر 2 — 2026-02
    await add_tx(uid, "income", 750000, "IQD", "2026-02-05")
    await add_tx(uid, "expense", 500000, "IQD", "2026-02-15")
    # الشهر 3 — 2026-03
    await add_tx(uid, "income", 750000, "IQD", "2026-03-05")
    await add_tx(uid, "expense", 600000, "IQD", "2026-03-18")


def stub_telegram():
    tg = types.ModuleType("telegram")
    tg.Update = object
    tg.InlineKeyboardMarkup = object
    tg.InlineKeyboardButton = object
    tg_ext = types.ModuleType("telegram.ext")

    class _ContextTypes:
        DEFAULT_TYPE = object

    tg_ext.ContextTypes = _ContextTypes
    tg_err = types.ModuleType("telegram.error")
    tg_err.BadRequest = Exception
    sys.modules["telegram"] = tg
    sys.modules["telegram.ext"] = tg_ext
    sys.modules["telegram.error"] = tg_err


def excel_summary_values(wb):
    """يقرأ قيم قسم الملخص من ورقة Excel المبنية."""
    ws = wb.active
    vals = {}
    for row in ws.iter_rows(values_only=True):
        if row and isinstance(row[0], str) and row[1] is not None and isinstance(row[1], (int, float)):
            vals[row[0].strip()] = row[1]
    return vals


async def main():
    await db.init_db()
    u1 = await db.get_or_create_user(111001, "taha", "taha")
    u2 = await db.get_or_create_user(222002, "sara", "sara")
    u3 = await db.get_or_create_user(333003, "ali", "ali")
    uid1, uid2, uid3 = u1["id"], u2["id"], u3["id"]
    await seed_user1(uid1)

    # ---------- 1: الرصيد لا يتغير بمجرد دخول شهر جديد ----------
    bal = await wallet_balance(uid1)
    check("1- الرصيد التراكمي الكلي", bal["net_iqd"], 700000)
    stmt4 = await month_statement(uid1, 2026, 4)
    check("1- شهر فارغ: المرحّل = 700,000", stmt4["opening_iqd"], 700000)
    check("1- شهر فارغ: النهائي = 700,000", stmt4["closing_iqd"], 700000)

    # ---------- 2: رصيد الشهر 1 يظهر كمرحّل في الشهر 2 ----------
    stmt1 = await month_statement(uid1, 2026, 1)
    stmt2 = await month_statement(uid1, 2026, 2)
    check("2- صافي الشهر 1 = 300,000", stmt1["net_iqd"], 300000)
    check("2- مرحّل الشهر 2 = 300,000", stmt2["opening_iqd"], 300000)

    # ---------- 3+4: راتب ومصاريف الشهر 2 على الرصيد المرحّل ----------
    check("3- دخل الشهر 2 (فقط) = 750,000", stmt2["income_iqd"], 750000)
    check("4- مصروف الشهر 2 (فقط) = 500,000", stmt2["expense_iqd"], 500000)
    check("3/4- صافي الشهر 2 = 250,000", stmt2["net_iqd"], 250000)
    check("3/4- نهائي الشهر 2 = 550,000", stmt2["closing_iqd"], 550000)

    # ---------- 5: التقرير الشهري يعرض أرقام الشهر + المرحّل ----------
    stmt3 = await month_statement(uid1, 2026, 3)
    check("5- مرحّل الشهر 3 = 550,000", stmt3["opening_iqd"], 550000)
    check("5- دخل الشهر 3 (فقط) = 750,000", stmt3["income_iqd"], 750000)
    check("5- مصروف الشهر 3 (فقط) = 600,000", stmt3["expense_iqd"], 600000)
    check("5- صافي الشهر 3 = 150,000", stmt3["net_iqd"], 150000)
    check("5- نهائي الشهر 3 = 700,000", stmt3["closing_iqd"], 700000)

    # ---------- 6: Excel يعطي نفس أرقام البوت ----------
    stub_telegram()
    from handlers.excel import _build_workbook
    wb_month = await _build_workbook(uid1, "2026-02-01", "2026-02-28", "test")
    s = excel_summary_values(wb_month)
    check("6- Excel: المرحّل (شهر 2) = 300,000", s.get("🔄 الرصيد المرحّل (بداية الفترة)", -1), 300000)
    check("6- Excel: نهائي الفترة (شهر 2) = 550,000", s.get("✅ رصيد نهاية الفترة", -1), 550000)
    wb_all = await _build_workbook(uid1, "0000-01-01", "9999-12-31", "test")
    sa = excel_summary_values(wb_all)
    check("6- Excel (كل الأشهر): النهائي = الرصيد التراكمي 700,000",
          sa.get("✅ رصيد نهاية الفترة", -1), bal["net_iqd"])

    # ---------- 7: استقلالية المستخدمين ----------
    bal2 = await wallet_balance(uid2)
    check("7- مستخدم جديد رصيده صفر", bal2["net_iqd"], 0)
    await add_tx(uid2, "income", 100000, "IQD", "2026-02-01")
    bal2 = await wallet_balance(uid2)
    check("7- رصيد المستخدم 2 = 100,000", bal2["net_iqd"], 100000)
    bal1_again = await wallet_balance(uid1)
    check("7- رصيد المستخدم 1 لم يتأثر = 700,000", bal1_again["net_iqd"], 700000)

    # ---------- 8: لا تكرار للأموال عند إعادة التقارير ----------
    before = len(await db.transactions_in_range(uid1, "0000-01-01", "9999-12-31"))
    await month_statement(uid1, 2026, 2)
    await month_statement(uid1, 2026, 2)
    await wallet_balance(uid1)
    await _build_workbook(uid1, "2026-02-01", "2026-02-28", "test")
    after = len(await db.transactions_in_range(uid1, "0000-01-01", "9999-12-31"))
    check("8- عدد العمليات ثابت (7) بعد كل التقارير", after, before)
    check("8- = 7 عمليات", after, 7)

    # ---------- 9: سعر الصرف مثبت وقت التسجيل ----------
    await add_tx(uid3, "income", 100, "USD", "2026-01-10")
    bal3 = await wallet_balance(uid3)
    check("9- 100$ بسعر 1500 = 150,000 د.ع", bal3["income_iqd"], 150000)
    # محاكاة تغيير سعر الصرف بالإعدادات لاحقًا — يجب ألا تتغير العمليات القديمة
    await db.set_setting("exchange_rate", "1600")
    bal3_after = await wallet_balance(uid3)
    check("9- بعد تغيير السعر: الرصيد ثابت 150,000", bal3_after["income_iqd"], 150000)

    print(f"\nالنتيجة: {len(PASSED)} ناجح / {len(FAILED)} فاشل")
    if FAILED:
        print("الفاشلة:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
