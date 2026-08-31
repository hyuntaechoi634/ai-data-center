#!/usr/bin/env python3
"""Draw the 32-region companion to main-text Figure 5d.

The figure contains only the regional heatmap. It recomputes each percentage
change from the latest frozen figure-data package and does not repeat panels
5a--c.
"""

from pathlib import Path
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = Path(os.environ.get(
    "FIG_DATA_DIR",
    REPO / "results/derived/figure-data",
))
OUT = HERE / "supplementary-05.jpg"

SCENARIOS = {
    "Low": "DLow_EMedium",
    "Medium": "DMedium_EMedium",
    "High": "DHigh_EMedium",
}
BASELINE = "DConstant_EMedium"
YEARS = (2030, 2040, 2050)
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


def main() -> None:
    prices = pd.read_csv(DATA / "solved_regional_prices_nz.csv")
    required = {BASELINE, *SCENARIOS.values()}
    if set(prices["scenario"].unique()) != required:
        raise ValueError("Unexpected scenario set in solved_regional_prices_nz.csv")
    if prices["region"].nunique() != 32:
        raise ValueError("The regional price table must contain exactly 32 regions")

    pivot = prices.pivot_table(
        index="region", columns=["scenario", "year"],
        values="price_2020USDperMWh", aggfunc="first",
    )
    responses = []
    for year in YEARS:
        for scenario in SCENARIOS.values():
            responses.append(
                100.0 * (pivot[(scenario, year)] / pivot[(BASELINE, year)] - 1.0)
            )
    values = pd.concat(responses, axis=1)
    values.columns = range(9)
    values = values.sort_values(8, ascending=False)
    if values.shape != (32, 9) or not np.isfinite(values.to_numpy()).all():
        raise ValueError("Incomplete 32-region electricity-price matrix")

    # Blank spacer columns separate model years while preserving equal cell size.
    array = np.full((32, 11), np.nan)
    array[:, 0:3] = values.iloc[:, 0:3]
    array[:, 4:7] = values.iloc[:, 3:6]
    array[:, 8:11] = values.iloc[:, 6:9]
    vmin = min(0.0, float(np.floor(np.nanmin(array))))
    vmax = float(np.ceil(np.nanmax(array) / 5.0) * 5.0)

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "price_response", plt.get_cmap("magma_r")(np.linspace(0.02, 0.82, 256))
    )
    cmap.set_bad("white")

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })
    fig, ax = plt.subplots(figsize=(9.2, 11.4))
    image = ax.imshow(array, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)

    threshold = vmin + 0.58 * (vmax - vmin)
    for row in range(array.shape[0]):
        for col in range(array.shape[1]):
            value = array[row, col]
            if np.isnan(value):
                continue
            ax.text(
                col, row, f"{value:.1f}", ha="center", va="center",
                fontsize=7.5, color="white" if value > threshold else "0.15",
            )

    tick_positions = [0, 1, 2, 4, 5, 6, 8, 9, 10]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(["Low", "Medium", "High"] * 3, fontsize=9.5)
    ax.set_yticks(range(32))
    ax.set_yticklabels([DISPLAY.get(r, r.replace("_", " ")) for r in values.index],
                       fontsize=8.5)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for x, year in ((1, 2030), (5, 2040), (9, 2050)):
        ax.text(x, -1.12, str(year), ha="center", va="bottom",
                fontsize=11.5, color="0.15")
    ax.text(5, 33.2, "Demand", ha="center", va="top", fontsize=10.5,
            color="0.35")

    cbar = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=0.035,
                        pad=0.075, aspect=35)
    cbar.set_label("Increase relative to the matching counterfactual (%)",
                   fontsize=10.5)
    cbar.ax.tick_params(labelsize=9)
    cbar.outline.set_visible(False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.31, right=0.98, top=0.965, bottom=0.12)
    fig.savefig(OUT, dpi=300)
    plt.close(fig)
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
