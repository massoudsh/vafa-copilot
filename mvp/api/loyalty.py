"""Loyalty programme for the synthetic MVP: RFM segments, points, wallet credit, coupons.

State lives in memory and is lost on restart; no credit is ever spent and no
coupon is ever redeemed against a real order.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from threading import Lock
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.next_best_action import DEMO_DATE, Customer, churn_risk_ratio, load_customers

router = APIRouter(prefix="/loyalty", tags=["loyalty"])

POINTS_PER_10K_TOMAN = 1
CREDIT_TOMAN_PER_POINTS = 1_000
CREDIT_EXPIRY_DAYS = 90
RFM_WINDOW_DAYS = 365
MAX_COUPON_DISCOUNT = 500_000


class CouponStatus(str, Enum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class CustomerProfile(BaseModel):
    customer_id: str
    name: str
    city: str
    last_purchase_date: date
    total_orders: int
    total_spend: int
    avg_order_value: int
    rfm_score: int
    rfm_segment: str
    segment_fa: str
    churn_ratio: float


class PointsEntry(BaseModel):
    points: int
    reason: str
    source: str = "manual"


class PointsSummary(BaseModel):
    customer_id: str
    points_balance: int
    rfm_segment: str
    entries: int


class CreditGrant(BaseModel):
    points: int = Field(gt=0, description="Points converted to credit")
    valid_days: int = Field(default=CREDIT_EXPIRY_DAYS, gt=0, le=365)


class CreditResponse(BaseModel):
    grant_id: int
    customer_id: str
    amount_toman: int
    expires_on: date
    remaining_toman: int


class CouponRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    discount_toman: int = Field(gt=0, le=MAX_COUPON_DISCOUNT)
    expires_in_days: int = Field(default=14, gt=0, le=90)


class CouponValidation(BaseModel):
    order_value_toman: int = Field(gt=0)
    as_of: Optional[date] = None


class CouponResponse(BaseModel):
    code: str
    customer_id: str
    discount_toman: int
    status: CouponStatus
    issued_on: date
    expires_on: date
    redeemed_on: Optional[date] = None


SEGMENTS_FA = {
    "champion": "وفادار ارزشمند",
    "loyal": "وفادار",
    "new": "تازه‌وارد",
    "at_risk": "در خطر ریزش",
    "dormant": "غیرفعال",
}


@dataclass
class PointsRecord:
    customer_id: str
    points: int
    reason: str
    source: str
    created_on: date


@dataclass
class CreditGrantRecord:
    grant_id: int
    customer_id: str
    amount_toman: int
    expires_on: date
    remaining_toman: int


@dataclass
class Coupon:
    code: str
    customer_id: str
    discount_toman: int
    status: CouponStatus
    issued_on: date
    expires_on: date
    redeemed_on: Optional[date] = None


_points: dict[str, list[PointsRecord]] = {}
_credit: list[CreditGrantRecord] = []
_coupons: dict[str, Coupon] = {}
_next_grant_id = 1
_coupon_counter = 0
_lock = Lock()


def reset() -> None:
    global _next_grant_id, _coupon_counter
    with _lock:
        _points.clear()
        _credit.clear()
        _coupons.clear()
        _next_grant_id = 1
        _coupon_counter = 0


def rfm_scores(c: Customer, as_of: date) -> tuple[int, int, int]:
    """Takes the snapshot aggregations at face value; there is no order history to window."""
    recency_days = max((as_of - c.last_purchase_date).days, 0)
    recency = 5 if recency_days <= 30 else 3 if recency_days <= 90 else 2 if recency_days <= RFM_WINDOW_DAYS else 1
    frequency = 5 if c.total_orders >= 15 else 4 if c.total_orders >= 8 else 3 if c.total_orders >= 4 else 2 if c.total_orders >= 2 else 1
    monetary = (
        5 if c.avg_order_value >= 1_500_000 else
        4 if c.avg_order_value >= 1_000_000 else
        3 if c.avg_order_value >= 700_000 else
        2 if c.avg_order_value >= 400_000 else 1
    )
    return recency, frequency, monetary


def rfm_segment(c: Customer, as_of: date) -> tuple[str, int]:
    recency, frequency, monetary = rfm_scores(c, as_of)
    if recency <= 2:
        segment = "at_risk" if frequency >= 3 or monetary >= 3 else "dormant"
    elif frequency >= 4 and monetary >= 4:
        segment = "champion"
    elif frequency >= 3:
        segment = "loyal"
    elif frequency <= 2:
        segment = "new"
    else:
        segment = "loyal" if monetary >= 4 else "new"
    return segment, recency + frequency + monetary


def profile(c: Customer, as_of: date) -> CustomerProfile:
    segment, score = rfm_segment(c, as_of)
    return CustomerProfile(
        customer_id=c.customer_id,
        name=c.name,
        city=c.city,
        last_purchase_date=c.last_purchase_date,
        total_orders=c.total_orders,
        total_spend=c.total_spend,
        avg_order_value=c.avg_order_value,
        rfm_score=score,
        rfm_segment=segment,
        segment_fa=SEGMENTS_FA[segment],
        churn_ratio=round(churn_risk_ratio(c, as_of), 2),
    )


def entry_points(c: Customer, as_of: date) -> list[PointsRecord]:
    base = c.total_spend // 10_000 * POINTS_PER_10K_TOMAN
    records = [PointsRecord(c.customer_id, base, "امتیاز خریدهای انجام‌شده", "purchase", c.last_purchase_date)]
    if rfm_segment(c, as_of)[0] in ("champion", "loyal") and c.total_orders >= 6:
        bonus = 500 if rfm_segment(c, as_of)[0] == "champion" else 250
        records.append(PointsRecord(c.customer_id, bonus, "پاداش باشگاه مشتریان", "loyalty_club", as_of))
    return records


def points_balance(customer_id: str, as_of: date) -> int:
    customer = _customer(customer_id)
    earned = sum(record.points for record in entry_points(customer, as_of))
    manual = sum(record.points for record in _points.get(customer_id, []))
    return earned + manual


def _customer(customer_id: str) -> Customer:
    customers = load_customers()
    if customer_id not in customers:
        raise HTTPException(status_code=404, detail="مشتری یافت نشد")
    return customers[customer_id]


def _grant_response(grant: CreditGrantRecord) -> CreditResponse:
    return CreditResponse(**grant.__dict__)


def _active_credit(customer_id: str, as_of: date) -> list[CreditGrantRecord]:
    return [
        grant for grant in _credit
        if grant.customer_id == customer_id and grant.expires_on >= as_of and grant.remaining_toman > 0
    ]


def _coupon_status(coupon: Coupon, as_of: date) -> CouponStatus:
    if coupon.status == CouponStatus.revoked:
        return CouponStatus.revoked
    if coupon.redeemed_on is None and as_of > coupon.expires_on:
        return CouponStatus.expired
    return coupon.status


def _coupon_response(coupon: Coupon, as_of: date) -> CouponResponse:
    return CouponResponse(
        code=coupon.code,
        customer_id=coupon.customer_id,
        discount_toman=coupon.discount_toman,
        status=_coupon_status(coupon, as_of),
        issued_on=coupon.issued_on,
        expires_on=coupon.expires_on,
        redeemed_on=coupon.redeemed_on,
    )


def _find_coupon(code: str) -> Coupon:
    coupon = _coupons.get(code.strip().upper())
    if coupon is None:
        raise HTTPException(status_code=404, detail="کد تخفیف یافت نشد")
    return coupon


AsOf = Annotated[Optional[date], Query(description=f"Evaluation date; defaults to today. Use {DEMO_DATE} for the snapshot.")]


@router.get("/segments")
def segments(as_of: AsOf = None, segment: Annotated[Optional[str], Query()] = None):
    as_of = as_of or date.today()
    if segment is not None and segment not in SEGMENTS_FA:
        raise HTTPException(status_code=422, detail="بخش نامعتبر است")
    profiles = [profile(c, as_of) for c in load_customers().values()]
    counts = Counter(p.rfm_segment for p in profiles)
    return {
        "as_of": as_of,
        "segment_counts": {key: counts.get(key, 0) for key in SEGMENTS_FA},
        "customers": [p for p in profiles if segment is None or p.rfm_segment == segment],
    }


@router.get("/customers/{customer_id}", response_model=CustomerProfile)
def customer_profile(customer_id: str, as_of: AsOf = None):
    return profile(_customer(customer_id), as_of or date.today())


@router.get("/points", response_model=PointsSummary)
def get_points(customer_id: str, as_of: AsOf = None):
    as_of = as_of or date.today()
    customer = _customer(customer_id)
    records = entry_points(customer, as_of) + _points.get(customer_id, [])
    return PointsSummary(
        customer_id=customer_id,
        points_balance=sum(record.points for record in records),
        rfm_segment=rfm_segment(customer, as_of)[0],
        entries=len(records),
    )


@router.post("/points", response_model=PointsSummary, status_code=201)
def earn_points(customer_id: str, entry: PointsEntry, as_of: AsOf = None):
    as_of = as_of or date.today()
    customer = _customer(customer_id)
    if entry.points == 0 or not entry.reason.strip():
        raise HTTPException(status_code=422, detail="امتیاز و دلیل آن الزامی است")
    if entry.points < 0 and entry.points + points_balance(customer_id, as_of) < 0:
        raise HTTPException(status_code=422, detail="موجودی امتیاز کافی نیست")
    with _lock:
        _points.setdefault(customer_id, []).append(
            PointsRecord(customer_id, entry.points, entry.reason.strip(), entry.source, as_of)
        )
    return get_points(customer_id, as_of)


@router.post("/customers/{customer_id}/credit", response_model=CreditResponse, status_code=201)
def grant_credit(customer_id: str, grant: CreditGrant):
    _customer(customer_id)
    as_of = date.today()
    with _lock:
        if grant.points > points_balance(customer_id, as_of):
            raise HTTPException(status_code=422, detail="موجودی امتیاز برای تبدیل به اعتبار کافی نیست")
        amount = grant.points * CREDIT_TOMAN_PER_POINTS
        global _next_grant_id
        record = CreditGrantRecord(
            _next_grant_id, customer_id, amount,
            as_of + timedelta(days=grant.valid_days), amount,
        )
        _next_grant_id += 1
        _credit.append(record)
        _points.setdefault(customer_id, []).append(
            PointsRecord(customer_id, -grant.points, "تبدیل امتیاز به اعتبار خرید", "credit_grant", as_of)
        )
    return _grant_response(record)


@router.get("/customers/{customer_id}/credit", response_model=list[CreditResponse])
def list_credit(customer_id: str, as_of: AsOf = None):
    _customer(customer_id)
    as_of = as_of or date.today()
    return [_grant_response(grant) for grant in _active_credit(customer_id, as_of)]


@router.post("/coupons", response_model=CouponResponse, status_code=201)
def issue_coupon(request: CouponRequest):
    _customer(request.customer_id)
    as_of = date.today()
    global _coupon_counter
    with _lock:
        _coupon_counter += 1
        code = f"VAFA-{_coupon_counter:04d}"
        coupon = Coupon(
            code, request.customer_id, request.discount_toman, CouponStatus.active,
            as_of, as_of + timedelta(days=request.expires_in_days),
        )
        _coupons[code] = coupon
    return _coupon_response(coupon, as_of)


@router.get("/coupons", response_model=list[CouponResponse])
def list_coupons(customer_id: Annotated[Optional[str], Query()] = None, as_of: AsOf = None):
    as_of = as_of or date.today()
    return [
        _coupon_response(c, as_of) for c in _coupons.values()
        if customer_id is None or c.customer_id == customer_id
    ]


@router.get("/coupons/{code}", response_model=CouponResponse)
def get_coupon(code: str, as_of: AsOf = None):
    as_of = as_of or date.today()
    return _coupon_response(_find_coupon(code), as_of)


@router.post("/coupons/{code}/validate")
def validate_coupon(code: str, check: CouponValidation):
    as_of = check.as_of or date.today()
    coupon = _find_coupon(code)
    status = _coupon_status(coupon, as_of)
    if status != CouponStatus.active or coupon.redeemed_on is not None:
        raise HTTPException(status_code=422, detail=f"کد تخفیف قابل استفاده نیست ({status.value})")
    final_value = max(check.order_value_toman - coupon.discount_toman, 0)
    return {
        "code": coupon.code,
        "valid": True,
        "discount_toman": coupon.discount_toman,
        "final_value_toman": final_value,
        "expires_on": coupon.expires_on,
    }


@router.post("/coupons/{code}/revoke", response_model=CouponResponse)
def revoke_coupon(code: str):
    coupon = _find_coupon(code)
    if coupon.redeemed_on is not None:
        raise HTTPException(status_code=409, detail="کد تخفیف قبلاً استفاده شده است")
    coupon.status = CouponStatus.revoked
    return _coupon_response(coupon, date.today())
