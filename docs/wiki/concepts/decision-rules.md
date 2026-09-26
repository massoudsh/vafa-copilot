# Decision Rules

> First matching rule wins; each result includes a human-readable Persian reason.

## Rule priority
1. Do-not-disturb or no consent on any channel: `suppress`, no channel or message.
2. Complaint aged 0–45 days: `care`, never a sales offer. Consent is still required; marketing fatigue does not block support.
3. `messages_last_30d >= 4`: `monitor`, no marketing message, including cart and high-churn scenarios.
4. Latest cart event aged 0–3 days is abandoned:
   - Payment question aged 0–30 days or **cart value** at least 1,200,000 toman: `bnpl`.
   - Shipping question aged 0–30 days: `free_shipping`.
   - Price question aged 0–30 days and non-VIP: `cashback`.
   - Otherwise: `reminder`.
5. Churn ratio > 1.6: VIP gets personalized `cashback`; non-VIP gets `discount_timeboxed`.
6. 1 < churn ratio <= 1.6: `reminder`.
7. Active VIP or regular: `loyalty_no_discount`.
8. Otherwise: `monitor`.

## Metrics and limitations
- VIP: orders >= 15 or total spend >= 20,000,000 toman. Regular: orders >= 6. Otherwise new.
- Churn ratio: non-negative days since purchase / max(typical cycle days, 1).
- A newer or same-day completed event cancels an abandoned event; absent cart IDs, this assumes one customer cart flow.
- Future events never contribute to signal scores. All upper day boundaries are inclusive.
- Evaluation date defaults to today; explicit dates enable deterministic fixture evaluation, not historical aggregate reconstruction.
- No real offer eligibility or dispatch is implemented.

## Dependencies
- [[entities/next-best-action-engine]] — implementation.
- [[entities/data-model]] — input fields.
- [[concepts/architecture-pipeline]] — product roadmap.

## Code sources
- `mvp/engine/next_best_action.py:110` — cart selection.
- `mvp/engine/next_best_action.py:171` — rule precedence.
- `mvp/test_mvp.py:25` — expected mock actions.
