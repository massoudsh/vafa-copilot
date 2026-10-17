# API

> Read-only FastAPI demo serving synthetic retention recommendations; no messages are sent.

## Routes
- `GET /` — service status.
- `GET /demo` — fixed synthetic snapshot metadata.
- `GET /analytics` — dashboard aggregates: matching customers, actionable count, high urgency, action/channel/city distributions.
- `GET /next-best-action` — all decisions with optional `as_of`, `action_type`, `urgency`, `channel`, and `city` filters.
- `GET /next-best-action/{customer_id}` — one decision; missing customer returns 404.
- `/openapi.json`, `/docs`, `/redoc` — generated contracts and documentation.

## Contracts / Edge cases
- Both list routes accept optional `as_of=YYYY-MM-DD`; invalid dates return 422, omitted dates use today.
- List filters are exact matches; an unknown value returns an empty list/zeroed analytics counts rather than broadening the result.
- Analytics counts are calculated from the same filtered recommendation set, so `matching_customers` equals the sum of `action_counts`.
- The date changes signal evaluation, not customer aggregate history; this is not historical backtesting.
- Response models use the `NextBestAction` dataclass, including its OpenAPI schema.
- CSV data is read per request, without caching or a database. No authentication: use synthetic data only.
- The static landing dashboard mirrors the filter experience with synthetic data and does not call the API.
- Tests use in-process HTTP through TestClient; no browser or persistent server is needed.

## Dependencies
- [[entities/next-best-action-engine]] — decisions and batch execution.
- [[entities/data-model]] — synthetic CSV snapshots.
- Runtime: FastAPI and Uvicorn; test requirements additionally include HTTPX.

## Code sources
- `mvp/api/main.py:21` — application metadata.
- `mvp/api/main.py:37` — demo metadata.
- `mvp/api/main.py:49` — decision routes and response models.
- `mvp/test_mvp.py:111` — endpoint regression tests.
