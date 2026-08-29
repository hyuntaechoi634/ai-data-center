#!/usr/bin/env python
"""Fig. 6 | Regional concentration of data-centre electricity, water and compute trade in 2050.

Layout (2 rows x 3 columns; ONE COLUMN PER QUANTITY, structure by POSITION):
  columns  1 electricity | 2 water consumption | 3 water withdrawal
  (the net-compute-trade column was removed 2026-07-31; trade goes to the SI)

  ROW 1 (a-d) = the spatial view. World choropleth of the 2050 amount in the upper-bound
      cell (High demand x Low efficiency, reference), Robinson projection.
      a-c are burden maps and share ONE sequential ramp (light = small, dark = large); each
      colour scale runs from zero to a ROUND ceiling just above that quantity's maximum,
      with round ticks. Consumption and withdrawal keep separate numeric scales because
      withdrawal is roughly three times consumption and one shared scale would flatten the
      consumption map to near-white everywhere and destroy the spatial pattern.
      d is the only SIGNED quantity in the figure and carries the trade argument: AI compute
      is a traded good, so the electricity and water burden settles where compute is
      PRODUCED, which need not be where it is used. Diverging red <-> blue through white at
      zero, with the limits rounded outward from the data to clean values.

  ROW 2 (d-f) = the full factorial SCENARIO SET, shown as structured points, not boxes
      (a box over 18 designed cases quotes quartiles that are not meaningful statistics).
      One horizontal row per reporting region around an INVISIBLE CENTERLINE:
        - SIX CIRCLES per row = 3 demand levels x 2 policies.
        - policy = VERTICAL DODGE + FILL: reference sits slightly ABOVE the centerline as
          a SOLID circle in the region colour; net-zero CO2 by 2050 sits slightly BELOW as
          an OPEN circle (white face, region-colour edge). Policy reads vertically,
          demand horizontally.
        - demand = CIRCLE SIZE ladder (small = Low, medium = Medium, large = High).
          Circles only; squares and triangles are reserved for efficiency in fig02e.
        - efficiency = a thin WHISKER in the region colour through each circle, spanning
          the Low-to-High efficiency range; the circle sits at the Medium-efficiency value
          (same whisker grammar as fig02e).
        - the CALIBRATED 2025 SHARE = one grey diamond ON the centerline at its own
          x-position, so the 2025-to-2050 shift reads as horizontal distance.
      The region NAME is written at the right end of its own row in that row's colour, so
      there is no legend and no y-axis tick label. Regions are ordered by panel d and hold
      the SAME row in all three panels so the eye can read across. A mini key drawn once
      under the row explains the non-standard encoding (house rule).
      d-f plot the region's 2050 WITHIN-REGION SHARE (data centres as a percentage of that
      region's own total electricity / water consumption / water withdrawal). d has its own
      x-scale; e and f share one tighter water scale (the sanctioned linear zoom), because
      one common 0-to-50% axis flattened every water row into a cluster at the origin.

"Data centre" = AI compute + conventional compute.

Current CSV names are `D{demand}_E{efficiency}`. Legacy aliases are created
only inside this plotting script to preserve the established panel layout.

The 12 reporting regions: United States, China, Republic of Korea, Pacific OECD, Europe,
Canada, Latin America, South Asia, Southeast Asia, Middle East, Africa, Reforming
economies. Republic of Korea and Canada are standalone GCAM-32 regions and are named as
such; Pacific OECD = Japan + Australia + New Zealand; Taiwan joins Southeast Asia.

All quantities are recomputed at GCAM-32 granularity from the unmodified result files and
re-aggregated to the 12 reporting regions:
  data centre electricity (TWh) = AI electricity (v7_regional.csv, ai_elec_TWh)
    + conventional-compute electricity (fig_region_elec_dc_v3.csv, conv_elec_TWh)
  regional total electricity (denominator) = fig_region_elec_dc_v3.csv total_elec_TWh
  data centre water footprint (km3) = direct cooling + indirect generation water
    (fig_water_footprint.csv, tot_cons / tot_withdr)
  regional total water (denominator) = the matching scenario and policy in
    v7_region_total_water.csv (year 2050)
  net AI-service trade (%) = (fixed-weight service-index output - use) / use x 100
    (v7_regional.csv, year 2050; 2021 Training/Inference weights 0.425/0.575)

EVERY axis limit and colour limit below is derived from the data at run time and then
rounded OUTWARD to clean values, so no scale endpoint is a raw data value.
"""
import os
import sys
import warnings
import urllib.request

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import matplotlib.patches as mpatches
from matplotlib import cm, colors
from matplotlib.ticker import FuncFormatter, MultipleLocator
import geopandas as gpd
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "figures", "helpers"))
import gcam_style as gs
from _registry import UPPER_BOUND
OUT = os.path.dirname(os.path.abspath(__file__))
import os as _os
D = _os.environ.get(
    "FIG_DATA_DIR", os.path.join(ROOT, "results/derived/figure-data"))
CACHE = os.path.join(ROOT, "figures", "source-data", "ne_110m_admin_0_countries.zip")
if not os.path.exists(CACHE):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    urllib.request.urlretrieve(
        "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip", CACHE)

YEAR = 2050

# ---------------------------------------------------------------------------------------
# DISPLAY RENAME (2026-07-13). CSVs keep the internal names; only labels change.
# ---------------------------------------------------------------------------------------
DEMAND_NAME = {"Low": "Low", "Medium": "Medium", "High": "High",
               "Constant": "Constant"}
EFF_NAME = {
    "": "High efficiency",
    "medeff": "Medium efficiency",
    "loweff": "Low efficiency",
}
POLICY_NAME = {"ref": "reference", "nz2050co2": "net-zero CO$_2$ by 2050"}


def cell_label(cell):
    """'High_medeff' -> 'High demand, Medium efficiency'."""
    dem, _, eff = cell.partition("_")
    return f"{DEMAND_NAME[dem]} demand, {EFF_NAME[eff]}"


# the 18 scenario cases the box spans: 3 demand x 3 efficiency x 2 policy
DEMANDS = ["Low", "Medium", "High"]
ALLCELLS = (
    DEMANDS
    + [f"{d}_medeff" for d in DEMANDS]
    + [f"{d}_loweff" for d in DEMANDS]
)
POLICIES = ["ref", "nz2050co2"]
N_CASES = len(ALLCELLS) * len(POLICIES)


def legacy_cell(name):
    """Internal scenario id -> legacy display cell. In the v3 tables the demand
    levels are already Low, Medium and High, so no remapping is needed."""
    if not str(name).startswith("D") or "_E" not in str(name):
        return name
    demand, efficiency = str(name)[1:].split("_E", 1)
    suffix = {"High": "", "Medium": "_medeff", "Low": "_loweff"}[efficiency]
    return demand + suffix

# --- GCAM-32 region -> 12 reporting regions ----------------------------------------
RMAP = {"USA": "United States", "China": "China", "Canada": "Canada",
        "EU-12": "Europe", "EU-15": "Europe", "Europe_Eastern": "Europe",
        "Europe_Non_EU": "Europe", "European Free Trade Association": "Europe",
        "Argentina": "Latin America", "Brazil": "Latin America",
        "Central America and Caribbean": "Latin America", "Colombia": "Latin America",
        "Mexico": "Latin America", "South America_Northern": "Latin America",
        "South America_Southern": "Latin America",
        "Africa_Eastern": "Africa", "Africa_Northern": "Africa", "Africa_Southern": "Africa",
        "Africa_Western": "Africa", "South Africa": "Africa",
        "Middle East": "Middle East", "India": "South Asia", "Pakistan": "South Asia",
        "South Asia": "South Asia",
        "Japan": "Pacific OECD", "South Korea": "Republic of Korea",
        "Australia_NZ": "Pacific OECD", "Taiwan": "Southeast Asia",
        "Russia": "Reforming economies", "Central Asia": "Reforming economies",
        "Ukraine": "Reforming economies",
        "Indonesia": "Southeast Asia", "Southeast Asia": "Southeast Asia"}
# user ruling 2026-08-24: report the 32 GCAM regions directly, no
# aggregation — the 12-region map above is kept for reference only
# Final regional layout: bars aggregate to 12 reporting regions,
# maps stay at GCAM-32 (see sc32 below)
# RMAP = {k: k for k in RMAP}
DISP = {"USA": "United States",
        "European Free Trade Association": "EFTA",
        "South Korea": "Republic of Korea"}
def rdisp(r):
    return DISP.get(r, r.replace("_", " "))

# country geometry -> GCAM-32 region -> 12 reporting regions, dissolved (Robinson).
world = gpd.read_file(f"zip://{CACHE}")
world["ISO3"] = world["ISO_A3_EH"].where(world["ISO_A3_EH"] != "-99", world["ISO_A3"])
iso = pd.read_csv(f"{ROOT}/figures/source-data/iso_GCAM_regID.csv",
                  comment="#")
nm = pd.read_csv(f"{ROOT}/figures/source-data/GCAM_region_names.csv",
                 comment="#")
iso["iso_u"] = iso.iso.str.upper()
c2r = iso.merge(nm, on="GCAM_region_ID")[["iso_u", "region"]]
world = world.merge(c2r, left_on="ISO3", right_on="iso_u", how="left")
world["RR"] = world.region
world = world[world.NAME != "Antarctica"].copy()
world["geometry"] = world.geometry.buffer(0)
world = gpd.clip(world, box(-179.99, -60.0, 179.99, 85.0))   # NCC-style frame band
world = world[~world.geometry.is_empty & world.geometry.notna()].copy()
ROBIN = "+proj=robin +lon_0=0 +datum=WGS84 +units=m +no_defs"
EQEARTH = "+proj=eqearth +lon_0=0 +datum=WGS84 +units=m +no_defs"
try:
    ctry = world[["ISO3", "NAME", "RR", "geometry"]].to_crs(ROBIN)
except Exception:
    ctry = world[["ISO3", "NAME", "RR", "geometry"]].to_crs(EQEARTH)
reg = (world[world.RR.notna()][["RR", "geometry"]].dissolve(by="RR").reset_index()
       .rename(columns={"RR": "region"}).to_crs(ctry.crs))

# ============================ recompute 12-region quantities ============================
ai = pd.read_csv(f"{D}/v7_regional.csv")   # v3: every demand level
ai["scenario"] = ai["scenario"].map(legacy_cell)
ai = ai[ai.year == YEAR][[
    "scenario", "policy", "region", "ai_elec_TWh",
    "ai_service_index_out", "ai_service_index_use",
]]
tot = pd.read_csv(f"{D}/fig_region_elec_dc_v3.csv")
tot["scenario"] = tot["scenario"].map(legacy_cell)
tot = tot[tot.year == YEAR]
el = tot.merge(ai, on=["scenario", "policy", "region"], how="left")
for c in ("ai_elec_TWh", "ai_service_index_out", "ai_service_index_use"):
    el[c] = el[c].fillna(0.0)
el["dc_elec_TWh"] = el.ai_elec_TWh + el.conv_elec_TWh
el["RR"] = el.region.map(RMAP)
elr = (el.groupby(["scenario", "policy", "RR"])
       .agg(dc_elec_TWh=("dc_elec_TWh", "sum"), _tot=("total_elec_TWh", "sum"),
            c_out=("ai_service_index_out", "sum"),
            c_use=("ai_service_index_use", "sum"))
       .reset_index())
elr["dc_elec_share"] = elr.dc_elec_TWh / elr._tot * 100.0
# NET AI-SERVICE TRADE. Training and Inference remain in separate normalized
# service units upstream. The regional aggregate is their fixed-2021-weight
# volume index (0.425/0.575), not a physical addition of TSU and ISU.
elr["net_trade_abs"] = elr.c_out - elr.c_use
elr["net_trade_pct"] = np.where(elr.c_use > 0,
                                (elr.c_out - elr.c_use) / elr.c_use.replace(0, np.nan) * 100.0,
                                np.nan)

fp = pd.read_csv(f"{D}/fig_water_footprint.csv")
fp["scenario"] = fp["scenario"].map(legacy_cell)
fp = fp[fp.year == YEAR].copy()
fp["RR"] = fp.region.map(RMAP)
fwr = (fp.groupby(["scenario", "policy", "RR"])
       .agg(dc_wcons_km3=("tot_cons", "sum"), dc_wwithdr_km3=("tot_withdr", "sum"))
       .reset_index())
tw = pd.read_csv(f"{D}/v7_region_total_water.csv")
tw = tw[tw.year == YEAR].copy()
tw["scenario"] = tw["scenario"].map(legacy_cell)
tw["RR"] = tw.region.map(RMAP)
twr = (tw.groupby(["scenario", "policy", "RR"])
       .agg(C=("total_water_consumption_km3", "sum"),
            W=("total_water_withdrawal_km3", "sum")).reset_index())
fwr = fwr.merge(twr, on=["scenario", "policy", "RR"], how="left",
                validate="one_to_one")
fwr["dc_wcons_share"] = fwr.dc_wcons_km3 / fwr.C * 100.0
fwr["dc_wwithdr_share"] = fwr.dc_wwithdr_km3 / fwr.W * 100.0

sc = (elr.merge(fwr.drop(columns=["C", "W"]), on=["scenario", "policy", "RR"], how="inner")
      .rename(columns={"RR": "region"}))
sc = sc[sc.scenario.isin(ALLCELLS) & sc.policy.isin(POLICIES)].copy()
# ---- 32-region share frame for the map panels ----
_el32 = el.copy()
_el32["dc_elec_share"] = _el32.dc_elec_TWh / _el32.total_elec_TWh * 100.0
_fp32 = fp.merge(tw[["scenario", "policy", "region",
                     "total_water_consumption_km3", "total_water_withdrawal_km3"]],
                 on=["scenario", "policy", "region"], how="left")
_fp32["dc_wcons_share"] = _fp32.tot_cons / _fp32.total_water_consumption_km3 * 100.0
_fp32["dc_wwithdr_share"] = _fp32.tot_withdr / _fp32.total_water_withdrawal_km3 * 100.0
_fp32 = _fp32.rename(columns={"tot_cons": "dc_wcons_km3", "tot_withdr": "dc_wwithdr_km3"})
sc32 = (_el32[["scenario", "policy", "region", "dc_elec_TWh", "dc_elec_share"]]
        .merge(_fp32[["scenario", "policy", "region", "dc_wcons_km3", "dc_wwithdr_km3",
                      "dc_wcons_share", "dc_wwithdr_share"]],
               on=["scenario", "policy", "region"], how="inner"))
sc32 = sc32[sc32.scenario.isin(ALLCELLS) & sc32.policy.isin(POLICIES)].copy()
_n = sc.groupby("region").size()
assert set(_n) == {N_CASES}, f"expected {N_CASES} cases per region, got {sorted(set(_n))}"

# ---- 2025 baseline (calibrated, common to all scenarios) ----
_b_ai = pd.read_csv(f"{D}/v7_regional.csv")
_b_ai = _b_ai[(_b_ai.scenario == "DLow_EHigh") & (_b_ai.policy == "ref")
              & (_b_ai.year == 2025)]
_b_tot = pd.read_csv(f"{D}/fig_region_elec_dc_v3.csv")
_b_tot = _b_tot[(_b_tot.scenario == "DLow_EHigh") & (_b_tot.policy == "ref")
                & (_b_tot.year == 2025)]
_b_el = _b_tot.merge(_b_ai[["region", "ai_elec_TWh"]], on="region",
                     how="left").fillna({"ai_elec_TWh": 0.0})
_b_el["dc"] = _b_el.ai_elec_TWh + _b_el.conv_elec_TWh
_b_el["RR"] = _b_el.region.map(RMAP)
_b_elr = _b_el.groupby("RR").agg(dc=("dc", "sum"),
                                 tot=("total_elec_TWh", "sum"))
_b_fp = pd.read_csv(f"{D}/fig_water_footprint.csv")
_b_fp = _b_fp[(_b_fp.scenario == "DLow_EHigh") & (_b_fp.policy == "ref")
              & (_b_fp.year == 2025)].copy()
_b_fp["RR"] = _b_fp.region.map(RMAP)
_b_fpr = _b_fp.groupby("RR").agg(c=("tot_cons", "sum"),
                                 w=("tot_withdr", "sum"))
_b_tw = pd.read_csv(f"{D}/v7_region_total_water.csv")
_b_tw = _b_tw[(_b_tw.scenario == "DLow_EHigh")
              & (_b_tw.policy == "ref") & (_b_tw.year == 2025)].copy()
_b_tw["RR"] = _b_tw.region.map(RMAP)
_b_twr = _b_tw.groupby("RR").agg(C=("total_water_consumption_km3", "sum"),
                                 W=("total_water_withdrawal_km3", "sum"))
BASE25 = {
    "dc_elec_share": (100.0 * _b_elr.dc / _b_elr.tot).to_dict(),
    "dc_wcons_share": (100.0 * _b_fpr.c / _b_twr.C).to_dict(),
    "dc_wwithdr_share": (100.0 * _b_fpr.w / _b_twr.W).to_dict(),
}
W25 = {"dc_elec_TWh": float(_b_elr.dc.sum()),
       "dc_wcons_km3": float(_b_fpr.c.sum()),
       "dc_wwithdr_km3": float(_b_fpr.w.sum())}

# mapped scenario = the policy-relevant High-demand case with Medium
# efficiency under net-zero CO2 by 2050 (user ruling 2026-07-31; the former
# High x Low-efficiency x reference upper-edge maps move to the SI as an
# upper-burden sensitivity).
MAP_CELL = "High_medeff"
mp = sc32[(sc32.scenario == MAP_CELL) & (sc32.policy == "nz2050co2")].copy()
MAP_TAG = f"{cell_label(MAP_CELL)}, {POLICY_NAME['nz2050co2']}"

REGIONS = sorted(sc.region.unique())

# SHARED region colour key keyed BY NAME: the same region carries the same hue in every
# panel, so the name written on one row also identifies that region on the maps. Okabe-Ito
# colour-blind-safe set, extended with four well-separated Tol/Brewer hues.
# 32 rows cannot carry 32 distinguishable hues; the rows go neutral and the
# row label alone identifies the region (2026-08-24)
from collections import defaultdict
RCOL = defaultdict(lambda: "0.25")

NICE = (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def _nice_ceil(v):
    if v <= 0:
        return 1.0
    k = 10.0 ** np.floor(np.log10(v))
    for m in NICE:
        if v <= m * k + 1e-9:
            return m * k
    return 10.0 * k


def _trunc(name, lo=0.18, hi=1.0, n=256):
    base = plt.get_cmap(name)
    return colors.LinearSegmentedColormap.from_list(name + "_t", base(np.linspace(lo, hi, n)))


BURDEN = _trunc("magma_r", lo=0.02, hi=0.90)   # one ramp for the three burden maps
TRADE = plt.get_cmap("RdBu")                   # the one signed quantity

# ---------------------------------------------------------------- panel specifications --
MAPS = [
    dict(let="a", col="dc_elec_TWh", kind="seq", unit="TWh",
         title=f"Data center electricity, {YEAR}", cblab="TWh", comma=True),
    dict(let="b", col="dc_wcons_km3", kind="seq", unit="km$^3$",
         title=f"Water consumption, {YEAR}", cblab="", comma=False),
    dict(let="c", col="dc_wwithdr_km3", kind="seq", unit="km$^3$",
         title=f"Water withdrawal, {YEAR}", cblab="", comma=False),
]
SUB_SHARE = f"% of the region's own total, {YEAR}"
ROWS = [
    dict(let="d", col="dc_elec_share", share=True, grp="elec", sub=SUB_SHARE,
         title="Data center share of electricity"),
    dict(let="e", col="dc_wcons_share", share=True, grp="water", sub=SUB_SHARE,
         title="Share of water consumption"),
    dict(let="f", col="dc_wwithdr_share", share=True, grp="water", sub=SUB_SHARE,
         title="Share of water withdrawal"),
]

# ---- DERIVED limits ----
for M in MAPS:
    v = mp[M["col"]].dropna()
    if M["kind"] == "seq":
        M["vmin"], M["vmax"] = 0.0, _nice_ceil(float(v.max()))  # round ceiling above the max
        M["top"] = mp.loc[v.idxmax(), "region"]
        _cnus = mp[mp.region.isin(["China", "USA"])][M["col"]].sum()
        M["cnus"] = _cnus / mp[M["col"]].sum() * 100.0
    else:
        M["vmin"] = -_nice_ceil(abs(float(v.min())))
        M["vmax"] = _nice_ceil(float(v.max()))
        assert M["vmin"] < 0 < M["vmax"]
        M["cnus"] = None

# TWO x-scales for the three share panels: electricity (d) on its own scale, the two
# water panels (e, f) on one shared tighter scale. The water shares peak near 25% while
# South Asia and Africa sit below 0.6%; one 0-to-50% axis across all three panels
# flattened every water row into an unreadable cluster at the axis origin, so the water
# pair takes the sanctioned x-axis zoom (linear, never log) while e and f stay mutually
# comparable, which is the comparison that matters within the water pair.
GRP_HI = {grp: _nice_ceil(max(sc[R["col"]].max() for R in ROWS if R["grp"] == grp))
          for grp in ("elec", "water")}
# a small NEGATIVE left data margin keeps every glyph of the near-zero rows off the
# y-spine (the 0% tick stays; the data floor stays 0)
XMARG = 0.015
for R in ROWS:
    R["hi"] = GRP_HI[R["grp"]]
    R["lo"] = -XMARG * R["hi"]
    R["step"] = _nice_ceil(R["hi"] / 2.6)

# (map callouts removed 2026-08-24 — regions are read from the colour scale)

gs.apply_rc()
SCALE = 1.60
import matplotlib as _mpl
for _k in ("font.size", "xtick.labelsize", "ytick.labelsize",
           "legend.fontsize", "axes.labelsize", "axes.titlesize"):
    try:
        _mpl.rcParams[_k] = _mpl.rcParams[_k] * SCALE
    except Exception:
        pass

# ======================================================================
# MAIN FIGURE (2026-08-24 ruling v2): a-c = share maps under the
# REFERENCE power system (one colour scale family per quantity);
# d-f = per-region rails simplified to the three demand levels at
# Medium efficiency (reference), one coloured | per demand.
# The full 18-scenario rails remain the SI companion figure.
# ======================================================================
def fmt(v, comma):
    if comma:
        return f"{v:,.0f}"
    if v == 0:
        return "0"
    return f"{v:,.0f}" if abs(v - round(v)) < 0.05 else f"{v:,.1f}"


def pct(v):
    s = f"{v:,.0f}%"
    return s.replace("-", "\u2212")


C_REF, C_NZ = "#b3531d", "#1f7a8c"
CM_ELEC = BURDEN                                   # warm (matches fig set)
CM_CONS = _trunc("YlGnBu", 0.08, 1.0)              # water consumption
CM_WITH = _trunc("BuPu", 0.12, 1.0)                # water withdrawal
SHARE_COLS = [
    dict(col="dc_elec_share", title="Data center share of electricity",
         cmap=CM_ELEC),
    dict(col="dc_wcons_share", title="Share of water consumption",
         cmap=CM_CONS),
    dict(col="dc_wwithdr_share", title="Share of water withdrawal",
         cmap=CM_WITH),
]
mp_ref = sc32[(sc32.scenario == MAP_CELL) & (sc32.policy == "ref")].set_index("region")
for C in SHARE_COLS:   # ONE scale per quantity, from the mapped case
    C["vmax"] = _nice_ceil(float(mp_ref[C["col"]].max()))
# user ruling 2026-08-24: cap the consumption scale at 30% and the
# withdrawal scale at 20% — only EFTA exceeds them and saturates into
# the colourbar's overflow arrow
SHARE_COLS[1]["vmax"] = 30.0
SHARE_COLS[2]["vmax"] = 20.0

DEM3 = ["Low", "Medium", "High"]
# demand ramps unified with fig03a: reference = warm ramp, net-zero = teal ramp
DEMCOL = {"Low": "#e0946a", "Medium": "#c2601f", "High": "#7d3506"}
NZCOL = {"Low": "#83b6c0", "Medium": "#3f93a4", "High": "#14596b"}

fig = plt.figure(figsize=(18.2, 16.8))
gsm = fig.add_gridspec(2, 3, height_ratios=[1.0, 2.55],
                       left=0.052, right=0.988, top=0.955, bottom=0.105,
                       hspace=0.22, wspace=0.13)

from pyproj import Transformer
_TR = Transformer.from_crs("EPSG:4326", ctry.crs, always_xy=True)
LAT0, LAT1 = -60.0, 85.0
_fr_lon = np.r_[np.linspace(-180, 180, 361), np.full(50, 180.0),
                np.linspace(180, -180, 361), np.full(50, -180.0)]
_fr_lat = np.r_[np.full(361, LAT1), np.linspace(LAT1, LAT0, 50),
                np.full(361, LAT0), np.linspace(LAT0, LAT1, 50)]
_fx, _fy = _TR.transform(_fr_lon, _fr_lat)

for ci, C in enumerate(SHARE_COLS):
    ax = fig.add_subplot(gsm[0, ci])
    ax.set_axis_off()
    ax.set_aspect("equal")
    norm = colors.Normalize(0.0, C["vmax"])
    vals = mp_ref[C["col"]].to_dict()
    cdat = ctry.copy()
    cdat["val"] = cdat.RR.map(vals)
    nod = cdat[cdat.val.isna()]
    have = cdat[cdat.val.notna()]
    if len(nod):
        nod.plot(ax=ax, color="#e2e2e2", edgecolor="white", linewidth=0.3,
                 zorder=1)
    have.plot(ax=ax, column="val", cmap=C["cmap"], norm=norm,
              edgecolor="white", linewidth=0.3, zorder=2)
    # NCC s41558-026-02724-8 Fig.2 furniture
    for latg in (-30, 0, 30, 60):
        _lo = np.linspace(-180, 180, 181)
        _x, _y = _TR.transform(_lo, np.full_like(_lo, float(latg)))
        ax.plot(_x, _y, color="0.78", lw=0.5, ls=(0, (2, 2)), zorder=0.5)
    for lng in (-120, -60, 0, 60, 120):
        _la = np.linspace(LAT0, LAT1, 100)
        _x, _y = _TR.transform(np.full_like(_la, float(lng)), _la)
        ax.plot(_x, _y, color="0.78", lw=0.5, ls=(0, (2, 2)), zorder=0.5)
    ax.plot(_fx, _fy, color="0.1", lw=1.0, zorder=6)
    if ci == 0:
        for latg in (60, 30, 0, -30, -60):
            _x, _y = _TR.transform(-180.0, float(latg))
            lab = ("0\u00b0" if latg == 0
                   else f"{abs(latg)}\u00b0 {'N' if latg > 0 else 'S'}")
            ax.annotate(lab, (_x, _y), xytext=(-4, 0),
                        textcoords="offset points", ha="right", va="center",
                        fontsize=7.6 * SCALE, color="0.25",
                        annotation_clip=False)
    for lng in (-120, -60, 0, 60, 120):
        _x, _y = _TR.transform(float(lng), LAT0)
        lab = ("0\u00b0" if lng == 0
               else f"{abs(lng)}\u00b0 {'W' if lng < 0 else 'E'}")
        ax.annotate(lab, (_x, _y), xytext=(0, -3),
                    textcoords="offset points", ha="center", va="top",
                    fontsize=7.6 * SCALE, color="0.25",
                    annotation_clip=False)
    ax.set_xlim(_fx.min() - 3e5, _fx.max() + 3e5)
    ax.set_ylim(_fy.min() - 3e5, _fy.max() + 3e5)
    C["ax"] = ax

# ------- d-f: all regions; filled bar = demand x efficiency range ----------
# (2026-08-24 ruling v3: filled bar spans ALL nine reference demand-by-
# efficiency cases; three coloured verticals mark the demand ladder at
# Medium efficiency; all 32 model regions are retained.)
XMARG = 0.015
NTOP = len(REGIONS)          # all 32 regions (user ruling 2026-08-24)
_val = sc.set_index(["region", "scenario", "policy"])
DIAMOND = dict(marker="D", ms=3.5, mfc="0.74", mec="0.38", mew=0.8)
HALO = [pe.withStroke(linewidth=2.0, foreground="white")]
RAILS = [dict(let="d", col="dc_elec_share", grp="elec",
              title="Data center share of electricity"),
         dict(let="e", col="dc_wcons_share", grp="water",
              title="Share of water consumption"),
         dict(let="f", col="dc_wwithdr_share", grp="water",
              title="Share of water withdrawal")]
CELLS9 = [f"{d}_loweff" for d in DEM3] + [f"{d}_medeff" for d in DEM3] + DEM3
for R in RAILS:
    v = _val[R["col"]]
    R["vs"] = {r: [float(v.loc[(r, f"{d}_medeff", "ref")]) for d in DEM3]
               for r in REGIONS}
    R["vsn"] = {r: [float(v.loc[(r, f"{d}_medeff", "nz2050co2")])
                    for d in DEM3] for r in REGIONS}
    R["rng"] = {r: [float(min(v.loc[(r, c, p)] for c in CELLS9
                              for p in POLICIES)),
                    float(max(v.loc[(r, c, p)] for c in CELLS9
                              for p in POLICIES))]
                for r in REGIONS}
    b25s = BASE25.get(R["col"], {})
    R["st"] = {r: dict(med=R["vs"][r][1],
                       hi=max(R["rng"][r][1],
                              b25s.get(r) if b25s.get(r) is not None else 0.0))
               for r in REGIONS}
GRP_HI = {g: _nice_ceil(max(R["st"][r]["hi"] for R in RAILS
                            if R["grp"] == g for r in REGIONS))
          for g in ("elec", "water")}
for ci, R in enumerate(RAILS):
    ax = fig.add_subplot(gsm[1, ci])
    # 2026-08-26 ruling: fixed axis ranges — electricity to 100%, water to 50%
    R["hi"] = 70.0 if R["grp"] == "elec" else 40.0
    R["lo"] = -XMARG * R["hi"]
    R["step"] = 10.0 if R["grp"] == "elec" else 5.0   # 2026-08-26 ruling: elec 10s to 70, water 5s to 40
    top = sorted(REGIONS, key=lambda r: R["st"][r]["med"], reverse=True)[:NTOP]
    order = list(reversed(top))          # largest ends up at the top row
    R["order"], R["ax"] = order, ax
    for i2, r in enumerate(order):
        rlo, rhi = R["rng"][r]
        ax.fill_between([rlo, rhi], i2 - 0.26, i2 + 0.26, color="0.86",
                        lw=0, zorder=2.5)
        for d, v in zip(DEM3, R["vs"][r]):       # reference: tick UP
            ax.plot([v, v], [i2, i2 + 0.32], color=DEMCOL[d], lw=2.0,
                    zorder=4, clip_on=False, solid_capstyle="butt")
        for d, v in zip(DEM3, R["vsn"][r]):      # net-zero: tick DOWN
            ax.plot([v, v], [i2 - 0.32, i2], color=NZCOL[d], lw=2.0,
                    zorder=4, clip_on=False, solid_capstyle="butt")
        b25 = BASE25.get(R["col"], {}).get(r)
        if b25 is not None:
            ax.plot(b25, i2, zorder=3.6, clip_on=False, path_effects=HALO,
                    **DIAMOND)
        R.setdefault("names", []).append(
            ax.annotate(rdisp(r), xy=(R["st"][r]["hi"], i2), xytext=(7, 0),
                        textcoords="offset points", ha="left", va="center",
                        fontsize=10.8 * SCALE, color="0.25", zorder=6))
    ax.set_ylim(-0.62, NTOP - 0.38)
    ax.set_xlim(R["lo"], R["hi"])
    ax.set_yticks([])
    ax.xaxis.set_major_locator(MultipleLocator(R["step"]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: pct(v)))
    ax.tick_params(axis="x", which="major",
                   labelsize=(9.3 if R["grp"] == "elec" else 11.0) * SCALE,
                   length=4, pad=5)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.spines["left"].set_position(("outward", 6))
    ax.spines["bottom"].set_position(("outward", 8))

# widen x ONLY until every name fits inside its panel (common per group)
# 2026-08-26 ruling: DISABLED — axes are fixed (elec 0-70, water 0-40) and the
# fixed headroom already holds every name
fig.canvas.draw()
rend = fig.canvas.get_renderer()
for _ in range(0):
    need = {"elec": 0.0, "water": 0.0}
    for R in RAILS:
        ab = R["ax"].get_window_extent(renderer=rend)
        px = max(t.get_window_extent(renderer=rend).x1 - (ab.x1 - 8)
                 for t in R["names"])
        if px > 0:
            need[R["grp"]] = max(need[R["grp"]],
                                 px / ab.width * (R["hi"] - R["lo"]))
    if max(need.values()) < 0.05:
        break
    for R in RAILS:
        R["hi"] += need[R["grp"]] * 1.02
        R["lo"] = -XMARG * R["hi"]
        R["ax"].set_xlim(R["lo"], R["hi"])
    fig.canvas.draw()
GRP_DMAX = {g: max(R["st"][r]["hi"] for R in RAILS if R["grp"] == g
                   for r in R["order"]) for g in ("elec", "water")}
for R in RAILS:
    ticks = np.arange(0.0, R["hi"] + 1e-9, R["step"])
    R["ax"].set_xticks(list(ticks))

# ---------------- furniture ----------------
fig.canvas.draw()
for ci, C in enumerate(SHARE_COLS):
    pos = C["ax"].get_position(original=False)
    fig.text(pos.x0 + pos.width / 2, pos.y1 + 0.009, C["title"],
             fontsize=12.5 * SCALE, color="0.12", ha="center", va="bottom")
    fig.text(pos.x0 - 0.010, pos.y1 + 0.009, "abc"[ci], fontsize=16 * SCALE,
             fontweight="bold", ha="left", va="bottom")
    sm = cm.ScalarMappable(norm=colors.Normalize(0.0, C["vmax"]),
                           cmap=C["cmap"])
    sm.set_array([])
    cw = 0.60 * pos.width
    cax = fig.add_axes([pos.x0 + (pos.width - cw) / 2, pos.y0 - 0.038,
                        cw, 0.0095])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal", extend="max")
    cb.outline.set_visible(True)
    cb.outline.set_linewidth(0.6)
    cb.outline.set_edgecolor("0.1")
    cb.set_ticks([0.0, C["vmax"] / 2.0, C["vmax"]])
    cb.ax.xaxis.set_major_formatter(
        FuncFormatter(lambda v, p: f"{v:g}%".replace("-", "\u2212")))
    cb.ax.tick_params(labelsize=10.0 * SCALE, length=2.5)
for ci, R in enumerate(RAILS):
    pos = R["ax"].get_position(original=False)
    fig.text(pos.x0 + pos.width / 2, pos.y1 + 0.006, R["title"],
             fontsize=12.5 * SCALE, color="0.12", ha="center", va="bottom")
    fig.text(pos.x0 - 0.012, pos.y1 + 0.006, R["let"], fontsize=16 * SCALE,
             fontweight="bold", ha="left", va="bottom")

# key: the three demand bars and the 2025 diamond
_p0 = RAILS[0]["ax"].get_position(original=False)
_p2 = RAILS[2]["ax"].get_position(original=False)
kax = fig.add_axes([_p0.x0, 0.012, _p2.x1 - _p0.x0, 0.048])
kax.set_xlim(0, 1)
kax.set_ylim(0, 1)
kax.set_axis_off()
KFS = 12.0 * SCALE
KY1, KY2 = 0.76, 0.24
# row 1: the filled bar and the demand colours (Medium efficiency)
_kx = 0.006
kax.fill_between([_kx, _kx + 0.050], KY1 - 0.16, KY1 + 0.16, color="0.86",
                 lw=0, clip_on=False)
kax.text(_kx + 0.057, KY1, "demand and efficiency range", ha="left",
         va="center", fontsize=KFS, color="0.25")
_kx += 0.335
for d, adv in (("Low", 0.130), ("Medium", 0.160), ("High", 0.135)):
    kax.plot([_kx, _kx], [KY1, KY1 + 0.20], color=DEMCOL[d], lw=2.2,
             clip_on=False, solid_capstyle="butt")
    kax.plot([_kx, _kx], [KY1 - 0.20, KY1], color=NZCOL[d], lw=2.2,
             clip_on=False, solid_capstyle="butt")
    kax.text(_kx + 0.008, KY1, f"{d} demand", ha="left", va="center",
             fontsize=KFS, color="0.25")
    _kx += adv
# row 2: policy = colour family (fig03a ramps) + tick direction; 2025 diamond
kax.plot([0.012, 0.012], [KY2, KY2 + 0.30], color=C_REF, lw=2.0,
         clip_on=False, solid_capstyle="butt")
kax.text(0.022, KY2 + 0.08, "tick up: reference", ha="left", va="center",
         fontsize=KFS, color="0.25")
kax.plot([0.190, 0.190], [KY2 - 0.14, KY2 + 0.16], color=C_NZ, lw=2.0,
         clip_on=False, solid_capstyle="butt")
kax.text(0.200, KY2 + 0.08, "tick down: net-zero CO$_2$ by 2050",
         ha="left", va="center", fontsize=KFS, color="0.25")
kax.plot(0.520, KY2 + 0.08, clip_on=False, path_effects=HALO,
         **dict(DIAMOND, ms=1.4 * DIAMOND["ms"]))
kax.text(0.533, KY2 + 0.08, "2025 share", ha="left", va="center",
         fontsize=KFS, color="0.25")

os.makedirs(OUT, exist_ok=True)
fig.savefig(f"{OUT}/figure-06.jpg", dpi=200)
print(f"WROTE {OUT}/figure-06.jpg")
print(" map scale maxima:", {C["col"]: C["vmax"] for C in SHARE_COLS})
