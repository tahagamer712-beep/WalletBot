"""الحسابات المالية المركزية — المصدر الوحيد للحقيقة.

القاعدة الذهبية: الرصيد تراكمي دائم (Carry Forward).
- الرصيد الحالي = مجموع كل الإيرادات − مجموع كل المصاريف (منذ بداية الاستخدام).
- لا يُصفَّر الرصيد أبدًا عند بداية شهر جديد.
- لا تُنشأ أي عملية وهمية لترحيل الرصيد — الرصيد المرحّل قيمة حسابية للعرض فقط.
- كل عملية تُحوَّل للدينار بسعر الصرف المحفوظ معها وقت التسجيل (amount_iqd)،
  ولا يُعاد حساب العمليات القديمة إذا تغيّر سعر الصرف لاحقًا.
- كل الدوال مفلترة بـ user_id: رصيد كل مستخدم مستقل تمامًا.

تستخدم هذه الوحدة في: شاشة الرصيد، التقارير الشهرية، المقارنات، وتصدير Excel —
حتى لا يظهر رقم مختلف في مكان عن الآخر.
"""
import database.db as db
from utils import dates


def _day_before(date_str: str) -> str:
    import datetime
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


async def balance_before(user_id: int, date_str: str) -> dict:
    """صافي كل العمليات قبل تاريخ معين (غير شامل) — يُستخدم كرصيد افتتاحي للتقارير."""
    if date_str <= "0000-01-01":
        return {"net_iqd": 0.0, "net_usd": 0.0}
    day_before = _day_before(date_str)
    income = await db.sum_by_type(user_id, "0000-01-01", day_before, "income")
    expense = await db.sum_by_type(user_id, "0000-01-01", day_before, "expense")
    return {
        "net_iqd": income["total_iqd"] - expense["total_iqd"],
        "net_usd": income["total_usd"] - expense["total_usd"],
    }


async def wallet_balance(user_id: int) -> dict:
    """الرصيد الحقيقي الحالي للمحفظة: كل الإيرادات − كل المصاريف (تراكمي دائم)."""
    income, expense = await db.overall_balance(user_id)
    return {
        "income_iqd": income["total_iqd"],
        "income_usd": income["total_usd"],
        "expense_iqd": expense["total_iqd"],
        "expense_usd": expense["total_usd"],
        "net_iqd": income["total_iqd"] - expense["total_iqd"],
        "net_usd": income["total_usd"] - expense["total_usd"],
    }


async def month_statement(user_id: int, year: int, month: int) -> dict:
    """كشف شهر كامل مع الترحيل:
    - opening_iqd: الرصيد المرحّل من نهاية الشهر السابق (قيمة حسابية فقط)
    - income_iqd / expense_iqd / net_iqd: أرقام هذا الشهر فقط
    - closing_iqd: الرصيد النهائي = المرحّل + صافي الشهر
    """
    d_from, d_to = dates.month_range(year, month)

    opening = await balance_before(user_id, d_from)
    opening_iqd = opening["net_iqd"]
    opening_usd = opening["net_usd"]

    income = await db.sum_by_type(user_id, d_from, d_to, "income")
    expense = await db.sum_by_type(user_id, d_from, d_to, "expense")
    net_iqd = income["total_iqd"] - expense["total_iqd"]
    net_usd = income["total_usd"] - expense["total_usd"]

    return {
        "year": year,
        "month": month,
        "label": dates.month_label(year, month),
        "date_from": d_from,
        "date_to": d_to,
        "opening_iqd": opening_iqd,
        "opening_usd": opening_usd,
        "income_iqd": income["total_iqd"],
        "income_usd": income["total_usd"],
        "expense_iqd": expense["total_iqd"],
        "expense_usd": expense["total_usd"],
        "net_iqd": net_iqd,
        "net_usd": net_usd,
        "closing_iqd": opening_iqd + net_iqd,
        "closing_usd": opening_usd + net_usd,
    }
