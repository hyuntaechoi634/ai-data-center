from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.billing import BillingStatusReader
import refresh_openai_billing


class BillingStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = Path(self.temporary.name) / "billing.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(
        self,
        updated_at: datetime | None = None,
        cost_source: str = "organization-costs",
    ) -> None:
        payload = {
            "schema_version": 1,
            "scope": "organization",
            "spent_usd": "1.250000",
            "cost_source": cost_source,
            "limit_usd": "10.00",
            "limit_verified": True,
            "currency": "USD",
            "enforcement": "enforcing",
            "updated_at": (updated_at or datetime.now(timezone.utc)).isoformat(),
        }
        self.cache.write_text(json.dumps(payload), encoding="utf-8")
        self.cache.chmod(0o600)

    def test_reads_only_sanitized_current_cache(self) -> None:
        self._write()
        with mock.patch.dict(
            os.environ,
            {"FIGURE_STUDIO_OPENAI_BILLING_CACHE": str(self.cache)},
            clear=False,
        ):
            status = BillingStatusReader().status()
        self.assertTrue(status["available"])
        self.assertEqual(status["spent_usd"], 1.25)
        self.assertEqual(status["limit_usd"], 10.0)
        self.assertTrue(status["limit_verified"])
        self.assertFalse(status["estimated"])

    def test_marks_usage_fallback_as_an_estimate(self) -> None:
        self._write(cost_source="usage-estimate")
        with mock.patch.dict(
            os.environ,
            {"FIGURE_STUDIO_OPENAI_BILLING_CACHE": str(self.cache)},
            clear=False,
        ):
            status = BillingStatusReader().status()
        self.assertTrue(status["available"])
        self.assertTrue(status["estimated"])
        self.assertEqual(status["cost_source"], "usage-estimate")
        self.assertIn("Estimated", status["message"])

    def test_stale_or_insecure_cache_is_not_current(self) -> None:
        self._write(datetime.now(timezone.utc) - timedelta(hours=1))
        with mock.patch.dict(
            os.environ,
            {
                "FIGURE_STUDIO_OPENAI_BILLING_CACHE": str(self.cache),
                "FIGURE_STUDIO_OPENAI_BILLING_STALE_SECONDS": "300",
            },
            clear=False,
        ):
            self.assertTrue(BillingStatusReader().status()["stale"])
            self.cache.chmod(0o644)
            status = BillingStatusReader().status()
        self.assertFalse(status["available"])
        self.assertIn("safely", status["message"])

    def test_unverified_display_limit_never_fakes_spend(self) -> None:
        missing = Path(self.temporary.name) / "missing.json"
        with mock.patch.dict(
            os.environ,
            {
                "FIGURE_STUDIO_OPENAI_BILLING_CACHE": str(missing),
                "FIGURE_STUDIO_OPENAI_DISPLAY_LIMIT_USD": "10",
            },
            clear=False,
        ):
            status = BillingStatusReader().status()
        self.assertIsNone(status["spent_usd"])
        self.assertEqual(status["limit_usd"], 10.0)
        self.assertFalse(status["limit_verified"])

    def test_usage_estimate_reproduces_cache_write_pricing(self) -> None:
        payload = {
            "data": [
                {
                    "results": [
                        {
                            "model": "gpt-5.6-sol",
                            "service_tier": "default",
                            "batch": False,
                            "input_tokens": 135688,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 135682,
                            "output_tokens": 15203,
                            "num_model_requests": 2,
                        }
                    ]
                }
            ],
            "has_more": False,
        }
        with mock.patch.object(
            refresh_openai_billing, "request_json", return_value=payload
        ):
            estimate, requests = refresh_openai_billing.month_usage_estimate(
                "private-token", 1, 2, ""
            )
        self.assertEqual(estimate, Decimal("0.982494"))
        self.assertEqual(requests, 2)

    def test_updates_an_organization_hard_limit_in_cents(self) -> None:
        response = {
            "object": "organization.spend_limit",
            "threshold_amount": 3000,
            "currency": "USD",
            "interval": "month",
            "enforcement": {"status": "inactive"},
        }
        with mock.patch.object(
            refresh_openai_billing, "request_json", return_value=response
        ) as request:
            limit, enforcement = refresh_openai_billing.update_spend_limit(
                "private-token", "", "30"
            )
        self.assertEqual(limit, Decimal("30"))
        self.assertEqual(enforcement, "inactive")
        request.assert_called_once_with(
            "private-token",
            "/organization/spend_limit",
            method="POST",
            payload={
                "threshold_amount": 3000,
                "currency": "USD",
                "interval": "month",
            },
        )


if __name__ == "__main__":
    unittest.main()
