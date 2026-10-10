"""بناء بيانات التقرير الشهري (تُستخدم في رسائل التقرير وفي ورقة الملخص بملف Excel)."""
from utils import dates
from reports.statistics import period_summary


async def build_monthly_report(user_id, year: int, month: int):
    d_from, d_to = dates.month_range(year, month)
    summary = await period_summary(user_id, d_from, d_to)
    summary["label"] = dates.month_label(year, month)
    summary["date_from"] = d_from
    summary["date_to"] = d_to
    return summary
