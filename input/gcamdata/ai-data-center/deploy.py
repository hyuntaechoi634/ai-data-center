#!/usr/bin/env python3
"""Deploy the descriptive authoring tree into GCAM's conventional paths."""

import argparse
import csv
import hashlib
from pathlib import Path
import re
import shutil
import sys


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_GCAMDATA_ROOT = PACKAGE_ROOT.parent
STOCK_BUILDING_CHUNK_SHA256 = (
    "23adb07d000d87eb5f61ef10a78a27c0c94b833c6c15d060df9c900cc1345c7f"
)
PATCHED_BUILDING_CHUNK_SHA256 = (
    "a1f269174d7e50fa99891db45f030082eb40b220e0f7746b0681a87244db6f7e"
)
BUILDING_INPUT_SWAPS = (
    ("L144.base_service_EJ_serv_fuel", "L1280.base_service_EJ_serv_fuel"),
    ("L144.base_service_EJ_serv", "L1280.base_service_EJ_serv"),
    ("L144.in_EJ_R_bld_serv_F_Yh", "L1280.in_EJ_R_bld_serv_F_Yh"),
    (
        "L1441.base_service_EJ_serv_fuel_tech_USA",
        "L1280.base_service_EJ_serv_fuel_tech_USA",
    ),
    (
        "L1441.in_EJ_R_bld_serv_F_tech_Yh_USA",
        "L1280.in_EJ_R_bld_serv_F_tech_Yh_USA",
    ),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_map():
    with (PACKAGE_ROOT / "filename-map.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        primary = list(csv.DictReader(stream))
    with (PACKAGE_ROOT / "supplemental-file-map.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        supplemental = list(csv.DictReader(stream))
    if len(primary) != 45:
        raise SystemExit(f"expected 45 source-manifest files, found {len(primary)}")
    if len(supplemental) != 1:
        raise SystemExit(
            f"expected one supplemental scenario overlay, found {len(supplemental)}"
        )
    return primary + supplemental


def patch_building_chunk(gcamdata_root):
    path = gcamdata_root / "R" / "zenergy_L244.building_det.R"
    current = digest(path)
    if current == PATCHED_BUILDING_CHUNK_SHA256:
        return False
    if current != STOCK_BUILDING_CHUNK_SHA256:
        raise SystemExit(
            "refusing to patch an unknown zenergy_L244.building_det.R: "
            f"sha256={current}"
        )

    text = path.read_text(encoding="utf-8")
    for old, new in BUILDING_INPUT_SWAPS:
        text = re.sub(
            rf"(?<![A-Za-z0-9_.]){re.escape(old)}(?![A-Za-z0-9_])",
            new,
            text,
        )
    path.write_text(text, encoding="utf-8")
    result = digest(path)
    if result != PATCHED_BUILDING_CHUNK_SHA256:
        raise SystemExit(
            "building integration patch produced an unexpected hash: "
            f"{result}"
        )
    return True


def verify_deployment(gcamdata_root, rows):
    mismatches = []
    for row in rows:
        source = PACKAGE_ROOT / row["public_path"]
        target = gcamdata_root / row["deployed_path"]
        if not target.is_file() or digest(source) != digest(target):
            mismatches.append(row["deployed_path"])

    building = gcamdata_root / "R" / "zenergy_L244.building_det.R"
    if not building.is_file() or digest(building) != PATCHED_BUILDING_CHUNK_SHA256:
        mismatches.append("R/zenergy_L244.building_det.R [building integration]")

    industry = gcamdata_root / "R" / "zenergy_L232.other_industry.R"
    if not industry.is_file() or "L1280" in industry.read_text(
        encoding="utf-8", errors="replace"
    ):
        mismatches.append("R/zenergy_L232.other_industry.R [must remain stock]")
    return mismatches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gcamdata-root",
        type=Path,
        default=DEFAULT_GCAMDATA_ROOT,
        help="GCAM gcamdata package root",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="copy mapped files and apply the building integration patch",
    )
    args = parser.parse_args()
    root = args.gcamdata_root.resolve()
    rows = read_map()

    if args.apply:
        for row in rows:
            source = PACKAGE_ROOT / row["public_path"]
            target = root / row["deployed_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        changed = patch_building_chunk(root)
        print(
            f"deployed {len(rows)} files; building integration "
            f"{'patched' if changed else 'already patched'}"
        )

    mismatches = verify_deployment(root, rows)
    if mismatches:
        print("deployment verification failed:", file=sys.stderr)
        for path in mismatches:
            print(f"  {path}", file=sys.stderr)
        if not args.apply:
            print("run deploy.py --apply to deploy the overlay", file=sys.stderr)
        return 1

    print(
        "PASS: 45 source files, one scenario overlay, and the building "
        "integration are deployed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
