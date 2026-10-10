"""
Regex Parser — يعمل كـ fallback عندما لا يتوفر AI أو يفشل، ويعمل أيضًا كمسار
سريع أساسي (بدون فعل صريح مثل "صرفت/استلمت") لتسجيل عملية بسرعة.

القاعدة العامة: أي رسالة فيها رقم واضح تُسجَّل دائمًا كعملية — حتى لو الكلمة
المرافقة غير معروفة (تُحفظ يومها تحت تصنيف "أخرى"/"دخل آخر" مع الكلمة الأصلية
كملاحظة، بدل رفض الرسالة). الرفض يصير فقط إذا ماكو رقم بالرسالة إطلاقًا.
"""
import re

from database.models import DEFAULT_INCOME_CATEGORIES

EXPENSE_VERBS = ["صرفت", "صرفـت", "دفعت", "اشتريت", "شريت", "دزيت", "خسرت"]
INCOME_VERBS = ["استلمت", "استلمـت", "وصلني", "وصلتني", "قبضت", "دخل", "استلمت راتب"]

CATEGORY_SYNONYMS = {
    # أكل
    "اكل": "أكل", "أكل": "أكل", "طعام": "أكل", "غداء": "أكل", "عشاء": "أكل",
    "فطور": "أكل", "قهوة": "أكل", "مطعم": "أكل", "كافيه": "أكل",
    # مشروبات (كحولية وغير كحولية)
    "ويسكي": "مشروبات", "بيرة": "مشروبات", "فودكا": "مشروبات", "عرك": "مشروبات",
    "خمر": "مشروبات", "نبيذ": "مشروبات", "مشروبات": "مشروبات", "كولا": "مشروبات",
    "ببسي": "مشروبات", "سفن أب": "مشروبات", "عصير": "مشروبات", "مشروب": "مشروبات",
    # مواصلات
    "تاكسي": "مواصلات", "تكسي": "مواصلات", "باص": "مواصلات", "مواصلات": "مواصلات",
    "كرايه": "مواصلات", "أجرة": "مواصلات", "اجره": "مواصلات",
    # وقود
    "بنزين": "وقود", "وقود": "وقود", "كازخانة": "وقود",
    # تسوق
    "تسوق": "تسوق", "ملابس": "تسوق", "شراء": "تسوق", "سوق": "تسوق",
    # أدوية
    "دواء": "أدوية", "أدوية": "أدوية", "ادويه": "أدوية", "صيدلية": "أدوية",
    # منزل
    "بيت": "منزل", "منزل": "منزل", "ايجار": "منزل", "إيجار": "منزل",
    # فواتير
    "فاتورة": "فواتير", "فواتير": "فواتير", "كهرباء": "فواتير", "ماء": "فواتير", "مي": "فواتير",
    # اتصالات
    "موبايل": "اتصالات", "رصيد": "اتصالات", "نت": "اتصالات", "انترنت": "اتصالات",
    # ترفيه
    "ترفيه": "ترفيه", "سينما": "ترفيه", "العاب": "ترفيه",
    # تعليم
    "تعليم": "تعليم", "مدرسة": "تعليم", "جامعة": "تعليم", "كورس": "تعليم",
    # هدايا
    "هدية": "هدايا", "هدايا": "هدايا",
    # مطاعم (أكل بره البيت — مختلف عن بقالة/أكل بيتي)
    "رستوران": "مطاعم", "مطعم فخم": "مطاعم", "دليفري": "مطاعم", "توصيل اكل": "مطاعم",
    # صيانة سيارة
    "صيانة": "صيانة سيارة", "ميكانيكي": "صيانة سيارة", "كراج": "صيانة سيارة",
    "بطارية سيارة": "صيانة سيارة", "تواير": "صيانة سيارة", "زيت سيارة": "صيانة سيارة",
    # صحة (زيارة طبيب/مستشفى — مختلف عن أدوية)
    "دكتور": "صحة", "طبيب": "صحة", "مستشفى": "صحة", "عيادة": "صحة", "تحليل": "صحة",
    "اشعة": "صحة", "اسنان": "صحة",
    # صيانة منزل
    "كهربائي": "صيانة منزل", "سباك": "صيانة منزل", "نجار": "صيانة منزل", "دهان": "صيانة منزل",
    # أثاث
    "اثاث": "أثاث", "موبيليا": "أثاث", "كنب": "أثاث", "سرير": "أثاث",
    # ألعاب
    "ستيم": "ألعاب", "بلايستيشن": "ألعاب", "لعبة": "ألعاب", "قيمنق": "ألعاب",
    # عناية شخصية
    "عطر": "عناية شخصية", "مكياج": "عناية شخصية", "كريم": "عناية شخصية", "شامبو": "عناية شخصية",
    # صالون
    "حلاقة": "صالون", "حلاق": "صالون", "صالون": "صالون",
    # رياضة
    "جيم": "رياضة", "نادي رياضي": "رياضة", "رياضة": "رياضة",
    # إلكترونيات
    "موبايل جديد": "إلكترونيات", "لابتوب": "إلكترونيات", "ايفون": "إلكترونيات",
    "سماعات": "إلكترونيات", "شاحن": "إلكترونيات",
    # سفر
    "طيارة": "سفر", "فندق": "سفر", "تذكرة سفر": "سفر", "سفرة": "سفر", "بلد": "سفر",
    # حيوانات أليفة
    "قطة": "حيوانات أليفة", "كلب": "حيوانات أليفة", "اكل حيوانات": "حيوانات أليفة",
    # قرطاسية
    "كتاب": "قرطاسية", "قلم": "قرطاسية", "دفتر": "قرطاسية",
    # تدخين
    "سيجارة": "تدخين", "دخان": "تدخين", "معسل": "تدخين", "ارجيلة": "تدخين",
    # مناسبات
    "عرس": "مناسبات", "خطوبة": "مناسبات", "عزيمة": "مناسبات",
    # تبرعات
    "تبرع": "تبرعات", "صدقة": "تبرعات", "زكاة": "تبرعات",
    # تأمين
    "تأمين": "تأمين", "تامين": "تأمين",
    # ضرائب ورسوم
    "ضريبة": "ضرائب ورسوم", "رسوم": "ضرائب ورسوم", "كمرك": "ضرائب ورسوم",
    # دخل
    "راتب": "راتب", "معاش": "راتب", "اضافي": "عمل إضافي", "إضافي": "عمل إضافي",
    "تحويل": "تحويل", "حوالة": "تحويل", "استثمار": "استثمار", "ارباح": "استثمار",
    "مكافأة": "مكافأة", "بونص": "مكافأة", "بيع": "بيع",
}

INCOME_CATEGORY_NAMES = set(DEFAULT_INCOME_CATEGORIES)  # {راتب, عمل إضافي, تحويل, هدية, دخل آخر}

# أرقام مكتوبة بالكلمات الشائعة (ألف/الف)
THOUSAND_WORDS = ["الف", "ألف", "آلاف"]

AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(الف|ألف|آلاف)?", re.UNICODE)
USD_MARKERS = ["$", "دولار", "دولارات"]

# تحويل الأرقام العربية-الهندية (٠-٩) إلى أرقام عادية حتى تفهمها AMOUNT_RE
_ARABIC_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _normalize_digits(text: str) -> str:
    return text.translate(_ARABIC_DIGITS_MAP)


def _normalize(text: str) -> str:
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ـ", "")
    text = text.replace("ى", "ي")  # ألف مقصورة <-> ياء (تبديل شائع جدًا بالكتابة السريعة)
    return text


def _compact_form(word: str) -> str:
    """
    يوحّد أشكال الأخطاء الإملائية الشائعة جدًا بالعامية العراقية عند الكتابة
    السريعة، بدون فتح باب fuzzy matching عام (خطر لأنه يقارب كلمات مختلفة
    المعنى، تحقّقنا من هذا فعليًا قبل اعتماد هذا الأسلوب المضبوط بدله):
    - ة/ه بنهاية الكلمة ("صيدليه" -> "صيدلية")
    - ألف داخلية زايدة ("بانزين" -> "بنزين")
    مطابقة القاموس المضغوط الناتج تبقى exact-lookup (O(1))، مو تقدير تشابه —
    صفر مجازفة إضافية على مطابقة exact substring الأصلية.
    """
    w = _normalize(word)
    if w.endswith("ه"):
        w = w[:-1] + "ة"
    if len(w) > 2:
        w = w[0] + w[1:].replace("ا", "")
    return w


# يُبنى مرة وحدة عند تحميل الموديول — تحققنا مسبقًا أن هذا التوحيد لا يسبب أي
# تصادم بين تصنيفات مختلفة داخل CATEGORY_SYNONYMS (أول كلمة تفوز لو تصادمت
# كلمتان على نفس الشكل المضغوط، وهذا لا يحدث فعليًا بالقاموس الحالي).
_COMPACT_SYNONYMS = {}
for _word, _cat in CATEGORY_SYNONYMS.items():
    _COMPACT_SYNONYMS.setdefault(_compact_form(_word), _cat)


def _detect_type(text: str) -> str:
    """يرجع 'income'/'expense' لو لقى فعلًا صريحًا، أو None لو ماكو فعل (يُحسم لاحقًا من التصنيف)."""
    for v in INCOME_VERBS:
        if v in text:
            return "income"
    for v in EXPENSE_VERBS:
        if v in text:
            return "expense"
    return None


def _detect_currency(chunk: str) -> str:
    for marker in USD_MARKERS:
        if marker in chunk:
            return "USD"
    return "IQD"


def _detect_category(chunk: str) -> str:
    norm = _normalize(chunk)
    # 1) مطابقة دقيقة أولًا (الأسرع والأدق — الكلمة السليمة إملائيًا)
    for word, cat in CATEGORY_SYNONYMS.items():
        if _normalize(word) in norm:
            return cat
    # 2) ماكو تطابق دقيق -> جرب كل كلمة بالرسالة بعد توحيد الأخطاء الإملائية
    #    الشائعة (تقطيع الكلمات أولًا يمنع أي تطابق عرضي عبر حدود كلمتين)
    for token in re.findall(r"[\u0600-\u06FF]+", chunk):
        compact = _compact_form(token)
        if compact in _COMPACT_SYNONYMS:
            return _COMPACT_SYNONYMS[compact]
    return None


def _amount_value(num_str: str, has_thousand: bool) -> float:
    val = float(num_str.replace(",", "."))
    if has_thousand:
        val *= 1000
    return val


def _extract_note_word(text: str, amount_match) -> str:
    """
    يستخرج الكلمة/الكلمات المتبقية بعد حذف الرقم والفعل ورموز العملة — تُستخدم
    كملاحظة عند عدم معرفة تصنيف الكلمة (مثلًا 'ببسي' في '250 ببسي').
    """
    working = text
    for v in EXPENSE_VERBS + INCOME_VERBS:
        working = working.replace(v, " ")
    working = working.replace(amount_match.group(0), " ")
    for marker in USD_MARKERS:
        working = working.replace(marker, " ")
    working = re.sub(r"[،,؟!.]", " ", working)
    tokens = [t.strip() for t in working.split() if t.strip()]
    return " ".join(tokens) if tokens else None


def parse_single(text: str, exchange_rate: float):
    """
    يحاول استخراج عملية واحدة (النمط الأشيع). يعمل بوجود فعل صريح ("صرفت 500 اكل")
    أو بدونه ("500 اكل" أو "200 الف راتب") — النوع (مصروف/دخل) يُحدَّد من الفعل
    إن وُجد، وإلا من التصنيف نفسه (لو كان من تصنيفات الدخل المعروفة).
    """
    m = AMOUNT_RE.search(text)
    if not m:
        return None  # ماكو رقم إطلاقًا -> مو عملية مالية

    type_ = _detect_type(text)
    amount = _amount_value(m.group(1), bool(m.group(2)))
    currency = _detect_currency(text)
    category = _detect_category(text)

    note = None
    if category is None:
        # كلمة غير معروفة -> نسجلها تحت "أخرى" (أو "دخل آخر" لو دخل) بدل الرفض،
        # ونحفظ الكلمة الأصلية كملاحظة حتى يقدر المستخدم يصححها لاحقًا.
        note = _extract_note_word(text, m)
        category = "دخل آخر" if type_ == "income" else "أخرى"

    if type_ is None:
        type_ = "income" if category in INCOME_CATEGORY_NAMES else "expense"

    return {
        "type": type_,
        "amount": amount,
        "currency": currency,
        "category": category,
        "note": note,
    }


def parse_multi(text: str, exchange_rate: float):
    """
    يحاول التعرف على أكثر من عملية بنفس الرسالة، مثال:
    'اليوم صرفت 35 الف، 10 اكل و15 بنزين و10 ملابس'
    يبحث عن كل زوج (رقم + تصنيف معروف) على حدة، ويتجاهل الرقم الإجمالي بدون
    تصنيف ملاصق. أجزاء بتصنيف غير معروف تُتجاهَل هنا (وليس تُحوَّل لـ"أخرى")
    لتفادي تسجيل عمليات وهمية من كلمات الجملة العامة (مثل "اليوم"، "صرفت").
    إذا كان هناك رقم إجمالي بصيغة "الف" في بداية الرسالة ومجموع الأجزاء (بدون
    ضرب) يساويه بعد ضربه بالألف، تُفترض نفس الوحدة (الألف) لكل الأجزاء.
    """
    type_ = _detect_type(text) or "expense"
    total_match = AMOUNT_RE.search(text)
    total_value = None
    if total_match and total_match.group(2):
        total_value = _amount_value(total_match.group(1), True)

    parts = re.split(r"[،,]|(?:\sو)", text)
    raw_results = []
    for part in parts:
        m = AMOUNT_RE.search(part)
        if not m:
            continue
        category = _detect_category(part)
        if not category:
            continue
        amount = _amount_value(m.group(1), bool(m.group(2)))
        currency = _detect_currency(part)
        raw_results.append({
            "type": type_, "amount": amount, "currency": currency,
            "category": category, "note": None,
        })

    if len(raw_results) < 2:
        return None

    if total_value:
        raw_sum = sum(r["amount"] for r in raw_results if r["currency"] == "IQD")
        if abs(raw_sum * 1000 - total_value) < 0.01:
            for r in raw_results:
                if r["currency"] == "IQD":
                    r["amount"] *= 1000

    return raw_results


def parse(text: str, exchange_rate: float):
    """نقطة الدخول: يرجع dict فيه transactions: [...] أو None (مو عملية مالية إطلاقًا)."""
    text = _normalize_digits(text)

    multi = parse_multi(text, exchange_rate)
    if multi:
        return {"transactions": multi}

    single = parse_single(text, exchange_rate)
    if single is None:
        return None
    return {"transactions": [single]}
