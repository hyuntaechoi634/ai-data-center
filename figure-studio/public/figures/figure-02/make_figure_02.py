#!/usr/bin/env python3
"""Render manuscript Figure 2 from the audited figure-data tables.

One message per element, 3-demand presentation:
  a/b | IRENA historical net additions followed by projected annualized
        Plutus retirement-adjusted generation-equivalent additions, with total
        clean capacity.
  c   | Total clean capacity in 2050 (renewables + nuclear + all CCS) per
        scenario. Short horizontal marks show the matching Constant-scenario
        capacity, so the portion above each mark is the increase associated
        with additional demand growth after 2025.
  d   | Generation in 2050 at Medium efficiency, with the efficiency range as
        whiskers on the totals (replaces old f, 3x3-consistent).
  e   | Electricity end-use in 2050 WITHOUT the world-total backdrop
        (replaces old g/h).
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
OUT_JPG = HERE / "figure-02.jpg"
import os as _os
D = Path(_os.environ.get(
    "FIG_DATA_DIR", str(ROOT / "results/derived/figure-data")))
S = ROOT / "figures/source-data"
AGX = ROOT / "analysis/agentic-extreme-demand"

DEMANDS = ["Low", "Medium", "High"]
DEM_DISP = {"Low": "Low", "Medium": "Medium", "High": "High"}
EFFS = ["Low", "Medium", "High"]
EFFS_C = ["High", "Medium", "Low"]   # panel c: inner axis, high to low
POLICIES = [("ref", "Reference"), ("nz2050co2", "Net-zero CO$_2$ by 2050")]

# fixed semantic colour key (identical to the old fig02 / whole figure set)
TECH_COLORS = {"coal": "#2b2b2b", "gas": "#c8a464", "other": "#b8b8b8",
               "CCS": "#5b7c99", "nuclear": "#e69f00", "hydro": "#00443f",
               "wind": "#56b4e9", "solar": "#f0e442"}
ORDER = ["coal", "gas", "CCS", "other", "hydro", "nuclear", "wind", "solar"]
POOL_OTHER = {"oil": "other", "biomass": "other", "geothermal": "other"}
CCS_POOL = {"biomass_ccs": "CCS", "coal_ccs": "CCS", "gas_ccs": "CCS",
            "oil_ccs": "CCS"}
CLEAN_ADD = {"solar", "wind", "hydro", "nuclear", "geothermal", "biomass",
             "CCS"}
AI_COL = "#7b3294"
BASE_COL = {"ref": "#f0d3bd", "nz2050co2": "#c6dfe4"}
C_REF, C_NZ = "#b3531d", "#1f7a8c"
EU_COL = {"Data centers": AI_COL, "Buildings": "#0072B2",
          "Industry": "#009E73", "Transport": "#999999", "Other": "#bdbdbd"}

FS = dict(tick=13, label=16.5, title=15, letter=21, ann=13, small=13)
CM = FuncFormatter(lambda v, _p: f"{int(round(v)):,}")


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=FS["tick"], width=0.8)
    ax.set_facecolor("white")


# ---------------------------------------------------------------- data
def load():
    # The v3 databases hold every demand level, so no splicing is needed.
    H = pd.read_csv(D / "fig_capacity_additions_historical.csv")
    M = pd.read_csv(D / "fig_capacity_additions_model.csv")
    cap = pd.read_csv(D / "v7_capacity.csv")
    gen = pd.read_csv(D / "v7_genmix.csv")
    use = pd.read_csv(D / "v7_elec_enduse.csv")
    clean_hist = pd.read_csv(S / "fig_clean_capacity_history.csv")
    expected = {
        "year", "electricity_source", "tech_class", "generation_TWh",
        "capacity_factor", "generation_equivalent_capacity_GW", "source",
    }
    if set(clean_hist.columns) != expected or set(clean_hist.year) != set(
            range(2000, 2026)):
        raise ValueError("historical clean-capacity source has an invalid schema")
    historical_tech = {
        "biomass", "coal", "gas", "geothermal", "hydro", "nuclear",
        "oil", "other", "solar", "wind",
    }
    if (
        set(H.columns)
        != {"year", "tech", "net_GWyr", "source", "accounting_method"}
        or set(H.year) != set(range(2001, 2026))
        or set(H.tech) != historical_tech
        or H.duplicated(["year", "tech"]).any()
    ):
        raise ValueError("historical capacity-additions table is incomplete")
    fossil = H.tech.isin({"coal", "gas", "oil"})
    if not H.loc[fossil, "accounting_method"].eq(
            "irena-total-with-gipt-net-flow-allocation").all():
        raise ValueError("historical fossil allocation has an invalid method")
    if not H.loc[~fossil, "accounting_method"].eq(
            "year-end-nameplate-capacity-change").all():
        raise ValueError("direct IRENA capacity rows have an invalid method")
    return H, M, cap, gen, use, clean_hist


def clean_stock(cap, scenario, policy, year):
    """Total clean capacity (renewables, nuclear and CCS), GW."""
    d = cap[(cap.scenario == scenario) & (cap.policy == policy)
            & (cap.year == year) & cap.tech_class.isin(CLEAN_ADD)]
    return float(d.capacity_GW.sum())


def main() -> None:
    H, M, cap, gen, use, clean_hist = load()

    fig = plt.figure(figsize=(15.6, 15.6))
    gs = fig.add_gridspec(4, 6, height_ratios=[1.0, 0.92, 0.98, 0.145],
                          hspace=0.52, wspace=0.9,
                          left=0.085, right=0.928, top=0.955, bottom=0.03)

    # ---------- a/b: observed net and modeled adjusted additions ----------
    BAR_SCEN = "DHigh_EMedium"          # bars: High demand, Medium efficiency
    RANGE_SCENS = ("DHigh_ELow", "DHigh_EHigh")   # whiskers: efficiency range
    hp = H.assign(tech=H.tech.replace(POOL_OTHER)).pivot_table(
        index="year", columns="tech", values="net_GWyr", aggfunc="sum")
    hp = hp.reindex(columns=[t for t in ORDER if t in hp.columns]).fillna(0.0)
    hp = hp.loc[[y for y in hp.index if 2001 <= y <= 2025]]

    historical_clean_stock = clean_hist.groupby(
        "year").generation_equivalent_capacity_GW.sum()
    CLEAN_STOCK_MAX = max(float(historical_clean_stock.max()), float(
        cap[(cap.scenario == BAR_SCEN) & cap.tech_class.isin(CLEAN_ADD)]
        .groupby(["policy", "year"]).capacity_GW.sum().max()))
    for k, (pol, disp) in enumerate(POLICIES):
        ax = fig.add_subplot(gs[0, 3 * k:3 * k + 3])
        style(ax)
        pp = M[(M.scenario == BAR_SCEN) & (M.policy == pol)].pivot_table(
            index="year", columns="group", values="adjusted_GWyr", aggfunc="sum")
        pp = pp.rename(columns=POOL_OTHER).T.groupby(level=0).sum().T
        pp = pp.reindex(columns=[t for t in ORDER if t in pp.columns]).fillna(0.0)
        # the 2025 model period (2021-2025) is already covered by observed
        # annual data, so the projection starts with the 2026-2030 period
        pp = pp.loc[pp.index >= 2030]
        # Efficiency range of total retirement-adjusted additions.
        rng = {}
        for scen in RANGE_SCENS:
            s = M[(M.scenario == scen) & (M.policy == pol)].groupby(
                "year").adjusted_GWyr.sum()
            rng[scen] = s.loc[s.index >= 2030]

        for p, w, off in ((hp, 0.9, -0.5), (pp, 5.0, -2.5)):
            for y in p.index:
                positive_bottom = 0.0
                negative_bottom = 0.0
                for t in ORDER:
                    if t not in p.columns:
                        continue
                    v = float(p.loc[y, t])
                    if v == 0.0:
                        continue
                    bottom = positive_bottom if v > 0 else negative_bottom
                    htch = "////" if t == "CCS" else None
                    ec = "0.25" if t == "CCS" else "white"
                    ax.bar(y + off, v, bottom=bottom, width=w,
                           color=TECH_COLORS[t], hatch=htch, edgecolor=ec,
                           linewidth=0.35, zorder=3)
                    if v > 0:
                        positive_bottom += v
                    else:
                        negative_bottom += v
        for y in pp.index:
            vals = [float(rng[s][y]) for s in RANGE_SCENS]
            wlo, whi = min(vals), max(vals)
            ax.errorbar(y - 2.5, (wlo + whi) / 2,
                        yerr=[[(whi - wlo) / 2], [(whi - wlo) / 2]],
                        fmt="none", ecolor="0.1", elinewidth=1.1,
                        capsize=4.5, capthick=1.1, zorder=6)
        # Total clean-capacity equivalent on the second y-axis. Independent
        # Ember history is converted with the same factors as the GCAM bridge;
        # the audited GCAM projection starts in 2030.
        projected_stock = cap[(cap.scenario == BAR_SCEN) & (cap.policy == pol)
                              & cap.tech_class.isin(CLEAN_ADD)]
        projected_stock = projected_stock.groupby("year").capacity_GW.sum()
        projected_stock = projected_stock.loc[
            (projected_stock.index >= 2030) & (projected_stock.index <= 2050)]
        stk = pd.concat([historical_clean_stock, projected_stock])
        ax2 = ax.twinx()
        ax2.plot(stk.index, stk.values, color="0.15", lw=1.9, zorder=5,
                 marker="o", ms=3.6, mfc="0.15", mec="0.15", mew=0.0,
                 solid_capstyle="butt", solid_joinstyle="miter")
        ax2.set_ylim(0, CLEAN_STOCK_MAX * 1.06)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_linewidth(0.8)
        ax2.tick_params(labelsize=FS["tick"], width=0.8)
        ax2.yaxis.set_major_formatter(CM)
        if k == 1:
            ax2.set_ylabel("Total clean capacity (GW)",
                           fontsize=FS["label"])
        else:
            ax2.tick_params(labelright=False)
        ax.axvspan(2000, 2025, color="#eceff1", zorder=0)
        ax.hlines(0, 2000, 2050.5, color="0.2", lw=1.0, zorder=4)
        ax.axvline(2025, ymin=0, ymax=0.82, color="0.45", lw=1.0,
                   ls=(0, (4, 3)), zorder=4)
        ax.set_xlim(1999.3, 2051.5)
        ax.set_xticks([2000, 2010, 2020, 2030, 2040, 2050])
        ax.set_ylim(-80, 1350)
        ax.yaxis.set_major_formatter(CM)
        ax.set_title(disp, fontsize=FS["title"],
                     color=C_REF if pol == "ref" else C_NZ, pad=8)
        if k == 0:
            ax.set_ylabel("Capacity additions\n(GW per year)",
                          fontsize=FS["label"])
            ax.text(-0.14, 1.10, "a", transform=ax.transAxes,
                    fontsize=FS["letter"], fontweight="bold")
        else:
            ax.text(-0.10, 1.10, "b", transform=ax.transAxes,
                    fontsize=FS["letter"], fontweight="bold")
            ax.tick_params(labelleft=False)

    # ---------- c: total clean capacity and matched Constant baseline ----------
    # Technology stacks retain the system composition. A short horizontal
    # mark within each bar shows the clean-capacity total in the matching
    # DConstant cell under the same efficiency and policy. The portion above
    # that mark is therefore the matched increase associated with additional demand growth
    # after 2025. This aggregate difference is kept distinct
    # from any technology-by-technology attribution.
    ax = fig.add_subplot(gs[1, :])
    style(ax)
    # Independent 2025 benchmark in the same generation-equivalent metric as
    # the model bars. It is generated from Ember with the GCAM bridge factors.
    stock25 = float(historical_clean_stock.loc[2025])
    CLEAN_ORDER = [t for t in ORDER if t not in ("coal", "gas")]

    def clean_by_tech(scenario, policy):
        d = cap[(cap.scenario == scenario) & (cap.policy == policy)
                & (cap.year == 2050) & cap.tech_class.isin(CLEAN_ADD)]
        s = d.assign(tech=d.tech_class.replace(POOL_OTHER)).groupby(
            "tech").capacity_GW.sum()
        return s.reindex(CLEAN_ORDER).fillna(0.0)

    x = 0.0
    xticks, xtlabs = [], []
    block_centres = {}
    hi_bar = 0.0
    for pol, disp in POLICIES:
        block_start = x
        # demand is the OUTER grouping, efficiency the inner tick labels
        for dem in DEMANDS:
            grp_start = x
            for eff in EFFS_C:
                s = clean_by_tech(f"D{dem}_E{eff}", pol)
                total = float(s.sum())
                baseline = clean_stock(
                    cap, f"DConstant_E{eff}", pol, 2050
                )
                if total < baseline - 1e-6:
                    raise ValueError(
                        "panel c requires non-negative capacity above the "
                        f"matching Constant scenario: {pol}, {dem}, {eff}"
                    )
                hi_bar = max(hi_bar, total)
                bottom = 0.0
                for t in CLEAN_ORDER:
                    v = float(s[t])
                    if v <= 0.0:
                        continue
                    htch = "////" if t == "CCS" else None
                    ec = "0.25" if t == "CCS" else "white"
                    ax.bar(x, v, bottom=bottom, width=0.8,
                           color=TECH_COLORS[t], hatch=htch, edgecolor=ec,
                           linewidth=0.35, zorder=3)
                    bottom += v
                ax.hlines(
                    baseline, x - 0.43, x + 0.43,
                    color="0.12", lw=1.35, zorder=7,
                )
                xticks.append(x)
                xtlabs.append("Med" if eff == "Medium" else eff)
                x += 1.0
            ax.text((grp_start + x - 1.0) / 2, -0.095, "efficiency",
                    transform=ax.get_xaxis_transform(), ha="center",
                    va="top", fontsize=FS["small"], color="0.45",
                    fontstyle="italic")
            ax.text((grp_start + x - 1.0) / 2, -0.175,
                    f"{DEM_DISP[dem]} demand",
                    transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=FS["ann"], color="0.25")
            x += 0.7
        block_centres[pol] = (block_start + x - 1.7) / 2
        x += 1.6
    ax.hlines(stock25, -0.7, x - 2.3, color="0.30", lw=1.2, ls=(0, (5, 3)),
              zorder=5)
    from matplotlib.lines import Line2D as _L2
    c_handles = [
        _L2([], [], color="0.12", lw=1.35, label="Constant scenario"),
        _L2([], [], color="0.30", lw=1.2, ls=(0, (5, 3)),
            label="2025 benchmark"),
    ]
    ax.legend(
        handles=c_handles, loc="upper left", bbox_to_anchor=(0.005, 0.985),
        ncol=2, frameon=False, fontsize=FS["small"], handlelength=2.4,
        columnspacing=1.5, borderaxespad=0.0,
    )
    for pol, disp in POLICIES:
        ax.text(block_centres[pol], 1.03, disp,
                transform=ax.get_xaxis_transform(), ha="center",
                fontsize=FS["title"] - 1,
                color=C_REF if pol == "ref" else C_NZ)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtlabs, fontsize=FS["tick"])
    ax.set_xlim(-0.7, x - 2.3)
    ax.set_ylim(0, hi_bar * 1.12)
    ax.yaxis.set_major_formatter(CM)
    ax.set_ylabel("Total clean capacity\nin 2050 (GW)",
                  fontsize=FS["label"])
    ax.text(-0.045, 1.10, "c", transform=ax.transAxes,
            fontsize=FS["letter"], fontweight="bold")

    # ---------- d: generation in 2050, Medium efficiency ----------
    ax = fig.add_subplot(gs[2, 0:3])
    style(ax)
    g50 = gen[gen.year == 2050].copy()
    g50["k"] = g50.tech.replace(CCS_POOL).replace(POOL_OTHER)
    x = 0.0
    xticks, xtlabs = [], []
    for dem in DEMANDS:
        for pol, disp in POLICIES:
            sub = g50[(g50.scenario == f"D{dem}_EMedium")
                      & (g50.policy == pol)]
            piv = sub.groupby("k").gen_TWh.sum()
            bottom = 0.0
            for t in ORDER:
                v = float(piv.get(t, 0.0))
                if v <= 0:
                    continue
                htch = "////" if t == "CCS" else None
                ec = "0.25" if t == "CCS" else "white"
                ax.bar(x, v, bottom=bottom, width=0.8,
                       color=TECH_COLORS[t], hatch=htch, edgecolor=ec,
                       linewidth=0.35, zorder=3)
                bottom += v
            xticks.append(x)
            xtlabs.append("Ref." if pol == "ref" else "NZ")
            x += 1.0
        ax.text(x - 1.5, -0.17, f"{DEM_DISP[dem]} demand",
                transform=ax.get_xaxis_transform(), ha="center",
                fontsize=FS["ann"] + 1, color="0.1")
        x += 0.8
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtlabs, fontsize=FS["tick"])
    ax.set_xlim(-0.7, x - 1.5)
    ax.yaxis.set_major_formatter(CM)
    ax.set_ylabel("Generation in 2050 (TWh)", fontsize=FS["label"])
    ax.text(-0.14, 1.06, "d", transform=ax.transAxes,
            fontsize=FS["letter"], fontweight="bold")

    # ---------- e: end-use in 2050 (no world total) ----------
    u50 = use[use.year == 2050].copy()
    dcs = u50[u50.category.isin(["conv", "training", "inference"])]
    dc = dcs.groupby(["scenario", "policy"]).TWh.sum()
    # equal-width panels with identical x-scale; the leading spacer column
    # separates e from d, and the panels use the full remaining width (the
    # old right-hand annotation column went away with the in-panel labels)
    sub = gs[2, 3:6].subgridspec(1, 3, width_ratios=[0.22, 1.0, 1.0],
                                 wspace=0.30)
    axes_e = [fig.add_subplot(sub[0, 1]), fig.add_subplot(sub[0, 2])]
    # "other" (generation minus the metered end-use groups) is T&D losses,
    # plant own use, hydrogen and heat conversion — not end-use sectors, so
    # the panel shows only the four true end-use groups (user ruling 2026-08-12).
    cats = [("Data centers", None), ("Buildings", "buildings"),
            ("Industry", "industry"), ("Transport", "transport")]
    xs = np.arange(3)
    STOCK_MAX = float(cap[cap.scenario == BAR_SCEN]
                      .groupby(["policy", "year"]).capacity_GW.sum().max())
    for k, (pol, disp) in enumerate(POLICIES):
        ax = axes_e[k]
        style(ax)
        for lab, cat in cats:
            ys, los, his, vgrid = [], [], [], []
            for dem in DEMANDS:
                vals = []
                for eff in EFFS:
                    scen = f"D{dem}_E{eff}"
                    if cat is None:
                        vals.append(float(dc.loc[(scen, pol)]))
                    else:
                        vals.append(float(
                            u50[(u50.scenario == scen)
                                & (u50.policy == pol)
                                & (u50.category == cat)].TWh.iloc[0]))
                ys.append(vals[1])
                los.append(min(vals))
                his.append(max(vals))
                vgrid.append(vals)
            lw = 2.6 if cat is None else 1.6
            ax.plot(xs, ys, color=EU_COL[lab], lw=lw, marker="o", ms=4.5)
            vlo = [v[0] for v in vgrid]
            vhi = [v[2] for v in vgrid]
            for xi, lo_, hi_, vl, vh in zip(xs, los, his, vlo, vhi):
                ax.plot([xi, xi], [lo_, hi_], color=EU_COL[lab], lw=1.1,
                        alpha=0.9, zorder=4)
                ax.plot([xi], [vl], marker="s", ms=3.8, mfc="white",
                        mec=EU_COL[lab], mew=1.0, ls="none", zorder=5)
                ax.plot([xi], [vh], marker="^", ms=4.4, mfc="white",
                        mec=EU_COL[lab], mew=1.0, ls="none", zorder=5)
        ax.set_xticks(xs)
        ax.set_xticklabels([DEM_DISP[d] for d in DEMANDS],
                           fontsize=FS["tick"])
        ax.text(1.0, -0.095, "demand", transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=FS["small"],
                color="0.45", fontstyle="italic")
        ax.set_xlim(-0.15, 2.25)
        ax.set_ylim(0, 33500)
        ax.set_title(disp, fontsize=FS["title"] - 2,
                     color=C_REF if pol == "ref" else C_NZ, pad=6)
        ax.yaxis.set_major_formatter(CM)
        if k == 0:
            ax.set_ylabel("End-use electricity\nconsumption (TWh)",
                          fontsize=FS["label"])
            ax.text(-0.34, 1.06, "e", transform=ax.transAxes,
                    fontsize=FS["letter"], fontweight="bold")
        else:
            ax.tick_params(labelleft=False)

    # ---------- key strip ----------
    kx = fig.add_subplot(gs[3, :])
    kx.axis("off")
    _bb = kx.get_position()
    kx.set_position([_bb.x0, _bb.y0 + 0.028, _bb.width, _bb.height])
    labs = {"coal": "Coal", "gas": "Gas", "CCS": "CCS", "other": "Other",
            "hydro": "Hydro", "nuclear": "Nuclear", "wind": "Wind",
            "solar": "Solar"}
    xs1 = [0.06, 0.15, 0.24, 0.33]   # centred under panel d, aligned columns
    for row, y0 in ((ORDER[:4], 0.86), (ORDER[4:], 0.38)):
        for t, x in zip(row, xs1):
            kx.add_patch(plt.Rectangle((x, y0), 0.010, 0.28,
                                       facecolor=TECH_COLORS[t],
                                       hatch="////" if t == "CCS" else None,
                                       edgecolor="0.25" if t == "CCS"
                                       else "none",
                                       transform=kx.transAxes))
            kx.text(x + 0.015, y0 + 0.14, labs[t], transform=kx.transAxes,
                    fontsize=FS["ann"], va="center")
    # panel-e key: sector colours and efficiency markers, below panel e
    from matplotlib.lines import Line2D as _L2
    e_handles = [
        _L2([], [], color=EU_COL["Data centers"], lw=2.6,
            label="Data centers"),
        _L2([], [], color=EU_COL["Buildings"], lw=1.6, label="Buildings"),
        _L2([], [], color=EU_COL["Industry"], lw=1.6, label="Industry"),
        _L2([], [], color=EU_COL["Transport"], lw=1.6, label="Transport"),
        _L2([], [], ls="none", marker="s", ms=4.5, mfc="white", mec="0.35",
            mew=1.1, label="Low efficiency"),
        _L2([], [], ls="none", marker="o", ms=4.8, mfc="0.35", mec="0.35",
            label="Medium efficiency"),
        _L2([], [], ls="none", marker="^", ms=5.2, mfc="white", mec="0.35",
            mew=1.1, label="High efficiency"),
    ]
    kx.legend(handles=e_handles, loc="center", bbox_to_anchor=(0.75, 0.5),
              ncol=2, frameon=False, fontsize=FS["ann"],
              handlelength=1.8, labelspacing=0.35, columnspacing=1.6)

    fig.savefig(OUT_JPG, dpi=150)
    print(f"WROTE {OUT_JPG}")


if __name__ == "__main__":
    main()
