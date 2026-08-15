# API

> لایه‌ی FastAPI که موتور تصمیم را در معرض HTTP قرار می‌دهد.

## مسئولیت‌ها
- `GET /` — health check ساده.
- `GET /next-best-action` — تصمیم برای همه‌ی مشتریان.
- `GET /next-best-action/{customer_id}` — تصمیم برای یک مشتری؛ در نبود مشتری، ۴۰۴ با پیام فارسی برمی‌گرداند.

## اجرا
```
cd mvp
pip install -r requirements.txt
cd api && uvicorn main:app --reload --port 8000
```

## وابستگی‌ها
- [[entities/next-best-action-engine]] — منطق تصمیم که این API فقط آن را serialize می‌کند (`.__dict__`)
- [[entities/data-model]] — داده‌ای که در هر request از دیسک خوانده می‌شود (بدون caching)

## قراردادها / Edge cases
- داده‌ها (customers/cart_events/conversations) در **هر request** از فایل CSV خوانده می‌شوند — بدون cache یا دیتابیس؛ مناسب MVP، نه production در مقیاس.
- پاسخ‌ها dataclass به dict تبدیل می‌شوند (`.__dict__`)، بدون Pydantic response model صریح.

## منابع کد
- `mvp/api/main.py` — تعریف کامل API (۳ endpoint)
