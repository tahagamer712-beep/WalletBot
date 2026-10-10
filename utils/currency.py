"""تحويل العملات. سعر الصرف يُحفظ مع كل عملية ولا يتغيّر بأثر رجعي."""


def to_iqd(amount: float, currency: str, exchange_rate: float) -> float:
    if currency == "USD":
        return round(amount * exchange_rate, 2)
    return round(amount, 2)


def fmt_iqd(amount: float) -> str:
    return f"{amount:,.0f} د.ع"


def fmt_usd(amount: float) -> str:
    return f"{amount:,.2f}$"


def fmt_amount(amount: float, currency: str) -> str:
    return fmt_usd(amount) if currency == "USD" else fmt_iqd(amount)
