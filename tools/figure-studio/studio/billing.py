from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import stat


MAX_CACHE_BYTES = 64 * 1024


def _money(value) -> float | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
        return None
    return float(amount.quantize(Decimal("0.000001")))


def _configured_limit() -> float | None:
    raw = os.environ.get("FIGURE_STUDIO_OPENAI_DISPLAY_LIMIT_USD", "").strip()
    return _money(raw) if raw else None


class BillingStatusReader:
    def __init__(self) -> None:
        raw_cache = os.environ.get("FIGURE_STUDIO_OPENAI_BILLING_CACHE", "").strip()
        candidate = Path(raw_cache).expanduser() if raw_cache else None
        self.cache_file = candidate if candidate and candidate.is_absolute() else None
        try:
            requested_stale = int(
                os.environ.get("FIGURE_STUDIO_OPENAI_BILLING_STALE_SECONDS", "900")
            )
        except ValueError:
            requested_stale = 900
        self.stale_seconds = max(60, min(requested_stale, 86400))

    @staticmethod
    def _base(message: str) -> dict:
        fallback = _configured_limit()
        return {
            "available": False,
            "spent_usd": None,
            "limit_usd": fallback,
            "limit_verified": False,
            "currency": "USD",
            "scope": "organization",
            "enforcement": "unknown",
            "updated_at": None,
            "stale": True,
            "message": message,
        }

    def status(self) -> dict:
        if self.cache_file is None:
            return self._base("Live API billing is not connected")
        path = self.cache_file
        try:
            details = path.lstat()
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_ISLNK(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_mode & 0o077
                or details.st_size < 2
                or details.st_size > MAX_CACHE_BYTES
            ):
                return self._base("The API billing cache is not configured safely")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return self._base("Live API billing is not available")
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return self._base("The API billing cache is invalid")

        spent = _money(payload.get("spent_usd"))
        limit = _money(payload.get("limit_usd"))
        updated_at = str(payload.get("updated_at", ""))
        currency = str(payload.get("currency", "")).upper()
        scope = str(payload.get("scope", ""))
        if spent is None or currency != "USD" or scope not in {"organization", "project"}:
            return self._base("The API billing cache is invalid")
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                raise ValueError
            age = (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            return self._base("The API billing cache timestamp is invalid")

        if limit is None:
            limit = _configured_limit()
            verified = False
        else:
            verified = bool(payload.get("limit_verified"))
        stale = age < -300 or age > self.stale_seconds
        message = "Current OpenAI API month-to-date cost"
        if stale:
            message = "OpenAI API billing cache is stale"
        elif limit is not None and not verified:
            message = "Current API cost with an unverified local display limit"
        return {
            "available": not stale,
            "spent_usd": spent,
            "limit_usd": limit,
            "limit_verified": verified,
            "currency": "USD",
            "scope": scope,
            "enforcement": str(payload.get("enforcement", "unknown"))[:32],
            "updated_at": updated_at,
            "stale": stale,
            "message": message,
        }
