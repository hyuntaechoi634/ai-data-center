#!/usr/bin/env python
"""Build calibrated post-2025 demand scenarios and GCAM aeei inputs.

The dimensionless autonomous-demand shifter follows:

    g_chi(t) = chi_inf + (chi0 - chi_inf) * exp(-(t-2025)/TAU)                  [F5]
    chi(t)   = exp[chi_inf*d + (chi0-chi_inf)*TAU*(1-exp(-d/TAU))].

`chi0` is read from the central 2021-2025 conditional calibration in
`analysis/demand-axes`. Low, Medium, and High use persistence times of 7, 10,
and 13 years, respectively, with a zero long-run autonomous-growth rate. These
are structured scenario values rather than probability quantiles or three
independently fitted estimates.

Constant is the matched attribution scenario. Training and inference remain at
their 2025 autonomous-demand levels after 2025, while conventional computing
retains its common path. Constant is included in the deployed scenario fan.

Run through ``python3 regenerate.py``. It writes the deployed-name scratch
files that the orchestrator maps back to descriptive public filenames.
"""
import os, csv, math, importlib.util
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "inputs")
_acs = importlib.util.spec_from_file_location(
    "ai_constants", os.path.join(HERE, "ai_constants.py")
)
AC = importlib.util.module_from_spec(_acs); _acs.loader.exec_module(AC)
_scs = importlib.util.spec_from_file_location(
    "scenario_parameterization", os.path.join(HERE, "scenario_parameterization.py")
)
SC = importlib.util.module_from_spec(_scs); _scs.loader.exec_module(SC)
ENE = os.environ.get("AI_GCAMDATA_ENERGY_DIR")
OUTPUT_DIR = os.environ.get("AI_GENERATION_OUTPUT_DIR")
if not ENE or not OUTPUT_DIR:
    raise SystemExit(
        "Run generation/regenerate.py; scratch output directories were not set."
    )
DEMAND_OUT = INPUTS
DEMAND_CONFIG = INPUTS
YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
FUT_TAIL = [2060, 2070, 2080, 2090, 2100]          # inert post-2050 (model stops 2050); carry F5 rates

PRIMARY_SCENARIOS = ["Low", "Medium", "High"]
SCENARIOS = PRIMARY_SCENARIOS
FROZEN = "Constant"

def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

_summary = _read_csv(os.path.join(DEMAND_OUT, "demand-calibration-summary.csv"))
_central = {r["service"]: r for r in _summary if r["case"] == "central"}
assert set(_central) == {"training", "inference", "conv"}, set(_central)
CHI0 = {
    service: float(row["autonomous_log_growth_2021_2025_per_year"])
    for service, row in _central.items()
}
BETA = {
    service: float(row["beta"])
    for service, row in _central.items()
}
_price_assumptions = {
    row["service"]: row
    for row in _read_csv(os.path.join(DEMAND_CONFIG, "demand-price-assumptions.csv"))
}
assert set(_price_assumptions) == {"training", "inference", "conv"}, set(
    _price_assumptions
)
ELECTRICITY_COST_SHARE = {
    service: float(row["electricity_cost_share_2021"])
    for service, row in _price_assumptions.items()
}

_design = {
    r["scenario"]: r
    for r in _read_csv(os.path.join(DEMAND_CONFIG, "demand-scenario-design.csv"))
    if r["deployment_scope"] != "not_deployed"
}
assert set(_design) == set(SCENARIOS), set(_design)
TAU = {
    scenario: {
        "training": float(row["tau_training_years"]),
        "inference": float(row["tau_inference_years"]),
    }
    for scenario, row in _design.items()
}
FLOORS = {
    scenario: {
        "training": float(row["long_run_training_log_rate"]),
        "inference": float(row["long_run_inference_log_rate"]),
    }
    for scenario, row in _design.items()
}

_conv_design = _read_csv(
    os.path.join(DEMAND_CONFIG, "conventional-demand-scenario-parameters.csv")
)
_conv = next(row for row in _conv_design if row["service"] == "conv")
CHI0_CONV = CHI0["conv"]
TAU_CHI_CONV = float(_conv["tau_years"])
GINF_CONV = float(_conv["long_run_log_rate"])

# ---- the F5 path (class grammar; common history through 2025, chi(2025)=1) ----
def chi_f5(service, scenario, y):
    if scenario == FROZEN or y <= 2025:
        return 1.0
    g0, gi = CHI0[service], FLOORS[scenario][service]
    d = y - 2025; t = TAU[scenario][service]
    return math.exp(gi * d + (g0 - gi) * t * (1.0 - math.exp(-d / t)))

def chi_f5_conv(y):
    if y <= 2025:
        return 1.0
    d = y - 2025
    return math.exp(GINF_CONV * d + (CHI0_CONV - GINF_CONV) * TAU_CHI_CONV
                    * (1.0 - math.exp(-d / TAU_CHI_CONV)))

def _gdp_world_factors():
    """World GDP factors vs 2025, read DIRECTLY from the socioeconomics input the configs load
    (generation/inputs/world-socioeconomics-core.xml, nationalAccount/GDP by
    region and year)."""
    path = os.path.join(INPUTS, "world-socioeconomics-core.xml")
    import xml.etree.ElementTree as ET
    from collections import defaultdict
    world = defaultdict(float)
    for na in ET.parse(path).getroot().iter("nationalAccount"):
        g = na.find("GDP")
        if g is not None:
            world[int(na.get("year"))] += float(g.text)
    return {y: world[y] / world[2025] for y in YEARS}
GDP_WORLD = _gdp_world_factors()   # {2030: 1.140, 2035: 1.282, 2040: 1.421, 2045: 1.565, 2050: 1.713}

def _mapped_service(service):
    return "conventional" if service == "conv" else service


def _global_m(year):
    if year <= 2021:
        return AC.M_GLOBAL[2021]
    if year <= 2025:
        return AC.M_GLOBAL[2025]
    return AC.PUE_INF + (
        AC.M_GLOBAL[2025] - AC.PUE_INF
    ) * math.exp(-(year - 2025) / AC.TAU_PUE)


def _price_and_intensity(service, year, efficiency="Medium"):
    """Return 2021-normalized price and facility intensity.

    This is the same service-specific iota-M-H-cost map used by
    scenario_parameterization.py and the scenario-screen pipeline.
    """
    mapped = _mapped_service(service)
    good = SC.SERVICE_MAP[mapped]["producer"]
    iota = SC.iota_level(mapped, efficiency, year)
    iota_2021 = SC.IOTA_BASE[good][2021]
    intensity = iota * _global_m(year) / (iota_2021 * AC.M_GLOBAL[2021])
    # v3.2 (2026-08-27): the composite COST_BASE dict became the split
    # COST_SPLIT_BASE; cost_2021_composite() returns the same 2021 anchor
    # (sum of the three split rows = 0.447 / 0.595851 / 7.4 exactly).
    nonenergy = (
        SC.cost_level(mapped, efficiency, year)
        / SC.cost_2021_composite(mapped)
    )
    electricity_share = ELECTRICITY_COST_SHARE[service]
    price = (
        (1.0 - electricity_share) * nonenergy
        + electricity_share * intensity
    )
    return price, intensity


_BASE_2025 = {
    service: _price_and_intensity(service, 2025)
    for service in ("training", "inference", "conv")
}


def df_service(service, year):
    """Facility electricity relative to 2025 with autonomous demand frozen."""
    price, intensity = _price_and_intensity(service, year)
    price_2025, intensity_2025 = _BASE_2025[service]
    return (
        GDP_WORLD[year]
        * (price / price_2025) ** BETA[service]
        * (intensity / intensity_2025)
    )

def main():
    historical = _read_csv(os.path.join(DEMAND_OUT, "historical-service-inputs.csv"))
    E25 = {
        row["service"]: float(row["allocated_facility_electricity_TWh"])
        for row in historical
        if row["workload_case"] == "central_linear_lbnl"
        and int(row["year"]) == 2025
    }
    assert set(E25) == {"training", "inference", "conv"}, set(E25)
    E25_AI = E25["training"] + E25["inference"]
    E25_CONV = E25["conv"]
    # chi(2030) per service: F5 landing, spliced to the commitment target where one is declared.
    # Medium inference = pure F5 (gate-only). Training = 175-splice (Medium/High) / frozen mix (Low).
    chi30, splice_log = {}, {}
    for nm in SCENARIOS:                            # pure F5 decay - no 2030 level operator
        for s in ("training", "inference"):
            chi30[(s, nm)] = chi_f5(s, nm, 2030)
        e_f5 = {
            s: E25[s] * chi30[(s, nm)] * df_service(s, 2030)
            for s in ("training", "inference")
        }
        total = e_f5["training"] + e_f5["inference"]
        splice_log[nm] = {"training": 0.0, "inference": 0.0, "total_F5": total, "total": total}
    chi30[("conv", None)] = chi_f5_conv(2030)

    # analytic previews (pure-F5 landings; the pipeline validates, does not impose)
    print(f"{'':10s} tau  ginf(tr/inf) | 2030  |  E_AI: 2035  2040    2050 | s_inf30 | CAGR25-30")
    previews = {}
    for nm in SCENARIOS:
        def E_ai(y):
            grow = {s: chi_f5(s, nm, y) / chi_f5(s, nm, 2030) for s in ("training", "inference")}
            e_tr = (
                E25["training"] * df_service("training", y)
                * chi30[("training", nm)] * grow["training"]
            )
            e_in = (
                E25["inference"] * df_service("inference", y)
                * chi30[("inference", nm)] * grow["inference"]
            )
            return e_tr + e_in
        sl = splice_log[nm]
        previews[nm] = {y: E_ai(y) for y in (2030, 2035, 2040, 2050)}
        cagr = math.log(sl["total"] / E25_AI) / 5 * 100
        s_inf30 = (
            E25["inference"] * chi30[("inference", nm)]
            * df_service("inference", 2030) / sl["total"]
        )
        print(f"{nm:10s} {TAU[nm]['training']:>2.0f}/{TAU[nm]['inference']:<2.0f}  {FLOORS[nm]['training']*100:>3.0f}/{FLOORS[nm]['inference']*100:>4.1f}% | {sl['total']:5.0f} | "
              + "  ".join(f"{previews[nm][y]:6.0f}" for y in (2035, 2040, 2050))
              + f" | {s_inf30:.2f}  | {cagr:5.1f}%/yr"
              + ("  [>analog top 30.3 - REPORT]" if cagr > 30.3 else ""))
    constant_2030 = sum(
        E25[s] * df_service(s, 2030)
        for s in ("training", "inference")
    )
    constant_2050 = sum(
        E25[s] * df_service(s, 2050)
        for s in ("training", "inference")
    )
    print(
        f"Constant  chi=1: E 2030 {constant_2030:.0f} -> 2050 "
        f"{constant_2050:.0f} TWh (attribution ruler)"
    )
    e_c30 = E25_CONV * chi_f5_conv(2030) * df_service("conv", 2030)
    e_c50 = E25_CONV * chi_f5_conv(2050) * df_service("conv", 2050)
    print(f"conv       chi30={chi30[('conv', None)]:.3f} | 2030 {e_c30:.0f} -> 2050 {e_c50:.0f} TWh "
          f"(F5 g0={100*CHI0_CONV:.1f}%, tau={TAU_CHI_CONV:g}, ginf={100*GINF_CONV:.1f}%)")

    # 2025 rows: carry the fit-derived common values from the previous ref CSV (calibration seed)
    with open(os.path.join(ENE, "aeei_chi_compute_ref.csv")) as f:
        body = [ln for ln in f if not ln.lstrip().startswith("#") and ln.strip()]
    prev25 = {r["service"]: float(r["aeei"]) for r in csv.DictReader(body) if int(r["year"]) == 2025}
    assert set(prev25) == {"training", "inference", "conv"}, prev25

    # per-period aeei: chi ratio over the period = (1+aeei)^-(step); 2030 carries the splice via chi30,
    # 2035+ carry the F5 per-period rates (the kink removal - rates DECAY through the tail).
    rows = []
    for nm in SCENARIOS + [FROZEN]:
        for svc in ("training", "inference", "conv"):
            rows.append(dict(service=svc, scenario=nm, year=2025, aeei=prev25[svc]))
            if svc == "conv":
                a30 = round(chi_f5_conv(2030) ** (-1.0 / 5.0) - 1.0, 6)
                rows.append(dict(service=svc, scenario=nm, year=2030, aeei=a30))
                prev_y = 2030
                for y in YEARS[2:] + FUT_TAIL:
                    ratio = chi_f5_conv(y) / chi_f5_conv(prev_y)
                    rows.append(dict(service=svc, scenario=nm, year=y,
                                     aeei=round(ratio ** (-1.0 / (y - prev_y)) - 1.0, 6)))
                    prev_y = y
            elif nm == FROZEN:
                for y in YEARS[1:] + FUT_TAIL:
                    rows.append(dict(service=svc, scenario=nm, year=y, aeei=0.0))
            else:
                a30 = round(chi30[(svc, nm)] ** (-1.0 / 5.0) - 1.0, 6)
                rows.append(dict(service=svc, scenario=nm, year=2030, aeei=a30))
                prev_y = 2030
                for y in YEARS[2:] + FUT_TAIL:
                    ratio = chi_f5(svc, nm, y) / chi_f5(svc, nm, prev_y)
                    rows.append(dict(service=svc, scenario=nm, year=y,
                                     aeei=round(ratio ** (-1.0 / (y - prev_y)) - 1.0, 6)))
                    prev_y = y
    df = pd.DataFrame(rows).sort_values(["scenario", "service", "year"])

    def write(path, fname, title, d):
        with open(path, "w", newline="") as f:
            f.write(f"# File: {fname}\n# Title: {title}\n# Units: /yr (autonomous demand growth; negative = growth)\n")
            f.write("# Column types: ccin\n# ----------\n")
            d.to_csv(f, index=False)
    write(os.path.join(ENE, "aeei_chi_compute.csv"), "aeei_chi_compute.csv",
          "demand-axis aeei by service x scenario "
          "(Low/Medium/High/Constant) x year "
          "(calibrated g0, scenario-specific persistence and declared long-run floor)", df)
    write(os.path.join(ENE, "aeei_chi_compute_ref.csv"), "aeei_chi_compute_ref.csv",
          "demand-axis aeei (reference = Medium) by service x year (Design A)", df[df.scenario == "Medium"])
    pd.DataFrame([dict(scenario=nm, chi0_conv=CHI0_CONV,
                       chi0_train=CHI0["training"], chi0_inf=CHI0["inference"],
                       tau_train=TAU[nm]["training"], tau_inf=TAU[nm]["inference"],
                       floor_train=FLOORS[nm]["training"], floor_inf=FLOORS[nm]["inference"],
                       E2030_landing=round(splice_log[nm]["total_F5"], 1),
                       splice_train=round(splice_log[nm]["training"], 4),
                       splice_inf=round(splice_log[nm]["inference"], 4),
                       chi30_training=round(chi30[("training", nm)], 3),
                       chi30_inference=round(chi30[("inference", nm)], 3),
                       chi30_conv=round(chi30[("conv", None)], 3),
                       **{f"E{y}_preview": round(previews[nm][y], 1) for y in (2030, 2035, 2040, 2050)})
                  for nm in SCENARIOS]).to_csv(
                      os.path.join(OUTPUT_DIR, "demand-axis-parameters.csv"),
                      index=False,
                  )
    print("WROTE aeei_chi_compute[_ref].csv "
          "(Low/Medium/High/Constant) "
          "+ demand-axis-parameters.csv")

if __name__ == "__main__":
    main()
