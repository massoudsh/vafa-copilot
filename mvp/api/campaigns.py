"""In-memory campaign review queue for the synthetic MVP; nothing is sent."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from threading import Lock
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.next_best_action import (
    NextBestAction,
    decide,
    load_cart_events,
    load_conversations,
    load_customers,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

MAX_MESSAGE_LENGTH = 1000
MAX_CUSTOMERS_PER_BATCH = 200


class CampaignStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ReviewRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class MessageEdit(BaseModel):
    message_fa: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class CampaignResponse(BaseModel):
    campaign_id: int
    customer_id: str
    customer_name: str
    action_type: str
    channel: str
    message_fa: str
    original_message_fa: str
    urgency: str
    reason_fa: str
    status: CampaignStatus
    created_on: date
    reviewed_on: Optional[date] = None
    review_reason: str = ""


@dataclass
class Campaign:
    campaign_id: int
    customer_id: str
    customer_name: str
    action_type: str
    channel: str
    message_fa: str
    original_message_fa: str
    urgency: str
    reason_fa: str
    status: CampaignStatus = CampaignStatus.pending
    created_on: date = field(default_factory=date.today)
    reviewed_on: Optional[date] = None
    review_reason: str = ""


_queue: list[Campaign] = []
_next_id = 1
_lock = Lock()


def reset() -> None:
    global _next_id
    with _lock:
        _queue.clear()
        _next_id = 1


def _actions(as_of: Optional[date]) -> dict[str, NextBestAction]:
    customers = load_customers()
    cart_events = load_cart_events()
    conversations = load_conversations()
    return {
        customer_id: decide(customer, cart_events.get(customer_id, []), conversations.get(customer_id, []), as_of)
        for customer_id, customer in customers.items()
    }


def _to_response(campaign: Campaign) -> CampaignResponse:
    return CampaignResponse(**campaign.__dict__)


def _find(campaign_id: int) -> Campaign:
    for campaign in _queue:
        if campaign.campaign_id == campaign_id:
            return campaign
    raise HTTPException(status_code=404, detail="کمپین یافت نشد")


def _pending_for(customer_id: str) -> Optional[Campaign]:
    return next(
        (c for c in _queue if c.customer_id == customer_id and c.status == CampaignStatus.pending),
        None,
    )


def _review(campaign_id: int, status: CampaignStatus, reason: str) -> CampaignResponse:
    campaign = _find(campaign_id)
    if campaign.status != CampaignStatus.pending:
        raise HTTPException(status_code=409, detail="این کمپین قبلاً بررسی شده است")
    campaign.status = status
    campaign.review_reason = reason.strip()
    campaign.reviewed_on = date.today()
    return _to_response(campaign)


@router.post("/preview", response_model=CampaignResponse)
def preview(
    customer_id: str = Query(description="Customer whose recommendation is being previewed"),
    message_fa: Annotated[Optional[str], Query(max_length=MAX_MESSAGE_LENGTH)] = None,
    as_of: Optional[date] = Query(default=None),
):
    actions = _actions(as_of)
    if customer_id not in actions:
        raise HTTPException(status_code=404, detail="مشتری یافت نشد")
    action = actions[customer_id]
    if action.action_type == "suppress":
        raise HTTPException(status_code=422, detail="برای این مشتری ارسال پیام مجاز نیست")
    return _to_response(Campaign(
        0, customer_id, action.name, action.action_type, action.channel,
        action.message_fa if message_fa is None else message_fa.strip(),
        action.message_fa, action.urgency, action.reason_fa,
    ))


@router.post("", response_model=list[CampaignResponse], status_code=201)
def create(
    customer_ids: Annotated[list[str], Query(min_length=1, max_length=MAX_CUSTOMERS_PER_BATCH)],
    as_of: Optional[date] = Query(default=None),
):
    actions = _actions(as_of)
    unique_ids = list(dict.fromkeys(customer_ids))
    unknown = [customer_id for customer_id in unique_ids if customer_id not in actions]
    if any(not customer_id.strip() for customer_id in unique_ids):
        raise HTTPException(status_code=422, detail="شناسه‌ی مشتری نامعتبر است")
    if unknown:
        raise HTTPException(status_code=404, detail=f"مشتری یافت نشد: {', '.join(unknown)}")
    blocked = [customer_id for customer_id in unique_ids if actions[customer_id].action_type == "suppress"]
    if blocked:
        raise HTTPException(status_code=422, detail=f"ارسال پیام برای این مشتریان مجاز نیست: {', '.join(blocked)}")
    duplicates = [customer_id for customer_id in unique_ids if _pending_for(customer_id)]
    if duplicates:
        raise HTTPException(status_code=409, detail=f"کمپین در انتظار بررسی وجود دارد: {', '.join(duplicates)}")

    global _next_id
    created = []
    for customer_id in unique_ids:
        action = actions[customer_id]
        campaign = Campaign(
            _next_id, customer_id, action.name, action.action_type, action.channel,
            action.message_fa, action.message_fa, action.urgency, action.reason_fa,
        )
        _next_id += 1
        _queue.append(campaign)
        created.append(_to_response(campaign))
    return created


@router.get("/summary")
def summary():
    return {
        "total": len(_queue),
        "status_counts": dict(Counter(c.status.value for c in _queue)),
        "action_counts": dict(Counter(c.action_type for c in _queue)),
        "channel_counts": dict(Counter(c.channel for c in _queue)),
        "sends_messages": False,
    }


@router.get("", response_model=list[CampaignResponse])
def list_campaigns(status: Optional[CampaignStatus] = None):
    return [_to_response(c) for c in _queue if status is None or c.status == status]


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(campaign_id: int):
    return _to_response(_find(campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def edit_message(campaign_id: int, edit: MessageEdit):
    campaign = _find(campaign_id)
    if campaign.status != CampaignStatus.pending:
        raise HTTPException(status_code=409, detail="فقط کمپین در انتظار بررسی قابل ویرایش است")
    campaign.message_fa = edit.message_fa.strip()
    return _to_response(campaign)


@router.post("/{campaign_id}/approve", response_model=CampaignResponse)
def approve(campaign_id: int):
    return _review(campaign_id, CampaignStatus.approved, "")


@router.post("/{campaign_id}/reject", response_model=CampaignResponse)
def reject(campaign_id: int, review: ReviewRequest = ReviewRequest()):
    if not (review.reason or "").strip():
        raise HTTPException(status_code=422, detail="دلیل رد کمپین ضروری است")
    return _review(campaign_id, CampaignStatus.rejected, review.reason)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
def cancel(campaign_id: int):
    campaign = _find(campaign_id)
    if campaign.status != CampaignStatus.pending:
        raise HTTPException(status_code=409, detail="فقط کمپین در انتظار بررسی قابل لغو است")
    campaign.status = CampaignStatus.cancelled
    campaign.reviewed_on = date.today()
    return _to_response(campaign)
