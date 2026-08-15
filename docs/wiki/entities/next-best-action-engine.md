# Next-Best-Action Engine

> موتور rule-based قابل‌توضیح که برای هر مشتری یک اقدام بعدی (کانال + پیام + دلیل) تولید می‌کند.

## مسئولیت‌ها
- خواندن داده‌ی مشتری، رویدادهای سبد خرید و تاریخچه‌ی مکالمه.
- محاسبه‌ی سیگنال‌ها: نرخ ریسک ریزش (`churn_risk_ratio`)، رده‌ی وفاداری (`loyalty_tier`)، حساسیت به قیمت/ارسال/پرداخت از روی intent مکالمات، سبد رهاشده‌ی تازه (≤۳ روز)، خستگی از پیام (`messages_last_30d >= 4`).
- انتخاب کانال ارسال با فالبک بر اساس opt-in (`pick_channel`).
- تولید `NextBestAction` با `action_type`, `channel`, `message_fa`, `reason_fa`, `urgency`, `context`.

## ترتیب اولویت تصمیم (خلاصه)
جزئیات کامل قوانین: [[concepts/decision-rules]].
1. `do_not_disturb` → `suppress` (override قطعی، هیچ پیامی ارسال نمی‌شود)
2. شکایت اخیر (≤۴۵ روز) → `care`
3. سبد رهاشده‌ی تازه → `bnpl` / `free_shipping` / `cashback` / `reminder` (بسته به سیگنال)
4. ریسک ریزش بالا (>۱.۶× چرخه) → `cashback` (VIP) یا `discount_timeboxed`
5. کمی دیرتر از چرخه → `monitor` (اگر fatigued) یا `reminder`
6. مشتری فعال/وفادار → `loyalty_no_discount`
7. پیش‌فرض → `monitor`

## قالب‌های پیام
هر `action_type` یک قالب فارسی در `MESSAGE_TEMPLATES` دارد (care, reminder, free_shipping, cashback, bnpl, discount_timeboxed, loyalty_no_discount, vip_personal). `monitor` و `suppress` پیام تولید نمی‌کنند.

## وابستگی‌ها
- [[entities/data-model]] — ساختار CSVهایی که موتور می‌خواند
- [[entities/api]] — لایه‌ای که این موتور را در معرض HTTP قرار می‌دهد
- [[concepts/decision-rules]] — منطق کامل و دلیل هر قانون

## قراردادها / Edge cases
- تاریخ «امروز» ثابت و hardcode است (`TODAY = date(2026, 7, 24)`) — برای دمو/داده‌ی نمونه؛ در production باید `date.today()` شود.
- `do_not_disturb` همیشه اولویت اول و override قطعی روی همه‌ی قوانین دیگر است.
- اگر مشتری در هیچ کانالی opt-in نداشته باشد، `pick_channel` مقدار `"none"` برمی‌گرداند (پیام تولید می‌شود ولی کانال ارسال معتبر نیست — باید در لایه‌ی ارسال چک شود).

## منابع کد
- `mvp/engine/next_best_action.py` — کل منطق (load, scoring, decide, run_all)
- `mvp/engine/next_best_action.py:173` — تابع اصلی `decide()`
