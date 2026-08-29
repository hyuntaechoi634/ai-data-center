#!/usr/bin/env python3
"""Reject restricted calibration files at the Git publication boundary."""

from __future__ import annotations

import argparse
import csv
import fnmatch
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[3]
DENYLIST = HERE / "restricted-publication-paths.txt"
LINEAGE = HERE / "restricted-publication-lineage.csv"
FILENAME_MAP = HERE.parent / "filename-map.csv"


def load_patterns() -> list[str]:
    patterns = []
    for raw in DENYLIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    if not patterns:
        raise RuntimeError(f"empty publication denylist: {DENYLIST}")
    if len(patterns) != len(set(patterns)):
        raise RuntimeError(f"duplicate publication denylist pattern: {DENYLIST}")
    return patterns


def load_lineage() -> list[dict[str, str]]:
    with LINEAGE.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"restricted_path", "upstream", "stage", "reason"}
        if not required.issubset(reader.fieldnames or []):
            raise RuntimeError(f"invalid publication lineage columns: {LINEAGE}")
        rows = list(reader)
    paths = [row["restricted_path"] for row in rows]
    if not paths:
        raise RuntimeError(f"empty publication lineage: {LINEAGE}")
    if len(paths) != len(set(paths)):
        raise RuntimeError(f"duplicate publication lineage path: {LINEAGE}")
    return rows


def validate_configuration(
    patterns: list[str], lineage: list[dict[str, str]]
) -> tuple[list[str], int]:
    errors: list[str] = []
    pattern_set = set(patterns)
    lineage_paths = {row["restricted_path"] for row in lineage}
    for path in sorted(lineage_paths - pattern_set):
        errors.append(f"lineage path missing from denylist: {path}")
    for path in sorted(pattern_set - lineage_paths):
        errors.append(f"denylist pattern missing from lineage: {path}")

    with FILENAME_MAP.open(newline="", encoding="utf-8") as stream:
        filename_rows = list(csv.DictReader(stream))
    mapping = {
        f"input/gcamdata/ai-data-center/{row['public_path']}":
        f"input/gcamdata/{row['deployed_path']}"
        for row in filename_rows
    }
    mapped_closure = 0
    for row in lineage:
        if row["stage"] not in {"locked-authoring", "generated-authoring"}:
            continue
        public_path = row["restricted_path"]
        deployed_path = mapping.get(public_path)
        if deployed_path is None:
            errors.append(
                f"restricted authoring path absent from filename map: "
                f"{public_path}"
            )
            continue
        mapped_closure += 1
        if deployed_path not in lineage_paths:
            errors.append(
                f"restricted deployment missing from lineage: "
                f"{public_path} -> {deployed_path}"
            )
    return errors, mapped_closure


def git_paths(root: Path, *arguments: str) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", *arguments],
        check=True,
        stdout=subprocess.PIPE,
    )
    return {
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    }


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    if not (root / ".git").exists():
        raise SystemExit(f"not a Git working tree: {root}")

    patterns = load_patterns()
    lineage = load_lineage()
    configuration_errors, mapped_closure = validate_configuration(
        patterns, lineage
    )
    if configuration_errors:
        print(
            "FAIL: publication boundary configuration is incomplete:",
            file=sys.stderr,
        )
        for error in configuration_errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    tracked = git_paths(root, "--cached")
    unignored = git_paths(root, "--others", "--exclude-standard")
    tracked_violations = sorted(path for path in tracked if matches(path, patterns))
    unignored_violations = sorted(
        path for path in unignored if matches(path, patterns)
    )

    if tracked_violations or unignored_violations:
        if tracked_violations:
            print("FAIL: restricted paths are tracked or staged:", file=sys.stderr)
            for path in tracked_violations:
                print(f"  {path}", file=sys.stderr)
        if unignored_violations:
            print("FAIL: restricted paths are untracked but not ignored:", file=sys.stderr)
            for path in unignored_violations:
                print(f"  {path}", file=sys.stderr)
        print(
            "Keep the audited local files private or replace them with a "
            "reviewed open-data profile.",
            file=sys.stderr,
        )
        return 1

    print(
        "PASS: restricted calibration paths are neither tracked nor "
        "present as unignored files"
    )
    print(
        f"checked {len(patterns)} denylist patterns, "
        f"{len(lineage)} lineage rows, and "
        f"{mapped_closure} filename-map deployments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
