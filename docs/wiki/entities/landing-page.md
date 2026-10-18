# Landing Page

> صفحه‌ی استاتیک معرفی محصول برای اعتبارسنجی بازار.

## Responsibilities
- معرفی محصول وفا برای بازدیدکننده/سرمایه‌گذار.
- نمایش داشبورد تعاملی نمونه با glass UI، KPIهای خلاصه، فیلتر فوریت/رسیدگی/کانال، جزئیات دلیل پیشنهاد و پنل نمایشی تأیید/زمان‌بندی/رد کمپین.
- انتشار روی GitHub Pages (منبع: برنچ `master`، پوشه‌ی `/docs`).

## Interaction contract
- The dashboard tries `GET /next-best-action` from the same origin and falls back to the built-in mock list when the request fails, so GitHub Pages stays standalone.
- The data-source line reports whether live API data or local mock data is displayed.
- Filters update visible recommendations and KPI values; selecting a row updates the detail panel and pre-fills the editable message preview.
- Campaign approve/schedule/reject buttons only update the local status line; they never call the API or send messages.
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
