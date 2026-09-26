# Next-Best-Action Engine

> Explainable rule-based retention recommendations with consent and marketing-frequency safeguards.

## Responsibilities
- Load customers, cart events, and tagged conversations from synthetic CSVs.
- Select a consented channel, compute signals, and return a `NextBestAction` with Persian message and reason.
- `decide(..., as_of=None)` and `run_all(as_of=None)` default to today's date. The CLI accepts `--as-of 2026-07-24` for reproducible mock results.

## Decision priority
1. Do-not-disturb or no consent: suppress, channel `none`, empty message.
2. Complaint within 45 days: care, including fatigued customers who consent.
3. Four or more messages in 30 days: monitor, channel `none`, no marketing message.
4. Latest eligible abandoned cart: installment, shipping, cashback, or reminder.
5. High churn: personalized VIP cashback or limited-time non-VIP discount.
6. Mild churn: reminder.
7. Active loyal customer: loyalty access; otherwise monitor.

## Contracts / Edge cases
- Negative event ages are excluded. Cart window is 0–3 days; complaint window 0–45; price, shipping, and payment signals 0–30, inclusive.
- Newer completion suppresses an older abandoned cart. Same-day completion wins because the schema has no timestamps. One cart flow per customer is assumed until cart IDs are added.
- BNPL threshold uses the actual cart value, not historical average order value.
- Future purchase dates produce zero churn days, not negative risk.
- Customer aggregates remain fixed even when evaluating a different date.
- Offer availability, import validation, auth, and dispatch remain future work in `docs/future-issues.json`.

## Dependencies
- [[entities/data-model]] — fixture schemas and scenarios.
- [[entities/api]] — HTTP exposure.
- [[concepts/decision-rules]] — thresholds and precedence.

## Code sources
- `mvp/engine/next_best_action.py:110` — latest cart selection.
- `mvp/engine/next_best_action.py:119` — time-bounded conversation signals.
- `mvp/engine/next_best_action.py:171` — decision function.
- `mvp/engine/next_best_action.py:288` — batch execution.
- `mvp/test_mvp.py:17` — engine regression tests.
