#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
from urllib.parse import urlparse

from studio.server import serve


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Figure Studio MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=Path(os.environ.get("FIGURE_STUDIO_SESSION_ROOT", ROOT / "var" / "sessions")),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(os.environ.get("FIGURE_STUDIO_TEMPLATE_ROOT", ROOT / "template")),
        help="Reviewed local figure template. It may remain outside the public code checkout.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("FIGURE_STUDIO_TOKEN", ""),
        help="Shared access token. Required when binding beyond localhost.",
    )
    parser.add_argument(
        "--generate-token",
        action="store_true",
        help="Generate and print a token for this server process.",
    )
    parser.add_argument(
        "--cloudflare-access",
        action="store_true",
        help="Require identity headers from a Cloudflare Access validated tunnel.",
    )
    parser.add_argument(
        "--public-origin",
        default=os.environ.get("FIGURE_STUDIO_PUBLIC_ORIGIN", ""),
        help="Exact HTTPS origin used for Cloudflare Access and same-origin checks.",
    )
    parser.add_argument(
        "--allowed-emails",
        default=os.environ.get("FIGURE_STUDIO_ALLOWED_EMAILS", ""),
        help="Comma-separated application email allowlist used in Cloudflare Access mode.",
    )
    parser.add_argument(
        "--max-sessions-per-user",
        type=int,
        default=int(os.environ.get("FIGURE_STUDIO_MAX_SESSIONS_PER_USER", "12")),
    )
    parser.add_argument(
        "--session-retention-days",
        type=int,
        default=int(os.environ.get("FIGURE_STUDIO_SESSION_RETENTION_DAYS", "0")),
        help="Delete inactive sessions older than this many days. Zero disables cleanup.",
    )
    args = parser.parse_args()
    token = args.token
    if args.generate_token:
        token = secrets.token_urlsafe(24)
        print(f"Generated access token: {token}")
    if args.host != "127.0.0.1":
        parser.error(
            "Figure Studio must bind exactly to 127.0.0.1. Use an authenticated tunnel "
            "or VPN while keeping the origin on loopback"
        )
    if args.cloudflare_access:
        if args.host != "127.0.0.1":
            parser.error("Cloudflare Access mode must bind exactly to 127.0.0.1")
        origin = urlparse(args.public_origin)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path not in {"", "/"}
            or origin.params
            or origin.query
            or origin.fragment
        ):
            parser.error("Cloudflare Access mode requires --public-origin with an HTTPS URL")
        if token:
            parser.error("Do not combine the legacy shared token with Cloudflare Access mode")
        allowed_emails = {
            email.strip().lower()
            for email in args.allowed_emails.split(",")
            if email.strip()
        }
        if not allowed_emails or any("@" not in email for email in allowed_emails):
            parser.error(
                "Cloudflare Access mode requires an exact comma-separated email allowlist"
            )
    else:
        allowed_emails = set()
    serve(
        ROOT,
        args.sessions,
        args.host,
        args.port,
        token,
        args.cloudflare_access,
        args.public_origin,
        allowed_emails,
        max(12, args.max_sessions_per_user),
        max(0, args.session_retention_days),
        args.template,
    )


if __name__ == "__main__":
    main()
