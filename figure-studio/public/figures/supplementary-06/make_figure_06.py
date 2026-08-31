#!/usr/bin/env python3
"""Draw the 32-region companion to main-text Figure 6d--f.

Only the three regional comparison panels are retained and relabeled a--c.
The map panels in Figure 6a--c are deliberately not repeated.
"""

from pathlib import Path
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = Path(os.environ.get(
    "FIG_DATA_DIR",
    REPO / "results/derived/figure-data",
))
OUT = HERE / "supplementary-06.jpg"

YEAR = 2050
DEMANDS = ("Low", "Medium", "High")
EFFICIENCIES = ("Low", "Medium", "High")
POLICIES = ("ref", "nz2050co2")
REF_COLORS = {"Low": "#e0946a", "Medium": "#c2601f", "High": "#7d3506"}
NZ_COLORS = {"Low": "#83b6c0", "Medium": "#3f93a4", "High": "#14596b"}
DISPLAY = {
    "Africa_Eastern": "Eastern Africa",
    "Africa_Northern": "Northern Africa",
    "Africa_Southern": "Southern Africa",
    "Africa_Western": "Western Africa",
    "Australia_NZ": "Australia and New Zealand",
    "Europe_Non_EU": "Non-EU Europe",
    "European Free Trade Association": "EFTA",
    "South America_Northern": "Northern South America",
    "South America_Southern": "Southern South America",
    "South Korea": "Republic of Korea",
    "USA": "United States",
}


def scenario(demand: str, efficiency: str) -> str:
    return f"D{demand}_E{efficiency}"


def build_shares() -> pd.DataFrame:
    ai = pd.read_csv(DATA / "v7_regional.csv")
    electricity = pd.read_csv(DATA / "fig_region_elec_dc_v3.csv")
    footprint = pd.read_csv(DATA / "fig_water_footprint.csv")
    total_water = pd.read_csv(DATA / "v7_region_total_water.csv")

    keys = ["scenario", "policy", "year", "region"]
    frame = electricity.merge(ai[keys + ["ai_elec_TWh"]], on=keys,
                              how="left", validate="one_to_one")
    frame["ai_elec_TWh"] = frame["ai_elec_TWh"].fillna(0.0)
    frame["dc_elec_share"] = 100.0 * (
        frame["ai_elec_TWh"] + frame["conv_elec_TWh"]
    ) / frame["total_elec_TWh"]

    water = footprint.merge(
        total_water[keys + ["total_water_consumption_km3",
                            "total_water_withdrawal_km3"]],
        on=keys, how="left", validate="one_to_one",
    )
    water["dc_wcons_share"] = (
        100.0 * water["tot_cons"] / water["total_water_consumption_km3"]
    )
    water["dc_wwithdr_share"] = (
        100.0 * water["tot_withdr"] / water["total_water_withdrawal_km3"]
    )

    shares = frame[keys + ["dc_elec_share"]].merge(
        water[keys + ["dc_wcons_share", "dc_wwithdr_share"]],
        on=keys, validate="one_to_one",
    )
    if shares["region"].nunique() != 32:
        raise ValueError("The figure-data package must contain 32 model regions")
    return shares


def main() -> None:
    shares = build_shares()
    growth_cells = [scenario(d, e) for d in DEMANDS for e in EFFICIENCIES]
    current = shares[
        (shares["year"] == YEAR)
        & shares["scenario"].isin(growth_cells)
        & shares["policy"].isin(POLICIES)
    ].copy()
    counts = current.groupby("region").size()
    if set(counts) != {18} or len(counts) != 32:
        raise ValueError("Expected 18 growth scenarios for each of 32 regions")

    baseline = shares[
        (shares["year"] == 2025)
        & (shares["scenario"] == "DLow_EHigh")
        & (shares["policy"] == "ref")
    ].set_index("region")
    if len(baseline) != 32:
        raise ValueError("Incomplete 2025 regional baseline")

    specs = [
        ("a", "dc_elec_share", "Data center share of electricity", 70.0, 10.0),
        ("b", "dc_wcons_share", "Share of water consumption", 40.0, 5.0),
        ("c", "dc_wwithdr_share", "Share of water withdrawal", 40.0, 5.0),
    ]

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.linewidth": 0.9,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    fig, axes = plt.subplots(1, 3, figsize=(18.2, 13.8))
    lookup = current.set_index(["region", "scenario", "policy"])

    for ax, (letter, column, title, upper, step) in zip(axes, specs):
        med_ref = {
            region: float(lookup.loc[(region, scenario("Medium", "Medium"), "ref"), column])
            for region in counts.index
        }
        order = sorted(counts.index, key=lambda r: med_ref[r], reverse=True)

        for row, region in enumerate(order):
            values = [
                float(lookup.loc[(region, scenario(d, e), p), column])
                for d in DEMANDS for e in EFFICIENCIES for p in POLICIES
            ]
            ax.fill_betweenx([row - 0.27, row + 0.27], min(values), max(values),
                             color="0.86", lw=0, zorder=2)
            for demand in DEMANDS:
                ref_value = float(lookup.loc[
                    (region, scenario(demand, "Medium"), "ref"), column
                ])
                nz_value = float(lookup.loc[
                    (region, scenario(demand, "Medium"), "nz2050co2"), column
                ])
                ax.plot([ref_value, ref_value], [row, row + 0.34],
                        color=REF_COLORS[demand], lw=2.0, solid_capstyle="butt",
                        zorder=4)
                ax.plot([nz_value, nz_value], [row - 0.34, row],
                        color=NZ_COLORS[demand], lw=2.0, solid_capstyle="butt",
                        zorder=4)
            ax.plot(float(baseline.loc[region, column]), row, marker="D", ms=3.8,
                    mfc="0.74", mec="0.38", mew=0.7, ls="none", zorder=5)

        ax.set_yticks(range(32))
        ax.set_yticklabels([DISPLAY.get(r, r.replace("_", " ")) for r in order],
                           fontsize=8.2)
        ax.invert_yaxis()
        ax.set_xlim(-0.015 * upper, upper)
        ax.xaxis.set_major_locator(MultipleLocator(step))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
        ax.tick_params(axis="x", labelsize=9.5, length=3.5, pad=4)
        ax.tick_params(axis="y", length=0, pad=4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_title(title, fontsize=15, pad=14)
        ax.text(-0.12, 1.018, letter, transform=ax.transAxes, fontsize=22,
                fontweight="bold", ha="left", va="bottom")

    handles = [
        Patch(facecolor="0.86", edgecolor="none", label="Demand and efficiency range"),
        Line2D([], [], marker="|", markersize=14, markeredgewidth=2.0,
               color=REF_COLORS["Medium"], ls="none", label="Reference"),
        Line2D([], [], marker="|", markersize=14, markeredgewidth=2.0,
               color=NZ_COLORS["Medium"], ls="none", label="Net-zero CO$_2$ by 2050"),
        Line2D([], [], marker="D", ms=4.2, mfc="0.74", mec="0.38", mew=0.7,
               color="none", ls="none", label="2025 share"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=11, bbox_to_anchor=(0.5, 0.025), handlelength=2.0,
               columnspacing=2.0)
    fig.text(0.5, 0.074,
             "Warm upward ticks show Low, Medium and High demand under the reference pathway; "
             "teal downward ticks show the corresponding net-zero pathway.",
             ha="center", va="center", fontsize=10.5, color="0.30")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.105, right=0.99, top=0.955, bottom=0.12, wspace=0.34)
    fig.savefig(OUT, dpi=300)
    plt.close(fig)
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
