# API

> Read-only FastAPI demo serving synthetic retention recommendations; no messages are sent.

## Routes
- `GET /` — service status.
- `GET /demo` — fixed snapshot date `2026-07-24`, synthetic source, customer count, action distribution, and `sends_messages: false`.
- `GET /next-best-action` — all decisions.
- `GET /next-best-action/{customer_id}` — one decision; missing customer returns 404 with Persian detail.
- `/openapi.json`, `/docs`, `/redoc` — generated contracts and documentation.

## Contracts / Edge cases
- Both decision routes accept optional `as_of=YYYY-MM-DD`; invalid dates return 422, omitted dates use today.
- The date changes signal evaluation, not customer aggregate history; this is not historical backtesting.
- Response models use the `NextBestAction` dataclass, including its OpenAPI schema.
- CSV data is read per request, without caching or a database. No authentication: use synthetic data only.
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
