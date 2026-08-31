#!/usr/bin/env python3
"""Build the three-panel Supplementary Information efficiency figure.

The figure adapts the service-specific efficiency panels used in the KEEA
presentation to the manuscript layout.  It reads only the active calibration
and scenario tables:

* analysis/efficiency-axes/fleet-path/data/
  fleet_efficiency_index_2021_2025.csv
* data-raw/out/efficiency_scenario_parameters.csv

The vertical quantity is effective information-technology efficiency,
R times B, in service-specific RFLOP/EJ.  PUE is deliberately excluded.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "source-data" / "supplementary-02"
HISTORY_FILE = SOURCE / "fleet_efficiency_index_2021_2025.csv"
PARAMETER_FILE = SOURCE / "efficiency_scenario_parameters.csv"
OUTPUT = HERE / "supplementary-02.jpg"

SERVICES = ("training", "inference", "conventional")
TITLES = {
    "training": "AI training",
    "inference": "AI inference",
    "conventional": "Conventional computing",
}
COLORS = {"Low": "#9BB8B5", "Medium": "#4F928A", "High": "#1D7065"}
HISTORY_COLOR = "#45515C"
CALIBRATION_FILL = "#EEF1F3"
BOUNDARY_COLOR = "#9BA5AD"
HALO = [pe.withStroke(linewidth=3.5, foreground="white")]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(
            csv.DictReader(
                line for line in stream if line.strip() and not line.startswith("#")
            )
        )


HISTORY_ROWS = read_rows(HISTORY_FILE)
PARAMETER_ROWS = read_rows(PARAMETER_FILE)


def historical_path(service: str) -> tuple[np.ndarray, np.ndarray]:
    rows = [row for row in HISTORY_ROWS if row["service"] == service]
    years = np.array([int(row["year"]) for row in rows])
    relative = np.array(
        [float(row["fleet_efficiency_index_2021_100"]) / 100.0 for row in rows]
    )
    return years, relative


def effective_efficiency_2021(service: str) -> float:
    """Recover the active 2021 R times B value in RFLOP/EJ."""
    rows = [row for row in PARAMETER_ROWS if row["service"] == service]
    inferred_iota = np.array(
        [
            float(row["iota_EJ_per_service_unit"])
            * float(row["B_relative_2021"])
            for row in rows
        ]
    )
    if not np.allclose(inferred_iota, inferred_iota[0], rtol=1e-8, atol=1e-12):
        raise ValueError(f"Inconsistent 2021 electricity coefficient for {service}")
    return 1.0 / float(inferred_iota[0])


def scenario_parameters(service: str) -> dict[str, tuple[float, float]]:
    values: dict[str, tuple[float, float]] = {}
    for scenario in ("Low", "Medium", "High"):
        rows = [
            row
            for row in PARAMETER_ROWS
            if row["service"] == service and row["scenario"] == scenario
        ]
        if not rows:
            raise ValueError(f"No efficiency parameters for {service}/{scenario}")
        values[scenario] = (float(rows[0]["phi_B"]), float(rows[0]["tau_B_years"]))
    return values


plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 15,
        "axes.linewidth": 1.1,
        "axes.labelsize": 15,
        "axes.titlesize": 15,
        "xtick.labelsize": 14,
        "ytick.labelsize": 14,
    }
)

fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.6), dpi=200)
future_years = np.linspace(2025, 2050, 251)
elapsed = future_years - 2025

for panel, (ax, service) in enumerate(zip(axes, SERVICES)):
    years, relative = historical_path(service)
    history = effective_efficiency_2021(service) * relative

    ax.axvspan(2021, 2025, color=CALIBRATION_FILL, zorder=0)
    ax.axvline(2025, color=BOUNDARY_COLOR, lw=1.0, ls=(0, (2, 2)), zorder=1)
    ax.plot(
        years,
        history,
        color=HISTORY_COLOR,
        lw=2.6,
        marker="o",
        ms=4.4,
        mfc="white",
        mec=HISTORY_COLOR,
        mew=1.2,
        zorder=5,
    )
    ax.text(
        2023.0,
        0.67,
        "CALIBRATED 2021–2025",
        transform=ax.get_xaxis_transform(),
        ha="center",
        va="center",
        rotation=90,
        fontsize=8.3,
        color="#68737C",
        zorder=10,
    )

    endpoints: dict[str, float] = {}
    for scenario, (phi, tau) in scenario_parameters(service).items():
        values = history[-1] * np.exp(
            math.log(phi) * (1.0 - np.exp(-elapsed / tau))
        )
        endpoints[scenario] = float(values[-1])
        ax.plot(future_years, values, color=COLORS[scenario], lw=2.4, zorder=4)

    for scenario in ("High", "Medium", "Low"):
        ax.annotate(
            scenario,
            xy=(2050, endpoints[scenario]),
            xytext=(2050.5, endpoints[scenario]),
            fontsize=13,
            color=COLORS[scenario],
            va="center",
            path_effects=HALO,
            annotation_clip=False,
        )

    ax.set_xlim(2020, 2056)
    ax.set_xticks([2021, 2030, 2040, 2050])
    if service in ("training", "inference"):
        ax.set_ylim(0, 1600)
        ax.set_yticks([0, 500, 1000, 1500])
    else:
        ax.set_ylim(0, 35)
        ax.set_yticks([0, 10, 20, 30])
    ax.set_title(TITLES[service], fontweight="normal")
    ax.text(
        -0.12,
        1.04,
        chr(ord("a") + panel),
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=15,
        fontweight="bold",
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(length=4, width=1.0)

axes[0].set_ylabel("Effective IT efficiency (RFLOP/EJ)")
fig.subplots_adjust(left=0.082, right=0.985, top=0.90, bottom=0.12, wspace=0.16)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(
    OUTPUT,
    format="jpg",
    dpi=300,
    facecolor="white",
    pil_kwargs={"quality": 96, "subsampling": 0, "optimize": True},
)
plt.close(fig)
print(f"Wrote {OUTPUT}")
