#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path

from studio.github_pr import ProposalError
from studio.proposal_queue import ProposalQueue


ROOT = Path(__file__).resolve().parent


def show_diff(template: Path, files) -> None:
    for item in files:
        before_path = template / item.workspace_path
        before = before_path.read_text(encoding="utf-8").splitlines(keepends=True)
        after = (
            []
            if item.content is None
            else item.content.decode("utf-8").splitlines(keepends=True)
        )
        diff = difflib.unified_diff(
            before,
            after,
            fromfile=f"baseline/{item.workspace_path}",
            tofile=f"proposal/{item.workspace_path}",
        )
        print("".join(diff), end="")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review a private Figure Studio proposal and optionally publish a Draft PR"
    )
    parser.add_argument("proposal_id")
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path(
            os.environ.get(
                "FIGURE_STUDIO_PROPOSAL_QUEUE_ROOT",
                "/home/hyuntae-choi/.local/share/figure-studio/proposals",
            )
        ),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(os.environ.get("FIGURE_STUDIO_TEMPLATE_ROOT", ROOT / "template")),
    )
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--approve-reviewed",
        action="store_true",
        help="Confirm that the displayed diff contains no restricted or private material",
    )
    parser.add_argument(
        "--github-token-file",
        type=Path,
        default=(
            Path(os.environ["FIGURE_STUDIO_GITHUB_TOKEN_FILE"])
            if os.environ.get("FIGURE_STUDIO_GITHUB_TOKEN_FILE")
            else None
        ),
    )
    args = parser.parse_args()

    queue_path = args.queue.expanduser().resolve()
    template = args.template.expanduser().resolve()
    os.environ["FIGURE_STUDIO_PROPOSAL_QUEUE_ROOT"] = str(queue_path)
    queue = ProposalQueue(template, require_cloudflare_access=True)
    try:
        payload, _, files = queue.load_pending(args.proposal_id)
        print(
            f"Proposal {payload['proposal_id']} from {payload['submitter']} "
            f"changes {len(files)} reviewed file(s)."
        )
        show_diff(template, files)
        if not args.publish:
            print("Review only. No GitHub branch or pull request was created.")
            return
        if not args.approve_reviewed:
            parser.error("--approve-reviewed is required before publishing")
        if args.github_token_file is None:
            parser.error("--github-token-file is required before publishing")
        result = queue.publish_pending(
            args.proposal_id,
            args.github_token_file.expanduser().resolve(),
        )
    except ProposalError as exc:
        parser.error(str(exc))
    print(f"Created Draft PR #{result.number}: {result.url}")


if __name__ == "__main__":
    main()
