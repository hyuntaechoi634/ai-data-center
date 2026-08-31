#!/usr/bin/env python3
"""Draw historical global electricity generation and capacity additions.

The source tables are the validated derivatives of Ember's Global Electricity
Data Explorer 2026 release and the August 2026 Global Integrated Power Tracker.
The raw-source validation and accounting audit are maintained with the
manuscript package; this renderer consumes only the exact plotted values.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MultipleLocator


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "source-data" / "supplementary-04"
OUTPUT = HERE / "supplementary-04.jpg"

START_YEAR = 2000
END_YEAR = 2025
CAPACITY_END_YEAR = 2024
SOURCE_ORDER = (
    "Coal",
    "Gas",
    "Other fossil",
    "Nuclear",
    "Hydro",
    "Bioenergy",
    "Other renewables",
    "Wind",
    "Solar",
)
COLORS = {
    "Coal": "#2B2B2B",
    "Gas": "#C8A464",
    "Other fossil": "#B8B8B8",
    "Nuclear": "#E69F00",
    "Hydro": "#00443F",
    "Bioenergy": "#4C9F50",
    "Other renewables": "#2A9D8F",
    "Wind": "#56B4E9",
    "Solar": "#F0E442",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_values():
    generation_rows = rows(
        SOURCE / "global-electricity-generation-by-source-2000-2025.csv"
    )
    summary_rows = rows(
        SOURCE / "global-electricity-generation-summary-2000-2025.csv"
    )
    capacity_rows = rows(
        SOURCE / "global-tracked-gross-capacity-additions-2000-2024.csv"
    )

    generation = {
        (int(row["year"]), row["electricity_source"]): float(row["generation_twh"])
        for row in generation_rows
    }
    summary = {int(row["year"]): row for row in summary_rows}
    capacity = {
        (int(row["year"]), row["technology_group"]): float(
            row["gross_capacity_additions_gw"]
        )
        for row in capacity_rows
    }
    expected_generation = {
        (year, source)
        for year in range(START_YEAR, END_YEAR + 1)
        for source in SOURCE_ORDER
    }
    expected_capacity = {
        (year, source)
        for year in range(START_YEAR, CAPACITY_END_YEAR + 1)
        for source in SOURCE_ORDER
    }
    if set(generation) != expected_generation:
        raise ValueError("The historical generation source table is incomplete")
    if set(summary) != set(range(START_YEAR, END_YEAR + 1)):
        raise ValueError("The historical generation summary is incomplete")
    if set(capacity) != expected_capacity:
        raise ValueError("The tracked capacity-additions table is incomplete")
    return generation, summary, capacity


def main() -> None:
    generation_values, summary, capacity_values = load_values()
    years = list(range(START_YEAR, END_YEAR + 1))
    generation = [
        [generation_values[(year, source)] for year in years]
        for source in SOURCE_ORDER
    ]
    renewable_shares = [
        float(summary[year]["renewable_share_percent"]) for year in years
    ]
    clean_shares = [float(summary[year]["clean_share_percent"]) for year in years]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 12.5,
            "axes.labelsize": 16,
            "axes.titlesize": 15,
            "xtick.labelsize": 13.5,
            "ytick.labelsize": 13.5,
            "legend.fontsize": 13.5,
            "axes.linewidth": 0.8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(22.8, 5.9))
    figure.subplots_adjust(
        left=0.048, right=0.815, top=0.88, bottom=0.14, wspace=0.27
    )
    colors = [COLORS[source] for source in SOURCE_ORDER]

    axes[0].stackplot(
        years,
        generation,
        colors=colors,
        edgecolor="white",
        linewidth=0.35,
    )
    clean_line, = axes[1].plot(
        years,
        clean_shares,
        color="0.15",
        linewidth=2.8,
        marker="o",
        markevery=5,
        markersize=5.0,
        label="Clean",
        zorder=3,
    )
    renewable_line, = axes[1].plot(
        years,
        renewable_shares,
        color="#009E73",
        linewidth=2.8,
        marker="s",
        markevery=5,
        markersize=4.8,
        label="Renewables",
        zorder=3,
    )

    capacity_years = list(range(START_YEAR, CAPACITY_END_YEAR + 1))
    capacity_bottom = [0.0] * len(capacity_years)
    for source in SOURCE_ORDER:
        values = [capacity_values[(year, source)] for year in capacity_years]
        axes[2].bar(
            capacity_years,
            values,
            bottom=capacity_bottom,
            width=0.82,
            color=COLORS[source],
            edgecolor="white",
            linewidth=0.35,
            zorder=3,
        )
        capacity_bottom = [
            bottom + value for bottom, value in zip(capacity_bottom, values)
        ]

    for axis in axes:
        axis.set_xlim(START_YEAR, END_YEAR)
        axis.set_xticks([2000, 2005, 2010, 2015, 2020, 2025])
        axis.spines[["top", "right"]].set_visible(False)
        axis.spines[["left", "bottom"]].set_color("#333333")
        axis.tick_params(width=0.8, length=4, color="#333333")
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.65, alpha=0.8)
        axis.set_axisbelow(True)

    axes[0].set_ylabel("Generation (TWh)")
    axes[0].set_ylim(0, 35000)
    axes[0].yaxis.set_major_locator(MultipleLocator(5000))
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))

    axes[1].set_ylabel("Share of generation (%)")
    axes[1].set_xlim(START_YEAR - 0.2, END_YEAR + 0.2)
    axes[1].set_ylim(0, 50)
    axes[1].yaxis.set_major_locator(MultipleLocator(10))

    axes[2].set_ylabel("Capacity additions (GW)")
    axes[2].set_xlim(1999.4, 2024.6)
    axes[2].set_xticks([2000, 2005, 2010, 2015, 2020, 2024])
    axes[2].set_ylim(0, 500)
    axes[2].yaxis.set_major_locator(MultipleLocator(100))

    for label, title, axis in zip(
        ("a", "b", "c"),
        (
            "Generation by source",
            "Clean and renewable shares",
            "Capacity additions",
        ),
        axes,
    ):
        axis.text(
            -0.105,
            1.035,
            label,
            transform=axis.transAxes,
            fontsize=18,
            fontweight="bold",
            ha="left",
            va="bottom",
        )
        axis.text(
            0.0,
            1.035,
            title,
            transform=axis.transAxes,
            fontsize=15,
            fontweight="bold",
            ha="left",
            va="bottom",
        )

    source_handles = [
        Patch(facecolor=COLORS[source], label=source) for source in SOURCE_ORDER
    ]
    blank_rows = [
        Patch(facecolor="none", edgecolor="none", label="") for _ in range(2)
    ]
    figure.legend(
        handles=[*source_handles, *blank_rows, clean_line, renewable_line],
        loc="center left",
        bbox_to_anchor=(0.835, 0.52),
        ncol=1,
        frameon=False,
        borderaxespad=0.0,
        labelspacing=0.78,
        handlelength=2.2,
        handletextpad=0.65,
    )
    figure.savefig(
        OUTPUT,
        dpi=300,
        pil_kwargs={"quality": 95, "optimize": True, "progressive": False},
    )
    plt.close(figure)
    print(f"WROTE {OUTPUT}")


if __name__ == "__main__":
    main()
