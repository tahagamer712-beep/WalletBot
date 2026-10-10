"""
مزودات AI مجانية قابلة للإضافة. كل Provider يطبّق دالة parse(text) -> dict (JSON).
لا توجد API keys هنا؛ تُجلب من قاعدة البيانات (مشفّرة) عند التشغيل.
"""
import json
import re
import httpx

from ai.prompts import build_system_prompt, build_user_prompt

TIMEOUT = 15.0


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("لا يوجد JSON في رد الـ AI")
    return json.loads(raw[start:end + 1])


async def _current_system_prompt() -> str:
    """
    يبني الـ system prompt من التصنيفات الفعّالة الحالية بقاعدة البيانات —
    نفس المصدر المستخدم بلوحة الأدمن وملف Excel. استيراد database.db هنا
    (بدل أعلى الملف) يتجنّب استيراد دائري: database/db.py لا يستورد ai/*
    إطلاقًا، فماكو خطر تصادم، لكن إبقاؤه محليًا يخلي اعتماديات الموديول
    أوضح عند القراءة.
    """
    import database.db as db
    expense_cats = [c["name"] for c in await db.list_categories("expense", active_only=True)]
    income_cats = [c["name"] for c in await db.list_categories("income", active_only=True)]
    return build_system_prompt(expense_cats, income_cats)


class BaseProvider:
    name = "base"

    def __init__(self, api_key: str, client: httpx.AsyncClient = None):
        """
        client: اختياري — يُستخدم فقط للاختبار (حقن httpx.AsyncClient مبني على
        MockTransport بدل اتصال إنترنت حقيقي). عند عدم تمريره (الاستخدام الطبيعي
        من ai/router.py) يبني كل استدعاء عميل httpx حقيقي خاص به كما كان سابقًا —
        لا تغيير في السلوك الفعلي عند التشغيل الحقيقي.
        """
        self.api_key = api_key
        self._injected_client = client

    async def _post(self, url: str, **kwargs) -> dict:
        if self._injected_client is not None:
            resp = await self._injected_client.post(url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def parse(self, text: str) -> dict:
        raise NotImplementedError


class GeminiProvider(BaseProvider):
    """
    Google Gemini — طبقة مجانية سخية.

    الموديل: gemini-3.5-flash-lite (GA، الأسرع والأرخص في عائلة Gemini 3.x،
    ومُوصى به رسميًا لمهام extraction/routing/classification عالية التكرار —
    بالضبط طبيعة مهمتنا هنا: تحويل رسالة قصيرة إلى JSON مُصنَّف).

    ملاحظة migration مهمة (تحقّقتها عبر توثيق Google الحالي بتاريخ هذا التعديل):
    - gemini-1.5-flash متوقف نهائيًا (404) — تم استبداله.
    - temperature/top_p/top_k أصبحت deprecated ومُتجاهَلة بالكامل في Gemini 3.x،
      وستُرجع HTTP 400 بأجيال قادمة — لذلك أُزيلت من generationConfig هنا بدل
      تركها كـ "لا ضرر" صامت.
    - البديل الحالي هو thinkingConfig.thinkingLevel، والقيمة "minimal" هي
      الموصى بها رسميًا لمهام التصنيف/الاستخراج عالية الحجم (تعطي أعلى إنتاجية
      وأقل زمن استجابة)، وهي أيضًا القيمة الافتراضية لهذا الموديل تحديدًا —
      أُضيفت صراحةً هنا لضمان الاستقرار حتى لو غيّرت Google الافتراضي لاحقًا.
    """
    name = "gemini"
    MODEL = "gemini-3.5-flash-lite"

    async def parse(self, text: str) -> dict:
        system_prompt = await _current_system_prompt()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.MODEL}:generateContent?key={self.api_key}"
        )
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": build_user_prompt(text)}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        }
        data = await self._post(url, json=body)
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(raw)


class GroqProvider(BaseProvider):
    """Groq — استضافة نماذج مفتوحة (Llama) مجانية وسريعة جدًا."""
    name = "groq"

    async def parse(self, text: str) -> dict:
        system_prompt = await _current_system_prompt()
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {
            "model": "llama-3.1-8b-instant",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_user_prompt(text)},
            ],
        }
        data = await self._post(url, headers=headers, json=body)
        raw = data["choices"][0]["message"]["content"]
        return _extract_json(raw)


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter — يوفر نماذج مجانية (:free) بواجهة متوافقة مع OpenAI.
    الموديل قابل للاختيار من لوحة الأدمن (🤖 الذكاء الاصطناعي -> 🆓 موديلات
    OpenRouter) من قائمة تُجلب حيًا من OpenRouter وتُفلتَر للمجانية حصرًا —
    يُخزَّن الاختيار بجدول settings ("openrouter_model")، ويُقرأ هنا حيًا بكل
    استدعاء حتى يسري تغيير الأدمن فورًا بدون إعادة تشغيل البوت.
    """
    name = "openrouter"
    DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

    async def parse(self, text: str) -> dict:
        import database.db as db
        model = await db.get_setting("openrouter_model", self.DEFAULT_MODEL)
        system_prompt = await _current_system_prompt()
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_user_prompt(text)},
            ],
        }
        data = await self._post(url, headers=headers, json=body)
        raw = data["choices"][0]["message"]["content"]
        return _extract_json(raw)


async def fetch_openrouter_free_models(api_key: str = None, timeout: float = 15.0) -> list:
    """
    يجلب قائمة موديلات OpenRouter الفعلية (endpoint عام، ماكو حاجة لمفتاح)
    ويفلترها للمجانية حصرًا (pricing.prompt == 0 و pricing.completion == 0،
    أو الـ id ينتهي بـ ":free" كتأكيد إضافي). يرجع [{"id":..., "name":...}, ...]
    مرتبة بالاسم. يرمي استثناء لو فشل الاتصال — المتصل يتعامل مع الخطأ.
    """
    url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    free_models = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        pricing = m.get("pricing", {}) or {}
        try:
            prompt_price = float(pricing.get("prompt", "1") or "1")
            completion_price = float(pricing.get("completion", "1") or "1")
        except (TypeError, ValueError):
            prompt_price = completion_price = 1.0
        is_free = (prompt_price == 0 and completion_price == 0) or model_id.endswith(":free")
        if is_free and model_id:
            free_models.append({"id": model_id, "name": m.get("name") or model_id})

    free_models.sort(key=lambda m: m["name"].lower())
    return free_models


# سجل المزودات المتاحة للإضافة من لوحة الأدمن. لإضافة مزوّد جديد:
# 1) أنشئ class يطبق parse()  2) أضفه هنا بنفس الاسم المستخدم في api_keys.provider_name
PROVIDER_CLASSES = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
}
