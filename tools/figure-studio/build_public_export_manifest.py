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
SAFE_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt"}
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


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

    hashes: dict[str, str] = {}
    for root in roots:
        for path in sorted((template / root).rglob("*")):
            if path.is_symlink():
                parser.error(f"symbolic link found under {root}: {path}")
            if not path.is_file() or path.suffix.lower() not in SAFE_SUFFIXES:
                continue
            relative = path.relative_to(template).as_posix()
            hashes[relative] = hash_file(path)
    if not hashes:
        parser.error("the reviewed template contains no public code files")

    payload = {
        "schema_version": 1,
        "status": "public-ready",
        "repository": args.repository,
        "base_branch": args.base_branch,
        "base_commit": args.base_commit,
        "repository_root": args.repository_root.strip("/"),
        "allowed_roots": [root.as_posix() for root in roots],
        "baseline_sha256": hashes,
    }
    output = (args.output or template / "PUBLIC_EXPORT.json").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Wrote {output} with {len(hashes)} reviewed text-file hashes")


if __name__ == "__main__":
    main()
