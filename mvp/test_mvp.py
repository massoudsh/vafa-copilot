import unittest
from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from mvp.api.main import app
from engine.next_best_action import (
    DEMO_DATE, churn_risk_ratio, decide, latest_abandoned_cart,
    load_cart_events, load_conversations, load_customers, payment_need_score,
    pick_channel, price_sensitivity_score, recent_complaint, run_all,
    shipping_sensitivity_score,
)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.customer = load_customers()["C016"]
        self.cart = {"date": "2026-07-24", "abandoned": "1", "items": "mock", "cart_value_toman": "450000"}

    def action(self, customer=None, carts=None, convs=None):
        return decide(customer or self.customer, carts or [], convs or [], DEMO_DATE)

    def test_mock_scenarios(self):
        expected = {
            "C001": "bnpl", "C002": "discount_timeboxed", "C003": "monitor",
            "C004": "discount_timeboxed", "C005": "cashback", "C006": "loyalty_no_discount",
            "C007": "monitor", "C008": "discount_timeboxed", "C009": "loyalty_no_discount",
            "C010": "suppress", "C011": "monitor", "C012": "reminder", "C013": "suppress",
            "C014": "care", "C015": "free_shipping", "C016": "reminder", "C017": "monitor",
        }
        self.assertEqual({a.customer_id: a.action_type for a in run_all(DEMO_DATE)}, expected)

    def test_no_consent_overrides_complaint_and_cart(self):
        customer = replace(self.customer, opt_in_sms=False)
        result = self.action(customer, [self.cart], [{"intent_tag": "complaint", "date": "2026-07-24"}])
        self.assertEqual((result.action_type, result.channel, result.message_fa), ("suppress", "none", ""))

    def test_do_not_disturb_overrides_care(self):
        result = self.action(replace(self.customer, do_not_disturb=True), convs=[{"intent_tag": "complaint", "date": "2026-07-24"}])
        self.assertEqual((result.action_type, result.channel, result.message_fa), ("suppress", "none", ""))

    def test_fatigue_blocks_cart_and_churn_offers(self):
        for carts in ([], [self.cart]):
            with self.subTest(carts=carts):
                customer = replace(self.customer, messages_last_30d=4, last_purchase_date=date(2025, 1, 1))
                result = self.action(customer, carts)
                self.assertEqual((result.action_type, result.message_fa), ("monitor", ""))

    def test_care_precedes_marketing_fatigue(self):
        result = self.action(replace(self.customer, messages_last_30d=4), convs=[{"intent_tag": "complaint", "date": "2026-07-24"}])
        self.assertEqual(result.action_type, "care")

    def test_channel_fallback_uses_consent(self):
        self.assertEqual(pick_channel(replace(self.customer, preferred_channel="instagram_dm")), "sms")

    def test_high_cart_value_not_historical_average_selects_bnpl(self):
        self.assertEqual(self.action(carts=[dict(self.cart, cart_value_toman="1200000")]).action_type, "bnpl")
        self.assertEqual(self.action(replace(self.customer, avg_order_value=2000000), [self.cart]).action_type, "reminder")

    def test_signal_windows_exclude_future_and_expired_dates(self):
        for scorer, intent, window in (
            (recent_complaint, "complaint", 45),
            (price_sensitivity_score, "price_question", 30),
            (shipping_sensitivity_score, "shipping_question", 30),
            (payment_need_score, "payment_question", 30),
        ):
            for age in (-1, 0, window, window + 1):
                with self.subTest(intent=intent, age=age):
                    conv = {"intent_tag": intent, "date": (DEMO_DATE - timedelta(days=age)).isoformat()}
                    self.assertEqual(bool(scorer([conv], DEMO_DATE)), 0 <= age <= window)

    def test_cart_window(self):
        for age in (-1, 0, 3, 4):
            with self.subTest(age=age):
                cart = dict(self.cart, date=(DEMO_DATE - timedelta(days=age)).isoformat())
                self.assertEqual(latest_abandoned_cart([cart], DEMO_DATE) is not None, 0 <= age <= 3)

    def test_completion_supersedes_abandonment(self):
        abandoned = dict(self.cart, date="2026-07-23")
        completed = dict(self.cart, abandoned="0")
        for events in ([abandoned, completed], [completed, abandoned], [self.cart, completed], [completed, self.cart]):
            with self.subTest(events=events):
                self.assertIsNone(latest_abandoned_cart(events, DEMO_DATE))

    def test_future_completion_does_not_hide_current_cart(self):
        self.assertEqual(latest_abandoned_cart([self.cart, dict(self.cart, date="2026-07-25", abandoned="0")], DEMO_DATE), self.cart)

    def test_default_date_is_today(self):
        self.assertEqual(run_all(), run_all(date.today()))

    def test_future_purchase_has_no_negative_churn(self):
        self.assertEqual(churn_risk_ratio(replace(self.customer, last_purchase_date=date(2027, 1, 1)), DEMO_DATE), 0)

    def test_vip_churn_avoids_generic_discount(self):
        customer = replace(self.customer, total_orders=20, last_purchase_date=date(2026, 1, 1))
        self.assertEqual(self.action(customer).action_type, "cashback")

    def test_churn_boundaries(self):
        for days, expected in ((30, "monitor"), (31, "reminder"), (48, "reminder"), (49, "discount_timeboxed")):
            with self.subTest(days=days):
                self.assertEqual(self.action(replace(self.customer, last_purchase_date=DEMO_DATE - timedelta(days=days))).action_type, expected)

    def test_mock_references_are_valid(self):
        customers = load_customers()
        self.assertTrue(set(load_cart_events()) <= customers.keys())
        self.assertTrue(set(load_conversations()) <= customers.keys())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_root(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_demo_metadata_and_action_coverage(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["sends_messages"])
        self.assertEqual(data["snapshot_date"], "2026-07-24")
        self.assertEqual(data["customer_count"], 17)
        self.assertEqual(sum(data["action_counts"].values()), 17)
        self.assertEqual(len(data["action_counts"]), 9)

    def test_batch_matches_all_individual_endpoints(self):
        response = self.client.get("/next-best-action", params={"as_of": "2026-07-24"})
        self.assertEqual(response.status_code, 200)
        for action in response.json():
            with self.subTest(customer=action["customer_id"]):
                single = self.client.get(f"/next-best-action/{action['customer_id']}", params={"as_of": "2026-07-24"})
                self.assertEqual(single.status_code, 200)
                self.assertEqual(single.json(), action)
                self.assertTrue(action["reason_fa"])

    def test_missing_customer(self):
        response = self.client.get("/next-best-action/UNKNOWN")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "مشتری یافت نشد")

    def test_invalid_dates(self):
        for route in ("/next-best-action", "/next-best-action/C001"):
            for value in ("invalid", "2026-02-30", "", "2026-13-01"):
                with self.subTest(route=route, value=value):
                    self.assertEqual(self.client.get(route, params={"as_of": value}).status_code, 422)

    def test_default_uses_today(self):
        self.assertEqual(self.client.get("/next-best-action").json(), self.client.get("/next-best-action", params={"as_of": date.today().isoformat()}).json())

    def test_empty_dataset(self):
        with patch("engine.next_best_action.load_customers", return_value={}):
            self.assertEqual(self.client.get("/next-best-action").json(), [])

    def test_post_not_supported(self):
        self.assertEqual(self.client.post("/next-best-action", json={}).status_code, 405)

    def test_openapi_contract(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("NextBestAction", schema["components"]["schemas"])
        self.assertIn("/demo", schema["paths"])

    def test_docs_endpoints(self):
        for path in ("/docs", "/redoc"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()
