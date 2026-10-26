"""Synthetic customer workspace; mutations are review-only and lost on restart."""

from datetime import date
from threading import RLock

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from engine.next_best_action import load_customers, load_cart_events, load_conversations, decide
if __package__:
    from .loyalty import profile, points_balance
else:
    from loyalty import profile, points_balance

router = APIRouter(prefix="/customers", tags=["customers"])
_lock = RLock()
MAX_ACTIVE_REFERRALS = 5
_tags: dict[str, list[str]] = {}
_referrals: dict[str, str] = {}
_feedback: dict[str, dict] = {}


class TextModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Tags(TextModel):
    tags: list[str] = Field(max_length=10)


class Referral(TextModel):
    referred_id: str = Field(min_length=1, max_length=40)


class Feedback(TextModel):
    score: int = Field(ge=0, le=10, strict=True)
    comment: str = Field(default="", max_length=500)


def reset():
    with _lock:
        _tags.clear()
        _referrals.clear()
        _feedback.clear()


def customer(customer_id):
    value = load_customers().get(customer_id)
    if value is None:
        raise HTTPException(404, "مشتری یافت نشد")
    return value


def normalize(value):
    return value.casefold().replace("ي", "ی").replace("ك", "ک").strip()


@router.get("")
def directory(q: str = Query(default="", max_length=100), tag: str | None = None,
              as_of: date | None = None):
    as_of = as_of or date.today()
    with _lock:
        return [
            {**profile(c, as_of).model_dump(), "tags": _tags.get(c.customer_id, []),
             "points": points_balance(c.customer_id, as_of)}
            for c in load_customers().values()
            if normalize(q) in normalize(f"{c.customer_id} {c.name} {c.city}")
            and (tag is None or normalize(tag) in _tags.get(c.customer_id, []))
        ]


@router.get("/feedback/summary")
def feedback_summary():
    with _lock:
        scores = [item["score"] for item in _feedback.values()]
    count = len(scores)
    promoters = sum(score >= 9 for score in scores)
    detractors = sum(score <= 6 for score in scores)
    return {"responses": count, "promoters": promoters, "detractors": detractors,
            "passives": count - promoters - detractors,
            "nps": round(100 * (promoters - detractors) / count, 1) if count else None,
            "data_source": "synthetic_manual_feedback"}


@router.get("/{customer_id}")
def customer_360(customer_id: str, as_of: date | None = None):
    c = customer(customer_id)
    as_of = as_of or date.today()
    carts = [e for e in load_cart_events().get(customer_id, []) if date.fromisoformat(e["date"]) <= as_of]
    conversations = [e for e in load_conversations().get(customer_id, []) if date.fromisoformat(e["date"]) <= as_of]
    with _lock:
        return {"profile": profile(c, as_of), "points": points_balance(customer_id, as_of),
                "tags": _tags.get(customer_id, []), "cart_events": carts,
                "conversations": conversations, "recommendation": decide(c, carts, conversations, as_of),
                "consent": {"sms": c.opt_in_sms, "whatsapp": c.opt_in_whatsapp,
                            "instagram_dm": c.opt_in_instagram, "do_not_disturb": c.do_not_disturb},
                "referrals": [key for key, value in _referrals.items() if value == customer_id],
                "referred_by": _referrals.get(customer_id), "feedback": _feedback.get(customer_id),
                "as_of": as_of, "synthetic": True}


@router.put("/{customer_id}/tags")
def set_tags(customer_id: str, request: Tags):
    customer(customer_id)
    tags = list(dict.fromkeys(normalize(tag) for tag in request.tags))
    if any(not tag or len(tag) > 40 for tag in tags):
        raise HTTPException(422, "برچسب باید ۱ تا ۴۰ نویسه باشد")
    with _lock:
        _tags[customer_id] = tags
    return {"customer_id": customer_id, "tags": tags}


@router.post("/{customer_id}/referrals", status_code=201)
def add_referral(customer_id: str, request: Referral):
    customer(customer_id)
    customer(request.referred_id)
    if customer_id == request.referred_id:
        raise HTTPException(422, "معرف و دعوت‌شده باید متفاوت باشند")
    with _lock:
        active_count = sum(value == customer_id for value in _referrals.values())
        if active_count >= MAX_ACTIVE_REFERRALS:
            raise HTTPException(422, "سقف دعوت فعال این مشتری پر شده است")
        if request.referred_id in _referrals:
            raise HTTPException(409, "برای این مشتری معرف ثبت شده است")
        ancestor = customer_id
        while ancestor in _referrals:
            ancestor = _referrals[ancestor]
            if ancestor == request.referred_id:
                raise HTTPException(422, "زنجیره دعوت نمی‌تواند حلقه داشته باشد")
        _referrals[request.referred_id] = customer_id
    return {"referrer_id": customer_id, "referred_id": request.referred_id,
            "reward_issued": False, "status": "recorded_for_review"}


@router.put("/{customer_id}/feedback")
def save_feedback(customer_id: str, request: Feedback):
    customer(customer_id)
    with _lock:
        _feedback[customer_id] = {**request.model_dump(), "recorded_on": date.today()}
        return {"customer_id": customer_id, **_feedback[customer_id]}
