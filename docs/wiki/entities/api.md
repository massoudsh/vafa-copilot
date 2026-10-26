# API

> FastAPI demo serving synthetic retention recommendations, a campaign review queue, a loyalty club, automation journeys, and store integrations; no messages are sent.

## Routes
- `GET /` — service status.
- `GET /demo` — fixed synthetic snapshot metadata.
- `GET /analytics` — dashboard aggregates: matching customers, actionable count, high urgency, action/channel/city distributions.
- `GET /next-best-action` — all decisions with optional `as_of`, `action_type`, `urgency`, `channel`, and `city` filters.
- `GET /next-best-action/{customer_id}` — one decision; missing customer returns 404.
- Campaign queue in `mvp/api/campaigns.py`: `POST /campaigns/preview`, `POST /campaigns`, `GET /campaigns`, `GET /campaigns/summary`, `GET|PATCH /campaigns/{id}`, and `POST /campaigns/{id}/{approve|reject|cancel}`.
- Customer workspace in `mvp/api/customers.py`: `GET /customers` search/tag directory, `GET /customers/{id}` 360 profile, `PUT /customers/{id}/tags`, `POST /customers/{id}/referrals`, `PUT /customers/{id}/feedback`, and `GET /customers/feedback/summary`. Referral rewards are deliberately not issued until an external order confirmation exists.
- Loyalty in `mvp/api/loyalty.py`: `GET /loyalty/segments`, `GET /loyalty/customers/{id}`, `GET|POST /loyalty/points`, `GET|POST /loyalty/customers/{id}/credit`, `POST /loyalty/coupons`, `GET /loyalty/coupons[?customer_id=]`, `GET /loyalty/coupons/{code}`, and `POST /loyalty/coupons/{code}/{validate|revoke}`.
- Automation in `mvp/api/automation.py`: `GET|POST /automation`, `GET /automation/{id}`, `POST /automation/{id}/schedule`, and `POST /automation/{id}/{pause|resume}`.
- Integrations in `mvp/api/integrations.py`: `GET|POST /integrations/tokens`, `DELETE /integrations/tokens/{id}`, `GET /integrations/protected/recommendations` (Bearer token), `GET|POST /integrations/webhooks`, `GET|POST /integrations/webhooks/{id}/deliveries`, and `GET|POST /integrations/branches`.
- `GET /dashboard` — serves `landing/index.html`; hidden from the OpenAPI schema. When loading fails, the page keeps its mock data.
- `/openapi.json`, `/docs`, `/redoc` — generated contracts and documentation.

## Contracts / Edge cases
- Both list routes accept optional `as_of=YYYY-MM-DD`; invalid dates return 422, omitted dates use today.
- List filters are exact matches; an unknown value returns an empty list/zeroed analytics counts rather than broadening the result.
- Analytics counts are calculated from the same filtered recommendation set, so `matching_customers` equals the sum of `action_counts`.
- The date changes signal evaluation, not customer aggregate history; this is not historical backtesting.
- Response models use the `NextBestAction` dataclass, including its OpenAPI schema.
- CSV data is read per request, without caching or a database. No authentication: use synthetic data only.
- The dashboard fetches `/next-best-action` on the same origin and keeps its mock data if the request fails or returns an empty list; no `as_of` is sent, so it shows today's evaluation date.
- CORS is opt-in through the comma-separated `VAFA_CORS_ORIGINS` environment variable; without it, cross-origin browsers are blocked by default.
- Campaign state is in memory, lost on restart, and has no persistence, authentication, or delivery. Suppressed customers are rejected with 422; duplicate pending campaigns return 409; only pending campaigns can be edited, approved, rejected, or cancelled.
- `original_message_fa` preserves the engine's template after an edit; rejecting requires a non-empty reason.
- Customer directory normalizes Persian ي/ی and ك/ک for search and tags; 360 responses are synthetic and include only events up to `as_of`.
- Referral records are one-to-one for the referred customer, cap a referrer at five active referrals, reject self/cycles/duplicates, and return `reward_issued: false`; no financial reward is created.
- Feedback scores are integer 0–10; summary reports NPS as promoters (9–10) minus detractors (0–6) over responses, or null with no responses.
- RFM scores R (≤30/≤90/≤365 days), F (orders), and M (avg order value) from 1 to 5; segments are champion, loyal, new, at_risk, dormant. The 2026-07-24 split is 3 champion, 2 loyal, 8 new, 4 at_risk.
- Points: 1 per 10,000 toman spent plus a club bonus for champion (500) and loyal (250); 1 point converts to 1,000 toman of credit with a 90-day default expiry, debiting points in the same lock.
- Coupons are per customer, capped at 500,000 toman with 1–90 day expiry; validation rejects revoked or expired codes with 422 after computing the discounted order value.
- Automation triggers derive from the same `decide()` output (cart actions, care, churn ratio > 1). Steps run after a 0–30 day delay; conditions are `always|consent|high_urgency`; quiet hours 21:00–09:00 push a send to 09:00; at most 2 sends are planned per run and later steps are recorded as `capped`. Paused journeys return 409.
- Integration tokens are scoped to `customers:read|recommendations:read|campaigns:read|webhooks:write`; a missing token is 401 and a missing scope is 403. Webhooks require https URLs and known events, sign bodies with HMAC-SHA256, and expose the retry schedule; simulated failures send nothing and three consecutive failures mark the webhook `failing`.
- Loyalty, automation, and integration state is in memory; each module exposes a `reset()` used by tests.
- Tests use in-process HTTP through TestClient; no browser or persistent server is needed.

## Dependencies
- [[entities/next-best-action-engine]] — decisions and batch execution.
- [[entities/data-model]] — synthetic CSV snapshots.
- Runtime: FastAPI and Uvicorn; test requirements additionally include HTTPX.

## Code sources
- `mvp/api/main.py:1` — app, routers, filters, and analytics.
- `mvp/api/campaigns.py:1` — campaign preview, review, and summary routes.
- `mvp/api/customers.py:1` — customer directory, 360 view, tags, referrals, feedback.
- `mvp/api/loyalty.py:1` — RFM segments, points, wallet credit, coupons.
- `mvp/api/automation.py:1` — journeys, quiet hours, weekly cap.
- `mvp/api/integrations.py:1` — tokens, signed webhooks, branches.
- `mvp/test_mvp.py:111` — endpoint and campaign regression tests; loyalty, automation, and integration suites follow.
