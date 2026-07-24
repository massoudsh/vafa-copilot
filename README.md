# وفا (Vafa) — کوپایلوت هوشمند رشد و حفظ مشتری برای خرده‌فروشی

به‌جای تخفیف کور برای همه، برای هر مشتری بهترین اقدام بعدی را پیدا می‌کنیم: چه کسی، چه زمانی، از چه کانالی، با چه پیشنهادی.

## محتوای این رپو

| بخش | توضیح | مسیر |
|---|---|---|
| پیچ‌دک | ارائه‌ی ۱۰ اسلایدی فارسی برای سرمایه‌گذار/تیم | [`outputs/vafa-pitch-deck.pdf`](outputs/vafa-pitch-deck.pdf) |
| معماری فنی | نقشه‌ی کامل سیستم از منبع داده تا ارسال پیام | [`docs/architecture.md`](docs/architecture.md) |
| MVP — موتور تصمیم | موتور rule-based و قابل‌توضیح next-best-action + داده‌ی نمونه + API | [`mvp/`](mvp/) |
| لندینگ‌پیج | صفحه‌ی معرفی محصول برای اعتبارسنجی بازار | [`landing/index.html`](landing/index.html) |

## اجرای سریع MVP

```bash
# فقط منطق موتور تصمیم (بدون نیاز به نصب چیزی، فقط Python استاندارد)
cd mvp/engine
python3 next_best_action.py

# یا از طریق API
cd mvp
pip install -r requirements.txt
cd api && uvicorn main:app --reload --port 8000
curl http://localhost:8000/next-best-action/C001
```

## دیدن لندینگ‌پیج

فایل `landing/index.html` یک صفحه‌ی استاتیک است؛ کافیست آن را در مرورگر خودتان باز کنید (نیازی به سرور نیست).

## چرا rule-based در فاز اول؟

خرده‌فروش به یک جعبه‌سیاه اعتماد نمی‌کند که margin و ارتباط با مشتری‌اش را دستش بدهد. هر خروجی موتور یک `reason_fa` دارد که دلیل تصمیم را شفاف توضیح می‌دهد. جزئیات کامل در [`docs/architecture.md`](docs/architecture.md).
