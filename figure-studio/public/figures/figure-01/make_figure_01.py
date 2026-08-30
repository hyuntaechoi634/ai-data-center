#!/usr/bin/env python3
"""Prototype redesign of manuscript fig01 (new file; existing figures untouched).

Structure (2 messages + 1 credibility strip):
  a | AI service growth   : 3 demand columns, physical RFLOP per year
                            (1 RFLOP = 1e27 operations), one LINE per
                            efficiency pathway and policy (solid reference,
                            dashed net-zero CO2 by 2050) — no ranges.
  b | Data Center power   : same 3 columns, SHARED y-scale, stacked
                            conventional/training/inference at Medium
                            efficiency (reference), with the total for every
                            efficiency pathway and policy drawn as LINES,
                            2050 endpoint labelled with TWh and share of
                            world generation. No Constant line, no ranges.
  c | Full-horizon check  : this study's scenario band to 2050 with the
                            published outlooks inside it (few reach past 2030).
  d | Near-term AI check  : this study against published AI outlooks to 2030.
  e | Policy insensitivity: net-zero minus reference total electricity (%),
                            all nine demand-by-efficiency scenarios — the
                            visual proof that the policy changes these
                            quantities by less than 1%.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
import os as _os
DATA = Path(_os.environ.get(
    "FIG_DATA_DIR", str(ROOT / "results/derived/figure-data")))
HERE = Path(__file__).resolve().parent
OUT_JPG = HERE / "figure-01.jpg"

# ---------------------------------------------------------------- data
YEARS = [2021, 2025, 2030, 2035, 2040, 2045, 2050]
XT5 = [2025, 2030, 2035, 2040, 2045, 2050]   # 5-year tick rule (all figures)
# Three demand pathways, read straight from the v3 result tables.
DEMANDS = ["Low", "Medium", "High"]
DEMAND_TITLE = {
    "Low": "Low demand",
    "Medium": "Medium demand",
    "High": "High demand",
}
C_STUDY = "#1D6E64"    # 'this study' identity in panels c-d (teal, distinct from outlook grey)
C_STUDY_BAND = "#2A9D8F"
EFFS = ["Low", "Medium", "High"]

C_INF = "#4878A8"      # inference (blue)  — fixed semantic key shared with fig02-05
C_TRN = "#E6A23C"      # training (orange)
C_CONV = "#C4C4C4"     # conventional load (grey)
C_TOT = "#4A4A4A"      # total-electricity lines in panel b
NZ_DASH = (0, (4, 3))  # net-zero CO2 by 2050 linestyle everywhere
RAMP = {"Low": "#9dc3dd", "Medium": "#4a8cba", "High": "#14496b"}


def load_service() -> pd.DataFrame:
    svc = pd.read_csv(DATA / "v7_service.csv")
    svc["demand"] = svc.scenario.str.extract(r"D(\w+?)_E")[0]
    svc["eff"] = svc.scenario.str.extract(r"_E(\w+)$")[0]
    # The final service-unit formulation uses one physical unit across sectors,
    # so panel a plots RFLOP
    # directly (1 RFLOP = 1e27 operations).
    svc["rflop"] = svc.output_RFLOP
    return svc


def load_electricity() -> tuple[pd.DataFrame, dict]:
    keep = ["demand", "efficiency", "policy", "year", "training_TWh",
            "inference_TWh", "conventional_TWh", "total_dc_TWh"]
    elec = pd.read_csv(DATA / "scenario_electricity_timeseries.csv")[keep]

    # share of world electricity CONSUMPTION at 2050 (end-use = industry +
    # buildings + transport deliveries; excludes own use and T&D losses),
    # per demand x efficiency (reference)
    master = pd.read_csv(DATA / "v7_master.csv")
    master = master[(master.policy == "ref") & (master.year == 2050)]
    enduse = {s: i + b + t for s, i, b, t in zip(
        master.scenario, master.ind_elec_TWh, master.bld_elec_TWh,
        master.trn_elec_TWh)}
    share = {}
    for d in DEMANDS:
        for e in EFFS:
            tot = elec[(elec.demand == d) & (elec.efficiency == e)
                       & (elec.policy == "ref")
                       & (elec.year == 2050)].total_dc_TWh.iloc[0]
            share[(d, e)] = 100.0 * tot / enduse[f"D{d}_E{e}"]
    return elec, share


LIT_FROZEN = HERE / "outlooks_literature.csv"


def load_outlooks():
    """Published outlooks. Reads the frozen CSV; regenerates it from the
    source workbook (user/AI_data_center_js.zip, 460 MB) when absent, so the
    figure travels without the workbook."""
    if LIT_FROZEN.is_file():
        lit = pd.read_csv(LIT_FROZEN)
    else:
        spec = importlib.util.spec_from_file_location(
            "setb",
            ROOT / "analysis/figure-rebuild-20260730/make_set_b_zip_port.py")
        setb = importlib.util.module_from_spec(spec)
        sys.modules["setb"] = setb
        spec.loader.exec_module(setb)
        lit = setb.literature_long()
        lit.to_csv(LIT_FROZEN, index=False)
    lit["year"] = lit.year.astype(int)
    lit = lit[(lit.year >= 2015) & (lit.year <= 2030)]
    # no magnitude cap: panels c-d now run on full-range axes, so every
    # multi-year outlook is drawn
    out = {kind: lit[lit.type == kind].copy()
           for kind in ("Total data center", "AI")}
    # long-horizon total-DC outlooks (panel c runs to 2050); frozen by
    # build_outlooks_2050.py from the two compilation CSVs under ../data/
    out["Total data center 2050"] = pd.read_csv(HERE / "outlooks_literature_2050.csv")
    return out


# ---------------------------------------------------------------- figure
def fmt(v: float) -> str:
    return f"{v:,.0f}"


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=12, width=0.8)
    ax.set_facecolor("white")


def main() -> None:
    svc = load_service()
    elec, share50 = load_electricity()
    lit = load_outlooks()

    fig = plt.figure(figsize=(15.6, 11.8))
    gs = fig.add_gridspec(4, 6, height_ratios=[1.0, 1.0, 0.02, 0.72],
                          hspace=0.52, wspace=0.55,
                          left=0.104, right=0.985, top=0.945, bottom=0.105)
    row3 = gs[3, :].subgridspec(1, 3, wspace=0.5)

    # ---------------- row a: service, one line per scenario ----------------
    for j, d in enumerate(DEMANDS):
        ax = fig.add_subplot(gs[0, 2 * j:2 * j + 2])
        style(ax)
        sub = svc[svc.demand == d]
        for service, color in (("conv", "#8C8C8C"), ("inference", C_INF),
                               ("training", C_TRN)):
            grid = sub[(sub.service == service)
                       & (sub.policy == "ref")].pivot_table(
                index="year", columns="eff", values="rflop").loc[YEARS]
            for eff in EFFS:
                bold = eff == "Medium"
                ax.plot(YEARS, grid[eff], color=color,
                        lw=1.8 if bold else 0.8,
                        alpha=1.0 if bold else 0.6,
                        zorder=4 if bold else 3)
            end = grid["Medium"].loc[2050]
            if service == "inference":
                dxy, va, label = (-1, 9), "bottom", "Inference"
            elif service == "training":
                dxy, va, label = (-1, -16), "top", "Training"
            else:
                dxy, va, label = (-1, -14), "top", "Conventional"
            ax.annotate(label, (2050, end), xytext=dxy,
                        textcoords="offset points", ha="right",
                        va=va, fontsize=12.6, fontstyle="italic",
                        color=color)
        ax.set_yscale("log")
        ax.set_ylim(1.5, 6e5)   # physical RFLOP: 2.3 (2021) to ~1.8e5 (High inference)
        ax.set_xlim(2021, 2050)
        ax.set_xticks(XT5)
        ax.set_yticks([10, 100, 1000, 10000, 100000])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fmt(v)))
        ax.minorticks_off()
        ax.set_xticks([2021] + XT5)   # 2021 opens the projection
        if j != 0:
            ax.tick_params(labelleft=False)
        ax.set_title(DEMAND_TITLE[d], fontsize=15, pad=6)
        if j == 0:
            ax.set_ylabel("Compute service volume (RFLOP)", fontsize=13.5)
            ax.text(-0.185, 1.14, "a", transform=ax.transAxes,
                    fontsize=21, fontweight="bold")
            # line-style legend (once, first panel), frameless like c-d;
            # neutral gray handles so no service colour is privileged
            from matplotlib.lines import Line2D
            key = [
                Line2D([], [], color="#555555", lw=0.8, alpha=0.6,
                       label="Low and High efficiency"),
            ]
            ax.legend(handles=key, loc="upper left", frameon=False,
                      fontsize=12.5, handlelength=2.2, borderaxespad=0.1,
                      labelspacing=0.35)

    # ---------------- row b: electricity ----------------
    panel_b_ymin, panel_b_ymax = 0, 30000
    panel_b_yticks = np.arange(panel_b_ymin, panel_b_ymax + 1, 5000)
    for j, d in enumerate(DEMANDS):
        ax = fig.add_subplot(gs[1, 2 * j:2 * j + 2])
        style(ax)
        sub = elec[elec.demand == d]
        med = sub[(sub.efficiency == "Medium")
                  & (sub.policy == "ref")].set_index("year").loc[YEARS]
        conv = med.conventional_TWh.to_numpy()
        trn = med.training_TWh.to_numpy()
        inf = med.inference_TWh.to_numpy()
        ax.fill_between(YEARS, 0, conv, color=C_CONV, lw=0)
        ax.fill_between(YEARS, conv, conv + trn, color=C_TRN, lw=0)
        ax.fill_between(YEARS, conv + trn, conv + trn + inf, color=C_INF, lw=0)
        # one TOTAL line per efficiency pathway and policy (no range)
        tot = sub[sub.policy == "ref"].pivot_table(
            index="year", columns="efficiency",
            values="total_dc_TWh").loc[YEARS]
        for eff in EFFS:
            ax.plot(YEARS, tot[eff], color=C_TOT,
                    lw=1.4 if eff == "Medium" else 0.8,
                    alpha=1.0 if eff == "Medium" else 0.7, zorder=4)
        ax.set_ylim(panel_b_ymin, panel_b_ymax)
        ax.set_xlim(2021, 2050)
        ax.set_xticks([2021] + XT5)
        ax.set_yticks(panel_b_yticks)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fmt(v)))
        if j != 0:
            ax.tick_params(labelleft=False)
        if j == 0:
            ax.set_ylabel("Data center electricity\nconsumption (TWh)", fontsize=13.5)
            ax.text(-0.185, 1.10, "b", transform=ax.transAxes,
                    fontsize=21, fontweight="bold")
            # panel-b legend: service colours + the net-zero total line
            from matplotlib.patches import Patch
            keyb = [
                Patch(fc=C_INF, ec="none", label="Inference"),
                Patch(fc=C_TRN, ec="none", label="Training"),
                Patch(fc=C_CONV, ec="none", label="Conventional"),
            ]
            ax.legend(handles=keyb, loc="upper left", frameon=False,
                      fontsize=12.5, handlelength=1.6, borderaxespad=0.1,
                      labelspacing=0.35)
        if j == 0:
            ins = ax.inset_axes([0.54, 0.38, 0.44, 0.56])
            ins.fill_between(YEARS, 0, conv, color=C_CONV, lw=0)
            ins.fill_between(YEARS, conv, conv + trn, color=C_TRN, lw=0)
            ins.fill_between(YEARS, conv + trn, conv + trn + inf,
                             color=C_INF, lw=0)
            for eff in EFFS:
                ins.plot(YEARS, tot[eff], color=C_TOT,
                         lw=1.1 if eff == "Medium" else 0.6,
                         alpha=1.0 if eff == "Medium" else 0.7)
            ins.set_xlim(2021, 2050)
            ins.set_ylim(0, float(tot["Low"].loc[2050]) * 1.12)
            ins.set_xticks([2030, 2040, 2050])
            ins.set_yticks([0, 1000, 2000, 3000, 4000, 5000])
            ins.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda v, _: fmt(v)))
            ins.tick_params(labelsize=9.6, width=0.6, length=2)
            ins.spines[["top", "right"]].set_visible(False)
            ins.spines[["left", "bottom"]].set_linewidth(0.6)
            # services and the net-zero variant are identified in the
            # panel-b legend, not by in-area labels

    # ---------------- row c-d: outlook comparison (narrowed) ----------------
    # Only the counterfactual is excluded. "High" once named a retired pathway
    # and was excluded here; in the v3 tables it is the high-demand case itself.
    ours = elec[(elec.policy == "ref")
                & ~elec.demand.isin(["Constant"])].copy()
    ours["AI_TWh"] = ours.training_TWh + ours.inference_TWh

    # ---- panels c-d: full horizon. The published outlooks (few, and none
    # past 2050) sit inside this study's scenario range — nothing truncated.
    from matplotlib.lines import Line2D
    LEG = [Line2D([], [], color=C_STUDY, lw=2.6, label="this study"),
           Line2D([], [], color="#9A9A9A", lw=0.9, label="published outlooks")]
    for letter, ci, srcs, col_val, ylab in (
            ("c", 0, (lit["Total data center"], lit["Total data center 2050"]),
             "total_dc_TWh", "Data center electricity\nconsumption (TWh)"),
            ("d", 1, (lit["AI"],), "AI_TWh",
             "AI electricity\nconsumption (TWh)")):
        ax = fig.add_subplot(row3[0, ci])
        style(ax)
        for src in srcs:
            for lbl, grp in src.groupby("source_label"):
                grp = grp.sort_values("year")
                if len(grp) < 2:
                    continue   # single-year estimates are not drawn (user ruling)
                # uniform grey for every outlook (user ruling 2026-08-14:
                # no single-source highlighting; Fan et al. 2026 is cited in
                # the Results prose instead)
                ax.plot(grp.year, grp.TWh, color="#9A9A9A", lw=0.7,
                        alpha=0.6, zorder=2)
        band = ours.pivot_table(index="year", columns=["demand", "efficiency"],
                                values=col_val).loc[YEARS]
        # one bold line per demand level (Medium efficiency); the Low/High
        # efficiency variants share the colour but fade back — no shading
        for dem in DEMANDS:
            for eff in EFFS:
                bold = eff == "Medium"
                ax.plot(band.index, band[(dem, eff)], color=C_STUDY,
                        lw=2.4 if bold else 0.9,
                        alpha=1.0 if bold else 0.35,
                        zorder=5 if bold else 3)
        ax.legend(handles=LEG, loc="upper left", frameon=False,
                  fontsize=12.5, handlelength=1.6, borderaxespad=0.1,
                  labelspacing=0.35)
        if letter == "d":
            # the AI outlooks all end by 2035 below ~1,000 TWh — invisible on
            # the shared 20,500 TWh axis, so the comparison lives in a zoom
            ins = ax.inset_axes([0.17, 0.34, 0.44, 0.38])
            for src in srcs:
                for lbl, grp in src.groupby("source_label"):
                    grp = grp.sort_values("year")
                    if len(grp) < 2:
                        continue
                    ins.plot(grp.year, grp.TWh, color="#9A9A9A", lw=0.7,
                             alpha=0.6, zorder=2)
            for dem in DEMANDS:
                for eff in EFFS:
                    bold = eff == "Medium"
                    ins.plot(band.index, band[(dem, eff)], color=C_STUDY,
                             lw=1.6 if bold else 0.7,
                             alpha=1.0 if bold else 0.35,
                             zorder=5 if bold else 3)
            ins.set_xlim(2015, 2035)
            ins.set_ylim(0, 1300)
            ins.set_xticks([2015, 2025, 2035])
            ins.set_yticks([0, 500, 1000])
            ins.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda v, _: fmt(v)))
            ins.tick_params(labelsize=9.6, width=0.6, length=2)
            ins.spines[["top", "right"]].set_visible(False)
            ins.spines[["left", "bottom"]].set_linewidth(0.6)
        ax.set_xlim(2015, 2050)
        ax.set_xticks([2015, 2020, 2030, 2040, 2050])
        ax.set_ylim(0, 30000)
        ax.set_yticks(np.arange(0, 30001, 5000))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fmt(v)))
        ax.set_ylabel(ylab, fontsize=13.5)
        ax.text(-0.24 if letter == "c" else -0.20, 1.12, letter,
                transform=ax.transAxes, fontsize=21, fontweight="bold")

    # ------- row e: net-zero sensitivity, bars, all nine scenarios -------
    ax = fig.add_subplot(row3[0, 2])
    style(ax)
    piv_r = elec[(elec.policy == "ref")
                 & elec.demand.isin(DEMANDS)].pivot_table(
        index="year", columns=["demand", "efficiency"],
        values="total_dc_TWh").loc[YEARS]
    piv_n = elec[(elec.policy == "nz2050co2")
                 & elec.demand.isin(DEMANDS)].pivot_table(
        index="year", columns=["demand", "efficiency"],
        values="total_dc_TWh").loc[YEARS]
    dpct = (100.0 * (piv_n / piv_r - 1.0)).loc[XT5]
    # Grouped-axis layout rule (shared with fig03b, fig06b-c): the three
    # efficiency ticks sit tight over their own demand name (rows 1-2 close),
    # groups are separated by a wider, uniform gap, and the axis title
    # follows directly under row 2.
    # two label blocks, one per axis: [L-M-H ticks + "efficiency"] tight,
    # then a clear break, then [demand name + "Demand"] tight
    GAP_IN, GAP_BETWEEN = 1.25, 0.95
    # all rows va="top", uniform ~0.04 gaps: ticks / efficiency / name / Demand
    Y_EFF, Y_GROUP, Y_TITLE = -0.175, -0.29, -0.42
    x = 0.0
    xticks, xtlabs = [], []
    for dem in DEMANDS:
        g0 = x
        for eff in EFFS:
            col = dpct[(dem, eff)]
            v = float(col.loc[col.abs().idxmax()])
            ax.bar(x, v, width=0.72, color=RAMP[dem], zorder=3)
            xticks.append(x)
            xtlabs.append("Med" if eff == "Medium" else eff)
            x += GAP_IN
        ax.text(g0 + GAP_IN, Y_EFF, "efficiency",
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=9.3, color="0.45", fontstyle="italic")
        ax.text(g0 + GAP_IN, Y_GROUP, DEMAND_TITLE[dem].split()[0],
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=12, color="0.1")
        x += GAP_BETWEEN
    ax.axhline(0, color="0.6", lw=0.7, zorder=1)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtlabs, fontsize=9.8)
    ax.text(0.5, Y_TITLE, "Demand", transform=ax.transAxes, ha="center",
            va="top", fontsize=12, color="0.25")
    ax.set_xlim(-0.8, x - GAP_BETWEEN - 0.3)
    ax.set_ylim(-1.5, 0.1)
    ax.set_yticks([0, -0.5, -1.0, -1.5])
    ax.set_ylabel(r"$\Delta$ Data center electricity (%)", fontsize=11.5)
    ax.text(-0.36, 1.12, "e", transform=ax.transAxes, fontsize=21,
            fontweight="bold")

    # (no key strip: service colours are labelled directly in panel a; the
    # line-style key lives in panel a's first-panel dead space)
    fig.savefig(OUT_JPG, dpi=170)
    print(f"WROTE {OUT_JPG}")


if __name__ == "__main__":
    main()
