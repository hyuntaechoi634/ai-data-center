#!/usr/bin/env python3
"""Build Figure 5 from the audited BaseX price queries.

Carbon prices are compared with the matching autonomous-intensity
counterfactual at the same efficiency. Electricity-price effects use fixed
industrial-electricity weights from that same policy-and-efficiency
counterfactual, so changes in regional weights do not enter the price index.
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
ROOT = HERE.parents[2]
D = Path(os.environ.get("FIG_DATA_DIR", str(ROOT / "results/derived/figure-data")))
DEMANDS = ["Low", "Medium", "High"]
NZ_RAMP = {"Low": "#83b6c0", "Medium": "#3f93a4", "High": "#14596b"}
C_REF, C_NZ = "#c98a4b", "#1f7a8c"
FS = dict(tick=20, label=24, letter=34, ann=20, small=20)

def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.8)
    ax.tick_params(labelsize=FS["tick"], width=0.8)

def weighted_price(group):
    """Return a weighted price without dividing by zero in historical rows."""
    total_weight = group.w.sum()
    if total_weight <= 0:
        return np.nan
    return (group.price_2020USDperMWh * group.w).sum() / total_weight


def validate_inputs(rp, carbon):
    """Reject incomplete or duplicated query exports before plotting."""
    price_years = {2025, 2030, 2035, 2040, 2045, 2050}
    if len(rp) != 24 * 32 * len(price_years):
        raise RuntimeError("regional-price query does not contain 24 x 32 x 6 rows")
    if rp[["scenario", "policy"]].drop_duplicates().shape[0] != 24:
        raise RuntimeError("regional-price query does not contain 24 cells")
    if rp.region.nunique() != 32 or set(rp.year) != price_years:
        raise RuntimeError("regional-price region or year coverage changed")
    if rp.duplicated(["scenario", "policy", "region", "year"]).any():
        raise RuntimeError("regional-price query contains duplicate rows")
    if (rp.price_2020USDperMWh <= 0).any() or (rp.ind_elec_EJ <= 0).any():
        raise RuntimeError("regional prices and fixed weights must be positive")
    if len(carbon) != 12 * len(price_years):
        raise RuntimeError("carbon-price query does not contain 12 x 6 rows")
    if carbon.duplicated(["scenario", "year"]).any():
        raise RuntimeError("carbon-price query contains duplicate rows")

def laspeyres(rp):
    """world DC attribution, fixed same-policy same-eff counterfactual weights"""
    out = {}
    for (pol, eff), g in rp.groupby(["policy", "eff"]):
        w = g[g.demand == "Constant"].set_index(["region", "year"]).ind_elec_EJ
        for dem in DEMANDS + ["Constant"]:
            gd = g[g.demand == dem].copy()
            gd["w"] = [w.get((r, y), 0.0) for r, y in zip(gd.region, gd.year)]
            wp = gd.groupby("year").apply(weighted_price)
            out[(pol, eff, dem)] = wp
    return out

def main():
    rp = pd.read_csv(D / "solved_regional_prices_all.csv")
    rp["demand"] = rp.scenario.str.extract(r"D(\w+?)_E")[0]
    rp["eff"] = rp.scenario.str.extract(r"_E(\w+)$")[0]
    c = pd.read_csv(D / "carbon_price_v91.csv")
    c["demand"] = c.scenario.str.extract(r"D(\w+?)_E")[0]
    c["eff"] = c.scenario.str.extract(r"_E(\w+)$")[0]
    validate_inputs(rp, c)
    W = laspeyres(rp)

    fig = plt.figure(figsize=(20.0, 14.4))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.06],
                          height_ratios=[1.0, 1.18], hspace=0.40, wspace=0.42,
                          left=0.075, right=0.965, bottom=0.09, top=0.925)

    # ---------- a: carbon price pathways ----------
    ax = fig.add_subplot(gs[0, 0]); style(ax)
    cp = c[c.year.between(2030, 2050)]
    for dem in DEMANDS:
        piv = cp[cp.demand == dem].pivot_table(index="year", columns="eff",
                                               values="price_USDtCO2")
        ax.fill_between(piv.index, piv.min(axis=1), piv.max(axis=1),
                        color=NZ_RAMP[dem], alpha=0.20, lw=0)
        ax.plot(piv.index, piv["Medium"], color=NZ_RAMP[dem], lw=2.4,
                marker="o", ms=8, mfc="white", mec=NZ_RAMP[dem], mew=1.8)
    ax.set_xticks([2030, 2035, 2040, 2045, 2050])
    ax.set_ylabel("CO$_2$ price (2020\\$ / tCO$_2$)", fontsize=FS["label"])
    ax.text(-0.14, 1.05, "a", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")
    ky = 0.955
    for dem, lab in (("High", "High demand"), ("Medium", "Medium demand"),
                     ("Low", "Low demand")):
        ax.plot([0.045], [ky], marker="o", ms=8, mfc="white",
                mec=NZ_RAMP[dem], mew=1.8, ls="none", transform=ax.transAxes,
                clip_on=False)
        ax.text(0.085, ky, lab, transform=ax.transAxes, fontsize=FS["ann"],
                color="0.15", va="center")
        ky -= 0.08

    # ---------- b: additional CO2 price bars (restored) ----------
    ax = fig.add_subplot(gs[0, 1]); style(ax)
    base_c = c[c.demand == "Constant"].set_index(["eff", "year"]).price_USDtCO2
    cd = c[c.demand.isin(DEMANDS)].copy()
    cd["dabs"] = cd.apply(lambda r: r.price_USDtCO2
                          - base_c.loc[(r.eff, r.year)], axis=1)
    if cd.dabs.min() < -1e-9 or cd.dabs.max() > 18:
        raise RuntimeError("additional carbon-price bars fall outside 0-18")
    x = 0.0; xticks, xtlabs = [], []
    for year in (2030, 2040, 2050):
        x0 = x
        for dem in DEMANDS:
            vals = cd[(cd.demand == dem) & (cd.year == year)].set_index("eff").dabs
            m, lo, hi = float(vals["Medium"]), float(vals.min()), float(vals.max())
            ax.bar(x, m, width=0.6, color=NZ_RAMP[dem], zorder=3)
            ax.errorbar(x, m, yerr=[[m - lo], [hi - m]], fmt="none",
                        ecolor="0.2", elinewidth=1.2, capsize=5.0,
                        capthick=1.2, zorder=5)
            xticks.append(x); xtlabs.append(dem.replace("Medium", "Med"))
            x += 0.8
        ax.text((x0 + x - 0.8) / 2, -0.082, "demand",
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["small"], color="0.45", fontstyle="italic")
        ax.text((x0 + x - 0.8) / 2, -0.16, str(year),
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["ann"] + 2, color="0.1")
        x += 0.7
    ax.axhline(0, color="0.6", lw=0.8, zorder=1)
    ax.set_xticks(xticks); ax.set_xticklabels(xtlabs, fontsize=FS["tick"])
    ax.set_xlim(-0.55, x - 0.7 - 0.25)
    ax.set_ylim(0, 18)
    ax.set_yticks([3, 6, 9, 12, 15, 18])
    ax.set_ylabel("Additional CO$_2$ price\n(2020\\$ / tCO$_2$)", fontsize=FS["label"])
    ax.text(-0.16, 1.05, "b", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")

    # ---------- c: DC attribution, ref and nz side by side ----------
    ax = fig.add_subplot(gs[1, 0]); style(ax)
    x = 0.0; xticks, xtlabs, tops = [], [], []
    for year in (2030, 2040, 2050):
        x0 = x
        for dem in DEMANDS:
            for pol, col, off in (("ref", C_REF, -0.17),
                                  ("nz2050co2", C_NZ, 0.17)):
                vals = [float(W[(pol, f, dem)][year]
                              - W[(pol, f, "Constant")][year])
                        for f in ("Low", "Medium", "High")]
                m = vals[1]
                ax.bar(x + off, m, width=0.32, color=col, zorder=3)
                lo, hi = min(vals), max(vals)
                ax.errorbar(x + off, m, yerr=[[m - lo], [hi - m]],
                            fmt="none", ecolor="0.2", elinewidth=1.2,
                            capsize=5.0, capthick=1.2, zorder=5)
                tops.append(max(vals))
            xticks.append(x)
            xtlabs.append(dem.replace("Medium", "Med"))
            x += 0.9
        ax.text((x0 + x - 0.9) / 2, -0.082, "demand",
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["small"], color="0.45", fontstyle="italic")
        ax.text((x0 + x - 0.9) / 2, -0.16, str(year),
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=FS["ann"] + 2, color="0.1")
        x += 0.75
    ax.axhline(0, color="0.6", lw=0.8, zorder=1)
    ax.set_xticks(xticks); ax.set_xticklabels(xtlabs, fontsize=FS["tick"])
    ax.set_xlim(-0.62, x - 0.75 - 0.28)
    ax.set_ylim(0, max(tops) * 1.28)
    ax.set_ylabel("Electricity-price increase from\ndata centers (2020\\$ / MWh)",
                  fontsize=FS["label"], labelpad=8)
    ax.text(-0.185, 1.05, "c", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")
    for yy, col, lab in ((0.944, C_REF, "Reference"),
                         (0.868, C_NZ, "Net-zero CO$_2$ by 2050")):
        ax.add_patch(plt.Rectangle((0.03, yy - 0.019), 0.045, 0.038,
                                   transform=ax.transAxes, facecolor=col,
                                   zorder=6))
        ax.text(0.09, yy, lab, transform=ax.transAxes, va="center",
                fontsize=FS["ann"], color="0.15", zorder=6)

    # ---------- d: regional heatmap ----------
    ax = fig.add_subplot(gs[1, 1])
    rpn = rp[rp.policy == "nz2050co2"].copy()
    RMAP12 = {"USA": "United States", "China": "China", "Canada": "Canada",
              "EU-12": "Europe", "EU-15": "Europe", "Europe_Non_EU": "Europe",
              "European Free Trade Association": "Europe",
              "Argentina": "Latin America", "Brazil": "Latin America",
              "Central America and Caribbean": "Latin America",
              "Colombia": "Latin America", "Mexico": "Latin America",
              "South America_Northern": "Latin America",
              "South America_Southern": "Latin America",
              "Africa_Eastern": "Africa", "Africa_Northern": "Africa",
              "Africa_Southern": "Africa", "Africa_Western": "Africa",
              "South Africa": "Africa", "Middle East": "Middle East",
              "India": "South Asia", "Pakistan": "South Asia",
              "South Asia": "South Asia", "Japan": "Pacific OECD",
              "South Korea": "Republic of Korea",
              "Australia_NZ": "Pacific OECD", "Taiwan": "Southeast Asia",
              "Russia": "Reforming economies",
              "Central Asia": "Reforming economies",
              "Ukraine": "Reforming economies",
              "Indonesia": "Southeast Asia",
              "Southeast Asia": "Southeast Asia"}
    rpn["grp"] = rpn.region.map(RMAP12)
    wtab = (rpn[rpn.scenario == "DConstant_EMedium"]
            .set_index(["region", "year"]).ind_elec_EJ)
    rpn["w"] = [wtab.get((r, y), 0.0) for r, y in zip(rpn.region, rpn.year)]
    rpn["pw"] = rpn.price_2020USDperMWh * rpn.w
    agg = (rpn.groupby(["grp", "scenario", "year"])
              .apply(weighted_price)
              .rename("p").reset_index())
    piv = agg.pivot_table(index="grp", columns=["scenario", "year"], values="p")
    cols = []
    for year in (2030, 2040, 2050):
        for dem in ("DLow_EMedium", "DMedium_EMedium", "DHigh_EMedium"):
            cols.append(100.0 * (piv[(dem, year)]
                                 / piv[("DConstant_EMedium", year)] - 1.0))
    dm = pd.concat(cols, axis=1); dm.columns = range(9)
    dm = dm.sort_values(8, ascending=False)
    arr = np.full((len(dm), 11), np.nan)
    arr[:, [0, 1, 2]] = dm[[0, 1, 2]].to_numpy()
    arr[:, [4, 5, 6]] = dm[[3, 4, 5]].to_numpy()
    arr[:, [8, 9, 10]] = dm[[6, 7, 8]].to_numpy()
    vmax = float(np.ceil(np.nanmax(arr) / 5.0) * 5.0)
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "heat", plt.get_cmap("magma_r")(np.linspace(0.02, 0.82, 256)))
    cmap.set_bad("white")
    ax.imshow(arr, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    for i in range(arr.shape[0]):
        for j in range(11):
            v = arr[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                        fontsize=19,
                        color="white" if v > 0.55 * vmax else "0.15")
    ax.set_xticks([0, 1, 2, 4, 5, 6, 8, 9, 10])
    ax.set_xticklabels(["Low", "Med", "High"] * 3, fontsize=FS["tick"])
    ax.set_yticks(range(len(dm)))
    ax.set_yticklabels(dm.index, fontsize=19)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    for jx, year in ((1.0, "2030"), (5.0, "2040"), (9.0, "2050")):
        ax.text(jx, -0.85, year, ha="center", va="bottom",
                fontsize=FS["ann"] + 1, color="0.1")
    ax.text(5.0, len(dm) + 1.2, "Demand", ha="center", va="top",
            fontsize=FS["small"], color="0.35")
    ax.text(-0.42, 1.02, "d", transform=ax.transAxes, fontsize=FS["letter"],
            fontweight="bold")

    fig.savefig(HERE / "figure-05.jpg", dpi=170)
    print("WROTE", HERE / "figure-05.jpg")

if __name__ == "__main__":
    main()
