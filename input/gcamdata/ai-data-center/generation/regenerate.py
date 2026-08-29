#!/usr/bin/env python3
"""Rebuild the derived AI data-center CSV inputs.

The public authoring tree uses descriptive filenames. GCAM's R chunks still
consume conventional gcamdata identifiers, so generation runs in a temporary
deployed-name tree and maps the results back through ``filename-map.csv``.
"""

import argparse
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
GCAMDATA_ROOT = PACKAGE_ROOT.parent
MAP_PATH = PACKAGE_ROOT / "filename-map.csv"


def read_map():
    with MAP_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 45:
        raise SystemExit(f"expected 45 mapped overlay files, found {len(rows)}")
    public_paths = [row["public_path"] for row in rows]
    deployed_paths = [row["deployed_path"] for row in rows]
    if len(public_paths) != len(set(public_paths)):
        raise SystemExit("duplicate public_path in filename-map.csv")
    if len(deployed_paths) != len(set(deployed_paths)):
        raise SystemExit("duplicate deployed_path in filename-map.csv")
    return rows


def run_generator(script, env):
    subprocess.run([sys.executable, str(script)], check=True, env=env)


def same_bytes(left, right):
    return left.read_bytes() == right.read_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace checked-in derived files after a successful rebuild",
    )
    args = parser.parse_args()
    rows = read_map()

    with tempfile.TemporaryDirectory(prefix="ai-data-center-gcamdata-") as tmp:
        scratch = Path(tmp)
        for row in rows:
            if not row["deployed_path"].startswith("inst/extdata/"):
                continue
            source = PACKAGE_ROOT / row["public_path"]
            target = scratch / row["deployed_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        energy_dir = scratch / "inst" / "extdata" / "energy"
        water_dir = scratch / "inst" / "extdata" / "water"
        auxiliary_dir = scratch / "generation-output"
        auxiliary_dir.mkdir(parents=True, exist_ok=True)

        region_names = Path(os.environ.get(
            "AI_GCAM_REGION_NAMES",
            GCAMDATA_ROOT / "inst" / "extdata" / "common"
            / "GCAM_region_names.csv",
        ))
        if not region_names.is_file():
            raise SystemExit(f"missing GCAM region table: {region_names}")

        env = os.environ.copy()
        env.update({
            "AI_GCAMDATA_ENERGY_DIR": str(energy_dir),
            "AI_GCAMDATA_WATER_DIR": str(water_dir),
            "AI_GCAM_REGION_NAMES": str(region_names),
            "AI_GENERATION_OUTPUT_DIR": str(auxiliary_dir),
        })
        run_generator(HERE / "generate_compute_inputs.py", env)
        run_generator(HERE / "generate_demand_scenarios.py", env)

        generated = [
            row for row in rows
            if row["kind"] in {"generated-main", "generated-demand"}
        ]
        mismatches = []
        for row in generated:
            current = PACKAGE_ROOT / row["public_path"]
            rebuilt = scratch / row["deployed_path"]
            if not same_bytes(current, rebuilt):
                mismatches.append((current, rebuilt))

        reference = HERE / "reference" / "demand-axis-parameters.csv"
        rebuilt_reference = auxiliary_dir / "demand-axis-parameters.csv"
        if not same_bytes(reference, rebuilt_reference):
            mismatches.append((reference, rebuilt_reference))

        if args.write:
            for current, rebuilt in mismatches:
                current.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(rebuilt, current)
            print(
                f"regenerated {len(generated)} deployed inputs and one "
                f"diagnostic table; updated {len(mismatches)} files"
            )
            return 0

        if mismatches:
            print("regeneration differs from the checked-in files:", file=sys.stderr)
            for current, _ in mismatches:
                print(f"  {current.relative_to(PACKAGE_ROOT)}", file=sys.stderr)
            print("run with --write to accept the rebuilt files", file=sys.stderr)
            return 1

        print(
            f"PASS: {len(generated)} derived inputs and one diagnostic table "
            "rebuild byte-for-byte"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
