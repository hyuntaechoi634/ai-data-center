#!/usr/bin/env python3
"""Verify public sources and, optionally, a rebuilt XML snapshot."""

import argparse
import csv
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
MAP_PATH = ROOT / "filename-map.csv"
SUPPLEMENTAL_MAP_PATH = ROOT / "supplemental-file-map.csv"
SOURCE_MANIFEST = (
    ROOT / "provenance" / "final-calibrated-source-manifest.sha256"
)
SUPPLEMENTAL_MANIFEST = ROOT / "provenance" / "supplemental-files.sha256"
GENERATION_MANIFEST = ROOT / "provenance" / "generation-inputs.sha256"
XML_MANIFEST = ROOT / "provenance" / "final-calibrated-xml-manifest.sha256"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path):
    entries = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            expected, name = line.split(None, 1)
        except ValueError as error:
            raise SystemExit(f"invalid manifest line {path}:{line_number}") from error
        entries[name.strip()] = expected
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xml-snapshot",
        type=Path,
        help="also verify a 226-file final calibrated XML directory",
    )
    args = parser.parse_args()
    with MAP_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    with SUPPLEMENTAL_MAP_PATH.open(newline="", encoding="utf-8") as stream:
        supplemental_rows = list(csv.DictReader(stream))
    expected = read_manifest(SOURCE_MANIFEST)
    supplemental_expected = read_manifest(SUPPLEMENTAL_MANIFEST)
    errors = []

    if len(rows) != 45:
        errors.append(f"filename map has {len(rows)} rows, expected 45")
    if len(expected) != 45:
        errors.append(f"source manifest has {len(expected)} rows, expected 45")
    if len(supplemental_rows) != 1:
        errors.append(
            f"supplemental file map has {len(supplemental_rows)} rows, expected 1"
        )
    if len(supplemental_expected) != 1:
        errors.append(
            "supplemental manifest has "
            f"{len(supplemental_expected)} rows, expected 1"
        )

    mapped_sources = {row["source_path"] for row in rows}
    if mapped_sources != set(expected):
        for name in sorted(set(expected) - mapped_sources):
            errors.append(f"source manifest entry is not mapped: {name}")
        for name in sorted(mapped_sources - set(expected)):
            errors.append(f"mapped source is absent from manifest: {name}")

    for row in rows:
        path = ROOT / row["public_path"]
        if not path.is_file():
            errors.append(f"missing public file: {row['public_path']}")
            continue
        source_name = row["source_path"]
        if source_name in expected and digest(path) != expected[source_name]:
            errors.append(f"hash mismatch: {row['public_path']}")

    supplemental_sources = {
        row["source_path"] for row in supplemental_rows
    }
    if supplemental_sources != set(supplemental_expected):
        errors.append("supplemental map and manifest contain different sources")
    for row in supplemental_rows:
        path = ROOT / row["public_path"]
        source_name = row["source_path"]
        if not path.is_file():
            errors.append(f"missing supplemental file: {row['public_path']}")
        elif (
            source_name in supplemental_expected
            and digest(path) != supplemental_expected[source_name]
        ):
            errors.append(f"supplemental hash mismatch: {row['public_path']}")

    generation_expected = read_manifest(GENERATION_MANIFEST)
    for relative, expected_hash in generation_expected.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing generation input: {relative}")
        elif digest(path) != expected_hash:
            errors.append(f"generation input hash mismatch: {relative}")

    if args.xml_snapshot:
        snapshot = args.xml_snapshot.resolve()
        xml_expected = read_manifest(XML_MANIFEST)
        actual_names = {
            path.name for path in snapshot.glob("*.xml") if path.is_file()
        }
        if len(xml_expected) != 226:
            errors.append(
                f"XML manifest has {len(xml_expected)} rows, expected 226"
            )
        if actual_names != set(xml_expected):
            for name in sorted(set(xml_expected) - actual_names):
                errors.append(f"XML snapshot is missing: {name}")
            for name in sorted(actual_names - set(xml_expected)):
                errors.append(f"XML snapshot has an unexpected file: {name}")
        for name, expected_hash in xml_expected.items():
            path = snapshot / name
            if path.is_file() and digest(path) != expected_hash:
                errors.append(f"XML hash mismatch: {name}")

    if errors:
        print("verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    message = (
        "PASS: 45 public files match the final calibrated source manifest, the "
        "supplemental scenario overlay matches its manifest, and "
        f"{len(generation_expected)} generation inputs match their manifest"
    )
    if args.xml_snapshot:
        message += "; 226 XML files match the final calibrated manifest"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
