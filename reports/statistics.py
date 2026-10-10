"""دوال إحصائية مشتركة تُستخدم في التقارير وتصدير Excel."""
import database.db as db


async def period_summary(user_id, d_from, d_to):
    income = await db.sum_by_type(user_id, d_from, d_to, "income")
    expense = await db.sum_by_type(user_id, d_from, d_to, "expense")
    expense_by_cat = await db.sum_by_category(user_id, d_from, d_to, "expense")
    income_by_cat = await db.sum_by_category(user_id, d_from, d_to, "income")
    tx_count = len(await db.transactions_in_range(user_id, d_from, d_to))
    return {
        "income_iqd": income["total_iqd"],
        "income_usd": income["total_usd"],
        "expense_iqd": expense["total_iqd"],
        "expense_usd": expense["total_usd"],
        "net_iqd": income["total_iqd"] - expense["total_iqd"],
        "expense_by_category": expense_by_cat,
        "income_by_category": income_by_cat,
        "transaction_count": tx_count,
    }
