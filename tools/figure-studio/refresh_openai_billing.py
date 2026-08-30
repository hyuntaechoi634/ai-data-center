#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from studio.github_pr import ProposalError, read_private_token_file


API_ROOT = "https://api.openai.com/v1"
PROJECT_ID = re.compile(r"^proj_[A-Za-z0-9_-]{6,200}$")

# Official per-million-token prices checked 2026-08-29. This table is used
# only as a clearly labeled fallback while the organization Costs endpoint
# has not posted any results. Reported costs always take precedence.
MODEL_PRICING = {
    "gpt-5.6": (Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "gpt-5.6-sol": (Decimal("4.00"), Decimal("0.40"), Decimal("20.00")),
    "gpt-5.6-terra": (Decimal("2.00"), Decimal("0.20"), Decimal("12.00")),
    "gpt-5.6-luna": (Decimal("0.20"), Decimal("0.02"), Decimal("1.20")),
}
CACHE_WRITE_MULTIPLIER = Decimal("1.25")
TOKENS_PER_MILLION = Decimal("1000000")


def request_json(
    token: str,
    path: str,
    method: str = "GET",
    payload: dict | None = None,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        API_ROOT + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ai-data-center-figure-studio-billing",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024)
    except HTTPError as exc:
        message = "request rejected"
        try:
            payload = json.loads(exc.read(8192))
            message = str(payload.get("error", {}).get("message", message))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(f"OpenAI returned HTTP {exc.code}: {message}") from exc
    except (OSError, URLError) as exc:
        raise RuntimeError("OpenAI billing API could not be reached") from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("OpenAI billing API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI billing API returned an invalid response")
    return payload


def money(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError("OpenAI billing API returned an invalid amount") from exc
    if not amount.is_finite() or amount < 0:
        raise RuntimeError("OpenAI billing API returned an invalid amount")
    return amount


def token_count(value) -> int:
    try:
        count = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("OpenAI usage API returned an invalid token count") from exc
    if count < 0:
        raise RuntimeError("OpenAI usage API returned an invalid token count")
    return count


def month_cost_details(
    token: str, start_time: int, end_time: int, project_id: str
) -> tuple[Decimal, int]:
    total = Decimal("0")
    result_count = 0
    page = ""
    for _ in range(100):
        parameters: list[tuple[str, str]] = [
            ("start_time", str(start_time)),
            ("end_time", str(end_time)),
            ("bucket_width", "1d"),
            ("limit", "31"),
        ]
        if project_id:
            parameters.append(("project_ids", project_id))
        if page:
            parameters.append(("page", page))
        payload = request_json(token, "/organization/costs?" + urlencode(parameters))
        for bucket in payload.get("data", []):
            if not isinstance(bucket, dict):
                raise RuntimeError("OpenAI billing API returned an invalid cost bucket")
            for result in bucket.get("results", []):
                if not isinstance(result, dict):
                    raise RuntimeError("OpenAI billing API returned an invalid cost result")
                amount = result.get("amount") or {}
                if str(amount.get("currency", "")).lower() != "usd":
                    raise RuntimeError("OpenAI billing API returned a non-USD cost")
                total += money(amount.get("value"))
                result_count += 1
        if not payload.get("has_more"):
            return total, result_count
        page = str(payload.get("next_page", ""))
        if not page:
            raise RuntimeError("OpenAI billing API omitted its next page cursor")
    raise RuntimeError("OpenAI billing API pagination exceeded the safety limit")


def month_cost(token: str, start_time: int, end_time: int, project_id: str) -> Decimal:
    return month_cost_details(token, start_time, end_time, project_id)[0]


def month_usage_estimate(
    token: str, start_time: int, end_time: int, project_id: str
) -> tuple[Decimal | None, int]:
    """Estimate current spend when the Costs ledger has not posted results.

    The estimate supports only the configured GPT-5.6 models on the default,
    non-batch service tier. Returning None keeps an unknown pricing case from
    being presented as a verified amount.
    """
    total = Decimal("0")
    request_count = 0
    page = ""
    for _ in range(100):
        parameters: list[tuple[str, str]] = [
            ("start_time", str(start_time)),
            ("end_time", str(end_time)),
            ("bucket_width", "1d"),
            ("limit", "31"),
            ("group_by", "model"),
            ("group_by", "service_tier"),
            ("group_by", "batch"),
        ]
        if project_id:
            parameters.append(("project_ids", project_id))
        if page:
            parameters.append(("page", page))
        payload = request_json(
            token,
            "/organization/usage/completions?" + urlencode(parameters),
        )
        for bucket in payload.get("data", []):
            if not isinstance(bucket, dict):
                raise RuntimeError("OpenAI usage API returned an invalid bucket")
            for result in bucket.get("results", []):
                if not isinstance(result, dict):
                    raise RuntimeError("OpenAI usage API returned an invalid result")
                model = str(result.get("model") or "")
                pricing = MODEL_PRICING.get(model)
                service_tier = str(result.get("service_tier") or "default")
                if pricing is None or service_tier != "default" or result.get("batch") is True:
                    return None, request_count

                input_tokens = token_count(result.get("input_tokens"))
                cached_tokens = token_count(result.get("input_cached_tokens"))
                cache_write_tokens = token_count(
                    result.get("input_cache_write_tokens")
                )
                output_tokens = token_count(result.get("output_tokens"))
                ordinary_tokens = input_tokens - cached_tokens - cache_write_tokens
                if ordinary_tokens < 0:
                    raise RuntimeError(
                        "OpenAI usage API returned inconsistent input token counts"
                    )
                input_price, cached_price, output_price = pricing
                total += (
                    Decimal(ordinary_tokens) * input_price
                    + Decimal(cached_tokens) * cached_price
                    + Decimal(cache_write_tokens)
                    * input_price
                    * CACHE_WRITE_MULTIPLIER
                    + Decimal(output_tokens) * output_price
                ) / TOKENS_PER_MILLION
                request_count += token_count(result.get("num_model_requests"))
        if not payload.get("has_more"):
            return total, request_count
        page = str(payload.get("next_page", ""))
        if not page:
            raise RuntimeError("OpenAI usage API omitted its next page cursor")
    raise RuntimeError("OpenAI usage API pagination exceeded the safety limit")


def spend_limit(token: str, project_id: str) -> tuple[Decimal, str]:
    if project_id:
        path = f"/organization/projects/{quote(project_id, safe='')}/spend_limit"
    else:
        path = "/organization/spend_limit"
    payload = request_json(token, path)
    if str(payload.get("currency", "")).upper() != "USD":
        raise RuntimeError("OpenAI spend limit is not denominated in USD")
    if payload.get("interval") != "month":
        raise RuntimeError("OpenAI spend limit is not monthly")
    cents = money(payload.get("threshold_amount"))
    enforcement = str((payload.get("enforcement") or {}).get("status", "unknown"))
    return cents / Decimal("100"), enforcement


def update_spend_limit(
    token: str, project_id: str, limit_usd: str
) -> tuple[Decimal, str]:
    amount = money(limit_usd)
    cents = amount * Decimal("100")
    if amount <= 0 or cents != cents.to_integral_value():
        raise RuntimeError("The OpenAI hard limit must be a positive whole-cent amount")
    path = (
        f"/organization/projects/{quote(project_id, safe='')}/spend_limit"
        if project_id
        else "/organization/spend_limit"
    )
    payload = request_json(
        token,
        path,
        method="POST",
        payload={
            "threshold_amount": int(cents),
            "currency": "USD",
            "interval": "month",
        },
    )
    if str(payload.get("currency", "")).upper() != "USD":
        raise RuntimeError("OpenAI returned an invalid spend-limit currency")
    if payload.get("interval") != "month":
        raise RuntimeError("OpenAI returned an invalid spend-limit interval")
    returned_cents = money(payload.get("threshold_amount"))
    if returned_cents != cents:
        raise RuntimeError("OpenAI did not confirm the requested hard limit")
    enforcement = str((payload.get("enforcement") or {}).get("status", "unknown"))
    return returned_cents / Decimal("100"), enforcement


def list_projects(token: str) -> list[dict]:
    projects: list[dict] = []
    after = ""
    for _ in range(100):
        parameters = [("limit", "100")]
        if after:
            parameters.append(("after", after))
        payload = request_json(token, "/organization/projects?" + urlencode(parameters))
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError("OpenAI Admin API returned an invalid project list")
        for project in data:
            if not isinstance(project, dict):
                raise RuntimeError("OpenAI Admin API returned an invalid project record")
            projects.append(project)
        if not payload.get("has_more"):
            return projects
        after = str(payload.get("last_id", ""))
        if not after:
            raise RuntimeError("OpenAI Admin API omitted its project cursor")
    raise RuntimeError("OpenAI project pagination exceeded the safety limit")


def write_cache(path: Path, payload: dict) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the sanitized OpenAI API cost cache for Figure Studio"
    )
    parser.add_argument(
        "--admin-key-file",
        type=Path,
        default=Path(
            os.environ.get(
                "FIGURE_STUDIO_OPENAI_ADMIN_KEY_FILE",
                "/home/hyuntae-choi/.config/figure-studio/openai-admin.key",
            )
        ),
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(
            os.environ.get(
                "FIGURE_STUDIO_OPENAI_BILLING_CACHE",
                "/home/hyuntae-choi/.cache/figure-studio/openai-billing.json",
            )
        ),
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("FIGURE_STUDIO_OPENAI_PROJECT_ID", "").strip(),
    )
    parser.add_argument(
        "--expected-limit-usd",
        default=os.environ.get("FIGURE_STUDIO_OPENAI_DISPLAY_LIMIT_USD", "").strip(),
        help="Fail if the verified hard limit differs from this expected value",
    )
    parser.add_argument(
        "--set-limit-usd",
        default="",
        help="Create or replace the monthly hard limit before refreshing the cache",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List project IDs and names without reading cost data",
    )
    args = parser.parse_args()
    if args.project_id and not PROJECT_ID.fullmatch(args.project_id):
        parser.error("--project-id is invalid")

    try:
        token = read_private_token_file(
            args.admin_key_file.expanduser().resolve(), "OpenAI Admin credentials"
        )
        if args.list_projects and args.set_limit_usd:
            raise RuntimeError("--list-projects cannot be combined with --set-limit-usd")
        if args.list_projects:
            for project in list_projects(token):
                print(
                    "\t".join(
                        [
                            str(project.get("id", "")),
                            str(project.get("name", "")),
                            str(project.get("status", "")),
                        ]
                    )
                )
            return
        if args.set_limit_usd:
            updated_limit, _ = update_spend_limit(
                token, args.project_id, args.set_limit_usd
            )
            if not args.expected_limit_usd:
                args.expected_limit_usd = str(updated_limit)
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        reported_cost, reported_results = month_cost_details(
            token, int(start.timestamp()), int(now.timestamp()), args.project_id
        )
        estimated_cost, usage_requests = month_usage_estimate(
            token, int(start.timestamp()), int(now.timestamp()), args.project_id
        )
        cost = reported_cost
        cost_source = "organization-costs"
        if (
            reported_results == 0
            and estimated_cost is not None
            and estimated_cost > 0
        ):
            cost = estimated_cost
            cost_source = "usage-estimate"
        limit, enforcement = spend_limit(token, args.project_id)
        if args.expected_limit_usd:
            expected = money(args.expected_limit_usd)
            if limit != expected:
                raise RuntimeError(
                    f"Verified hard limit is ${limit:.2f}, not expected ${expected:.2f}"
                )
    except (ProposalError, RuntimeError) as exc:
        parser.error(str(exc))

    payload = {
        "schema_version": 1,
        "source": "openai-admin-api",
        "scope": "project" if args.project_id else "organization",
        "period_start": start.isoformat(),
        "period_end": now.isoformat(),
        "spent_usd": str(cost.quantize(Decimal("0.000001"))),
        "reported_spent_usd": str(reported_cost.quantize(Decimal("0.000001"))),
        "estimated_spent_usd": (
            str(estimated_cost.quantize(Decimal("0.000001")))
            if estimated_cost is not None
            else None
        ),
        "cost_source": cost_source,
        "usage_request_count": usage_requests,
        "limit_usd": str(limit.quantize(Decimal("0.01"))),
        "limit_verified": True,
        "currency": "USD",
        "enforcement": enforcement,
        "updated_at": now.isoformat(),
    }
    write_cache(args.cache, payload)
    print(
        f"Updated {args.cache.expanduser()} with ${cost:.6f} spent of "
        f"verified ${limit:.2f} monthly hard limit ({cost_source})"
    )


if __name__ == "__main__":
    main()
