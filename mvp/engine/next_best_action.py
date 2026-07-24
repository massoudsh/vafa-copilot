"""
موتور تصمیم‌سازی «بهترین اقدام بعدی» (Next-Best-Action) — نسخه MVP

منطق کاملاً rule-based و قابل توضیح است (نه جعبه‌سیاه) تا خرده‌فروش بتواند
به هر تصمیم اعتماد کند و دلیل آن را ببیند. در فاز بعد می‌توان وزن‌ها را
از داده‌ی واقعی کمپین‌ها (نتیجه‌ی ارسال‌ها) یاد گرفت بدون تغییر ساختار.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

TODAY = date(2026, 7, 24)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@dataclass
class Customer:
    customer_id: str
    name: str
    city: str
    last_purchase_date: date
    total_orders: int
    total_spend: int
    avg_order_value: int
    preferred_channel: str
    typical_cycle_days: int
    messages_last_30d: int
    opt_in_sms: bool
    opt_in_whatsapp: bool
    opt_in_instagram: bool
    do_not_disturb: bool


@dataclass
class NextBestAction:
    customer_id: str
    name: str
    action_type: str          # suppress | care | reminder | free_shipping | cashback |
                               # bnpl | discount_timeboxed | loyalty_no_discount | monitor
    channel: str
    message_fa: str
    reason_fa: str
    urgency: str               # low | medium | high
    context: dict = field(default_factory=dict)


def load_customers() -> dict[str, Customer]:
    customers: dict[str, Customer] = {}
    with open(DATA_DIR / "customers.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            customers[row["customer_id"]] = Customer(
                customer_id=row["customer_id"],
                name=row["name"],
                city=row["city"],
                last_purchase_date=parse_date(row["last_purchase_date"]),
                total_orders=int(row["total_orders"]),
                total_spend=int(row["total_spend_toman"]),
                avg_order_value=int(row["avg_order_value_toman"]),
                preferred_channel=row["preferred_channel"],
                typical_cycle_days=int(row["typical_cycle_days"]),
                messages_last_30d=int(row["messages_last_30d"]),
                opt_in_sms=row["opt_in_sms"] == "1",
                opt_in_whatsapp=row["opt_in_whatsapp"] == "1",
                opt_in_instagram=row["opt_in_instagram"] == "1",
                do_not_disturb=row["do_not_disturb"] == "1",
            )
    return customers


def load_cart_events() -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    with open(DATA_DIR / "cart_events.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.setdefault(row["customer_id"], []).append(row)
    return events


def load_conversations() -> dict[str, list[dict]]:
    convs: dict[str, list[dict]] = {}
    with open(DATA_DIR / "conversations.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            convs.setdefault(row["customer_id"], []).append(row)
    return convs


def pick_channel(c: Customer) -> str:
    """کانال ترجیحی مشتری را برمی‌گرداند، در صورت نبود opt-in به ترتیب اولویت فالبک می‌کند."""
    opt_map = {
        "whatsapp": c.opt_in_whatsapp,
        "instagram_dm": c.opt_in_instagram,
        "sms": c.opt_in_sms,
    }
    if opt_map.get(c.preferred_channel):
        return c.preferred_channel
    for channel in ("whatsapp", "instagram_dm", "sms"):
        if opt_map[channel]:
            return channel
    return "none"


def latest_abandoned_cart(events: list[dict]) -> Optional[dict]:
    abandoned = [e for e in events if e["abandoned"] == "1"]
    if not abandoned:
        return None
    abandoned.sort(key=lambda e: parse_date(e["date"]), reverse=True)
    latest = abandoned[0]
    if (TODAY - parse_date(latest["date"])).days <= 3:
        return latest
    return None


def recent_complaint(convs: list[dict]) -> bool:
    return any(
        v["intent_tag"] == "complaint" and (TODAY - parse_date(v["date"])).days <= 45
        for v in convs
    )


def price_sensitivity_score(convs: list[dict]) -> int:
    return sum(1 for v in convs if v["intent_tag"] == "price_question" and (TODAY - parse_date(v["date"])).days <= 30)


def shipping_sensitivity_score(convs: list[dict]) -> int:
    return sum(1 for v in convs if v["intent_tag"] == "shipping_question" and (TODAY - parse_date(v["date"])).days <= 30)


def payment_need_score(convs: list[dict]) -> int:
    return sum(1 for v in convs if v["intent_tag"] == "payment_question")


def loyalty_tier(c: Customer) -> str:
    if c.total_orders >= 15 or c.total_spend >= 20_000_000:
        return "vip"
    if c.total_orders >= 6:
        return "regular"
    return "new"


def churn_risk_ratio(c: Customer) -> float:
    days_since = (TODAY - c.last_purchase_date).days
    return days_since / max(c.typical_cycle_days, 1)


MESSAGE_TEMPLATES = {
    "care": "سلام {name} عزیز 🌿 می‌خواستیم مطمئن بشیم تجربه‌ی خریدتون خوب بوده. اگه مشکلی هست همین‌جا بگید تا سریع رسیدگی کنیم.",
    "reminder": "سلام {name} جان، سبد خریدتون «{item}» هنوز منتظرتونه 🛍️ هر وقت راحت بودید تکمیلش کنید.",
    "free_shipping": "سلام {name} عزیز، «{item}» توی سبدتونه — امروز ارسالش رایگانه، از دست ندید 🚚",
    "cashback": "سلام {name} جان، برای تکمیل خرید «{item}» {cashback_pct}٪ کش‌بک برای خرید بعدیتون در نظر گرفتیم 🎁",
    "bnpl": "سلام {name} عزیز، می‌تونید «{item}» رو الان بردارید و پرداختش رو در چند قسط انجام بدید 💳",
    "discount_timeboxed": "سلام {name} جان، فقط تا ۴۸ ساعت آینده یک پیشنهاد ویژه برای بازگشتتون داریم — دلمون براتون تنگ شده 🌟",
    "loyalty_no_discount": "سلام {name} عزیز، به‌خاطر همراهیتون، دسترسی زودتر به کالکشن جدید رو براتون فعال کردیم — بدون نیاز به هیچ کد تخفیفی 💛",
    "vip_personal": "سلام {name} عزیز، به‌عنوان یکی از مشتری‌های ویژه‌مون یه پیشنهاد اختصاصی (اقساط/کش‌بک) براتون آماده کردیم، اگه مایل بودید بهتون معرفی کنیم.",
    "monitor": None,
}


def build_message(action_type: str, name: str, item: str = "", cashback_pct: int = 8) -> str:
    template = MESSAGE_TEMPLATES.get(action_type)
    if not template:
        return ""
    return template.format(name=name, item=item or "محصول موردعلاقه‌تون", cashback_pct=cashback_pct)


def decide(c: Customer, cart_events: list[dict], convs: list[dict]) -> NextBestAction:
    channel = pick_channel(c)
    fatigued = c.messages_last_30d >= 4

    # ۱) عدم مزاحمت صریح
    if c.do_not_disturb:
        return NextBestAction(
            c.customer_id, c.name, "suppress", channel, "",
            "مشتری در لیست «عدم ارسال پیام» است؛ هیچ پیامی ارسال نمی‌شود.",
            "low",
        )

    # ۲) شکایت اخیر — اول رسیدگی، نه فروش
    if recent_complaint(convs):
        return NextBestAction(
            c.customer_id, c.name, "care", channel,
            build_message("care", c.name),
            "شکایت اخیر ثبت شده؛ اولویت با پیگیری رضایت است نه ارسال کمپین فروش.",
            "high",
        )

    tier = loyalty_tier(c)
    price_score = price_sensitivity_score(convs)
    shipping_score = shipping_sensitivity_score(convs)
    payment_score = payment_need_score(convs)
    cart = latest_abandoned_cart(cart_events)

    # ۳) سبد رهاشده‌ی تازه
    if cart:
        item = cart["items"]
        if payment_score > 0 or c.avg_order_value >= 1_200_000:
            return NextBestAction(
                c.customer_id, c.name, "bnpl", channel,
                build_message("bnpl", c.name, item),
                "سبد رهاشده + سابقه‌ی پرسش از پرداخت قسطی یا مبلغ سبد بالا → پیشنهاد BNPL به‌جای تخفیف.",
                "high", {"cart_value": cart["cart_value_toman"]},
            )
        if shipping_score > 0:
            return NextBestAction(
                c.customer_id, c.name, "free_shipping", channel,
                build_message("free_shipping", c.name, item),
                "سبد رهاشده + پرسش قبلی درباره‌ی هزینه‌ی ارسال → محرک ارسال رایگان به‌جای تخفیف قیمتی.",
                "high", {"cart_value": cart["cart_value_toman"]},
            )
        if price_score > 0 and tier != "vip":
            return NextBestAction(
                c.customer_id, c.name, "cashback", channel,
                build_message("cashback", c.name, item),
                "سبد رهاشده + حساسیت به قیمت، اما مشتری وفادار نیست تا تخفیف مستقیم بدهیم → کش‌بک برای خرید بعدی (margin کمتر آسیب می‌بیند).",
                "medium", {"cart_value": cart["cart_value_toman"]},
            )
        return NextBestAction(
            c.customer_id, c.name, "reminder", channel,
            build_message("reminder", c.name, item),
            "سبد رهاشده بدون سیگنال حساسیت به قیمت یا ارسال → فقط یادآوری ساده، بدون تخفیف.",
            "medium", {"cart_value": cart["cart_value_toman"]},
        )

    ratio = churn_risk_ratio(c)

    # ۴) ریسک بالای ریزش (خیلی دیرتر از چرخه‌ی معمول خریدش)
    if ratio > 1.6:
        if tier == "vip":
            return NextBestAction(
                c.customer_id, c.name, "cashback", channel,
                build_message("vip_personal", c.name),
                f"مشتری VIP با ریسک ریزش بالا ({ratio:.1f}× چرخه‌ی معمول) → پیشنهاد شخصی‌سازی‌شده به‌جای تخفیف عمومی.",
                "high", {"churn_ratio": round(ratio, 2)},
            )
        return NextBestAction(
            c.customer_id, c.name, "discount_timeboxed", channel,
            build_message("discount_timeboxed", c.name),
            f"ریسک ریزش بالا ({ratio:.1f}× چرخه‌ی معمول) و مشتری غیر VIP → پیشنهاد محدودزمان برای بازگرداندن سریع.",
            "high", {"churn_ratio": round(ratio, 2)},
        )

    # ۵) کمی دیرتر از حد معمول
    if ratio > 1.0:
        if fatigued:
            return NextBestAction(
                c.customer_id, c.name, "monitor", channel, "",
                "کمی دیرتر از چرخه‌ی معمول اما اخیراً پیام زیاد دریافت کرده → صبر تا کاهش خستگی از پیام.",
                "low", {"churn_ratio": round(ratio, 2)},
            )
        return NextBestAction(
            c.customer_id, c.name, "reminder", channel,
            build_message("reminder", c.name, "کالکشن جدید"),
            f"کمی دیرتر از چرخه‌ی معمول خرید ({ratio:.1f}×) → یادآوری ملایم بدون تخفیف.",
            "medium", {"churn_ratio": round(ratio, 2)},
        )

    # ۶) مشتری فعال و وفادار — نیازی به تخفیف نیست
    if tier in ("vip", "regular") and not fatigued:
        return NextBestAction(
            c.customer_id, c.name, "loyalty_no_discount", channel,
            build_message("loyalty_no_discount", c.name),
            "مشتری فعال و وفادار، بدون سیگنال حساسیت به قیمت → دسترسی زودهنگام به‌جای تخفیف تا margin حفظ شود.",
            "low", {"churn_ratio": round(ratio, 2)},
        )

    # ۷) هیچ سیگنال خاصی نیست
    return NextBestAction(
        c.customer_id, c.name, "monitor", channel, "",
        "مشتری در چرخه‌ی سالم خرید است و سیگنال خاصی برای اقدام وجود ندارد.",
        "low", {"churn_ratio": round(ratio, 2)},
    )


def run_all() -> list[NextBestAction]:
    customers = load_customers()
    cart_events = load_cart_events()
    convs = load_conversations()
    results = []
    for cid, c in customers.items():
        results.append(decide(c, cart_events.get(cid, []), convs.get(cid, [])))
    return results


if __name__ == "__main__":
    import json

    actions = run_all()
    print(json.dumps([a.__dict__ for a in actions], ensure_ascii=False, indent=2))
