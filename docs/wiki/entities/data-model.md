# Data Model

> ساختار داده‌ی نمونه‌ای که موتور تصمیم و API از آن تغذیه می‌کنند. مسیر: `mvp/data/`.

## فایل‌ها
- `customers.csv` — یک ردیف به‌ازای هر مشتری: `customer_id, name, city, last_purchase_date, total_orders, total_spend_toman, avg_order_value_toman, preferred_channel, typical_cycle_days, messages_last_30d, opt_in_sms, opt_in_whatsapp, opt_in_instagram, do_not_disturb`
- `cart_events.csv` — رویدادهای سبد خرید per customer: شامل `date, items, cart_value_toman, abandoned`
- `conversations.csv` — تاریخچه‌ی مکالمه per customer: شامل `date, intent_tag` (مقادیر شناخته‌شده: `complaint`, `price_question`, `shipping_question`, `payment_question`, ...)

## وابستگی‌ها
- [[entities/next-best-action-engine]] — تنها مصرف‌کننده‌ی این داده (توابع `load_customers`, `load_cart_events`, `load_conversations`)

## قراردادها / Edge cases
- فیلدهای boolean (`opt_in_*`, `do_not_disturb`, `abandoned`) در CSV به‌صورت رشته‌ی `"1"`/`"0"` ذخیره می‌شوند، نه `true`/`false`.
- این داده صرفاً **نمونه** است برای دمو/MVP؛ در فاز ۲ باید از فروشگاه‌ساز واقعی (وبهوک سفارش/سبد) تغذیه شود — نگاه کنید [[concepts/architecture-pipeline]].

## منابع کد
- `mvp/data/customers.csv`
- `mvp/data/cart_events.csv`
- `mvp/data/conversations.csv`
