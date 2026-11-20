# Landing Page

> صفحه‌ی استاتیک معرفی محصول برای اعتبارسنجی بازار.

## Responsibilities
- معرفی محصول وفا برای بازدیدکننده/سرمایه‌گذار.
- نمایش داشبورد تعاملی نمونه با glass UI، KPIهای خلاصه، فیلتر فوریت/رسیدگی/کانال، پنل بخش‌های RFM، امتیاز و مسیر خودکار، و میز مشتریان با جست‌وجو، پرونده ۳۶۰، برچسب، ارجاع و بازخورد.
- انتشار روی GitHub Pages (منبع: برنچ `master`، پوشه‌ی `/docs`).

## Interaction contract
- The dashboard tries `GET /next-best-action` from the same origin and falls back to the built-in mock list when the request fails, so GitHub Pages stays standalone.
- The data-source line reports whether live API data or local mock data is displayed.
- Filters update visible recommendations and KPI values; selecting a row updates the detail panel and pre-fills the editable message preview.
- In live mode the campaign buttons call the queue: schedule creates a pending campaign (reusing an existing pending one on 409), approve/reject review it, and an edited message is saved first. Suppressed customers get an inline error. In static mode the same buttons only show a demo status line; no message is ever sent.
- In live mode the page also loads `/loyalty/segments` and `/automation`; points come from the `/customers` directory response instead of one request per customer. Selecting a segment filters both the list and the KPI cards.
- The customer desk loads `/customers`, supports Persian search and tag filters, then loads a 360 profile. Tag, referral, and feedback forms call their API routes; referral UI explicitly reports that no reward is issued before order confirmation. NPS summary is shown when available.
- The coupon and journey buttons call `POST /loyalty/coupons` and `POST /automation/{id}/schedule`; without a reachable API they report a mock result and state that nothing was sent. The journey button uses the first existing journey and creates a default cart-recovery journey when none exists, so a fresh container does not 404.
- The evaluation date comes from `?as_of=YYYY-MM-DD` and is forwarded to every request (recommendations, segments, customer directory, 360 profile, journey schedule); without it the page uses today. `/dashboard?as_of=2026-07-24` reproduces the synthetic snapshot.
- Re-rendering after a filter keeps the selected customer and the edited message; filter and segment toggles use `aria-pressed`, the selected action row uses `aria-current`.
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
