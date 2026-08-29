#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess


ALLOWLIST_PATH = Path("figure-studio/public/PROPOSAL_ALLOWLIST.json")
SAFE_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_CHANGED_FILES = 40
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
REGULAR_MODES = {"100644", "100755"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class BoundaryError(RuntimeError):
    pass


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def tracked_entries(repository: Path) -> dict[str, tuple[str, str]]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "ls-files", "-s", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BoundaryError("Could not enumerate tracked proposal files") from exc
    entries: dict[str, tuple[str, str]] = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, raw_relative = raw.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii").split()
            relative = raw_relative.decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
            raise BoundaryError("A tracked index entry is invalid") from exc
        if stage != "0":
            raise BoundaryError("A tracked path has unresolved index stages")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise BoundaryError("A tracked proposal path is unsafe")
        entries[path.as_posix()] = (mode, object_id)
    return entries


def read_tracked(repository: Path, relative: str) -> bytes:
    path = repository / relative
    try:
        details = path.lstat()
    except OSError as exc:
        raise BoundaryError(f"Tracked file is missing: {relative}") from exc
    if not stat.S_ISREG(details.st_mode) or stat.S_ISLNK(details.st_mode):
        raise BoundaryError(f"Tracked proposal path is not a regular file: {relative}")
    return path.read_bytes()


def load_allowlist(base: Path) -> tuple[str, dict[str, str]]:
    path = base / ALLOWLIST_PATH
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024:
        raise BoundaryError("The reviewed proposal allowlist is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryError("The reviewed proposal allowlist is invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("status") != "public-ready"
    ):
        raise BoundaryError("The reviewed proposal allowlist is not public-ready")
    repository_root = str(payload.get("repository_root", "")).strip("/")
    if repository_root != "figure-studio/public":
        raise BoundaryError("The reviewed proposal repository root is invalid")
    raw_hashes = payload.get("allowed_sha256")
    if not isinstance(raw_hashes, dict) or not raw_hashes:
        raise BoundaryError("The reviewed proposal allowlist is empty")
    hashes: dict[str, str] = {}
    for raw_path, raw_digest in raw_hashes.items():
        relative = Path(str(raw_path))
        digest = str(raw_digest)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.parts[0] != "figures"
            or relative.suffix.lower() not in SAFE_SUFFIXES
            or not SHA256.fullmatch(digest)
        ):
            raise BoundaryError("The reviewed proposal allowlist contains an invalid entry")
        hashes[relative.as_posix()] = digest
    return repository_root, hashes


def validate_proposal(base: Path, proposal: Path) -> list[str]:
    repository_root, hashes = load_allowlist(base)
    allowed_repository_paths = {
        (Path(repository_root) / relative).as_posix(): digest
        for relative, digest in hashes.items()
    }
    for relative, digest in allowed_repository_paths.items():
        if hash_bytes(read_tracked(base, relative)) != digest:
            raise BoundaryError(f"Base branch hash does not match allowlist: {relative}")

    base_entries = tracked_entries(base)
    proposal_entries = tracked_entries(proposal)
    changed: list[str] = []
    for relative in sorted(set(base_entries) | set(proposal_entries)):
        before_entry = base_entries.get(relative)
        after_entry = proposal_entries.get(relative)
        if (
            before_entry is not None
            and after_entry is not None
            and before_entry[0] in REGULAR_MODES
            and after_entry[0] in REGULAR_MODES
        ):
            differs = (
                before_entry[0] != after_entry[0]
                or read_tracked(base, relative) != read_tracked(proposal, relative)
            )
        else:
            differs = before_entry != after_entry
        if differs:
            changed.append(relative)
    if not changed:
        raise BoundaryError("The proposal contains no tracked changes")
    if len(changed) > MAX_CHANGED_FILES:
        raise BoundaryError("The proposal changes too many files")

    total = 0
    for relative in changed:
        if relative not in allowed_repository_paths:
            raise BoundaryError(f"Proposal changes an unreviewed path: {relative}")
        if relative in proposal_entries:
            content = read_tracked(proposal, relative)
            total += len(content)
            if len(content) > MAX_FILE_BYTES:
                raise BoundaryError(f"Proposal file is too large: {relative}")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BoundaryError(f"Proposal file is not UTF-8: {relative}") from exc
            if "\x00" in text or any(len(line) > 20000 for line in text.splitlines()):
                raise BoundaryError(f"Proposal file contains unsafe text: {relative}")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                raise BoundaryError(f"Proposal file appears to contain a credential: {relative}")
    if total > MAX_TOTAL_BYTES:
        raise BoundaryError("The proposal is too large")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a Figure Studio proposal against the base branch allowlist"
    )
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    args = parser.parse_args()
    try:
        changed = validate_proposal(args.base.resolve(), args.proposal.resolve())
    except BoundaryError as exc:
        parser.error(str(exc))
    print(f"PASS: {len(changed)} changed file(s) match the exact reviewed allowlist")


if __name__ == "__main__":
    main()
