"""أدوات التاريخ والوقت بتوقيت بغداد (Asia/Baghdad) — عبر zoneinfo القياسية (بدون pytz)."""
import datetime
import calendar
from zoneinfo import ZoneInfo
import config

TZ = ZoneInfo(config.TIMEZONE)


def now():
    return datetime.datetime.now(TZ)


def now_date_str():
    return now().strftime("%Y-%m-%d")


def now_time_str():
    return now().strftime("%H:%M:%S")


def display_date(date_str: str) -> str:
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return d.strftime("%d/%m/%Y")


def display_time(time_str: str) -> str:
    t = datetime.datetime.strptime(time_str, "%H:%M:%S")
    return t.strftime("%I:%M %p").replace("AM", "ص").replace("PM", "م")


def month_range(year: int, month: int):
    first = f"{year:04d}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    last = f"{year:04d}-{month:02d}-{last_day:02d}"
    return first, last


def current_month_range():
    n = now()
    return month_range(n.year, n.month)


def previous_month_range(offset=1):
    n = now()
    month = n.month - offset
    year = n.year
    while month <= 0:
        month += 12
        year -= 1
    return month_range(year, month)


def today_range():
    d = now_date_str()
    return d, d


def year_range(year: int = None):
    year = year or now().year
    return f"{year}-01-01", f"{year}-12-31"


def month_label(year: int, month: int) -> str:
    names = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    return f"{names[month-1]} {year}"
