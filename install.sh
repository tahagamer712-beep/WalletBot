#!/data/data/com.termux/files/usr/bin/bash
# سكربت تثبيت محفظة على Termux. شغّله من داخل مجلد المشروع:
#   bash install.sh
set -e

echo "=== تحديث الحزم ==="
pkg update -y
pkg upgrade -y

echo "=== تثبيت Python (النسخة الحالية في مستودعات Termux، بدون تحديد رقم إصدار) ==="
pkg install -y python

echo "=== ترقية pip ==="
python -m pip install --upgrade pip

echo "=== تثبيت مكتبات المشروع (كلها Pure-Python — لا حاجة لـ Rust/C/C++) ==="
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "=== إنشاء .env من .env.example ==="
  cp .env.example .env
  echo ">>> افتح ملف .env الآن واملأ BOT_TOKEN و ADMIN_ID قبل التشغيل."
else
  echo ".env موجود مسبقًا — تم تخطي هذه الخطوة."
fi

echo "=== تشغيل فحص التوافق الحقيقي (termux_check.py) ==="
python termux_check.py || {
  echo ">>> فحص التوافق أظهر مشاكل. راجع الرسائل أعلاه قبل تشغيل البوت.";
  exit 1;
}

echo ""
echo "=== كل شيء جاهز. لتشغيل البوت: ==="
echo "python bot.py"
