#!/usr/bin/env python3
"""Verify the complete AI data-center GCAM runtime without running GCAM."""

from __future__ import annotations

import argparse
import csv
from functools import lru_cache
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
EXE_ROOT = REPO_ROOT / "exe"
CONFIG_ROOT = HERE / "configurations"
MAP_PATH = HERE / "configuration-map.csv"
HASH_PATH = HERE / "runtime-hashes.sha256"
SOURCE_MAP_PATH = HERE / "provenance" / "runtime-source-map.csv"
XML_MANIFEST = (
    REPO_ROOT
    / "input/gcamdata/ai-data-center/provenance/"
    / "final-calibrated-xml-manifest.sha256"
)
XML_SNAPSHOT = REPO_ROOT / "input/gcamdata/xml-ai-data-center-calibrated"
SCENARIO = re.compile(
    r"^ai-data-center_demand-(constant|low|medium|high)_"
    r"efficiency-(low|medium|high)_(reference|net-zero-2050)$"
)
GROUPS = (
    "efficiency-low",
    "efficiency-medium",
    "efficiency-high",
    "demand-constant",
)


@lru_cache(maxsize=None)
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)
    print(f"FAIL {message}", file=sys.stderr)


def read_hash_manifest(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        digest, name = line.split(maxsplit=1)
        rows.append((digest, name.strip()))
    return rows


def verify_hashes(failures: list[str]) -> None:
    if not HASH_PATH.is_file():
        fail(f"missing runtime hash manifest: {HASH_PATH}", failures)
        return
    for expected, relative in read_hash_manifest(HASH_PATH):
        path = REPO_ROOT / relative
        if not path.is_file():
            fail(f"missing runtime asset: {relative}", failures)
        elif sha256(path) != expected:
            fail(f"runtime hash mismatch: {relative}", failures)


def verify_source_map(
    failures: list[str],
    canonical_matrix: Path | None = None,
) -> None:
    if not SOURCE_MAP_PATH.is_file():
        fail(f"missing runtime source map: {SOURCE_MAP_PATH}", failures)
        return
    with SOURCE_MAP_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 300:
        fail(f"runtime source map has {len(rows)} rows, expected 300", failures)
    seen: set[str] = set()
    for row in rows:
        public_name = row["public_path"]
        if public_name in seen:
            fail(f"duplicate runtime public path: {public_name}", failures)
            continue
        seen.add(public_name)
        public = REPO_ROOT / public_name
        if not public.is_file():
            fail(f"runtime source-map target missing: {public_name}", failures)
        elif sha256(public) != row["public_sha256"]:
            fail(f"runtime source-map hash mismatch: {public_name}", failures)

        if canonical_matrix is not None and row["source_tree"] == "canonical-matrix":
            source = canonical_matrix / row["source_path"]
            if not source.is_file():
                fail(f"canonical source-map file missing: {source}", failures)
            elif sha256(source) != row["source_sha256"]:
                fail(f"canonical source-map hash mismatch: {source}", failures)


def verify_xml_snapshot(failures: list[str]) -> None:
    if not XML_MANIFEST.is_file():
        fail(f"missing XML manifest: {XML_MANIFEST}", failures)
        return
    expected = read_hash_manifest(XML_MANIFEST)
    actual_names = {
        path.name for path in XML_SNAPSHOT.iterdir() if path.is_file()
    } if XML_SNAPSHOT.is_dir() else set()
    expected_names = {name for _, name in expected}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        fail(
            f"calibrated XML file set differs: missing={missing}, extra={extra}",
            failures,
        )
        return
    for digest, name in expected:
        if sha256(XML_SNAPSHOT / name) != digest:
            fail(f"calibrated XML hash mismatch: {name}", failures)


def value(
    root: ET.Element,
    section: str,
    name: str,
) -> ET.Element | None:
    return root.find(f"./{section}/Value[@name='{name}']")


def required_value(
    root: ET.Element,
    section: str,
    name: str,
    config: Path,
    failures: list[str],
) -> ET.Element | None:
    node = value(root, section, name)
    if node is None:
        fail(f"{config}: missing {section}/{name}", failures)
    return node


def check_text(
    root: ET.Element,
    section: str,
    name: str,
    expected: str,
    config: Path,
    failures: list[str],
) -> None:
    node = required_value(root, section, name, config, failures)
    if node is not None and (node.text or "") != expected:
        fail(
            f"{config}: {name} is {(node.text or '')!r}, expected {expected!r}",
            failures,
        )


def resolve_from_exe(text: str) -> Path:
    return (EXE_ROOT / text).resolve()


def verify_references(
    root: ET.Element,
    config: Path,
    failures: list[str],
) -> None:
    batch_mode = value(root, "Bools", "BatchMode")
    for node in root.findall("./Files/Value"):
        name = node.attrib.get("name", "")
        text = node.text or ""
        if name in {
            "xmldb-location",
            "xmlDebugFileName",
            "hector-output",
            "costCurvesOutputFileName",
            "supplyDemandOutputFileName",
        }:
            continue
        if name == "BatchFileName" and (
            batch_mode is not None and batch_mode.text == "0"
        ):
            continue
        if name == "restart":
            prefix = resolve_from_exe(text)
            pieces = sorted(prefix.parent.glob(f"{prefix.name}.*"))
            if len(pieces) != 7:
                fail(
                    f"{config}: warm restart requires 7 pieces at {prefix}",
                    failures,
                )
            continue
        path = resolve_from_exe(text)
        if not path.is_file():
            fail(f"{config}: missing referenced file {path}", failures)

    for node in root.findall("./ScenarioComponents/Value"):
        text = node.text or ""
        path = resolve_from_exe(text)
        if not path.is_file():
            fail(f"{config}: missing component {path}", failures)


def verify_config(
    path: Path,
    *,
    kind: str,
    group: str | None,
    failures: list[str],
) -> str | None:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        fail(f"{path}: invalid XML: {error}", failures)
        return None

    stem = path.stem
    match = SCENARIO.fullmatch(stem)
    if match is None:
        fail(f"{path}: filename does not follow the descriptive contract", failures)
        return None
    demand, efficiency, policy = match.groups()
    expected_group = (
        "demand-constant"
        if demand == "constant"
        else f"efficiency-{efficiency}"
    )
    if kind == "database-archive" and group != expected_group:
        fail(
            f"{path}: belongs in {expected_group}, not {group}",
            failures,
        )

    check_text(root, "Strings", "scenarioName", stem, path, failures)
    check_text(root, "Ints", "stop-period", "11", path, failures)
    check_text(root, "Ints", "stop-year", "2050", path, failures)
    check_text(root, "Ints", "restart-period", "7", path, failures)
    check_text(root, "Ints", "max-parallelism", "16", path, failures)
    check_text(
        root,
        "ScenarioComponents",
        "solver",
        "../input/solution/cal_broyden_kaist.xml",
        path,
        failures,
    )
    check_text(
        root,
        "ScenarioComponents",
        "ai_demand",
        f"../input/policy/ai-data-center/demand-{demand}.xml",
        path,
        failures,
    )
    check_text(
        root,
        "ScenarioComponents",
        "ai_efficiency",
        f"../input/policy/ai-data-center/efficiency-{efficiency}.xml",
        path,
        failures,
    )
    check_text(
        root,
        "ScenarioComponents",
        "ai_trade",
        "../input/policy/ai-data-center/trade-open.xml",
        path,
        failures,
    )
    climate_file = (
        "carbon-policy-reference.xml"
        if policy == "reference"
        else "carbon-policy-net-zero-2050.xml"
    )
    check_text(
        root,
        "ScenarioComponents",
        "ai_climate",
        f"../input/policy/ai-data-center/{climate_file}",
        path,
        failures,
    )
    check_text(
        root,
        "Files",
        "restart",
        "restart/ai-data-center-warm-start/restart",
        path,
        failures,
    )

    database = required_value(
        root, "Files", "xmldb-location", path, failures
    )
    if database is not None:
        expected_write = "1" if kind == "database-archive" else "0"
        if database.attrib.get("write-output") != expected_write:
            fail(
                f"{path}: xmldb write-output must be {expected_write}",
                failures,
            )
        expected_database = (
            f"../output/ai-data-center-databases/{group}"
            if kind == "database-archive"
            else "../output/ai-data-center-database"
        )
        if database.text != expected_database:
            fail(
                f"{path}: database path is {database.text!r}, "
                f"expected {expected_database!r}",
                failures,
            )

    verify_references(root, path, failures)
    return stem


def expected_scenarios() -> set[str]:
    return {
        f"ai-data-center_demand-{demand}_efficiency-{efficiency}_{policy}"
        for demand in ("constant", "low", "medium", "high")
        for efficiency in ("low", "medium", "high")
        for policy in ("reference", "net-zero-2050")
    }


def verify_configurations(failures: list[str]) -> None:
    expected = expected_scenarios()
    direct_paths = sorted((CONFIG_ROOT / "scenarios").glob("*.xml"))
    direct = {
        name
        for path in direct_paths
        if (
            name := verify_config(
                path, kind="scenario", group=None, failures=failures
            )
        )
    }
    if direct != expected:
        fail(
            f"scenario configuration coverage differs: "
            f"missing={sorted(expected - direct)}, extra={sorted(direct - expected)}",
            failures,
        )

    archived: set[str] = set()
    for group in GROUPS:
        paths = sorted(
            (CONFIG_ROOT / "database-archive" / group).glob("*.xml")
        )
        if len(paths) != 6:
            fail(f"database group {group} has {len(paths)} files, expected 6", failures)
        for path in paths:
            name = verify_config(
                path,
                kind="database-archive",
                group=group,
                failures=failures,
            )
            if name is not None:
                archived.add(name)
    if archived != expected:
        fail(
            f"database configuration coverage differs: "
            f"missing={sorted(expected - archived)}, "
            f"extra={sorted(archived - expected)}",
            failures,
        )

    with MAP_PATH.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 48:
        fail(f"configuration map has {len(rows)} rows, expected 48", failures)
    for row in rows:
        path = CONFIG_ROOT / row["public_file"]
        if path.is_file() and sha256(path) != row["public_sha256"]:
            fail(f"configuration map hash mismatch: {row['public_file']}", failures)


def verify_binary(failures: list[str]) -> None:
    binary = EXE_ROOT / "gcam.exe"
    if not binary.is_file():
        fail("missing built executable exe/gcam.exe", failures)
    elif not binary.stat().st_mode & 0o111:
        fail("exe/gcam.exe is not executable", failures)

    source = REPO_ROOT / "cvs/objects"
    origin_path = HERE / "gcam-core-origin.txt"
    expected = "11e128fb7ce3e14e9c4daf3903ba73123046a7aa"
    try:
        git_root = Path(subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"cannot identify the GCAM core source repository: {error}", failures)
        return

    if git_root != REPO_ROOT.resolve():
        commit = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if commit != expected:
            fail(f"GCAM core revision is {commit}, expected v9.1 {expected}", failures)
        return

    if not origin_path.is_file():
        fail(f"missing migrated-core origin record: {origin_path}", failures)
        return
    origin = {}
    for line in origin_path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            origin[key] = value
    if origin.get("upstream_commit") != expected:
        fail("migrated-core origin does not identify GCAM v9.1", failures)

    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", "cvs/objects"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    digest = hashlib.sha256(listing.encode("utf-8")).hexdigest()
    entries = len([line for line in listing.splitlines() if line])
    if digest != origin.get("index_sha256") or str(entries) != origin.get("tracked_entries"):
        fail("migrated GCAM core index differs from its frozen v9.1 origin", failures)
    dirty = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--quiet", "--", "cvs/objects"],
        check=False,
    ).returncode
    if dirty != 0:
        fail("migrated GCAM core has uncommitted tracked-file changes", failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--canonical-matrix",
        type=Path,
        help="also compare against a read-only frozen matrix tree",
    )
    args = parser.parse_args()

    failures: list[str] = []
    verify_binary(failures)
    verify_hashes(failures)
    verify_xml_snapshot(failures)
    verify_configurations(failures)
    canonical = (
        args.canonical_matrix.resolve()
        if args.canonical_matrix is not None
        else None
    )
    verify_source_map(failures, canonical)

    if failures:
        print(f"FAIL: {len(failures)} runtime verification errors", file=sys.stderr)
        return 1
    print("PASS: GCAM v9.1 source revision")
    print("PASS: 226 calibrated gcamdata XML files")
    print("PASS: 24 scenario and 24 database-archive configurations")
    print("PASS: solver, policies, warm restart, and runtime references")
    print("PASS: 300-row reversible runtime source map")
    if args.canonical_matrix is not None:
        print("PASS: public runtime matches the read-only canonical matrix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
