# Decision Rules

> منطق دقیق و ترتیب اولویت قوانین موتور تصمیم (`decide()` در [[entities/next-best-action-engine]]). ترتیب پایین به معنای اولویت پایین‌تر است — اولین قانونی که match شود، تصمیم نهایی است.

## چرا rule-based نه ML
خرده‌فروش ایرانی به جعبه‌سیاه اعتماد نمی‌کند که margin و رابطه با مشتری‌اش را دستش بدهد. هر تصمیم یک `reason_fa` انسان‌خوان دارد. این اعتماد پیش‌نیاز رفتن به فاز ۲ (یادگیری وزن‌ها) است — [[concepts/architecture-pipeline]].

## ترتیب قوانین
1. **`do_not_disturb` == true** → `suppress`, بدون پیام. override قطعی روی همه‌چیز.
2. **شکایت در ۴۵ روز اخیر** → `care`. رسیدگی به رضایت، نه فروش.
3. **سبد رهاشده در ۳ روز اخیر** — بسته به سیگنال مکالمه:
   - سابقه‌ی پرسش پرداخت **یا** `avg_order_value ≥ 1,200,000` تومان → `bnpl` (اقساط به‌جای تخفیف)
   - سابقه‌ی پرسش هزینه‌ی ارسال → `free_shipping`
   - حساسیت به قیمت و **غیر VIP** → `cashback` (margin کمتر آسیب می‌بیند از تخفیف مستقیم)
   - در غیر این صورت → `reminder` ساده، بدون تخفیف
4. **ریسک ریزش بالا** (`churn_risk_ratio > 1.6`، یعنی مشتری بیش از ۱.۶ برابر چرخه‌ی معمول خریدش دیر کرده):
   - VIP → `cashback` با پیام شخصی‌سازی‌شده (`vip_personal`)
   - غیر VIP → `discount_timeboxed` (محدودزمان، بازگشت سریع)
5. **کمی دیرتر از چرخه** (`1.0 < ratio ≤ 1.6`):
   - اگر خسته از پیام (`messages_last_30d ≥ 4`) → `monitor` (صبر، بدون ارسال)
   - در غیر این صورت → `reminder` ملایم
6. **فعال و وفادار** (`tier` در `vip`/`regular` و نه fatigued) → `loyalty_no_discount` (دسترسی زودهنگام به‌جای تخفیف، برای حفظ margin)
7. **پیش‌فرض** (هیچ سیگنالی) → `monitor`، بدون پیام.

## تعریف معیارها
- `loyalty_tier`: `total_orders ≥ 15` یا `total_spend ≥ 20,000,000` → `vip`؛ `total_orders ≥ 6` → `regular`؛ در غیر این صورت `new`.
- `churn_risk_ratio` = روزهای گذشته از آخرین خرید ÷ `typical_cycle_days`.
- `fatigued` = `messages_last_30d ≥ 4`.

## وابستگی‌ها
- [[entities/next-best-action-engine]] — پیاده‌سازی
- [[entities/data-model]] — منبع فیلدهایی که این قوانین از آن‌ها استفاده می‌کنند

## منابع کد
- `mvp/engine/next_best_action.py:173-278` — تابع `decide()`
