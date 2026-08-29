#!/usr/bin/env python3
"""Shared compute price and electricity-intensity parameterization.

This is the small, data-only subset needed by the demand generator. It keeps
the demand rebuild independent of the policy XML writer used in the private
analysis tree.
"""

import csv
import importlib.util
import math
import os


HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "inputs")
ENERGY_DIR = os.environ.get("AI_GCAMDATA_ENERGY_DIR")
if not ENERGY_DIR:
    raise SystemExit(
        "Run generation/regenerate.py; the scratch energy directory was not set."
    )

_spec = importlib.util.spec_from_file_location(
    "ai_constants", os.path.join(HERE, "ai_constants.py")
)
AC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AC)

ALL_SERVICES = ("conventional", "training", "inference")
NONENERGY_INPUTS = ("hw-capital", "facility-capital", "opex")
SERVICE_MAP = {
    "training": {"producer": "training compute"},
    "inference": {"producer": "inference compute"},
    "conventional": {"producer": "conventional compute"},
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(
            row for row in stream
            if row.strip() and not row.lstrip().startswith("#")
        ))


def wide_path(path, key_column):
    result = {}
    for row in read_csv(path):
        result[row[key_column]] = {
            int(year): float(row[year])
            for year in row if year.isdigit() and row[year] != ""
        }
    return result


def wide_path_split(path):
    result = {}
    for row in read_csv(path):
        key = (row["supplysector"], row["minicam.non.energy.input"])
        if key in result:
            raise AssertionError(f"duplicate cost row {key} in {path}")
        result[key] = {
            int(year): float(row[year])
            for year in row if year.isdigit() and row[year] != ""
        }
    return result


IOTA_BASE = wide_path(
    os.path.join(ENERGY_DIR, "A280.globaltech_eff.csv"), "supplysector"
)
IOTA_BASE.update(wide_path(
    os.path.join(ENERGY_DIR, "A281.globaltech_eff.csv"), "supplysector"
))
COST_SPLIT_BASE = wide_path_split(
    os.path.join(ENERGY_DIR, "A280.globaltech_cost.csv")
)
COST_SPLIT_BASE.update(wide_path_split(
    os.path.join(ENERGY_DIR, "A281.globaltech_cost.csv")
))


def benchmark_history():
    result = {service: {} for service in ALL_SERVICES}
    path = os.path.join(INPUTS, "fleet-efficiency-index-2021-2025.csv")
    for row in read_csv(path):
        result[row["service"]][int(row["year"])] = (
            float(row["fleet_efficiency_index_2021_100"]) / 100
        )
    for service, series in result.items():
        if series.get(2021) != 1.0 or 2025 not in series:
            raise AssertionError(service)
    return result


def hardware_history():
    rows = read_csv(
        os.path.join(INPUTS, "non-energy-cost-productivity-mapping.csv")
    )
    return {
        service: {
            int(row["year"]): float(
                row["hardware_productivity_index_2021_1"]
            )
            for row in rows if row["service"] == service
        }
        for service in ALL_SERVICES
    }


BENCHMARK = benchmark_history()
HARDWARE = hardware_history()


def benchmark_post2025(service, scenario, year):
    phi = AC.EFFICIENCY_PHI[scenario][service]
    tau = math.log(phi) / AC.EFFICIENCY_HIST_LOG_GROWTH[service]
    elapsed = max(year - 2025, 0)
    return math.exp(math.log(phi) * (1 - math.exp(-elapsed / tau)))


def benchmark_level(service, scenario, year):
    if year <= 2025:
        return BENCHMARK[service][year]
    return (
        BENCHMARK[service][2025]
        * benchmark_post2025(service, scenario, year)
    )


def hardware_level(service, scenario, year):
    if year <= 2025:
        return HARDWARE[service][year]
    return (
        HARDWARE[service][2025]
        * benchmark_post2025(service, scenario, year) ** AC.RHO_COST[service]
    )


def iota_level(service, scenario, year):
    good = SERVICE_MAP[service]["producer"]
    return IOTA_BASE[good][2021] / benchmark_level(service, scenario, year)


def cost_2021_composite(service):
    good = SERVICE_MAP[service]["producer"]
    return sum(
        COST_SPLIT_BASE[(good, name)][2021] for name in NONENERGY_INPUTS
    )


def cost_level(service, scenario, year):
    cost_2021 = cost_2021_composite(service)
    mapping = AC.COST_MAPPING[service]
    hardware = hardware_level(service, scenario, year)
    benchmark = benchmark_level(service, scenario, year)
    return cost_2021 * (
        mapping["hw_share"] / hardware
        + mapping["fac_share"] / benchmark
        + mapping["opex_share"]
    )
