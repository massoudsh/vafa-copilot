# Landing Page

> صفحه‌ی استاتیک معرفی محصول برای اعتبارسنجی بازار.

## Responsibilities
- معرفی محصول وفا برای بازدیدکننده/سرمایه‌گذار.
- نمایش داشبورد تعاملی نمونه با glass UI، KPIهای خلاصه، فیلتر فوریت/رسیدگی/کانال و جزئیات دلیل پیشنهاد.
- انتشار روی GitHub Pages (منبع: برنچ `master`، پوشه‌ی `/docs`).

## Interaction contract
- Dashboard data is synthetic and client-side; it intentionally does not call the API so GitHub Pages remains standalone.
- Filters update visible recommendations and KPI values; selecting a row updates the detail panel.
- `prefers-reduced-transparency` disables blur, preserving readable content on supported systems.

## دسترسی
- زنده: https://massoudsh.github.io/vafa-copilot/
- فایل اصلی محلی: `landing/index.html`
- کپی منتشرشده برای GitHub Pages: `docs/index.html` + `docs/.nojekyll`

## قراردادها / Edge cases
- `docs/index.html` باید هم‌زمان با `landing/index.html` sync بماند (کپی دستی است، نه symlink یا build step).
- ریپو اکنون **public** است (پیش‌نیاز Pages رایگان).

## منابع کد
- `landing/index.html`
- `docs/index.html`
