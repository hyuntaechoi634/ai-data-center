#!/usr/bin/env python3
"""Redesigned manuscript fig03 (v2b; existing figures untouched).

Skill conventions applied (ncc-figure-maker figure-anatomy): lines over bands,
direct on-data labelling, one message per panel, contiguous stacks, sparse
annotations, mechanics in the caption.

  a | Annual indirect data-center emissions: one LINE per demand pathway at
      Medium efficiency, reference and net-zero on the SAME axes (net-zero
      collapses to near zero — that is the message), efficiency range as a
      2050 whisker, values printed at line ends.
  b | Cumulative 2026-2050 indirect emissions with an illustrative
      manufacturing sensitivity against the 1.5 C budget;
      efficiency groups ordered High -> Low; embodied drawn contiguously
      (solid lower bound + hatched upper increment).
  c | Emission intensity of electricity from the canonical BaseX query;
      common model history and two policy means over individual AR6 paths.

Data-center emissions are attributed with region-specific gross electricity
intensities; panel c separately reports the global-average grid intensity.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT_JPG = HERE / "figure-03.jpg"
import os as _os
D = Path(_os.environ.get(
    "FIG_DATA_DIR", str(ROOT / "results/derived/figure-data")))
AGX = ROOT / "analysis/agentic-extreme-demand"

DEMANDS = ["Low", "Medium", "High"]
DEM_DISP = {"Low": "Low", "Medium": "Medium", "High": "High"}
EFFS_B = ["High", "Medium", "Low"]           # panel b group order
EFFS = ["Low", "Medium", "High"]

C_REF, C_NZ = "#b3531d", "#1f7a8c"
C_HIST = "#3f3f3f"
REF_RAMP = {"Low": "#e0946a", "Medium": "#c2601f", "High": "#7d3506"}
NZ_RAMP = {"Low": "#83b6c0", "Medium": "#3f93a4", "High": "#14596b"}
C_AI = "#a04000"          # panel b: AI training
C_INFB = "#cf7a45"        # panel b: AI inference
C_CONV = "#e8c4a8"
C_EMB = "#8a5a32"
B15_50, B15_67, B2C_50 = 130.0, 80.0, 1050.0  # Forster 2026 Table 8, from start of 2026
EMB_LO, EMB_HI = 0.15, 0.40

FS = dict(tick=17, label=19, title=21, letter=28, ann=17, small=17)
CM = FuncFormatter(lambda v, _p: f"{int(round(v)):,}")


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=FS["tick"], width=0.8)
    ax.set_facecolor("white")


def load():
    d = pd.read_csv(D / "fig3_dc_co2_regional.csv").rename(columns={
        "training_co2_Gt": "trn_co2",
        "inference_co2_Gt": "inf_co2",
        "conventional_co2_Gt": "conv_co2",
        "ai_co2_Gt": "ai_co2",
        "dc_co2_Gt": "dc_co2",
    })
    d["demand"] = d.scenario.str.extract(r"D(\w+?)_E")[0]
    d["eff"] = d.scenario.str.extract(r"_E(\w+)$")[0]
    d = d[d.demand.isin(DEMANDS)]

    gef = pd.read_csv(D / "fig3_gridEF_net.csv")
    gef["demand"] = gef.scenario.str.extract(r"D(\w+?)_E")[0]
    gef = gef[gef.demand.isin(DEMANDS)]
    return d, gef


def cum_2026_2050(s: pd.DataFrame, col: str) -> float:
    s = s[s.year.between(2021, 2050)].sort_values("year")
    yrs = s.year.to_numpy(dtype=float)
    v = s[col].to_numpy(dtype=float)
    v26 = np.interp(2026.0, yrs, v)
    yy = np.r_[2026.0, yrs[yrs > 2026]]
    vv = np.r_[v26, v[yrs > 2026]]
    return float(np.trapezoid(vv, yy))


def main() -> None:
    d, gef = load()

    fig = plt.figure(figsize=(19.4, 6.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.18, 1.30, 1.02], wspace=0.42,
                          left=0.052, right=0.972, bottom=0.245, top=0.90)

    # ================ a: annual indirect emissions, lines ================
    ax = fig.add_subplot(gs[0, 0])
    style(ax)
    # six centre-line + scenario-range bands (demand x policy); efficiency
    # spread is the shaded range, so no per-efficiency lines and no numbers
    med50 = {}
    for pol, ramp in (("ref", REF_RAMP), ("nz2050co2", NZ_RAMP)):
        for dem in DEMANDS:
            sub = d[(d.demand == dem) & (d.policy == pol)
                    & d.year.between(2025, 2050)]
            piv = sub.pivot_table(index="year", columns="eff",
                                  values="dc_co2")
            col = ramp[DEM_DISP[dem]]
            ax.fill_between(piv.index, piv.min(axis=1), piv.max(axis=1),
                            color=col, alpha=0.18, lw=0, zorder=2)
            ax.plot(piv.index, piv["Medium"], color=col, lw=2.2, zorder=4)
            med50[(pol, dem)] = float(piv["Medium"].loc[2050])
    # two stacked frameless legends replace the in-panel labels (policy as
    # coloured title, demand as entries); the shaded efficiency range is
    # explained in the caption
    from matplotlib.lines import Line2D
    def _handles(ramp):
        return [Line2D([], [], color=ramp[dm], lw=2.2,
                       label=f"{dm} demand")
                for dm in ("High", "Medium", "Low")]
    leg1 = ax.legend(handles=_handles(REF_RAMP), loc="upper left",
                     bbox_to_anchor=(0.015, 1.00), frameon=False,
                     fontsize=FS["small"], title="Reference",
                     handlelength=1.5, labelspacing=0.28,
                     borderaxespad=0.0)
    leg1.get_title().set(color=C_REF, fontsize=FS["small"],
                         fontstyle="italic")
    leg1._legend_box.align = "left"
    ax.add_artist(leg1)
    leg2 = ax.legend(handles=_handles(NZ_RAMP), loc="upper left",
                     bbox_to_anchor=(0.015, 0.655), frameon=False,
                     fontsize=FS["small"],
                     title="Net-zero CO$_2$ by 2050",
                     handlelength=1.5, labelspacing=0.28,
                     borderaxespad=0.0)
    leg2.get_title().set(color=C_NZ, fontsize=FS["small"],
                         fontstyle="italic")
    leg2._legend_box.align = "left"
    ax.set_xlim(2025, 2050)
    ax.set_xticks([2025, 2030, 2035, 2040, 2045, 2050])
    ax.set_ylim(0, 6.6)
    ax.set_ylabel("Annual indirect emissions from data\ncenter electricity use (GtCO$_2$)",
                  fontsize=FS["label"])
    ax.text(-0.16, 1.05, "a", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")

    # ================ b: cumulative against the 1.5 C budget ================
    ax = fig.add_subplot(gs[0, 1])
    style(ax)
    x = 0.0
    xticks, xtlabs = [], []
    for dem in DEMANDS:
        grp_start = x
        for eff in EFFS_B:
            sub = d[(d.demand == dem) & (d.eff == eff) & (d.policy == "ref")]
            trn = cum_2026_2050(sub, "trn_co2")
            inf = cum_2026_2050(sub, "inf_co2")
            dc = cum_2026_2050(sub, "dc_co2")
            conv = cum_2026_2050(sub, "conv_co2")
            emb_lo, emb_hi = dc * EMB_LO, dc * EMB_HI
            ax.bar(x, trn, width=0.78, color=C_AI, zorder=3)
            ax.bar(x, inf, bottom=trn, width=0.78, color=C_INFB, zorder=3)
            ax.bar(x, conv, bottom=trn + inf, width=0.78, color=C_CONV,
                   zorder=3)
            ax.bar(x, emb_lo, bottom=dc, width=0.78, color=C_EMB, zorder=3)
            ax.bar(x, emb_hi - emb_lo, bottom=dc + emb_lo, width=0.78,
                   facecolor="white", edgecolor=C_EMB, hatch="////",
                   linewidth=0.8, zorder=3)
            xticks.append(x)
            xtlabs.append("Med" if eff == "Medium" else eff)
            x += 1.0
        # grouped-axis rule (shared with fig01e, fig06b-c): ticks tight over
        # their own demand name, uniform wider gap between groups
        ax.text((grp_start + x - 1.0) / 2, -0.095, "efficiency",
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["small"], color="0.45", fontstyle="italic")
        ax.text((grp_start + x - 1.0) / 2, -0.185, DEM_DISP[dem],
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["ann"], color="0.25")
        x += 0.7
    ax.text(0.5, -0.255, "Demand", transform=ax.transAxes, ha="center",
            va="top", fontsize=FS["small"], color="0.35")
    xmax = x - 1.7 + 0.55
    ax.hlines(B15_50, -0.55, xmax, color="0.1", lw=2.0, zorder=5)
    ax.text(-0.4, B15_50 + 3, "1.5 °C budget, 50%",
            fontsize=FS["ann"], color="0.1")

    ax.hlines(B15_67, -0.55, xmax, color="0.3", lw=1.3, ls=(0, (5, 3)),
              zorder=5)
    ax.text(-0.4, B15_67 + 3, "1.5 °C budget, 67%",
            fontsize=FS["ann"], color="0.3")
    ax.text(xmax - 0.15, 288, f"2 °C budget, 50% ({B2C_50:,.0f} GtCO$_2$)  ↑",
            fontsize=FS["ann"], color="0.45", fontstyle="italic",
            ha="right")
    # standard legend in the empty band above the 1.5 C budget line
    from matplotlib.patches import Patch
    keyb = [
        Patch(fc=C_AI, ec="none", label="AI training"),
        Patch(fc=C_INFB, ec="none", label="AI inference"),
        Patch(fc=C_CONV, ec="none", label="Conventional compute"),
        Patch(fc=C_EMB, ec="none", label="Manufacturing sensitivity (+15%)"),
        Patch(fc="white", ec=C_EMB, hatch="////", lw=0.8,
              label="Sensitivity range (to +40%)"),
    ]
    ax.legend(handles=keyb, loc="upper left", bbox_to_anchor=(0.015, 0.925),
              frameon=False, fontsize=FS["ann"], handlelength=1.3,
              handleheight=1.05, labelspacing=0.35, borderaxespad=0.0)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtlabs, fontsize=15)
    ax.set_xlim(-0.55, xmax)
    ax.set_ylim(0, 300)
    ax.set_yticks([0, 50, 100, 150, 200, 250, 300])
    ax.set_ylabel("Cumulative emissions\nfrom 2026 to 2050 (GtCO$_2$)",
                  fontsize=FS["label"])
    ax.text(-0.115, 1.05, "b", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")

    # ================ c: emission intensity, four labelled lines ============
    ax = fig.add_subplot(gs[0, 2])
    style(ax)
    # IPCC AR6 assessed ranges (C1-C2 and C7-C8), from the AR6 Scenarios
    # Database extraction shipped with the outlook workbook (min-max across
    # model-scenarios; WITCH 5.0 EN_NPi2020_800/900 excluded as in the
    # source port). Bands sit under our lines; the C1-C2 range extends
    # below the axis floor.
    a6 = pd.read_csv(ROOT / "figures/source-data/ar6_selected_rows.csv.gz")
    a6 = a6[a6.Variable.isin(["Emissions|CO2|Energy|Supply|Electricity",
                              "Secondary Energy|Electricity"])]
    a6 = a6[~(a6.Model.eq("WITCH 5.0")
              & a6.Scenario.isin(["EN_NPi2020_800", "EN_NPi2020_900"]))]
    ycols = [c for c in a6.columns if c.isdigit() and 2005 <= int(c) <= 2050]
    a6l = a6.melt(id_vars=["Model", "Scenario", "Variable", "category2"],
                  value_vars=ycols, var_name="year",
                  value_name="value").dropna()
    a6l["year"] = a6l.year.astype(int)
    w6 = a6l.pivot_table(index=["Model", "Scenario", "category2", "year"],
                         columns="Variable", values="value",
                         aggfunc="first").reset_index().dropna()
    w6 = w6[w6["Secondary Energy|Electricity"].ne(0)]
    w6["ef"] = (3.6 * w6["Emissions|CO2|Energy|Supply|Electricity"]
                / w6["Secondary Energy|Electricity"])
    # spaghetti: one faint line per AR6 model-scenario (user ruling
    # 2026-08-14, same grammar as the outlook sheaf in fig01c)
    w6 = w6[(w6.year >= 2005) & (w6.year <= 2050)]
    for _cat, _c6 in (("C1-C2", "#2C7FB8"), ("C7-C8", "#C73E1D")):
        sub6 = w6[w6.category2.eq(_cat)]
        for _, grp6 in sub6.groupby(["Model", "Scenario"]):
            grp6 = grp6.sort_values("year")
            if len(grp6) < 2:
                continue
            ax.plot(grp6.year, grp6.ef, color=_c6, lw=0.45, alpha=0.14,
                    zorder=1)
    # All scenarios share the same BaseX-query history and 2025 anchor. Draw
    # that section once, then branch into the two policy means to avoid one
    # coincident coloured line obscuring the other.
    hist = (gef[gef.year.between(2005, 2025)]
            .groupby("year")["gross_EF"].mean().sort_index())
    ax.plot(hist.index, hist, color=C_HIST, lw=2.0, zorder=4)
    # BECCS removals are NOT credited (grid intensity without BECCS); the
    # including-BECCS variant was dropped 2026-08-24 (user ruling) — the
    # accounting note lives in the caption
    for pol, col in (("ref", C_REF), ("nz2050co2", C_NZ)):
        piv = gef[gef.policy == pol].pivot_table(
            index="year", columns="scenario", values="gross_EF")
        mean = piv.mean(axis=1).sort_index()
        projection = mean[mean.index >= 2025]
        ax.plot(projection.index, projection, color=col, lw=2.0, zorder=5)
    ax.axhline(0, color="0.6", lw=0.8)
    policy_key = [
        Line2D([], [], color=C_REF, lw=2.0, label="Reference"),
        Line2D([], [], color=C_NZ, lw=2.0,
               label="Net-zero CO$_2$ by 2050"),
    ]
    ax.legend(handles=policy_key, loc="lower left",
              bbox_to_anchor=(0.015, 0.025), frameon=False,
              fontsize=FS["ann"], handlelength=1.5, handletextpad=0.55,
              labelspacing=0.35, borderaxespad=0.0)
    ax.set_xlim(2005, 2050)
    ax.set_xticks([2005, 2015, 2025, 2035, 2050])
    # Preserve the full valid AR6 and model range (approximately -262 to
    # 633 gCO2/kWh) rather than clipping high-emission or net-negative paths.
    ax.set_ylim(-300, 680)
    ax.set_yticks([-300, -150, 0, 150, 300, 450, 600])
    ax.set_ylabel("Emission intensity of electricity\n(gCO$_2$ / kWh)",
                  fontsize=FS["label"])
    ax.text(-0.17, 1.05, "c", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")

    fig.savefig(OUT_JPG, dpi=150)
    print(f"WROTE {OUT_JPG}")


if __name__ == "__main__":
    main()
