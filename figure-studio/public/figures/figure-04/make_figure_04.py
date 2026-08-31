#!/usr/bin/env python3
"""Build Figure 4 from the audited BaseX freshwater queries.

Panel a stacks water consumption and return flow so that the upper edge gives
total withdrawal. Panels b and c separately decompose consumption and return
flow into direct data-center and indirect power-generation use. The figure
reports global annual volumes rather than basin-level water scarcity.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT_JPG = HERE / "figure-04.jpg"
import os as _os
D = Path(_os.environ.get(
    "FIG_DATA_DIR", str(ROOT / "results/derived/figure-data")))
DEMANDS = ["Low", "Medium", "High"]
DEM_DISP = {"Low": "Low", "Medium": "Medium", "High": "High"}
EFFS = ["Low", "Medium", "High"]
C_REF, C_NZ = "#b3531d", "#1f7a8c"
C_DIR, C_IND = "#1d5e86", "#a8cbe0"   # direct (deep) / indirect (pale) water
C_CONS, C_RET = "#2b6a92", "#dcdcdc"
C_WEDGE = "#14496b"

FS = dict(tick=20, label=24, title=26, letter=34, ann=20, small=20)
CM = FuncFormatter(lambda v, _p: f"{int(round(v)):,}")


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=FS["tick"], width=0.8)
    ax.set_facecolor("white")


def load():
    cols = ["scenario", "policy", "year", "region", "dir_cons", "dir_withdr",
            "ind_cons", "ind_withdr"]
    w = pd.read_csv(D / "fig_water_footprint.csv")[cols]   # v3: every demand level
    t = w.groupby(["scenario", "policy", "year"])[
        ["dir_cons", "dir_withdr", "ind_cons", "ind_withdr"]].sum().reset_index()
    t["demand"] = t.scenario.str.extract(r"D(\w+?)_E")[0]
    t["eff"] = t.scenario.str.extract(r"_E(\w+)$")[0]
    t = t[t.demand.isin(DEMANDS)]
    t["cons"] = t.dir_cons + t.ind_cons
    t["withdr"] = t.dir_withdr + t.ind_withdr
    t["net_dir"] = t.dir_withdr - t.dir_cons
    t["net_ind"] = t.ind_withdr - t.ind_cons
    t["net"] = t.withdr - t.cons
    g = t[t.year == 2050].copy()
    return g, t


def stack_panel(ax, g, dcol, icol, tcol, letter, ylab, ymax,
                key=False, cdir=C_DIR, cind=C_IND):
    x = 0.0
    xticks, xtlabs = [], []
    med_tot, hi_tot = {}, {}
    for dem in DEMANDS:
        for pol in ("ref", "nz2050co2"):
            sub = g[(g.demand == dem) & (g.policy == pol)]
            r = sub[sub.eff == "Medium"].iloc[0]
            d, ind = float(r[dcol]), float(r[icol])
            ax.bar(x, d, width=0.62, color=cdir, zorder=3)
            ax.bar(x, ind, bottom=d, width=0.62, color=cind, zorder=3)
            totals = sub.set_index("eff")[tcol]
            lo, hi = float(totals.min()), float(totals.max())
            ax.plot([x, x], [lo, hi], color="0.2", lw=1.2, zorder=5)
            for e_ in (lo, hi):
                ax.plot([x - 0.10, x + 0.10], [e_, e_], color="0.2", lw=1.2,
                        zorder=5)
            med_tot[(dem, pol)] = d + ind
            hi_tot[(dem, pol)] = hi
            xticks.append(x)
            xtlabs.append("Ref." if pol == "ref" else "NZ")
            x += 1.25
        ax.text(x - 1.875, -0.155, DEM_DISP[dem],
                transform=ax.get_xaxis_transform(), ha="center",
                fontsize=FS["ann"] + 1, color="0.1")
        if dem == "Medium":
            ax.text(x - 1.875, -0.20, "demand",
                    transform=ax.get_xaxis_transform(), ha="center",
                    va="top", fontsize=FS["small"], color="0.45",
                    fontstyle="italic")
        x += 0.9
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtlabs, fontsize=FS["tick"])
    ax.set_xlim(-0.65, x - 0.9 + 0.25)
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_formatter(CM)
    ax.set_ylabel(ylab, fontsize=FS["label"])
    ax.text(-0.16, 1.05, letter, transform=ax.transAxes,
            fontsize=FS["letter"], fontweight="bold")
    if key:
        ax.add_patch(plt.Rectangle((0.03, 0.925), 0.045, 0.040,
                                   transform=ax.transAxes, facecolor=cdir,
                                   zorder=6))
        ax.text(0.095, 0.945, "Direct",
                transform=ax.transAxes, va="center",
                fontsize=FS["ann"], color="0.15", zorder=6)
        ax.add_patch(plt.Rectangle((0.03, 0.850), 0.045, 0.040,
                                   transform=ax.transAxes, facecolor=cind,
                                   zorder=6))
        ax.text(0.095, 0.870, "Indirect",
                transform=ax.transAxes, va="center",
                fontsize=FS["ann"], color="0.15", zorder=6)


def main() -> None:
    g, t = load()

    fig = plt.figure(figsize=(21.0, 6.8))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.5, 1.0, 1.0], wspace=0.30,
                          left=0.05, right=0.975, bottom=0.175, top=0.875)

    # -------- a: stacked water-use pathways, one column per demand --------
    sub_gs = gs[0].subgridspec(1, 3, wspace=0.38)
    med = t[(t.policy == "ref") & (t.eff == "Medium")
            & t.year.between(2021, 2050)]
    ymax = float(med.withdr.max()) * 1.18
    for i, dem in enumerate(DEMANDS):
        ax = fig.add_subplot(sub_gs[0, i])
        style(ax)
        s = med[med.demand == dem].sort_values("year")
        ax.fill_between(s.year, 0.0, s.cons, color=C_CONS, lw=0, zorder=3)
        ax.fill_between(s.year, s.cons, s.withdr, color=C_RET, lw=0, zorder=2)
        ax.plot(s.year, s.withdr, color=C_WEDGE, lw=1.5, zorder=4)
        ax.set_xlim(2021, 2050)
        ax.set_xticks([2021, 2030, 2040, 2050])
        ax.set_ylim(0, ymax)
        ax.tick_params(axis="y", labelsize=FS["tick"] - 3)
        ax.tick_params(axis="x", labelsize=14)
        ax.set_title({"Low": "Low demand", "Medium": "Med. demand",
                      "High": "High demand"}[dem],
                     fontsize=FS["title"] - 2, color="0.15", pad=6)
        if i == 0:
            ax.set_ylabel("Total withdrawal (km$^3$)",
                          fontsize=FS["label"])
            ax.text(-0.46, 1.07, "a", transform=ax.transAxes,
                    fontsize=FS["letter"], fontweight="bold")
        else:
            ax.tick_params(labelleft=False)
        if dem == "Low":
            ax.plot([0.07, 0.19], [0.935, 0.935], color=C_WEDGE, lw=1.8,
                    transform=ax.transAxes, zorder=6, clip_on=False)
            ax.text(0.24, 0.935, "Withdrawal", transform=ax.transAxes,
                    fontsize=FS["small"], color="0.2", va="center",
                    zorder=6)
            ax.add_patch(plt.Rectangle((0.07, 0.825), 0.12, 0.05,
                                       transform=ax.transAxes,
                                       facecolor=C_RET, zorder=6))
            ax.text(0.24, 0.85, "Return flow", transform=ax.transAxes,
                    fontsize=FS["small"], color="0.2", va="center",
                    zorder=6)
            ax.add_patch(plt.Rectangle((0.07, 0.715), 0.12, 0.05,
                                       transform=ax.transAxes,
                                       facecolor=C_CONS, zorder=6))
            ax.text(0.24, 0.74, "Consumption", transform=ax.transAxes,
                    fontsize=FS["small"], color="0.2", va="center",
                    zorder=6)

    shared_max = float(g.net.max()) * 1.30
    ax = fig.add_subplot(gs[1])
    style(ax)
    stack_panel(ax, g, "dir_cons", "ind_cons", "cons", "b",
                "Consumption, 2050 (km$^3$)", shared_max, key=True)

    ax = fig.add_subplot(gs[2])
    style(ax)
    stack_panel(ax, g, "net_dir", "net_ind", "net", "c",
                "Return flow, 2050 (km$^3$)", shared_max, key=True,
                cdir="#6e6e6e", cind="#d8d8d8")

    fig.savefig(OUT_JPG, dpi=150)
    print(f"WROTE {OUT_JPG}")


if __name__ == "__main__":
    main()
