#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path

from refresh_openai_billing import month_cost, money, request_json, spend_limit
from studio.github_pr import ProposalError, read_private_token_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set and verify the OpenAI organization monthly hard spend limit"
    )
    parser.add_argument("--limit-usd", required=True)
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
        "--confirm-organization-hard-limit",
        action="store_true",
        help="Confirm that this hard limit applies to every project in the organization",
    )
    parser.add_argument(
        "--allow-current-spend-at-or-over-limit",
        action="store_true",
        help="Allow a limit that may immediately stop organization API requests",
    )
    args = parser.parse_args()
    if not args.confirm_organization_hard_limit:
        parser.error("--confirm-organization-hard-limit is required")
    try:
        limit = money(args.limit_usd)
    except RuntimeError as exc:
        parser.error(str(exc))
    cents = limit * Decimal("100")
    if cents != cents.to_integral_value() or cents < 1:
        parser.error("--limit-usd must be a positive amount with at most two decimals")

    try:
        token = read_private_token_file(
            args.admin_key_file.expanduser().resolve(), "OpenAI Admin credentials"
        )
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent = month_cost(token, int(start.timestamp()), int(now.timestamp()), "")
        if spent >= limit and not args.allow_current_spend_at_or_over_limit:
            raise RuntimeError(
                f"Current organization spend is ${spent:.6f}, which is already at or over "
                f"the requested ${limit:.2f} hard limit"
            )
        response = request_json(
            token,
            "/organization/spend_limit",
            method="POST",
            payload={
                "threshold_amount": int(cents),
                "currency": "USD",
                "interval": "month",
            },
        )
        if (
            response.get("threshold_amount") != int(cents)
            or response.get("currency") != "USD"
            or response.get("interval") != "month"
        ):
            raise RuntimeError("OpenAI did not return the requested organization hard limit")
        verified, enforcement = spend_limit(token, "")
        if verified != limit:
            raise RuntimeError("OpenAI organization hard limit verification failed")
    except (ProposalError, RuntimeError) as exc:
        parser.error(str(exc))
    print(
        f"Verified organization month-to-date spend ${spent:.6f}, monthly hard "
        f"limit ${verified:.2f}, enforcement status {enforcement}"
    )


if __name__ == "__main__":
    main()
