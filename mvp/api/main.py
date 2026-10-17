"""Read-only mock-data API; recommendations do not send messages."""

import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query
from engine.next_best_action import (
    DEMO_DATE,
    NextBestAction,
    decide,
    load_cart_events,
    load_conversations,
    load_customers,
    run_all,
)

app = FastAPI(
    title="Retail Retention Copilot — Next-Best-Action API",
    description="Read-only synthetic-data demo, not a production messaging service. "
    "Dates control signal evaluation only; customer aggregates remain a fixed snapshot.",
    version="0.2.0",
)

AsOf = Annotated[date | None, Query(description="Evaluation date (YYYY-MM-DD); defaults to today. Use 2026-07-24 for the mock snapshot.")]


@app.get("/")
def root():
    return {"status": "ok", "service": "next-best-action-api"}


@app.get("/demo")
def demo():
    actions = run_all(DEMO_DATE)
    return {
        "data_source": "synthetic_csv",
        "snapshot_date": DEMO_DATE,
        "sends_messages": False,
        "customer_count": len(actions),
        "action_counts": dict(Counter(a.action_type for a in actions)),
    }


@app.get("/next-best-action", response_model=list[NextBestAction])
def all_actions(
    as_of: AsOf = None,
    action_type: str | None = Query(default=None, description="Filter by action type"),
    urgency: str | None = Query(default=None, description="Filter by urgency: low, medium, high"),
    channel: str | None = Query(default=None, description="Filter by channel"),
    city: str | None = Query(default=None, description="Filter by customer city"),
):
    customers = load_customers()
    cart_events = load_cart_events()
    conversations = load_conversations()
    actions = [
        decide(customer, cart_events.get(customer_id, []), conversations.get(customer_id, []), as_of)
        for customer_id, customer in customers.items()
    ]
    return filter_actions(actions, customers, action_type, urgency, channel, city)


def filter_actions(actions, customers, action_type=None, urgency=None, channel=None, city=None):
    return [
        action for action in actions
        if (action_type is None or action.action_type == action_type)
        and (urgency is None or action.urgency == urgency)
        and (channel is None or action.channel == channel)
        and (city is None or customers[action.customer_id].city == city)
    ]


@app.get("/analytics")
def analytics(
    as_of: AsOf = None,
    action_type: str | None = Query(default=None, description="Filter by action type"),
    urgency: str | None = Query(default=None, description="Filter by urgency: low, medium, high"),
    channel: str | None = Query(default=None, description="Filter by channel"),
    city: str | None = Query(default=None, description="Filter by customer city"),
):
    customers = load_customers()
    cart_events = load_cart_events()
    conversations = load_conversations()
    actions = [
        decide(customer, cart_events.get(customer_id, []), conversations.get(customer_id, []), as_of)
        for customer_id, customer in customers.items()
    ]
    filtered = filter_actions(actions, customers, action_type, urgency, channel, city)
    return {
        "snapshot_date": as_of or date.today(),
        "total_customers": len(customers),
        "matching_customers": len(filtered),
        "actionable_customers": sum(action.action_type not in {"monitor", "suppress"} for action in filtered),
        "high_urgency": sum(action.urgency == "high" for action in filtered),
        "action_counts": dict(Counter(action.action_type for action in filtered)),
        "urgency_counts": dict(Counter(action.urgency for action in filtered)),
        "channel_counts": dict(Counter(action.channel for action in filtered)),
        "city_counts": dict(Counter(customers[action.customer_id].city for action in filtered)),
        "filters": {"action_type": action_type, "urgency": urgency, "channel": channel, "city": city},
    }


@app.get("/next-best-action/{customer_id}", response_model=NextBestAction)
def one_action(customer_id: str, as_of: AsOf = None):
    customers = load_customers()
    if customer_id not in customers:
        raise HTTPException(status_code=404, detail="مشتری یافت نشد")
    cart_events = load_cart_events()
    convs = load_conversations()
    return decide(customers[customer_id], cart_events.get(customer_id, []), convs.get(customer_id, []), as_of)
