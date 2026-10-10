"""يتحقق من صحة الـ JSON القادم من AI أو Regex قبل حفظه في SQLite."""

VALID_TYPES = {"expense", "income"}
VALID_CURRENCIES = {"IQD", "USD"}
MAX_REASONABLE_IQD = 500_000_000  # حد أعلى منطقي لتفادي أخطاء تحويل ضخمة
MAX_REASONABLE_USD = 300_000


class ValidationError(Exception):
    pass


def validate_transaction(tx: dict) -> dict:
    if not isinstance(tx, dict):
        raise ValidationError("العملية ليست بصيغة صحيحة")

    type_ = tx.get("type")
    if type_ not in VALID_TYPES:
        raise ValidationError(f"نوع غير صالح: {type_}")

    amount = tx.get("amount")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValidationError("المبلغ غير رقمي")
    if amount <= 0:
        raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")

    currency = tx.get("currency", "IQD")
    if currency not in VALID_CURRENCIES:
        raise ValidationError(f"عملة غير مدعومة: {currency}")

    if currency == "IQD" and amount > MAX_REASONABLE_IQD:
        raise ValidationError("المبلغ كبير جدًا وغير منطقي (IQD)")
    if currency == "USD" and amount > MAX_REASONABLE_USD:
        raise ValidationError("المبلغ كبير جدًا وغير منطقي (USD)")

    category = tx.get("category")
    if not category or not isinstance(category, str):
        raise ValidationError("التصنيف مفقود")

    note = tx.get("note")
    if note is not None and not isinstance(note, str):
        note = str(note)

    return {
        "type": type_,
        "amount": amount,
        "currency": currency,
        "category": category.strip(),
        "note": note,
    }


def validate_payload(payload: dict) -> list:
    """payload = {'transactions': [...]}. يرجع قائمة عمليات صالحة، أو يرمي استثناء إذا كلها فاشلة."""
    if not payload or "transactions" not in payload:
        raise ValidationError("لا توجد عمليات في الرد")
    txs = payload["transactions"]
    if not isinstance(txs, list) or len(txs) == 0:
        raise ValidationError("قائمة العمليات فارغة")

    valid = []
    for tx in txs:
        try:
            valid.append(validate_transaction(tx))
        except ValidationError:
            continue
    if not valid:
        raise ValidationError("لم تجتز أي عملية التحقق")
    return valid
