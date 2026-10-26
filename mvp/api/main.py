"""Mock-data API with an in-memory campaign review queue; nothing is sent."""

import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

if __package__:
    from . import automation, campaigns, customers, integrations, loyalty
else:
    import automation
    import campaigns
    import customers
    import integrations
    import loyalty

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    description="Synthetic-data demo with a review-only campaign queue, loyalty club, "
    "automation journeys, and store integrations. Dates control signal evaluation only; "
    "customer aggregates remain a fixed snapshot; no message is ever sent.",
    version="0.5.0",
)

allow_origins = [origin.strip() for origin in os.getenv("VAFA_CORS_ORIGINS", "").split(",") if origin.strip()]
if allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

LANDING_FILE = Path(__file__).resolve().parents[2] / "landing" / "index.html"

ActionType = Annotated[Optional[str], Query(description="Filter by action type")]
Urgency = Annotated[Optional[str], Query(description="Filter by urgency: low, medium, high")]
Channel = Annotated[Optional[str], Query(description="Filter by channel: whatsapp, instagram_dm, sms, none")]
City = Annotated[Optional[str], Query(description="Filter by customer city")]

AsOf = Annotated[date | None, Query(description="Evaluation date (YYYY-MM-DD); defaults to today. Use 2026-07-24 for the mock snapshot.")]


@app.get("/")
def root():
    return {"status": "ok", "service": "next-best-action-api"}


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(LANDING_FILE)


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


app.include_router(customers.router)
app.include_router(campaigns.router)
app.include_router(loyalty.router)
app.include_router(automation.router)
app.include_router(integrations.router)


@app.get("/next-best-action", response_model=list[NextBestAction])
def all_actions(
    as_of: AsOf = None,
    action_type: ActionType = None,
    urgency: Urgency = None,
    channel: Channel = None,
    city: City = None,
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
    action_type: ActionType = None,
    urgency: Urgency = None,
    channel: Channel = None,
    city: City = None,
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
