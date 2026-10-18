"""Store integrations: scoped API tokens, HMAC-signed webhook deliveries, branches.

Signing secrets are generated per webhook and kept only in process memory;
deliveries are simulated and never leave the process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from engine.next_best_action import load_customers, run_all

router = APIRouter(prefix="/integrations", tags=["integrations"])

SCOPES = ("customers:read", "recommendations:read", "campaigns:read", "webhooks:write")
WEBHOOK_EVENTS = ("campaign.approved", "campaign.rejected", "cart.abandoned", "customer.segment_changed")
RETRY_DELAY_MINUTES = (1, 5)
FAILING_AFTER = 3


class TokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=len(SCOPES))


class TokenResponse(BaseModel):
    token_id: str
    name: str
    scopes: list[str]
    token: str
    created_on: date
    revoked: bool = False


class WebhookRequest(BaseModel):
    url: str = Field(pattern=r"^https://[^\s]+$", max_length=300)
    events: list[str] = Field(default_factory=lambda: ["campaign.approved"], min_length=1, max_length=5)
    description: str = Field(default="", max_length=200)


class WebhookResponse(BaseModel):
    webhook_id: str
    url: str
    events: list[str]
    signing_secret: str


class DeliveryRequest(BaseModel):
    event: str = Field(default="campaign.approved", max_length=80)
    payload: dict = Field(default_factory=dict)


class DeliveryReceipt(BaseModel):
    delivery_id: int
    webhook_id: str
    event: str
    signature: str
    attempts: int
    delivered: bool
    next_retry_at: Optional[datetime] = None
    note_fa: str


class BranchRequest(BaseModel):
    city: str = Field(min_length=1, max_length=60)


class BranchResponse(BaseModel):
    city: str
    is_branch: bool
    customer_count: int


class WebhookStatus(str, Enum):
    active = "active"
    failing = "failing"
    disabled = "disabled"


@dataclass
class Token:
    token_id: str
    name: str
    scopes: list[str]
    token: str
    created_on: date
    revoked: bool = False


@dataclass
class Webhook:
    webhook_id: str
    url: str
    events: list[str]
    signing_secret: str
    deliveries: int = 0
    retries: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    status: WebhookStatus = WebhookStatus.active


@dataclass
class Delivery:
    delivery_id: int
    webhook_id: str
    event: str
    body: str
    signature: str
    attempts: int
    delivered: bool
    next_retry_at: Optional[datetime]


_tokens: dict[str, Token] = {}
_webhooks: dict[str, Webhook] = {}
_deliveries: list[Delivery] = []
_branches: set[str] = set()
_next_delivery_id = 1
_lock = Lock()


def reset() -> None:
    global _next_delivery_id
    with _lock:
        _tokens.clear()
        _webhooks.clear()
        _deliveries.clear()
        _branches.clear()
        _next_delivery_id = 1


def sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def require_scope(authorization: Optional[str], scope: str) -> Token:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="توکن دسترسی ارسال نشده است")
    token = _tokens.get(authorization.split(" ", 1)[1].strip())
    if token is None or token.revoked:
        raise HTTPException(status_code=401, detail="توکن دسترسی نامعتبر است")
    if scope not in token.scopes:
        raise HTTPException(status_code=403, detail=f"این توکن دسترسی {scope} ندارد")
    return token


def _find_webhook(webhook_id: str) -> Webhook:
    webhook = _webhooks.get(webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="وبهوک یافت نشد")
    return webhook


@router.post("/tokens", response_model=TokenResponse, status_code=201)
def create_token(request: TokenRequest):
    invalid = [scope for scope in request.scopes if scope not in SCOPES]
    if invalid:
        raise HTTPException(status_code=422, detail=f"دسترسی نامعتبر: {', '.join(invalid)}")
    token = Token(
        token_id=secrets.token_hex(4),
        name=request.name.strip(),
        scopes=list(dict.fromkeys(request.scopes)),
        token=secrets.token_urlsafe(24),
        created_on=date.today(),
    )
    with _lock:
        _tokens[token.token] = token
    return TokenResponse(**token.__dict__)


@router.get("/tokens", response_model=list[TokenResponse])
def list_tokens():
    return [TokenResponse(**token.__dict__) for token in _tokens.values()]


@router.delete("/tokens/{token_id}", response_model=TokenResponse)
def revoke_token(token_id: str):
    for token in _tokens.values():
        if token.token_id == token_id:
            token.revoked = True
            return TokenResponse(**token.__dict__)
    raise HTTPException(status_code=404, detail="توکن یافت نشد")


@router.get("/protected/recommendations")
def protected_recommendations(authorization: Optional[str] = Header(default=None)):
    require_scope(authorization, "recommendations:read")
    return [action.__dict__ for action in run_all()]


@router.post("/webhooks", response_model=WebhookResponse, status_code=201)
def create_webhook(request: WebhookRequest):
    invalid = [event for event in request.events if event not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"رویداد نامعتبر: {', '.join(invalid)}")
    webhook = Webhook(
        webhook_id=secrets.token_hex(4),
        url=request.url,
        events=list(dict.fromkeys(request.events)),
        signing_secret=secrets.token_urlsafe(32),
    )
    with _lock:
        _webhooks[webhook.webhook_id] = webhook
    return WebhookResponse(webhook_id=webhook.webhook_id, url=webhook.url, events=webhook.events, signing_secret=webhook.signing_secret)


@router.get("/webhooks")
def list_webhooks():
    return [
        {
            "webhook_id": webhook.webhook_id, "url": webhook.url, "events": webhook.events,
            "deliveries": webhook.deliveries, "retries": webhook.retries, "failures": webhook.failures,
            "status": webhook.status,
        }
        for webhook in _webhooks.values()
    ]


@router.post("/webhooks/{webhook_id}/deliveries", response_model=DeliveryReceipt)
def deliver(webhook_id: str, request: DeliveryRequest, simulate_failure: Annotated[bool, Query(description="Pretend the endpoint is down")] = False):
    webhook = _find_webhook(webhook_id)
    if webhook.status == WebhookStatus.disabled:
        raise HTTPException(status_code=409, detail="این وبهوک غیرفعال است")
    if request.event not in webhook.events:
        raise HTTPException(status_code=422, detail="این وبهوک برای این رویداد ثبت نشده است")
    body = json.dumps({"event": request.event, "data": request.payload, "webhook_id": webhook_id}, ensure_ascii=False, sort_keys=True)
    signature = sign(webhook.signing_secret, body)
    global _next_delivery_id
    with _lock:
        webhook.deliveries += 1
        if simulate_failure:
            # The first attempt fails; the retry is queued but not executed.
            attempts, delivered = 1, False
            next_retry = datetime.now() + timedelta(minutes=RETRY_DELAY_MINUTES[0])
        else:
            attempts, delivered, next_retry = 1, True, None
        if delivered:
            webhook.consecutive_failures = 0
            webhook.status = WebhookStatus.active
            note = "امضاء HMAC-SHA256 محاسبه شد؛ ارسال واقعی انجام نمی‌شود."
        else:
            webhook.retries += 1
            webhook.failures += 1
            webhook.consecutive_failures += 1
            if webhook.consecutive_failures >= FAILING_AFTER:
                webhook.status = WebhookStatus.failing
            note = "ارسال ناموفق بود؛ در صف تلاش مجدد با تأخیر قرار گرفت."
        delivery = Delivery(_next_delivery_id, webhook_id, request.event, body, signature, attempts, delivered, next_retry)
        _next_delivery_id += 1
        _deliveries.append(delivery)
    return DeliveryReceipt(
        delivery_id=delivery.delivery_id, webhook_id=webhook_id, event=request.event,
        signature=signature, attempts=attempts, delivered=delivered,
        next_retry_at=next_retry, note_fa=note,
    )


@router.get("/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: str):
    _find_webhook(webhook_id)
    return [
        {"delivery_id": d.delivery_id, "event": d.event, "attempts": d.attempts,
         "delivered": d.delivered, "signature": d.signature, "body": d.body}
        for d in _deliveries if d.webhook_id == webhook_id
    ]


@router.get("/branches", response_model=list[BranchResponse])
def list_branches():
    counts: dict[str, int] = {}
    for customer in load_customers().values():
        counts[customer.city] = counts.get(customer.city, 0) + 1
    return [
        BranchResponse(city=city, is_branch=city in _branches, customer_count=count)
        for city, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


@router.post("/branches", response_model=BranchResponse, status_code=201)
def add_branch(request: BranchRequest):
    city = request.city.strip()
    counts: dict[str, int] = {}
    for customer in load_customers().values():
        counts[customer.city] = counts.get(customer.city, 0) + 1
    if city not in counts:
        raise HTTPException(status_code=404, detail="شعبه‌ای با این شهر در داده‌ها نیست")
    with _lock:
        _branches.add(city)
    return BranchResponse(city=city, is_branch=True, customer_count=counts[city])


@router.delete("/branches/{city}", response_model=BranchResponse)
def remove_branch(city: str):
    with _lock:
        if city not in _branches:
            raise HTTPException(status_code=404, detail="این شهر به‌عنوان شعبه ثبت نشده است")
        _branches.discard(city)
    count = sum(1 for customer in load_customers().values() if customer.city == city)
    return BranchResponse(city=city, is_branch=False, customer_count=count)
