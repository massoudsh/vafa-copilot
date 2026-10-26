import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from mvp.api.main import app
from mvp.api import automation, campaigns, customers, integrations, loyalty
from mvp.api.automation import next_send_time
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

    def test_analytics_summary_and_filters(self):
        response = self.client.get("/analytics", params={"as_of": "2026-07-24"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_customers"], 17)
        self.assertEqual(data["matching_customers"], 17)
        self.assertEqual(sum(data["action_counts"].values()), 17)
        self.assertEqual(data["high_urgency"], 6)

        filtered = self.client.get("/analytics", params={"as_of": "2026-07-24", "urgency": "high"}).json()
        self.assertEqual(filtered["matching_customers"], 6)
        self.assertEqual(set(filtered["urgency_counts"]), {"high"})

        city_filtered = self.client.get("/next-best-action", params={"as_of": "2026-07-24", "city": "تهران", "channel": "none"})
        self.assertEqual(city_filtered.status_code, 200)
        self.assertTrue(all(item["channel"] == "none" for item in city_filtered.json()))

    def test_analytics_unknown_filter_returns_empty(self):
        response = self.client.get("/analytics", params={"as_of": "2026-07-24", "action_type": "unknown"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matching_customers"], 0)
        self.assertEqual(response.json()["action_counts"], {})

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
        with patch("mvp.api.main.load_customers", return_value={}):
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

    def test_dashboard_route_serves_landing_page(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertIn("next-best-action", response.text)
        self.assertNotIn("/dashboard", self.client.get("/openapi.json").json()["paths"])

    def test_cors_is_opt_in(self):
        preflight = {"Origin": "https://shop.example", "Access-Control-Request-Method": "GET"}
        self.assertNotIn("access-control-allow-origin", self.client.options("/next-best-action", headers=preflight).headers)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        campaigns.reset()
        self.addCleanup(campaigns.reset)
        self.snapshot = {"as_of": "2026-07-24"}

    def create(self, *customer_ids):
        return self.client.post(
            "/campaigns",
            params=[("customer_ids", customer_id) for customer_id in customer_ids] + list(self.snapshot.items()),
        )

    def test_preview_uses_recommendation_and_rejects_suppressed(self):
        response = self.client.post("/campaigns/preview", params={"customer_id": "C001", **self.snapshot})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message_fa"], response.json()["original_message_fa"])
        self.assertEqual(response.json()["channel"], "instagram_dm")
        edited = self.client.post("/campaigns/preview", params={"customer_id": "C001", "message_fa": "متن سفارشی", **self.snapshot})
        self.assertEqual(edited.json()["message_fa"], "متن سفارشی")
        for customer_id in ("C010", "C013"):
            with self.subTest(customer=customer_id):
                blocked = self.client.post("/campaigns/preview", params={"customer_id": customer_id, **self.snapshot})
                self.assertEqual(blocked.status_code, 422)
        self.assertEqual(self.client.post("/campaigns/preview", params={"customer_id": "NOPE"}).status_code, 404)

    def test_create_approve_edit_and_reject_flow(self):
        created = self.create("C001", "C002", "C001")
        self.assertEqual(created.status_code, 201)
        self.assertEqual([item["campaign_id"] for item in created.json()], [1, 2])
        self.assertTrue(all(item["status"] == "pending" for item in created.json()))

        edited = self.client.patch("/campaigns/1", json={"message_fa": "سلام سارا، اقساط آماده‌ست."})
        self.assertEqual(edited.json()["message_fa"], "سلام سارا، اقساط آماده‌ست.")
        self.assertEqual(edited.json()["original_message_fa"], created.json()[0]["message_fa"])

        approved = self.client.post("/campaigns/1/approve")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertIsNotNone(approved.json()["reviewed_on"])

        rejected = self.client.post("/campaigns/2/reject", json={"reason": "پیام مناسب نیست"})
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual(rejected.json()["review_reason"], "پیام مناسب نیست")

        self.assertEqual(self.client.post("/campaigns/1/approve").status_code, 409)
        self.assertEqual(self.client.patch("/campaigns/1", json={"message_fa": "x"}).status_code, 409)
        self.assertEqual(self.client.post("/campaigns/2/reject", json={}).status_code, 422)
        self.assertEqual(self.client.get("/campaigns/999").status_code, 404)

    def test_suppressed_unknown_and_duplicate_customers_are_blocked(self):
        self.assertEqual(self.create("C010").status_code, 422)
        self.assertEqual(self.create("C013").status_code, 422)
        self.assertEqual(self.create("NOPE").status_code, 404)
        self.assertEqual(self.create("C005").status_code, 201)
        self.assertEqual(self.create("C005").status_code, 409)
        self.assertEqual(self.client.get("/campaigns").json()[0]["customer_id"], "C005")
        self.assertEqual(self.client.get("/campaigns").json()[0]["status"], "pending")

    def test_cancel_and_status_filter_and_summary(self):
        self.create("C001", "C005")
        self.assertEqual(self.client.post("/campaigns/1/cancel").json()["status"], "cancelled")
        self.client.post("/campaigns/2/approve")
        self.assertEqual(self.client.post("/campaigns/1/cancel").status_code, 409)
        self.assertEqual(len(self.client.get("/campaigns", params={"status": "cancelled"}).json()), 1)
        summary = self.client.get("/campaigns/summary").json()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["status_counts"], {"cancelled": 1, "approved": 1})
        self.assertFalse(summary["sends_messages"])


class LoyaltyTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        for module in (loyalty,):
            module.reset()
            self.addCleanup(module.reset)

    def test_segments_cover_every_customer_and_are_filterable(self):
        response = self.client.get("/loyalty/segments", params={"as_of": "2026-07-24"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(sum(data["segment_counts"].values()), 17)
        self.assertEqual(len(data["customers"]), 17)
        filtered = self.client.get("/loyalty/segments", params={"as_of": "2026-07-24", "segment": "champion"}).json()
        self.assertTrue(all(item["rfm_segment"] == "champion" for item in filtered["customers"]))
        self.assertEqual(self.client.get("/loyalty/segments", params={"segment": "nope"}).status_code, 422)

    def test_profile_and_unknown_customer(self):
        profile = self.client.get("/loyalty/customers/C006", params={"as_of": "2026-07-24"}).json()
        self.assertEqual(profile["rfm_segment"], "champion")
        self.assertEqual(profile["segment_fa"], "وفادار ارزشمند")
        self.assertGreaterEqual(profile["rfm_score"], 12)
        self.assertEqual(self.client.get("/loyalty/customers/NOPE").status_code, 404)

    def test_points_can_be_earned_and_converted_to_credit(self):
        before = self.client.get("/loyalty/points", params={"customer_id": "C001", "as_of": "2026-07-24"}).json()
        self.assertGreater(before["points_balance"], 0)
        self.assertEqual(self.client.post("/loyalty/points", params={"customer_id": "C001"}, json={"points": 0, "reason": "x"}).status_code, 422)

        earned = self.client.post("/loyalty/points", params={"customer_id": "C001", "as_of": "2026-07-24"}, json={"points": 100, "reason": "نظر مفید"})
        self.assertEqual(earned.status_code, 201)
        self.assertEqual(earned.json()["points_balance"], before["points_balance"] + 100)
        self.assertEqual(self.client.post("/loyalty/points", params={"customer_id": "C001"}, json={"points": -10_000, "reason": "x"}).status_code, 422)

        too_much = self.client.post("/loyalty/customers/C001/credit", json={"points": 10_000_000})
        self.assertEqual(too_much.status_code, 422)
        grant = self.client.post("/loyalty/customers/C001/credit", json={"points": 50})
        self.assertEqual(grant.status_code, 201)
        self.assertEqual(grant.json()["amount_toman"], 50 * 1_000)
        self.assertEqual(len(self.client.get("/loyalty/customers/C001/credit").json()), 1)
        remaining = self.client.get("/loyalty/points", params={"customer_id": "C001", "as_of": "2026-07-24"}).json()["points_balance"]
        self.assertEqual(remaining, earned.json()["points_balance"] - 50)

    def test_coupon_issue_validate_revoke(self):
        issued = self.client.post("/loyalty/coupons", json={"customer_id": "C002", "discount_toman": 100_000, "expires_in_days": 7})
        self.assertEqual(issued.status_code, 201)
        code = issued.json()["code"]
        self.assertEqual(issued.json()["status"], "active")
        self.assertEqual(self.client.post("/loyalty/coupons", json={"customer_id": "NOPE", "discount_toman": 1000}).status_code, 404)
        self.assertEqual(self.client.post("/loyalty/coupons", json={"customer_id": "C002", "discount_toman": 0}).status_code, 422)

        valid = self.client.post(f"/loyalty/coupons/{code}/validate", json={"order_value_toman": 700_000})
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["final_value_toman"], 600_000)
        self.assertEqual(self.client.post("/loyalty/coupons/VAFA-9999/validate", json={"order_value_toman": 1}).status_code, 404)
        self.assertEqual(self.client.post(f"/loyalty/coupons/{code}/validate", json={"order_value_toman": 0}).status_code, 422)

        expired = self.client.post(f"/loyalty/coupons/{code}/validate", json={"order_value_toman": 700_000, "as_of": "2030-01-01"})
        self.assertEqual(expired.status_code, 422)
        self.assertEqual(self.client.get(f"/loyalty/coupons/{code}", params={"as_of": "2030-01-01"}).json()["status"], "expired")

        self.assertEqual(self.client.post(f"/loyalty/coupons/{code.lower()}/revoke").json()["status"], "revoked")
        self.assertEqual(self.client.post(f"/loyalty/coupons/{code}/validate", json={"order_value_toman": 700_000}).status_code, 422)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        automation.reset()
        self.addCleanup(automation.reset)
        self.journey = {
            "name": "بازگشت سبد",
            "trigger": "cart_abandoned",
            "steps": [
                {"name": "یادآوری", "delay_days": 0, "condition": "always", "message_fa": "سبدتون منتظرتونه"},
                {"name": "پیگیری", "delay_days": 1, "condition": "always", "message_fa": "هنوز منتظرتونه"},
                {"name": "آخرین یادآوری", "delay_days": 2, "condition": "always", "message_fa": "فردا حذف می‌شود"},
                {"name": "پیشنهاد ویژه", "delay_days": 3, "condition": "high_urgency", "message_fa": "ویژه"},
            ],
        }

    def test_quiet_hours_move_sends_to_morning(self):
        self.assertEqual(next_send_time(datetime(2026, 7, 24, 23, 30)), datetime(2026, 7, 25, 9))
        self.assertEqual(next_send_time(datetime(2026, 7, 24, 6, 0)), datetime(2026, 7, 24, 9))
        self.assertEqual(next_send_time(datetime(2026, 7, 24, 12, 15)), datetime(2026, 7, 24, 12, 15))

    def test_weekly_cap_limits_planned_sends(self):
        journey_id = self.client.post("/automation", json=self.journey).json()["journey_id"]
        response = self.client.post(f"/automation/{journey_id}/schedule", params={"as_of": "2026-07-24"}, json={"customer_id": "C001"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([step["status"] for step in data["steps"]], ["planned", "planned", "capped", "capped"])
        self.assertTrue(data["capped"])

    def test_trigger_condition_and_pause(self):
        journey_id = self.client.post("/automation", json=self.journey).json()["journey_id"]
        not_triggered = self.client.post(f"/automation/{journey_id}/schedule", params={"as_of": "2026-07-24"}, json={"customer_id": "C003"})
        self.assertEqual(not_triggered.status_code, 422)
        self.assertEqual(self.client.post(f"/automation/{journey_id}/schedule", json={"customer_id": "NOPE"}).status_code, 404)

        complaint = {"name": "پیگیری شکایت", "trigger": "complaint", "steps": [self.journey["steps"][0]]}
        complaint_id = self.client.post("/automation", json=complaint).json()["journey_id"]
        self.assertEqual(self.client.post(f"/automation/{complaint_id}/schedule", params={"as_of": "2026-07-24"}, json={"customer_id": "C014"}).status_code, 200)
        self.assertEqual(self.client.post("/automation", json=dict(complaint, steps=[dict(complaint["steps"][0], condition="bogus")])).status_code, 422)

        self.assertFalse(self.client.post(f"/automation/{journey_id}/pause").json()["enabled"])
        self.assertEqual(self.client.post(f"/automation/{journey_id}/schedule", json={"customer_id": "C001"}).status_code, 409)
        self.assertTrue(self.client.post(f"/automation/{journey_id}/resume").json()["enabled"])
        self.assertEqual(len(self.client.get("/automation").json()), 2)
        self.assertEqual(self.client.get("/automation/99").status_code, 404)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        integrations.reset()
        self.addCleanup(integrations.reset)

    def test_scoped_token_protects_endpoint(self):
        self.assertEqual(self.client.get("/integrations/protected/recommendations").status_code, 401)
        self.assertEqual(self.client.post("/integrations/tokens", json={"name": "x", "scopes": ["root"]}).status_code, 422)
        token = self.client.post("/integrations/tokens", json={"name": "داشبورد", "scopes": ["campaigns:read"]}).json()
        denied = self.client.get("/integrations/protected/recommendations", headers={"Authorization": f"Bearer {token['token']}"})
        self.assertEqual(denied.status_code, 403)
        reader = self.client.post("/integrations/tokens", json={"name": "خواننده", "scopes": ["recommendations:read"]}).json()
        allowed = self.client.get("/integrations/protected/recommendations", headers={"Authorization": f"Bearer {reader['token']}"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(len(allowed.json()), 17)
        self.client.delete(f"/integrations/tokens/{reader['token_id']}")
        assert self.client.get("/integrations/protected/recommendations", headers={"Authorization": f"Bearer {reader['token']}"}).status_code == 401

    def test_webhook_signature_and_retry(self):
        self.assertEqual(self.client.post("/integrations/webhooks", json={"url": "http://shop.example/hook"}).status_code, 422)
        self.assertEqual(self.client.post("/integrations/webhooks", json={"url": "https://shop.example/hook", "events": ["bogus"]}).status_code, 422)
        hook = self.client.post("/integrations/webhooks", json={"url": "https://shop.example/hook", "events": ["campaign.approved"]}).json()
        ok = self.client.post(f"/integrations/webhooks/{hook['webhook_id']}/deliveries", json={"event": "campaign.approved", "payload": {"id": 1}}).json()
        self.assertTrue(ok["delivered"])
        self.assertEqual(ok["signature"], integrations.sign(hook["signing_secret"], integrations._deliveries[-1].body))
        self.assertEqual(self.client.post(f"/integrations/webhooks/{hook['webhook_id']}/deliveries", json={"event": "cart.abandoned"}).status_code, 422)

        failed = self.client.post(
            f"/integrations/webhooks/{hook['webhook_id']}/deliveries",
            params={"simulate_failure": "true"}, json={"event": "campaign.approved"},
        ).json()
        self.assertFalse(failed["delivered"])
        self.assertIsNotNone(failed["next_retry_at"])
        self.assertEqual(self.client.get("/integrations/webhooks/unknown/deliveries").status_code, 404)
        listed = self.client.get("/integrations/webhooks").json()[0]
        self.assertEqual((listed["deliveries"], listed["retries"]), (2, 1))
        self.assertEqual(len(self.client.get(f"/integrations/webhooks/{hook['webhook_id']}/deliveries").json()), 2)

    def test_branches(self):
        cities = self.client.get("/integrations/branches").json()
        self.assertEqual(sum(city["customer_count"] for city in cities), 17)
        self.assertTrue(all(not city["is_branch"] for city in cities))
        self.assertEqual(self.client.post("/integrations/branches", json={"city": "تهران"}).json()["is_branch"], True)
        self.assertEqual(self.client.post("/integrations/branches", json={"city": "شهر ناموجود"}).status_code, 404)
        self.assertEqual(self.client.delete("/integrations/branches/تهران").json()["is_branch"], False)




class CustomerWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        customers.reset()
        self.addCleanup(customers.reset)

    def test_customer_360_search_tags_referral_and_feedback(self):
        directory = self.client.get("/customers", params={"q": "سارا", "as_of": "2026-07-24"})
        self.assertEqual(directory.status_code, 200)
        self.assertEqual([item["customer_id"] for item in directory.json()], ["C001"])
        self.assertEqual(self.client.get("/customers/NOPE").status_code, 404)

        tagged = self.client.put("/customers/C001/tags", json={"tags": [" VIP ", "بازگشت", "VIP"]})
        self.assertEqual(tagged.json()["tags"], ["vip", "بازگشت"])
        self.assertEqual(self.client.get("/customers", params={"tag": "vip"}).json()[0]["customer_id"], "C001")

        blocked = self.client.post("/customers/C001/referrals", json={"referred_id": "C001"})
        self.assertEqual(blocked.status_code, 422)
        referral = self.client.post("/customers/C001/referrals", json={"referred_id": "C002"})
        self.assertEqual(referral.status_code, 201)
        self.assertFalse(referral.json()["reward_issued"])
        self.assertEqual(self.client.post("/customers/C003/referrals", json={"referred_id": "C002"}).status_code, 409)

        feedback = self.client.put("/customers/C001/feedback", json={"score": 10, "comment": "عالی"})
        self.assertEqual(feedback.status_code, 200)
        summary = self.client.get("/customers/feedback/summary").json()
        self.assertEqual((summary["responses"], summary["promoters"], summary["nps"]), (1, 1, 100.0))

        profile = self.client.get("/customers/C001", params={"as_of": "2026-07-24"})
        self.assertEqual(profile.status_code, 200)
        data = profile.json()
        self.assertEqual(data["profile"]["customer_id"], "C001")
        self.assertEqual(data["referred_by"], None)
        self.assertEqual(data["feedback"]["score"], 10)
        self.assertEqual(len(data["cart_events"]), 1)
        invalid = self.client.put("/customers/C001/feedback", json={"score": 11})
        self.assertEqual(invalid.status_code, 422)

    def test_search_is_case_and_persian_variant_tolerant(self):
        self.assertEqual(self.client.get("/customers", params={"q": "ی"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
