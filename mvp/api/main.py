"""
API نمونه برای Next-Best-Action Copilot (MVP).

اجرا:
    pip install -r ../requirements.txt
    uvicorn main:app --reload --port 8000

تست بدون مرورگر:
    curl http://localhost:8000/next-best-action
    curl http://localhost:8000/next-best-action/C001
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from engine.next_best_action import decide, load_cart_events, load_conversations, load_customers

app = FastAPI(
    title="Retail Retention Copilot — Next-Best-Action API",
    description="پیشنهاد بهترین اقدام بعدی برای هر مشتری (MVP، rule-based و قابل توضیح).",
    version="0.1.0",
)


@app.get("/")
def root():
    return {"status": "ok", "service": "next-best-action-api"}


@app.get("/next-best-action")
def all_actions():
    customers = load_customers()
    cart_events = load_cart_events()
    convs = load_conversations()
    return [
        decide(c, cart_events.get(cid, []), convs.get(cid, [])).__dict__
        for cid, c in customers.items()
    ]


@app.get("/next-best-action/{customer_id}")
def one_action(customer_id: str):
    customers = load_customers()
    if customer_id not in customers:
        raise HTTPException(status_code=404, detail="مشتری یافت نشد")
    cart_events = load_cart_events()
    convs = load_conversations()
    c = customers[customer_id]
    return decide(c, cart_events.get(customer_id, []), convs.get(customer_id, [])).__dict__
