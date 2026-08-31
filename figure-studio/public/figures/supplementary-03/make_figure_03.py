#!/usr/bin/env python3
"""Build the Supplementary Information climate-policy pathway figure.

The figure isolates the policy axis by holding computing demand and efficiency
at their Medium settings. It reads the validated figure bridge and plots
solved global CO2 emissions for the Reference and global net-zero CO2
pathways. The underlying regional emissions query is reported in MtC and is
converted here to GtCO2 using 44/12.
"""

from __future__ import annotations

import csv
from pathlib import Path
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
SOURCE = Path(
    os.environ.get(
        "FIG_DATA_DIR",
        PROJECT_ROOT / "results" / "derived" / "figure-data",
    )
) / "v7_master.csv"
SOURCE_OUTPUT = HERE / "supplementary-03.jpg"

SCENARIO = "DMedium_EMedium"
POLICIES = ("ref", "nz2050co2")
YEARS = (2021, 2025, 2030, 2035, 2040, 2045, 2050)
COLORS = {"ref": "#B3531D", "nz2050co2": "#1F7A8C"}
LABELS = {
    "ref": "Reference",
    "nz2050co2": "Net-zero CO$_2$ by 2050",
}
HALO = [pe.withStroke(linewidth=3.5, foreground="white")]


def load_paths() -> dict[str, dict[int, float]]:
    paths = {policy: {} for policy in POLICIES}
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["scenario"] != SCENARIO or row["policy"] not in paths:
                continue
            year = int(row["year"])
            if year in YEARS:
                paths[row["policy"]][year] = float(row["total_co2_GtCO2"])

    for policy, values in paths.items():
        missing = sorted(set(YEARS) - set(values))
        if missing:
            raise ValueError(f"Missing {policy} emissions for years {missing}")

    if abs(paths["ref"][2025] - 37.301) > 0.001:
        raise ValueError("Reference pathway does not reproduce the 2025 anchor")
    if abs(paths["nz2050co2"][2025] - 37.301) > 0.001:
        raise ValueError("Net-zero pathway does not reproduce the 2025 anchor")

    expected_nz = {
        2030: 8138 * 44 / 12 / 1000,
        2035: 6104 * 44 / 12 / 1000,
        2040: 4069 * 44 / 12 / 1000,
        2045: 2035 * 44 / 12 / 1000,
        2050: -1 * 44 / 12 / 1000,
    }
    for year, expected in expected_nz.items():
        if abs(paths["nz2050co2"][year] - expected) > 0.001:
            raise ValueError(
                f"Solved net-zero emissions differ from the constraint in {year}"
            )
    return paths


def make_figure(paths: dict[str, dict[int, float]]) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 15,
            "axes.linewidth": 1.1,
            "axes.labelsize": 15,
            "xtick.labelsize": 14,
            "ytick.labelsize": 14,
        }
    )

    fig, ax = plt.subplots(figsize=(9.4, 5.25), dpi=200)

    common_years = [2021, 2025]
    common_values = [paths["ref"][year] for year in common_years]
    ax.plot(
        common_years,
        common_values,
        color="#45515C",
        lw=2.6,
        marker="o",
        ms=5.2,
        mfc="white",
        mec="#45515C",
        mew=1.3,
        zorder=5,
    )

    policy_years = [year for year in YEARS if year >= 2025]
    for policy in POLICIES:
        values = [paths[policy][year] for year in policy_years]
        ax.plot(
            policy_years,
            values,
            color=COLORS[policy],
            lw=2.6,
            marker="o",
            ms=5.2,
            mfc="white",
            mec=COLORS[policy],
            mew=1.3,
            zorder=4,
        )

    ax.axvline(2025, color="#9BA5AD", lw=1.0, ls=(0, (2, 2)), zorder=1)
    ax.annotate(
        "Common 2025 constraint\n37.3 GtCO$_2$",
        xy=(2025, paths["ref"][2025]),
        xytext=(2029.2, 48.2),
        ha="center",
        va="top",
        fontsize=12.5,
        color="#45515C",
        arrowprops={"arrowstyle": "-", "color": "#7C8790", "lw": 1.0},
        path_effects=HALO,
        zorder=8,
    )

    ax.annotate(
        LABELS["ref"],
        xy=(2050, paths["ref"][2050]),
        xytext=(2051.0, paths["ref"][2050]),
        ha="left",
        va="center",
        fontsize=13,
        color=COLORS["ref"],
        annotation_clip=False,
        path_effects=HALO,
    )
    ax.annotate(
        LABELS["nz2050co2"],
        xy=(2050, paths["nz2050co2"][2050]),
        xytext=(2051.0, 1.0),
        ha="left",
        va="center",
        fontsize=13,
        color=COLORS["nz2050co2"],
        annotation_clip=False,
        path_effects=HALO,
    )

    ax.set_xlim(2020, 2059)
    ax.set_ylim(-1.0, 50.0)
    ax.set_xticks(YEARS)
    ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_ylabel("Global CO$_2$ emissions (GtCO$_2$ yr$^{-1}$)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=4, width=1.0)

    fig.subplots_adjust(left=0.12, right=0.79, top=0.96, bottom=0.13)
    SOURCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        SOURCE_OUTPUT,
        format="jpg",
        dpi=300,
        facecolor="white",
        pil_kwargs={"quality": 96, "subsampling": 0, "optimize": True},
    )
    plt.close(fig)

if __name__ == "__main__":
    policy_paths = load_paths()
    make_figure(policy_paths)
    print(f"Wrote {SOURCE_OUTPUT}")
