from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class BillingStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = Path(self.temporary.name) / "billing.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(self, updated_at: datetime | None = None) -> None:
        payload = {
            "schema_version": 1,
            "scope": "organization",
            "spent_usd": "1.250000",
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


if __name__ == "__main__":
    unittest.main()
