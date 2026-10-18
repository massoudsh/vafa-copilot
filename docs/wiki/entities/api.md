# API

> FastAPI demo serving synthetic retention recommendations plus an in-memory campaign review queue; no messages are sent.

## Routes
- `GET /` — service status.
- `GET /demo` — fixed synthetic snapshot metadata.
- `GET /analytics` — dashboard aggregates: matching customers, actionable count, high urgency, action/channel/city distributions.
- `GET /next-best-action` — all decisions with optional `as_of`, `action_type`, `urgency`, `channel`, and `city` filters.
- `GET /next-best-action/{customer_id}` — one decision; missing customer returns 404.
- Campaign queue in `mvp/api/campaigns.py`: `POST /campaigns/preview`, `POST /campaigns`, `GET /campaigns`, `GET /campaigns/summary`, `GET|PATCH /campaigns/{id}`, and `POST /campaigns/{id}/{approve|reject|cancel}`.
- `/openapi.json`, `/docs`, `/redoc` — generated contracts and documentation.

## Contracts / Edge cases
- Both list routes accept optional `as_of=YYYY-MM-DD`; invalid dates return 422, omitted dates use today.
- List filters are exact matches; an unknown value returns an empty list/zeroed analytics counts rather than broadening the result.
- Analytics counts are calculated from the same filtered recommendation set, so `matching_customers` equals the sum of `action_counts`.
- The date changes signal evaluation, not customer aggregate history; this is not historical backtesting.
- Response models use the `NextBestAction` dataclass, including its OpenAPI schema.
- CSV data is read per request, without caching or a database. No authentication: use synthetic data only.
- The static landing dashboard mirrors the filter experience with synthetic data and does not call the API.
- Campaign state is in memory, lost on restart, and has no persistence, authentication, or delivery. Suppressed customers are rejected with 422; duplicate pending campaigns return 409; only pending campaigns can be edited, approved, rejected, or cancelled.
- `original_message_fa` preserves the engine's template after an edit; rejecting requires a non-empty reason.
- Tests use in-process HTTP through TestClient; no browser or persistent server is needed.

## Dependencies
- [[entities/next-best-action-engine]] — decisions and batch execution.
- [[entities/data-model]] — synthetic CSV snapshots.
- Runtime: FastAPI and Uvicorn; test requirements additionally include HTTPX.

## Code sources
- `mvp/api/main.py:1` — app, routers, filters, and analytics.
- `mvp/api/campaigns.py:1` — campaign preview, review, and summary routes.
- `mvp/test_mvp.py:111` — endpoint and campaign regression tests.
