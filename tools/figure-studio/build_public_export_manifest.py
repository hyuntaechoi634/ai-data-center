#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


FIGURES = tuple(f"figure-{number:02d}" for number in range(1, 7))
SHARED_HELPERS = ("_registry.py", "gcam_style.py", "layout_runtime.py")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict, mode: int) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the reviewed local contract for public Figure Studio PRs"
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument(
        "--repository", default="hyuntaechoi634/ai-data-center"
    )
    parser.add_argument(
        "--base-branch", default="cht/proj/figure-studio"
    )
    parser.add_argument("--base-commit", required=True)
    parser.add_argument(
        "--repository-root", default="figure-studio/public"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--ci-allowlist-output",
        type=Path,
        help="Also write the public exact-path CI allowlist for the integration branch",
    )
    parser.add_argument(
        "--approve-publication",
        action="store_true",
        help="Confirm that this template has passed the separate publication review",
    )
    args = parser.parse_args()

    if not args.approve_publication:
        parser.error("--approve-publication is required after the external review")
    if not COMMIT.fullmatch(args.base_commit):
        parser.error("--base-commit must be a full 40-character Git commit")

    template = args.template.resolve()
    if not (template / "project.json").is_file():
        parser.error("the template does not contain project.json")

    roots = [
        Path("figures") / figure_id
        for figure_id in FIGURES
        if (template / "figures" / figure_id).is_dir()
    ]
    helpers = Path("figures/helpers")
    if (template / helpers).is_dir():
        roots.append(helpers)
    if len([root for root in roots if root.name.startswith("figure-")]) != 6:
        parser.error("the reviewed template must contain Figure 01 through Figure 06")

    reviewed_paths = []
    for figure_id in FIGURES:
        root = Path("figures") / figure_id
        reviewed_paths.extend(
            (
                root / "CAPTION.md",
                root / "layout-overrides.json",
                root / "make_figure.py",
                root / f"make_figure_{figure_id[-2:]}.py",
            )
        )
    reviewed_paths.extend(Path("figures/helpers") / name for name in SHARED_HELPERS)

    hashes: dict[str, str] = {}
    for relative in reviewed_paths:
        path = template / relative
        if path.is_symlink():
            parser.error(f"symbolic link found at reviewed path: {relative}")
        if not path.is_file():
            parser.error(f"reviewed public file is missing: {relative}")
        hashes[relative.as_posix()] = hash_file(path)
    if not hashes:
        parser.error("the reviewed template contains no public code files")

    payload = {
        "schema_version": 2,
        "status": "public-ready",
        "repository": args.repository,
        "base_branch": args.base_branch,
        "base_commit": args.base_commit,
        "repository_root": args.repository_root.strip("/"),
        "allowed_roots": [root.as_posix() for root in roots],
        "allowed_files": sorted(hashes),
        "baseline_sha256": hashes,
    }
    output = (args.output or template / "PUBLIC_EXPORT.json").resolve()
    write_json(output, payload, 0o600)
    if args.ci_allowlist_output:
        ci_payload = {
            "schema_version": 1,
            "status": "public-ready",
            "repository_root": args.repository_root.strip("/"),
            "allowed_sha256": hashes,
        }
        write_json(args.ci_allowlist_output, ci_payload, 0o644)
    print(f"Wrote {output} with {len(hashes)} reviewed text-file hashes")


if __name__ == "__main__":
    main()
