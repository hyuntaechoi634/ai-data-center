#!/usr/bin/env python3
"""Generate service-specific GCAM compute inputs.

Training, inference, and conventional compute use separate 2021-normalized
chained benchmark-equivalent volume units (TSU, ISU, and CSU). World output of
each service is one in 2021. These service quantities are never added.

Run through ``python3 regenerate.py`` from this directory. The orchestrator
provides scratch directories that retain GCAM's conventional deployed names
while the checked-in authoring files use descriptive public names.

Method:
    analysis/cost-diagnostics/GCAM_COMPUTE_SERVICE_COST_METHOD.md
    analysis/demand-axes/GCAM_COMPUTE_SERVICE_DEMAND_METHOD.md
"""

import csv
import importlib.util
import math
import os


HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(HERE)
INPUTS = os.path.join(HERE, "inputs")
_spec = importlib.util.spec_from_file_location(
    "ai_constants", os.path.join(HERE, "ai_constants.py")
)
AC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AC)

ENE = os.environ.get("AI_GCAMDATA_ENERGY_DIR")
WAT = os.environ.get("AI_GCAMDATA_WATER_DIR")
if not ENE or not WAT:
    raise SystemExit(
        "Run generation/regenerate.py; scratch output directories were not set."
    )
REGIONS_CSV = os.environ.get(
    "AI_GCAM_REGION_NAMES",
    os.path.join(
        os.path.dirname(PACKAGE_ROOT), "inst", "extdata", "common",
        "GCAM_region_names.csv",
    ),
)
SITING_CSV = os.path.join(INPUTS, "ai-production-share-2021.csv")
DC_TARGETS_CSV = os.path.join(
    INPUTS, "regional-data-center-electricity-targets-2021-2025.csv"
)

MODEL_YEARS = [
    2021, 2025, 2030, 2035, 2040, 2045, 2050,
    2060, 2070, 2080, 2090, 2100,
]
AI_SERVICES = ("training", "inference")
ALL_SERVICES = ("conventional",) + AI_SERVICES
SERVICE_MAP = {
    "training": {
        "producer": "training compute",
        "traded": "traded training compute",
        "regional": "regional training compute",
        "unit": "TSU",
        "price_unit": "1975 billion$/TSU",
        "domimp_logit": -6,
    },
    "inference": {
        "producer": "inference compute",
        "traded": "traded inference compute",
        "regional": "regional inference compute",
        "unit": "ISU",
        "price_unit": "1975 billion$/ISU",
        "domimp_logit": -3,
    },
    "conventional": {
        "producer": "conventional compute",
        "unit": "CSU",
        "price_unit": "1975 billion$/CSU",
    },
}

LOGIT_PRODUCTION = -3
LOGIT_TRADED = -6
LOGIT_REGIONAL = -3
FAI_CAP = 0.6
FAI_GROWTH_TO_2030 = 1.8
# Delivered-electricity market the compute sectors buy from. The base-year
# carve is taken out of commercial building electricity, which reaches
# buildings through elect_td_bld, so the services buy it back in the same
# market and the base-year delivery balance is preserved (2026-08-17).
ELEC_MARKET = "elect_td_bld"

TRAIN_DC_WEIGHT = 0.7

# Preserve the calibrated 2021 non-energy/electricity cost ratio when changing
# the quantity unit. The level was originally derived from 2021 energy cost and
# the assumed energy/non-energy cost shares.
AI_NU_GAMMA_RATIO = (AC.NU0 / AC.PRICE_SCALE) / AC.GAMMA0
CONV_NU_GAMMA_RATIO = AC.NU_CONV0 / AC.GAMMA_CONV0

GDP_SHARE = {
    "USA": 0.245, "China": 0.185, "EU-15": 0.145, "EU-12": 0.018,
    "European Free Trade Association": 0.012, "Japan": 0.052,
    "South Korea": 0.019, "Canada": 0.021, "India": 0.034,
    "Southeast Asia": 0.032, "Australia_NZ": 0.018,
    "Middle East": 0.038, "Russia": 0.019, "Brazil": 0.017,
    "Mexico": 0.013, "Taiwan": 0.008, "South Africa": 0.004,
    "Europe_Non_EU": 0.020, "Indonesia": 0.013, "Ukraine": 0.002,
    "Central Asia": 0.003, "Pakistan": 0.004, "South Asia": 0.006,
    "Central America and Caribbean": 0.004,
    "South America_Northern": 0.004,
    "South America_Southern": 0.004, "Argentina": 0.005,
    "Colombia": 0.004, "Africa_Eastern": 0.004,
    "Africa_Northern": 0.006, "Africa_Southern": 0.003,
    "Africa_Western": 0.006,
}


def read_regions():
    regions = []
    with open(REGIONS_CSV) as stream:
        for row in csv.reader(stream):
            if not row or row[0].startswith("#") or row[0] == "GCAM_region_ID":
                continue
            regions.append(row[1])
    return regions


def read_siting():
    # no longer drives anything (see allocate_ai_electricity); optional
    if not os.path.exists(SITING_CSV):
        return {}
    with open(SITING_CSV) as stream:
        return {
            row["region"]: float(row["share"])
            for row in csv.DictReader(stream)
        }


def read_dc_targets():
    if not os.path.exists(DC_TARGETS_CSV):
        raise SystemExit(
            f"MISSING {DC_TARGETS_CSV}; run scripts/recal/step2b_bnef_targets.py"
        )
    targets = {2021: {}, 2025: {}}
    with open(DC_TARGETS_CSV) as stream:
        for row in csv.DictReader(stream):
            targets[2021][row["region"]] = (
                float(row["dc2021_TWh"]) / AC.TWH_PER_EJ
            )
            targets[2025][row["region"]] = (
                float(row["dc2025_TWh"]) / AC.TWH_PER_EJ
            )
    for year, values in targets.items():
        expected = AC.E_DC_GLOBAL_TWH[year] / AC.TWH_PER_EJ
        scale = expected / sum(values.values())
        values.update({region: value * scale for region, value in values.items()})
    return targets


def read_benchmark_history():
    """2021-2025 efficiency path, IT level, 2021 = 1.

    2026-08-19: the calibration driver is the FLEET instrument (same one that
    set GAMMA0 / GAMMA_CONV0 -- LBNL 2024 operating conventions x installed-base
    generation mix x MFU 0.40 for AI; SEED tier x vintage x utilisation for
    conventional), measured at 2021 and 2025 and log-interpolated between.
    Training/inference x1.90, conventional x2.02 (IT level; PUE enters through
    m_path). The benchmark indices (MLPerf Training x2.65, MLPerf Inference
    x2.15, SPECpower x1.77) are retained as supporting evidence in
    analysis/efficiency-axes/*/ but no longer drive the path: a benchmark is
    new-vs-new and system-equal weighted, the fleet is stock weighted. See
    analysis/efficiency-axes/REVIEW_2026-08-19_SUMMARY.md and DEEP_REVIEW_RESULT.md.
    """
    path = os.path.join(INPUTS, "fleet-efficiency-index-2021-2025.csv")
    result = {s: {} for s in ALL_SERVICES}
    with open(path) as stream:
        for row in csv.DictReader(stream):
            result[row["service"]][int(row["year"])] = (
                float(row["fleet_efficiency_index_2021_100"]) / 100
            )
    for service in ALL_SERVICES:
        assert result[service][2021] == 1.0 and 2025 in result[service], service
    return result


def read_hardware_history():
    path = os.path.join(INPUTS, "non-energy-cost-productivity-mapping.csv")
    with open(path) as stream:
        rows = list(csv.DictReader(stream))
    return {
        service: {
            int(row["year"]): float(row["hardware_productivity_index_2021_1"])
            for row in rows if row["service"] == service
        }
        for service in ALL_SERVICES
    }


def post2025_benchmark_multiplier(service, scenario, year):
    if year <= 2025:
        return 1
    phi = AC.EFFICIENCY_PHI[scenario][service]
    tau = math.log(phi) / AC.EFFICIENCY_HIST_LOG_GROWTH[service]
    return math.exp(math.log(phi) * (1 - math.exp(-(year - 2025) / tau)))


def post2025_power_multiplier(service, year):
    if year <= 2025:
        return 1
    g0 = AC.POWER_ENVELOPE_INITIAL_LOG_GROWTH[service]
    tau = AC.POWER_ENVELOPE_TAU
    return math.exp(g0 * tau * (1 - math.exp(-(year - 2025) / tau)))


def nonenergy_relative(service, hardware_relative, benchmark_relative):
    # 2026-08-20 3-term mapping: hw capex follows H, facility capex ($/W) follows B
    # (W/FLOP = 1/B), opex flat. COST_AXIS_DESIGN SS1/SS4.
    mapping = AC.COST_MAPPING[service]
    return (
        mapping["hw_share"] / hardware_relative
        + mapping["fac_share"] / benchmark_relative
        + mapping["opex_share"]
    )


# v3.2 three-input split (2026-08-27, analysis/brp7-capital-audit/V32_SPEC.md).
# The single composite "non-energy" input is replaced by three inputs whose
# costs are the SAME three terms of nonenergy_relative, so the sum identity
# with the previous composite nu holds by construction at full precision:
#   hw-capital       = nu0 x w_hw / H(t)   (plain input, untracked)
#   facility-capital = nu0 x w_fac / B(t)  (the ONLY capital-tracked input)
#   opex             = nu0 x w_opex        (plain input, flat)
NONENERGY_INPUTS = ("hw-capital", "facility-capital", "opex")


def nonenergy_components(service, hardware_relative, benchmark_relative):
    mapping = AC.COST_MAPPING[service]
    return {
        "hw-capital": mapping["hw_share"] / hardware_relative,
        "facility-capital": mapping["fac_share"] / benchmark_relative,
        "opex": mapping["opex_share"],
    }


def component_cost_rows(good, service, nu0, hardware_path, benchmark_path):
    """Three CSV rows (one per v3.2 input) + the gate-5a identity assert."""
    for year in sorted(hardware_path):
        components = nonenergy_components(
            service, hardware_path[year], benchmark_path[year]
        )
        composite = nonenergy_relative(
            service, hardware_path[year], benchmark_path[year]
        )
        total = sum(components.values())
        assert abs(total - composite) <= 1e-12 * composite, (
            "v3.2 sum identity broken in-generator: "
            f"{service} {year}: {total!r} != {composite!r}"
        )
    return [
        [good, good, good, input_name]
        + [
            sig(
                nu0
                * nonenergy_components(
                    service, hardware_path[year], benchmark_path[year]
                )[input_name]
            )
            for year in MODEL_YEARS
        ]
        for input_name in NONENERGY_INPUTS
    ]


def write_csv(path, headers, coltypes, columns, rows):
    with open(path, "w", newline="") as stream:
        for header in headers:
            stream.write(f"# {header}\n")
        if not any(header.lower().startswith("units:") for header in headers):
            stream.write("# Units: see Title\n")
        stream.write(f"# Column types: {coltypes}\n")
        stream.write("# ----------\n")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def sig(value, digits=8):
    if value == 0:
        return "0"
    return f"{value:.{digits}g}"


def allocate_ai_electricity(regions, siting, total_dc):
    # 2026-08-19: geography is set ONCE, by the BNEF market totals and their
    # GDP split (total_dc). AI is a world share of that, f_AI = E_AI/E_DC, the
    # same in every region -- the same rule the 2025 targets use. Epoch cluster
    # siting used to set the AI geography here, and set it differently in the
    # two years (2021 = mostly national supercomputers, 320 MW; 2025 = hyper-
    # scaler GPU clusters, 2,068 MW), which asked the 2025 calibration to move
    # 35 share points of world AI production between regions in one step. That
    # is a difference between two samples, not a real shift; `siting` is kept
    # in the signature only so the call site does not change.
    world_ai = AC.E_AI_GLOBAL_TWH[2021] / AC.TWH_PER_EJ
    world_dc = sum(total_dc[region] for region in regions)
    f_ai = world_ai / world_dc
    allocated = {region: total_dc[region] * f_ai for region in regions}
    for _ in range(10):
        excess = {
            region: allocated[region] - FAI_CAP * total_dc[region]
            for region in regions
            if allocated[region] > FAI_CAP * total_dc[region] + 1e-14
        }
        if not excess:
            break
        spill = sum(excess.values())
        for region in excess:
            allocated[region] = FAI_CAP * total_dc[region]
        room = {
            region: siting.get(region, 0)
            for region in regions
            if region not in excess
            and allocated[region] < FAI_CAP * total_dc[region]
        }
        room_total = sum(room.values())
        for region, weight in room.items():
            allocated[region] += spill * weight / room_total
    assert abs(sum(allocated.values()) - world_ai) < 1e-10
    return allocated


def normalized_facility_multiplier(regions, weights, world_multiplier):
    denominator = sum(weights.values())
    survey_mean = sum(
        weights[region] * AC.pue_of(region) for region in regions
    ) / denominator
    return {
        region: world_multiplier * AC.pue_of(region) / survey_mean
        for region in regions
    }


def facility_multiplier_paths(regions, targets):
    paths = {}
    for year in (2021, 2025):
        paths[year] = normalized_facility_multiplier(
            regions, targets[year], AC.M_GLOBAL[year]
        )
    for year in MODEL_YEARS:
        if year > 2025:
            paths[year] = {
                region: AC.PUE_INF
                + (paths[2025][region] - AC.PUE_INF)
                * math.exp(-(year - 2025) / AC.TAU_PUE)
                for region in regions
            }
    return paths


def write_service_map():
    rows = [
        [
            service,
            SERVICE_MAP[service]["producer"],
            SERVICE_MAP[service]["traded"],
            SERVICE_MAP[service]["regional"],
            SERVICE_MAP[service]["unit"],
            SERVICE_MAP[service]["price_unit"],
            SERVICE_MAP[service]["domimp_logit"],
        ]
        for service in AI_SERVICES
    ]
    write_csv(
        os.path.join(ENE, "A_aicomp_services.csv"),
        [
            "File: A_aicomp_services.csv",
            "Title: Live topology and units for service-specific AI compute",
            "Units: service-specific output units; logit exponent is unitless",
            "Source: structural specification. TSU and ISU are separate "
            "2021-normalized chained benchmark-equivalent units and are not added.",
        ],
        "ccccccn",
        [
            "service", "production.good", "traded.good", "regional.good",
            "output.unit", "price.unit", "logit.exponent",
        ],
        rows,
    )


def write_production_inputs(benchmark, hardware, iota0, world_facility_electricity):
    benchmark_paths = {}
    hardware_paths = {}
    for service in ALL_SERVICES:
        benchmark_paths[service] = {}
        hardware_paths[service] = {}
        for year in MODEL_YEARS:
            if year <= 2025:
                benchmark_paths[service][year] = benchmark[service][year]
                hardware_paths[service][year] = hardware[service][year]
            else:
                benchmark_paths[service][year] = (
                    benchmark[service][2025]
                    * post2025_benchmark_multiplier(service, "Medium", year)
                )
                # H is FLOP per $ of capex (measured 2021-25); after 2025 it grows at
                # RHO_COST x the efficiency rate. The old power-envelope factor belonged
                # to the retired "service per hardware-hour" definition of H.
                hardware_paths[service][year] = (
                    hardware[service][2025]
                    * post2025_benchmark_multiplier(service, "Medium", year)
                    ** AC.RHO_COST[service]
                )

    ai_eff_rows = []
    ai_cost_rows = []
    for service in AI_SERVICES:
        good = SERVICE_MAP[service]["producer"]
        ai_eff_rows.append(
            [good, good, good, ELEC_MARKET]
            + [
                sig(iota0[service] / benchmark_paths[service][year])
                for year in MODEL_YEARS
            ]
        )
        # 2026-08-26 UNIT FIX (external review): with output in physical RFLOP
        # the base non-energy cost is the per-RFLOP anchor DIRECTLY.
        # The former electricity x (NU0/GAMMA0) construction belonged to the
        # 2021-normalized unit and over-stated nu by the 2021 world output
        # (x4.79 training / x4.86 inference), breaking the 5.8% electricity
        # share of service cost. Inference carries the same 1.333 intensity
        # ratio as iota (more machine-time per delivered RFLOP).
        nu0 = (AC.NU0 / AC.PRICE_SCALE) * (
            AC.INFERENCE_GAMMA_RATIO if service == "inference" else 1.0
        )
        # v3.2 (2026-08-27): three rows per service, one per split input.
        ai_cost_rows.extend(
            component_cost_rows(
                good, service, nu0,
                hardware_paths[service], benchmark_paths[service],
            )
        )

    common_columns = [
        "supplysector", "subsector", "technology", "minicam.energy.input",
    ] + [str(year) for year in MODEL_YEARS]
    write_csv(
        os.path.join(ENE, "A280.globaltech_eff.csv"),
        [
            "File: A280.globaltech_eff.csv",
            "Title: AI IT-electricity coefficient iota by service",
            "Units: EJ IT electricity per TSU or ISU",
            "Source: 2021 service electricity normalization and audited chained "
            "benchmark B; facility coefficient is gamma=iota*M in the R chunks.",
        ],
        "cccc" + "n" * len(MODEL_YEARS),
        common_columns,
        ai_eff_rows,
    )
    write_csv(
        os.path.join(ENE, "A280.globaltech_cost.csv"),
        [
            "File: A280.globaltech_cost.csv",
            "Title: AI non-energy cost by service, v3.2 three-input split",
            "Units: 1975 billion$/TSU or 1975 billion$/ISU",
            "Source: 2021 level preserves the energy/non-energy cost-share "
            "calibration; the 3-term mapping s_hw/H + s_fac/B + s_opex",
            "(AI 0.83/0.15/0.02, H=B rho=1) is carried as THREE inputs "
            "(hw-capital / facility-capital / opex, one term each;",
            "sum identical to the former composite non-energy row) - "
            "v3.2 2026-08-27, V32_SPEC.md.",
        ],
        "cccc" + "n" * len(MODEL_YEARS),
        [
            "supplysector", "subsector", "technology",
            "minicam.non.energy.input",
        ] + [str(year) for year in MODEL_YEARS],
        ai_cost_rows,
    )

    service = "conventional"
    good = SERVICE_MAP[service]["producer"]
    conv_eff = [
        [good, good, good, ELEC_MARKET]
        + [
            sig(iota0[service] / benchmark_paths[service][year])
            for year in MODEL_YEARS
        ]
    ]
    # 2026-08-26 UNIT FIX (external review): per-RFLOP anchor directly
    # (was electricity x NU_CONV0/GAMMA_CONV0 = x3.38 over-statement).
    nu0 = AC.NU_CONV0
    # v3.2 (2026-08-27): three rows, one per split input (see component_cost_rows).
    conv_cost = component_cost_rows(
        good, service, nu0,
        hardware_paths[service], benchmark_paths[service],
    )
    write_csv(
        os.path.join(ENE, "A281.globaltech_eff.csv"),
        [
            "File: A281.globaltech_eff.csv",
            "Title: Conventional IT-electricity coefficient iota",
            "Units: EJ IT electricity per CSU",
            "Source: 2021 conventional electricity normalization and audited "
            "SPECpower chained benchmark B; gamma=iota*M in the R chunks.",
        ],
        "cccc" + "n" * len(MODEL_YEARS),
        common_columns,
        conv_eff,
    )
    write_csv(
        os.path.join(ENE, "A281.globaltech_cost.csv"),
        [
            "File: A281.globaltech_cost.csv",
            "Title: Conventional non-energy cost, v3.2 three-input split",
            "Units: 1975 billion$/CSU",
            "Source: 2021 level preserves the energy/non-energy cost-share "
            "calibration; the 3-term mapping s_hw/H + s_fac/B + s_opex",
            "(conv 0.7662/0.2008/0.0330, H=B rho_conv=1 ruling) is carried as "
            "THREE inputs (hw-capital / facility-capital / opex, one term each;",
            "sum identical to the former composite non-energy row) - "
            "v3.2 2026-08-27, V32_SPEC.md.",
        ],
        "cccc" + "n" * len(MODEL_YEARS),
        [
            "supplysector", "subsector", "technology",
            "minicam.non.energy.input",
        ] + [str(year) for year in MODEL_YEARS],
        conv_cost,
    )
    return benchmark_paths, hardware_paths


def write_production_structure():
    ai_sector_rows = []
    ai_subsector_rows = []
    ai_interp_rows = []
    ai_share_rows = []
    ai_water_rows = []
    for service in AI_SERVICES:
        entry = SERVICE_MAP[service]
        good = entry["producer"]
        ai_sector_rows.append(
            [
                good, entry["unit"], "EJ", entry["price_unit"],
                LOGIT_PRODUCTION, "", "",
            ]
        )
        ai_subsector_rows.append([good, good, LOGIT_PRODUCTION, ""])
        ai_interp_rows.append(
            [good, good, "share-weight", 2021, 2100, "linear"]
        )
        ai_share_rows.append([good, good, good, 0, 0, 0, 0, 0, 1, 1])
        ai_water_rows.extend(
            [
                [good, good, good, "water_td_ind_W", AC.OMEGA_W],
                [good, good, good, "water_td_ind_C", AC.OMEGA_C],
            ]
        )

    write_csv(
        os.path.join(ENE, "A280.sector.csv"),
        [
            "File: A280.sector.csv",
            "Title: Service-specific AI production sectors",
            "Units: TSU or ISU output; EJ input; service-specific price unit",
        ],
        "ccccncc",
        [
            "supplysector", "output.unit", "input.unit", "price.unit",
            "logit.exponent", "final.energy", "logit.type",
        ],
        ai_sector_rows,
    )
    write_csv(
        os.path.join(ENE, "A280.subsector_logit.csv"),
        [
            "File: A280.subsector_logit.csv",
            "Title: AI production subsector logits",
            "Units: unitless",
        ],
        "ccnc",
        ["supplysector", "subsector", "logit.exponent", "logit.type"],
        ai_subsector_rows,
    )
    write_csv(
        os.path.join(ENE, "A280.subsector_interp.csv"),
        [
            "File: A280.subsector_interp.csv",
            "Title: AI production subsector interpolation",
            "Units: NA",
        ],
        "ccciic",
        [
            "supplysector", "subsector", "apply.to", "from.year",
            "to.year", "interpolation.function",
        ],
        ai_interp_rows,
    )
    write_csv(
        os.path.join(ENE, "A280.globaltech_shrwt.csv"),
        [
            "File: A280.globaltech_shrwt.csv",
            "Title: AI production technology share weights",
            "Units: unitless",
        ],
        "cccnnnnnnn",
        [
            "supplysector", "subsector", "technology", "1975", "1990",
            "2005", "2010", "2015", "2021", "2100",
        ],
        ai_share_rows,
    )
    write_csv(
        os.path.join(WAT, "A280.globaltech_water_coef.csv"),
        [
            "File: A280.globaltech_water_coef.csv",
            "Title: AI scope-1 cooling-water intensity per electricity input",
            "Units: m3/GJ electricity",
        ],
        "ccccn",
        [
            "supplysector", "subsector", "technology",
            "minicam.water.input", "coefficient",
        ],
        ai_water_rows,
    )

    good = SERVICE_MAP["conventional"]["producer"]
    write_csv(
        os.path.join(ENE, "A281.sector.csv"),
        [
            "File: A281.sector.csv",
            "Title: Conventional compute production sector",
            "Units: CSU output; EJ input; 1975 billion$/CSU",
        ],
        "ccccncc",
        [
            "supplysector", "output.unit", "input.unit", "price.unit",
            "logit.exponent", "final.energy", "logit.type",
        ],
        [[good, "CSU", "EJ", "1975 billion$/CSU", -3, "", ""]],
    )
    write_csv(
        os.path.join(WAT, "A281.globaltech_water_coef.csv"),
        [
            "File: A281.globaltech_water_coef.csv",
            "Title: Conventional scope-1 cooling-water intensity",
            "Units: m3/GJ electricity",
        ],
        "ccccn",
        [
            "supplysector", "subsector", "technology",
            "minicam.water.input", "coefficient",
        ],
        [
            [good, good, good, "water_td_ind_W", AC.OMEGA_W],
            [good, good, good, "water_td_ind_C", AC.OMEGA_C],
        ],
    )


def write_trade_structure():
    traded_sector = []
    traded_subsector = []
    traded_technology = []
    regional_sector = []
    regional_subsector = []
    regional_technology = []
    for service in AI_SERVICES:
        entry = SERVICE_MAP[service]
        traded = entry["traded"]
        regional = entry["regional"]
        producer = entry["producer"]
        unit = entry["unit"]
        price_unit = entry["price_unit"]
        domimp = entry["domimp_logit"]
        traded_sector.append(
            [traded, unit, "EJ", price_unit, 1, LOGIT_TRADED, ""]
        )
        traded_subsector.append(
            [
                traded, traded, LOGIT_TRADED, "start-year", 1,
                "share-weight", 2025, 2100, 1,
                "fixed", 1, "",
            ]
        )
        traded_technology.append(
            [traded, traded, traded, producer, 1, 0, 1, 1]
        )
        regional_sector.append(
            [regional, unit, "EJ", price_unit, LOGIT_REGIONAL, ""]
        )
        domestic = f"domestic {service} compute"
        imported = f"imported {service} compute"
        for subsector in (domestic, imported):
            regional_subsector.append(
                [
                    regional, subsector, domimp, "start-year", 1,
                    "share-weight", 2025, 2100, 1,
                    "fixed", "",
                ]
            )
        regional_technology.extend(
            [
                [regional, domestic, domestic, producer, 1, 0, 1, "regional"],
                [regional, imported, imported, traded, 1, 0, 1, "USA"],
            ]
        )

    write_csv(
        os.path.join(ENE, "A_aicomp_TradedSector.csv"),
        [
            "File: A_aicomp_TradedSector.csv",
            "Title: Service-specific traded AI-compute sectors",
            "Units: service-specific",
        ],
        "ccccinc",
        [
            "supplysector", "output.unit", "input.unit", "price.unit",
            "traded", "logit.exponent", "logit.type",
        ],
        traded_sector,
    )
    write_csv(
        os.path.join(ENE, "A_aicomp_TradedSubsector.csv"),
        [
            "File: A_aicomp_TradedSubsector.csv",
            "Title: Service-specific traded AI-compute subsectors",
            "Units: unitless",
        ],
        "ccnccccinccc",
        [
            "supplysector", "subsector", "logit.exponent", "year.fillout",
            "share.weight", "apply.to", "from.year", "to.year", "to.value",
            "interpolation.function", "traded", "logit.type",
        ],
        traded_subsector,
    )
    write_csv(
        os.path.join(ENE, "A_aicomp_TradedTechnology.csv"),
        [
            "File: A_aicomp_TradedTechnology.csv",
            "Title: Service-specific traded AI-compute technologies",
            "Units: unitless coefficient",
        ],
        "ccccnnni",
        [
            "supplysector", "subsector", "technology",
            "minicam.energy.input", "coefficient", "input.cost",
            "share.weight", "traded",
        ],
        traded_technology,
    )
    write_csv(
        os.path.join(ENE, "A_aicomp_RegionalSector.csv"),
        [
            "File: A_aicomp_RegionalSector.csv",
            "Title: Regional training and inference compute sectors",
            "Units: service-specific",
        ],
        "ccccnc",
        [
            "supplysector", "output.unit", "input.unit", "price.unit",
            "logit.exponent", "logit.type",
        ],
        regional_sector,
    )
    write_csv(
        os.path.join(ENE, "A_aicomp_RegionalSubsector.csv"),
        [
            "File: A_aicomp_RegionalSubsector.csv",
            "Title: Domestic and imported AI-compute subsectors",
            "Units: unitless",
        ],
        "ccnccccincc",
        [
            "supplysector", "subsector", "logit.exponent", "year.fillout",
            "share.weight", "apply.to", "from.year", "to.year", "to.value",
            "interpolation.function", "logit.type",
        ],
        regional_subsector,
    )
    write_csv(
        os.path.join(ENE, "A_aicomp_RegionalTechnology.csv"),
        [
            "File: A_aicomp_RegionalTechnology.csv",
            "Title: Regional AI-compute pass-through technologies",
            "Units: unitless coefficient",
        ],
        "ccccnnnc",
        [
            "supplysector", "subsector", "technology",
            "minicam.energy.input", "coefficient", "input.cost",
            "share.weight", "market.name",
        ],
        regional_technology,
    )


def main():
    regions = read_regions()
    siting = read_siting()
    targets = read_dc_targets()
    missing = [region for region in regions if region not in targets[2021]]
    if missing:
        raise AssertionError(f"DC target is missing regions: {missing}")

    ai_facility = allocate_ai_electricity(regions, siting, targets[2021])
    conv_facility = {
        region: targets[2021][region] - ai_facility[region]
        for region in regions
    }
    m_path = facility_multiplier_paths(regions, targets)

    service_facility = {
        "training": {
            region: ai_facility[region]
            * AC.AI_ELECTRICITY_SHARE[2021]["training"]
            for region in regions
        },
        "inference": {
            region: ai_facility[region]
            * AC.AI_ELECTRICITY_SHARE[2021]["inference"]
            for region in regions
        },
        "conventional": conv_facility,
    }
    service_it = {
        service: {
            region: service_facility[service][region] / m_path[2021][region]
            for region in regions
        }
        for service in ALL_SERVICES
    }
    # Unit convention (restored 2026-08-17). Output is measured in RFLOP,
    # one RFLOP being 1e27 operations, so the electricity coefficient is the
    # physical intensity in EJ per RFLOP rather than a 2021 normalization.
    # iota is the IT-electricity intensity; the regional facility multiplier
    # m_path carries power usage effectiveness, so gamma = iota x M_r.
    IOTA_REF = {
        "training": AC.GAMMA0 / AC.PUE_REF_US,
        # same accelerator fleet, but LBNL 2024 active time is 0.40 for inference
        # vs 0.80 for training; the idle term does not cancel, so inference
        # electricity per delivered RFLOP is 1.33x training (audited 2026-08-19)
        "inference": AC.GAMMA0 * AC.INFERENCE_GAMMA_RATIO / AC.PUE_REF_US,
        # 2026-08-26 FIX (external review): GAMMA_CONV0 = 0.288 is defined at
        # the 2021 WORLD overhead M_GLOBAL[2021]=1.4958 (=1.496/(0.551x9.44));
        # dividing by the legacy 1.55 left the reassembled coefficient 3.5% low.
        "conventional": AC.GAMMA_CONV0 / AC.M_GLOBAL[2021],
    }
    iota0 = {service: IOTA_REF[service] for service in ALL_SERVICES}
    production = {
        service: {
            region: service_it[service][region] / iota0[service]
            for region in regions
        }
        for service in ALL_SERVICES
    }
    # Output is now in RFLOP, so the world total is a physical quantity
    # rather than one. What must hold is the accounting identity that the
    # base-year electricity of each service is recovered by multiplying
    # regional output by the regional intensity.
    for service in ALL_SERVICES:
        recovered = sum(
            production[service][region] * iota0[service] * m_path[2021][region]
            for region in regions
        )
        assert abs(recovered - sum(service_facility[service].values())) < 1e-9, (
            f"{service}: output x intensity does not recover base-year electricity"
        )

    benchmark = read_benchmark_history()
    hardware = read_hardware_history()
    world_facility = {
        service: sum(service_facility[service].values())
        for service in ALL_SERVICES
    }

    write_service_map()
    benchmark_paths, _ = write_production_inputs(
        benchmark, hardware, iota0, world_facility
    )
    write_production_structure()
    write_trade_structure()

    write_csv(
        os.path.join(ENE, "pue_R.csv"),
        [
            "File: pue_R.csv",
            "Title: Regional facility-overhead multiplier M",
            "Units: dimensionless facility electricity / IT electricity",
            "Source: Uptime regional PUE signal normalized to IEA/LBNL world M "
            "in 2021 and 2025; after 2025 approaches 1.10 with tau=20 years.",
        ],
        "cinn",
        ["region", "year", "pue_survey", "M"],
        [
            [
                region, year, AC.pue_of(region), sig(m_path[year][region])
            ]
            for region in regions for year in MODEL_YEARS
        ],
    )

    write_csv(
        os.path.join(ENE, "datacenter_elec_EJ_R_Yh.csv"),
        [
            "File: datacenter_elec_EJ_R_Yh.csv",
            "Title: 2021 total data-center facility electricity",
            "Units: EJ facility electricity",
            "Source: restricted BNEF regional shares rescaled to audited "
            f"{AC.E_DC_GLOBAL_TWH[2021]:.2f} TWh world level.",
        ],
        "cn",
        ["region", "2021"],
        [[region, sig(targets[2021][region])] for region in regions],
    )
    conv_total = sum(conv_facility.values())
    write_csv(
        os.path.join(ENE, "datacenter_convshare_R.csv"),
        [
            "File: datacenter_convshare_R.csv",
            "Title: Regional allocation of conventional data-center electricity",
            "Units: share, sums to one",
        ],
        "cn",
        ["region", "convshare"],
        [[region, sig(conv_facility[region] / conv_total)] for region in regions],
    )
    write_csv(
        os.path.join(ENE, "ai_share_fAI_R_Y.csv"),
        [
            "File: ai_share_fAI_R_Y.csv",
            "Title: AI share of regional data-center facility electricity",
            "Units: share",
            "Source: 2021 total AI level allocated with the date-consistent "
            "terminal-phase Epoch facility-power proxy; "
            "2030 is a bounded structural ramp used only for compatibility.",
        ],
        "cnn",
        ["region", "2021", "2030"],
        [
            [
                region,
                sig(ai_facility[region] / targets[2021][region]),
                sig(
                    min(
                        FAI_CAP,
                        ai_facility[region] / targets[2021][region]
                        * FAI_GROWTH_TO_2030,
                    )
                ),
            ]
            for region in regions
        ],
    )

    service_share_rows = []
    for year in (2021, 2025):
        for service in AI_SERVICES:
            facility = (
                AC.E_AI_GLOBAL_TWH[year]
                * AC.AI_ELECTRICITY_SHARE[year][service]
                / AC.TWH_PER_EJ
            )
            it_electricity = facility / AC.M_GLOBAL[year]
            service_index = (
                it_electricity * benchmark[service][year] / iota0[service]
            )
            service_share_rows.append(
                [
                    service, year,
                    AC.AI_ELECTRICITY_SHARE[year][service],
                    sig(service_index),
                ]
            )
    write_csv(
        os.path.join(ENE, "ai_service_electricity_share_Y.csv"),
        [
            "File: ai_service_electricity_share_Y.csv",
            "Title: AI facility-electricity allocation and implied service index",
            "Units: share; TSU or ISU index with world 2021=1",
            "Source: LBNL/Omdia workload allocation and audited benchmark B.",
        ],
        "cinn",
        ["service", "year", "electricity.share", "world.service.index"],
        service_share_rows,
    )

    # 2021 consumption geography = production geography (user ruling
    # 2026-08-17). The only base-year observation is regional data center
    # electricity; compute is backed out of it, then split into
    # conventional and AI and again into training and inference. There is
    # no independent measurement of where that compute is consumed, so a
    # separate demand prior would manufacture trade that nobody observed.
    # Setting consumption equal to production leaves the base year with no
    # cross-border flow, and trade emerges only as the model diverges.
    consumption = {
        service: dict(production[service]) for service in AI_SERVICES
    }
    trade_rows = []
    for service in AI_SERVICES:
        # consumption equals production region by region (base year has no
        # observed trade), so the world total is the physical service output
        assert abs(sum(consumption[service].values())
                   - sum(production[service].values())) < 1e-12
        for region in regions:
            produced = production[service][region]
            consumed = consumption[service][region]
            trade_rows.append(
                [
                    service, region, sig(produced), sig(consumed),
                    sig(max(produced - consumed, 0)),
                    sig(max(consumed - produced, 0)),
                    sig(min(produced, consumed)),
                ]
            )
    write_csv(
        os.path.join(ENE, "datacenter_tradebalance_R_Y.csv"),
        [
            "File: datacenter_tradebalance_R_Y.csv",
            "Title: Constructed 2021 service-specific AI trade balance",
            "Units: TSU for training rows; ISU for inference rows",
            "Source: each service production and consumption sums separately "
            "to one. Values are an accounting initialization, not observed trade.",
        ],
        "ccnnnnn",
        [
            "service", "region", "production", "consumption",
            "exports", "imports", "domestic",
        ],
        trade_rows,
    )

    print("Generated service-specific GCAM inputs.")
    for service in ALL_SERVICES:
        b25 = benchmark_paths[service][2025]
        print(
            f"{service}: unit={AC.SERVICE_UNIT[service]}, "
            f"world_2021=1, iota_2021={iota0[service]:.8g}, "
            f"B_2025/B_2021={b25:.6g}"
        )
    print(
        "2021 facility electricity: "
        f"total={sum(targets[2021].values()) * AC.TWH_PER_EJ:.6f} TWh, "
        f"AI={sum(ai_facility.values()) * AC.TWH_PER_EJ:.6f} TWh"
    )


if __name__ == "__main__":
    main()
