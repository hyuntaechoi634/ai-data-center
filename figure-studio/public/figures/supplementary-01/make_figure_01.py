"""Supplementary demand-path figure (review request section 6.7, 2026-08-26).

Generates figures/supplementary_demand_paths_revised.jpg from the ACTIVE
central calibration and scenario design only:
  chi (2021-2025 annual residuals):
    analysis/demand-axes/data/derived/demand_calibration_annual.csv
    (falls back to the endpoint rate from demand_calibration_summary.csv)
  g_A,2025 and the ladder: demand_calibration_summary.csv (central) and
    analysis/demand-axes/config/scenario_design.csv (tau 7/10/13, g_inf 0)
  conventional common path: scenario_common_parameters.csv (tau 13, g_inf 0)
Vertical quantity: autonomous demand index A (2025 = 1), log axis.
The three service indices are separately normalized and cannot be added.
Constant is drawn only for training and inference (conventional keeps its
common path in every scenario)."""
import math
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "source-data" / "supplementary-01"
OUTPUT = HERE / "supplementary-01.jpg"

summ = pd.read_csv(SOURCE / "demand_calibration_summary.csv")
cen = summ[summ.case == "central"].set_index("service")
G25 = {s: float(cen.loc[s, "autonomous_log_growth_2021_2025_per_year"])
       for s in ("training", "inference", "conv")}
A25 = {s: float(cen.loc[s, "autonomous_index_2025_2021_1"])
       for s in ("training", "inference", "conv")}

sd = pd.read_csv(SOURCE / "scenario_design.csv")
sd = sd[sd.deployment_scope == "full_factorial"]
TAU = {r.scenario: float(r.tau_training_years) for r in sd.itertuples()}
cp = pd.read_csv(SOURCE / "scenario_common_parameters.csv").iloc[0]
TAU_CONV, GINF_CONV = float(cp.tau_years), float(cp.long_run_log_rate)

# annual calibration path 2021-2025 (level-exact through the endpoint identity)
try:
    ann = pd.read_csv(SOURCE / "demand_calibration_annual.csv")
    acol = [c for c in ann.columns if "autonomous_index" in c][0]
    CAL = {s: ann[(ann.case == "central") & (ann.service == s)]
           .set_index("year")[acol] for s in ("training", "inference", "conv")}
except Exception:
    CAL = {s: pd.Series({y: math.exp(G25[s] * (y - 2021))
                         for y in range(2021, 2026)}) for s in G25}

def path(svc, tau, ginf=0.0):
    yrs = np.arange(2025, 2051)
    d = yrs - 2025
    lnA = (ginf * d + (G25[svc] - ginf) * tau * (1 - np.exp(-d / tau)))
    return yrs, np.exp(lnA)

COLS = {"Low": "#DDB45F", "Medium": "#C98B24", "High": "#955F00"}
HISTORY = "#45515C"
CAL_FILL = "#EEF1F3"
BOUNDARY = "#9BA5AD"
HALO = [pe.withStroke(linewidth=3.5, foreground="white")]
plt.rcParams.update({"font.size": 15, "axes.linewidth": 1.1,
                     "xtick.labelsize": 14, "ytick.labelsize": 14,
                     "axes.labelsize": 15})

def demand_tick(value, _position):
    if value >= 1:
        return f"{value:g}"
    return f"{value:.1f}"


# The manuscript asset is 2,720 by 919 pixels. The explicit fractional inch
# height keeps that canvas stable across Matplotlib versions.
fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.595), dpi=200)
for ax, svc, ttl in zip(axes, ("training", "inference", "conv"),
                        ("AI training", "AI inference", "Conventional computing")):
    cal = CAL[svc] / A25[svc]
    ax.axvspan(2021, 2025, color=CAL_FILL, zorder=0)
    ax.axvline(2025, color=BOUNDARY, lw=1.0, ls=(0, (2, 2)), zorder=1)
    ax.plot(cal.index, cal.values, color=HISTORY, lw=2.6, marker="o", ms=4.4,
            mfc="white", mec=HISTORY, mew=1.2, zorder=5)
    ax.text(2023.0, 0.67, "CALIBRATED 2021–2025",
            transform=ax.get_xaxis_transform(), ha="center", va="center",
            rotation=90, fontsize=8.3, color="#68737C", zorder=10)
    if svc == "conv":
        yrs, A = path(svc, TAU_CONV, GINF_CONV)
        ax.plot(yrs, A, color=COLS["Medium"], lw=2.8, zorder=4)
        ax.annotate("common path", xy=(2050, A[-1]), xytext=(2036.5, A[-1]*0.72),
                    fontsize=13, color="#68737C", path_effects=HALO)
    else:
        for name, tau in TAU.items():
            yrs, A = path(svc, tau)
            ax.plot(yrs, A, color=COLS[name], lw=2.4, zorder=4)
            ax.annotate(name, xy=(2050, A[-1]), xytext=(2050.5, A[-1]),
                        fontsize=13, color=COLS[name], va="center",
                        path_effects=HALO, annotation_clip=False)
        ax.plot([2025, 2050], [1.0] * 2, color="#C4452C", lw=2.0,
                ls=(0, (4, 2)), zorder=3)
        ax.annotate("Constant", xy=(2049.8, 0.72), fontsize=13,
                    color="#C4452C", ha="right", path_effects=HALO)
    ax.set_yscale("log")
    ax.set_xlim(2020, 2056)
    if svc == "conv":
        ax.set_ylim(0.45, 6.0)
        ticks = (0.5, 1, 2, 5)
    else:
        ax.set_ylim(0.1, 360)
        ticks = (0.1, 1, 10, 100)
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_major_formatter(FuncFormatter(demand_tick))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.set_xticks([2021, 2030, 2040, 2050])
    ax.set_title(ttl, fontsize=15, fontweight="normal")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=4, width=1.0)
axes[0].set_ylabel("Autonomous demand index\n(2025 = 1, log scale)")
fig.subplots_adjust(left=0.085, right=0.985, top=0.92, bottom=0.11, wspace=0.10)
fig.savefig(OUTPUT)
plt.close(fig)
print(f"WROTE {OUTPUT}")
