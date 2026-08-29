#!/usr/bin/env python3
"""Byte-reconstruct the frozen calibrated brp7d8 regional 2025 demand seed.

The calibrated rows come from the preserved brp7d8 S7 foldback evidence. The
ordering, eight-significant-digit formatting, and CRLF body reproduce the
audited brp7d8-cal source hash without reading a mutable build tree.
"""

import argparse
import csv
import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
EVIDENCE = HERE / "inputs" / "frozen-calibration-foldback-evidence.csv"
OUTPUT = (
    PACKAGE_ROOT / "data" / "locked" / "energy"
    / "regional-demand-calibration-2025.csv"
)
EXPECTED_SHA256 = (
    "ff2e5f82e4bb50f3eece769973e27eba170f4b15a0b2eabf583299fad319705c"
)
HEADER = (
    "# File: aeei_calib_2025_R.csv\n"
    "# Title: REGION-specific aeei at year 2025 (2025 soft-calibration lever; overrides the\n"
    "#   region-common aeei_chi_compute value at 2025 in L2282/L2286 and in the scenario overlays)\n"
    "# Status: converged service-specific soft-calibration result.\n"
    "# Units: /yr (autonomous demand growth; negative = growth)\n"
    "# Column types: ccn\n"
    "# ----------\n"
)


def rebuilt_bytes():
    with EVIDENCE.open(newline="", encoding="utf-8") as stream:
        rows = sorted(
            csv.DictReader(stream),
            key=lambda row: (row["service"], row["region"]),
        )
    body = "service,region,aeei\r\n" + "".join(
        f'{row["service"]},{row["region"]},'
        f'{float(row["aeei_2025"]):.8g}\r\n'
        for row in rows
    )
    result = (HEADER + body).encode("utf-8")
    actual = hashlib.sha256(result).hexdigest()
    if actual != EXPECTED_SHA256:
        raise SystemExit(
            f"reconstruction hash mismatch: expected {EXPECTED_SHA256}, got {actual}"
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = rebuilt_bytes()
    current = OUTPUT.read_bytes() if OUTPUT.is_file() else b""

    if current == expected:
        print(f"PASS: frozen calibration seed {EXPECTED_SHA256}")
        return 0
    if not args.write:
        print("frozen calibration seed differs; run with --write", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print(f"wrote frozen calibration seed {EXPECTED_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
