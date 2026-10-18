"""In-memory marketing automation journeys: triggers, delays, conditions, quiet hours, caps.

Executing a journey only records a plan of steps; nothing is sent and no
delivery ledger exists, so caps are checked against the synthetic plan only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.next_best_action import Customer, decide, load_cart_events, load_conversations, load_customers

router = APIRouter(prefix="/automation", tags=["automation"])

QUIET_START_HOUR = 21
QUIET_END_HOUR = 9
MAX_MESSAGES_PER_WEEK = 2
MAX_STEPS = 6


class Trigger(str, Enum):
    cart_abandoned = "cart_abandoned"
    complaint = "complaint"
    churn_risk = "churn_risk"


TRIGGER_FA = {
    "cart_abandoned": "سبد رهاشده",
    "complaint": "شکایت اخیر",
    "churn_risk": "ریسک ریزش",
}


class JourneyStep(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    delay_days: int = Field(default=0, ge=0, le=30)
    condition: str = Field(default="always", description="always | consent | high_urgency")
    message_fa: str = Field(min_length=1, max_length=1000)


class JourneyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    trigger: Trigger
    steps: list[JourneyStep] = Field(min_length=1, max_length=MAX_STEPS)


class JourneyResponse(BaseModel):
    journey_id: int
    name: str
    trigger: Trigger
    steps: list[JourneyStep]
    enabled: bool = True


class ScheduleRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    start: Optional[datetime] = None


class PlannedStep(BaseModel):
    step: str
    planned_at: datetime
    channel: str
    status: str
    note_fa: str = ""


class ScheduleResponse(BaseModel):
    customer_id: str
    journey_id: int
    as_of: date
    steps: list[PlannedStep]
    capped: bool


@dataclass
class Journey:
    journey_id: int
    name: str
    trigger: Trigger
    steps: list[JourneyStep]
    enabled: bool = True
    created_on: date = field(default_factory=date.today)


_journeys: dict[int, Journey] = {}
_next_id = 1
_lock = Lock()


def reset() -> None:
    global _next_id
    with _lock:
        _journeys.clear()
        _next_id = 1


def _response(journey: Journey) -> JourneyResponse:
    return JourneyResponse(
        journey_id=journey.journey_id, name=journey.name, trigger=journey.trigger,
        steps=journey.steps, enabled=journey.enabled,
    )


def _find(journey_id: int) -> Journey:
    journey = _journeys.get(journey_id)
    if journey is None:
        raise HTTPException(status_code=404, detail="مسیر خودکار یافت نشد")
    return journey


def triggered(customer: Customer, carts: list[dict], convs: list[dict], trigger: Trigger, as_of: date) -> bool:
    action = decide(customer, carts, convs, as_of)
    if trigger == Trigger.cart_abandoned:
        return action.action_type in {"reminder", "free_shipping", "cashback", "bnpl"}
    if trigger == Trigger.complaint:
        return action.action_type == "care"
    return "churn_ratio" in action.context and action.context["churn_ratio"] > 1.0


def next_send_time(moment: datetime) -> datetime:
    """Quiet hours run 21:00–09:00; sends wait until 09:00 without moving the weekday."""
    if moment.hour >= QUIET_START_HOUR:
        return (moment + timedelta(days=1)).replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    if moment.hour < QUIET_END_HOUR:
        return moment.replace(hour=QUIET_END_HOUR, minute=0, second=0, microsecond=0)
    return moment


def condition_holds(condition: str, action_type: str, urgency: str) -> bool:
    if condition == "always":
        return True
    if condition == "consent":
        return action_type != "suppress"
    if condition == "high_urgency":
        return urgency == "high"
    return False


@router.get("", response_model=list[JourneyResponse])
def list_journeys():
    return [_response(journey) for journey in _journeys.values()]


@router.post("", response_model=JourneyResponse, status_code=201)
def create_journey(request: JourneyRequest):
    for step in request.steps:
        if step.condition not in {"always", "consent", "high_urgency"}:
            raise HTTPException(status_code=422, detail=f"شرط نامعتبر: {step.condition}")
    global _next_id
    with _lock:
        journey = Journey(_next_id, request.name.strip(), request.trigger, request.steps)
        _next_id += 1
        _journeys[journey.journey_id] = journey
    return _response(journey)


@router.post("/{journey_id}/schedule", response_model=ScheduleResponse)
def schedule(journey_id: int, request: ScheduleRequest, as_of: Annotated[Optional[date], Query()] = None):
    journey = _find(journey_id)
    if not journey.enabled:
        raise HTTPException(status_code=409, detail="این مسیر خودکار متوقف است")
    customers = load_customers()
    if request.customer_id not in customers:
        raise HTTPException(status_code=404, detail="مشتری یافت نشد")
    as_of = as_of or date.today()
    customer = customers[request.customer_id]
    carts = load_cart_events().get(request.customer_id, [])
    convs = load_conversations().get(request.customer_id, [])
    if not triggered(customer, carts, convs, journey.trigger, as_of):
        raise HTTPException(status_code=422, detail="شرط شروع این مسیر برای مشتری برقرار نیست")
    action = decide(customer, carts, convs, as_of)
    start = request.start or datetime.combine(as_of, datetime.min.time()).replace(hour=10)
    planned: list[PlannedStep] = []
    sends = 0
    for step in journey.steps:
        scheduled_at = next_send_time(start + timedelta(days=step.delay_days))
        if not condition_holds(step.condition, action.action_type, action.urgency):
            planned.append(PlannedStep(step=step.name, planned_at=scheduled_at, channel="none",
                                       status="skipped", note_fa="شرط این مرحله برقرار نیست"))
            continue
        if sends >= MAX_MESSAGES_PER_WEEK:
            planned.append(PlannedStep(step=step.name, planned_at=scheduled_at, channel="none",
                                       status="capped", note_fa=f"سقف {MAX_MESSAGES_PER_WEEK} پیام در هفته"))
            continue
        planned.append(PlannedStep(step=step.name, planned_at=scheduled_at, channel=action.channel,
                                   status="planned", note_fa="در محدوده‌ی ساعت مجاز"))
        sends += 1
    return ScheduleResponse(
        customer_id=request.customer_id, journey_id=journey_id, as_of=as_of,
        steps=planned, capped=any(step.status == "capped" for step in planned),
    )


@router.get("/{journey_id}", response_model=JourneyResponse)
def get_journey(journey_id: int):
    return _response(_find(journey_id))


@router.post("/{journey_id}/{state}", response_model=JourneyResponse)
def set_state(journey_id: int, state: str):
    if state not in {"pause", "resume"}:
        raise HTTPException(status_code=404, detail="عملیات یافت نشد")
    journey = _find(journey_id)
    journey.enabled = state == "resume"
    return _response(journey)
